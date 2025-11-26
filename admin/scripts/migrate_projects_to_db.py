"""
Migrate existing projects from config.yaml to database.

This script reads projects from gateway/config.yaml and creates
database records with billing and quota management fields.
"""
import sys
import yaml
import hashlib
from pathlib import Path
from datetime import datetime

# Add admin app to path
sys.path.insert(0, str(Path(__file__).parent.parent / "admin"))

from app.models import Project, init_db


def hash_password(password: str) -> str:
    """Simple password hashing for demo (use bcrypt in production)."""
    return hashlib.sha256(password.encode()).hexdigest()


def migrate_projects(
    config_path: Path,
    engine,
    SessionLocal,
    default_plan_id: str = "professional",
    dry_run: bool = False,
):
    """Migrate projects from config.yaml to database."""
    
    # Read config.yaml
    print(f"📖 Reading config from: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    projects_data = config.get("projects", [])
    print(f"Found {len(projects_data)} projects in config\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    session = SessionLocal()
    migrated = []
    
    try:
        for proj_data in projects_data:
            project_id = proj_data["id"]
            name = proj_data["name"]
            password = proj_data["password"]
            upstream_url = proj_data["upstream_url"]
            
            # Check if project already exists
            existing = session.query(Project).filter(Project.id == project_id).first()
            
            if existing:
                print(f"⚠️  Project '{project_id}' already exists in database - skipping")
                continue
            
            # Create new project record
            project = Project(
                id=project_id,
                name=name,
                password_hash=hash_password(password),
                upstream_url=upstream_url,
                plan_id=default_plan_id,
                status="active",
                created_at=datetime.utcnow(),
            )
            
            print(f"✓ {name}")
            print(f"  ID: {project_id}")
            print(f"  Upstream: {upstream_url}")
            print(f"  Plan: {default_plan_id}")
            print(f"  Status: active")
            print()
            
            if not dry_run:
                session.add(project)
                migrated.append(project_id)
        
        if not dry_run:
            session.commit()
            print(f"\n✅ Successfully migrated {len(migrated)} projects!")
        else:
            print(f"\n🔍 Would migrate {len(projects_data)} projects (dry run)")
        
        return migrated
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Error during migration: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate projects from config.yaml to database")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("gateway/config.yaml"),
        help="Path to config.yaml (default: gateway/config.yaml)",
    )
    parser.add_argument(
        "--database",
        default="sqlite:///./admin.db",
        help="Database URL (default: sqlite:///./admin.db)",
    )
    parser.add_argument(
        "--plan",
        default="professional",
        help="Default plan to assign (default: professional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )
    args = parser.parse_args()
    
    # Validate config exists
    if not args.config.exists():
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    
    # Initialize database
    print(f"🔌 Connecting to database: {args.database}\n")
    engine, SessionLocal = init_db(args.database)
    
    # Migrate projects
    migrate_projects(
        args.config,
        engine,
        SessionLocal,
        default_plan_id=args.plan,
        dry_run=args.dry_run,
    )
