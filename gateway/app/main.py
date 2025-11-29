import os
import yaml
import uuid
import sqlite3
import httpx
from typing import Optional
from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta

# --- Configuration ---
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yaml")
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

PROJECTS = {p["password"]: p for p in config["projects"]}
PROJECT_IDS = {p["id"]: p for p in config["projects"]}
SECRET_KEY = config["security"]["secret_key"]
SESSION_EXPIRE_MINUTES = config["security"]["session_expire_minutes"]
ADMIN_DB_PATH = os.getenv("ADMIN_DB_PATH", "/admin_data/admin.db")

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)

Base.metadata.create_all(bind=engine)

# --- App Setup ---
app = FastAPI()

# Add CORS middleware to fix Safari blocking issues
allowed_origins = config.get("cors", {}).get("allowed_origins", ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="app/templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_project_status(project_id: str) -> bool:
    """
    Checks if a project is active in the admin database.
    Returns True if active or not found in DB (fail open), False if suspended.
    """
    if not os.path.exists(ADMIN_DB_PATH):
        # Fallback if DB not mounted (e.g. dev mode)
        print(f"Admin DB not found at {ADMIN_DB_PATH}, allowing access")
        return True
        
    try:
        print(f"Checking status for project: {project_id} using DB: {ADMIN_DB_PATH}")
        conn = sqlite3.connect(ADMIN_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        conn.close()
        
        print(f"DB Result for {project_id}: {row}")
        
        if row is None:
            # Project not in admin DB yet - allow access (fail open)
            print(f"Project {project_id} not found in admin DB, allowing access")
            return True
        
        # Project exists in DB - check status
        status = row[0]
        if status == 'active':
            return True
        else:
            print(f"Project {project_id} has status: {status}, blocking access")
            return False
    except Exception as e:
        print(f"Error checking project status: {e}")
        return True # Fail open to avoid blocking valid users on DB error

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(response: Response, password: str = Form(...), db: Session = Depends(get_db)):
    project = PROJECTS.get(password)
    if not project:
        return RedirectResponse(url="/?error=invalid", status_code=303)
    
    # Check suspension status
    if not check_project_status(project["id"]):
        # Redirect to suspended page via admin-go
        return RedirectResponse(url=f"/suspended?project={project['id']}", status_code=303)
    
    # Create Session
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    
    db_session = UserSession(
        id=session_id,
        project_id=project["id"],
        expires_at=expires_at
    )
    db.add(db_session)
    db.commit()
    
    # Set Cookie
    resp = RedirectResponse(url=f"/p/{project['id']}/", status_code=303)
    resp.set_cookie(
        key="gateway_session",
        value=session_id,
        httponly=True,
        max_age=SESSION_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return resp

@app.get("/auth")
async def auth_check(request: Request, db: Session = Depends(get_db)):
    """
    Internal endpoint for Nginx auth_request.
    Returns 200 if authorized, 401 if not.
    Also sets 'X-Target-Upstream' header for Nginx to use.
    """
    session_id = request.cookies.get("gateway_session")
    if not session_id:
        raise HTTPException(status_code=401)
    
    user_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    
    if not user_session or not user_session.is_active or user_session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401)
    
    # Check suspension status on every request
    if not check_project_status(user_session.project_id):
        # Return 403 so nginx can redirect to suspended page
        response = Response(status_code=403)
        response.headers["X-Project-ID"] = user_session.project_id
        return response
    
    # Check if the user is accessing the correct project path
    # Nginx passes the original URI in X-Original-URI
    original_uri = request.headers.get("X-Original-URI", "")
    
    # Simple check: ensure the path starts with /p/{project_id}/
    expected_prefix = f"/p/{user_session.project_id}/"
    if not original_uri.startswith(expected_prefix) and original_uri != "/":
         # Allow access if it's just a resource loading (might need refinement)
         # For strict project isolation:
         if original_uri.startswith("/p/"):
             # Trying to access another project
             raise HTTPException(status_code=403)

    project = PROJECT_IDS.get(user_session.project_id)
    if not project:
        raise HTTPException(status_code=401)

    # Return success with upstream info
    response = Response(status_code=200)
    response.headers["X-Target-Upstream"] = project["upstream_url"]
    return response

@app.get("/suspended")
async def suspended_page(request: Request, db: Session = Depends(get_db)):
    """
    Proxy endpoint to show suspended page from admin-go.
    Gets project ID from query param or session cookie.
    """
    project_id = request.query_params.get("project")
    
    # If no project in query, try to get from session
    if not project_id:
        session_id = request.cookies.get("gateway_session")
        if session_id:
            user_session = db.query(UserSession).filter(UserSession.id == session_id).first()
            if user_session:
                project_id = user_session.project_id
    
    if not project_id:
        return RedirectResponse(url="/?error=invalid", status_code=303)
    
    # Proxy to admin-go suspended page
    try:
        async with httpx.AsyncClient() as client:
            admin_url = f"http://127.0.0.1:9999/suspended?project={project_id}"
            response = await client.get(admin_url, timeout=5.0)
            if response.status_code == 200:
                return HTMLResponse(content=response.text, status_code=200)
            else:
                # Fallback to simple error message
                return HTMLResponse(
                    content=f"<html><body><h1>Service Suspended</h1><p>Project {project_id} has been suspended.</p></body></html>",
                    status_code=200
                )
    except Exception as e:
        print(f"Error proxying to admin-go: {e}")
        # Fallback to simple error message
        return HTMLResponse(
            content=f"<html><body><h1>Service Suspended</h1><p>Project {project_id} has been suspended.</p></body></html>",
            status_code=200
        )

@app.get("/logout")
async def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get("gateway_session")
    if session_id:
        user_session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if user_session:
            user_session.is_active = False
            db.commit()
    
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("gateway_session")
    return resp
