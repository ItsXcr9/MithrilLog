import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Project, init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_session(database_url):
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()

def cleanup_duplicates(session):
    """Delete stale projects from config that don't match disk."""
    stale_ids = ["project1", "project2", "project3", "project4", "project5"]
    
    logger.info(f"Checking for stale projects: {stale_ids}")
    
    deleted_count = 0
    for pid in stale_ids:
        project = session.query(Project).filter(Project.id == pid).first()
        if project:
            logger.info(f"Deleting stale project: {pid} ({project.name})")
            session.delete(project)
            deleted_count += 1
    
    session.commit()
    logger.info(f"Cleanup complete. Deleted {deleted_count} projects.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cleanup duplicate projects")
    parser.add_argument("--database", required=True, help="Database URL")
    args = parser.parse_args()
    
    session = get_db_session(args.database)
    try:
        cleanup_duplicates(session)
    finally:
        session.close()
