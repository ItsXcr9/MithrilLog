import os
import yaml
import uuid
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

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(response: Response, password: str = Form(...), db: Session = Depends(get_db)):
    project = PROJECTS.get(password)
    if not project:
        return RedirectResponse(url="/?error=invalid", status_code=303)
    
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
