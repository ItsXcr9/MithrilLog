import sys
import os

# Add the parent directory to sys.path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import init_db, GlobalSettings
from sqlalchemy import text

def migrate():
    print("Starting migration...")
    # Get database URL from environment or use default
    database_url = os.getenv("DATABASE_URL", "sqlite:///./admin.db")
    print(f"Using database: {database_url}")
    
    engine, SessionLocal = init_db(database_url=database_url)
    
    with engine.connect() as conn:
        try:
            # Check and add storage_bytes column to usage_metrics_daily
            result = conn.execute(text("PRAGMA table_info(usage_metrics_daily)"))
            columns = [row[1] for row in result]
            
            if 'storage_bytes' not in columns:
                print("Adding 'storage_bytes' column to 'usage_metrics_daily' table...")
                conn.execute(text("ALTER TABLE usage_metrics_daily ADD COLUMN storage_bytes INTEGER DEFAULT 0"))
                conn.commit()
                print("Added 'storage_bytes' column.")
            else:
                print("Column 'storage_bytes' already exists.")
            
            # Create global_settings table if it doesn't exist
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='global_settings'"))
            if not result.fetchone():
                print("Creating 'global_settings' table...")
                conn.execute(text("""
                    CREATE TABLE global_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        prompts JSON,
                        default_llm JSON,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                print("Created 'global_settings' table.")
            else:
                print("Table 'global_settings' already exists.")
                
            print("Migration successful!")
                
        except Exception as e:
            print(f"Migration failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    migrate()
