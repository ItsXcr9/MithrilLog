import os
import glob
import json
import logging
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.models import Project, UsageMetricDaily, UsageMetricHourly, SubscriptionPlan

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_session(database_url):
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()

def scan_projects(base_dir="/host_home"):
    """Scan for project directories matching MithrilLog-* pattern."""
    projects = []
    pattern = os.path.join(base_dir, "MithrilLog-*")
    for path in glob.glob(pattern):
        if os.path.isdir(path):
            project_id = os.path.basename(path).replace("MithrilLog-", "")
            projects.append({
                "id": project_id,
                "path": path,
                "data_dir": os.path.join(path, "data")
            })
    return projects

def count_ndjson_events(file_path):
    """Count lines in NDJSON file."""
    count = 0
    size = 0
    try:
        size = os.path.getsize(file_path)
        with open(file_path, 'rb') as f:
            for _ in f:
                count += 1
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
    return count, size

def calculate_usage_by_date(data_dir):
    """Calculate usage aggregated by date from bucket directories."""
    usage_by_date = {} # {date_obj: {'events': 0, 'size': 0}}
    
    buckets_dir = os.path.join(data_dir, "buckets")
    if not os.path.exists(buckets_dir):
        return usage_by_date
        
    # Walk through buckets/YYYY/MM/DD
    # Structure: buckets/2025/11/26/14-30.ndjson
    
    for root, dirs, files in os.walk(buckets_dir):
        for file in files:
            if file.endswith(".ndjson"):
                file_path = os.path.join(root, file)
                
                # Try to extract date from path
                # root ends with .../2025/11/26
                try:
                    parts = Path(file_path).parts
                    # Find 'buckets' index
                    idx = parts.index('buckets')
                    if len(parts) >= idx + 4:
                        year = int(parts[idx+1])
                        month = int(parts[idx+2])
                        day = int(parts[idx+3])
                        date_obj = datetime(year, month, day).date()
                        
                        events, size = count_ndjson_events(file_path)
                        
                        if date_obj not in usage_by_date:
                            usage_by_date[date_obj] = {'events': 0, 'size': 0}
                        
                        usage_by_date[date_obj]['events'] += events
                        usage_by_date[date_obj]['size'] += size
                except ValueError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    
    return usage_by_date

def calculate_usage_by_hour(data_dir):
    """Calculate usage aggregated by hour from bucket directories."""
    usage_by_hour = {} # {(date_obj, hour): {'events': 0, 'size': 0}}
    
    buckets_dir = os.path.join(data_dir, "buckets")
    if not os.path.exists(buckets_dir):
        return usage_by_hour
        
    # Walk through buckets/YYYY/MM/DD
    # Structure: buckets/2025/11/26/14-30.ndjson
    # Filename format: HH-MM.ndjson
    
    for root, dirs, files in os.walk(buckets_dir):
        for file in files:
            if file.endswith(".ndjson"):
                file_path = os.path.join(root, file)
                
                try:
                    parts = Path(file_path).parts
                    idx = parts.index('buckets')
                    if len(parts) >= idx + 4:
                        year = int(parts[idx+1])
                        month = int(parts[idx+2])
                        day = int(parts[idx+3])
                        
                        # Extract hour from filename: "14-30.ndjson" -> 14
                        filename = Path(file).stem  # "14-30"
                        hour = int(filename.split('-')[0])
                        
                        date_obj = datetime(year, month, day, hour, 0, 0)
                        hour_key = (date_obj.date(), hour)
                        
                        events, size = count_ndjson_events(file_path)
                        
                        if hour_key not in usage_by_hour:
                            usage_by_hour[hour_key] = {'events': 0, 'size': 0, 'datetime': date_obj}
                        
                        usage_by_hour[hour_key]['events'] += events
                        usage_by_hour[hour_key]['size'] += size
                except (ValueError, IndexError):
                    continue
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    
    return usage_by_hour

def backfill_usage(session, projects):
    """Update database with calculated usage."""
    
    for proj in projects:
        logger.info(f"Processing project: {proj['id']}")
        
        # Ensure project exists
        db_project = session.query(Project).filter(Project.id == proj['id']).first()
        if not db_project:
            logger.warning(f"Project {proj['id']} not found. Creating default.")
            default_plan = session.query(SubscriptionPlan).filter(SubscriptionPlan.id == "professional").first()
            new_project = Project(
                id=proj['id'],
                name=f"Project {proj['id']}",
                password_hash="hash",
                upstream_url="http://localhost:8080",
                plan_id="professional",
                status="active"
            )
            session.add(new_project)
            session.commit()
            db_project = new_project

        # Calculate usage by hour and date
        usage_by_hour = calculate_usage_by_hour(proj['data_dir'])
        usage_by_date = calculate_usage_by_date(proj['data_dir'])
        
        total_events_all_time = 0
        
        # Update hourly metrics
        for (date_obj, hour), metrics in usage_by_hour.items():
            hour_dt = metrics['datetime']
            logger.info(f"  - Hour {hour_dt}: {metrics['events']} events")
            total_events_all_time += metrics['events']
            
            # Update or create hourly metric
            hourly_metric = session.query(UsageMetricHourly).filter(
                UsageMetricHourly.project_id == proj['id'],
                UsageMetricHourly.timestamp_hour == hour_dt
            ).first()
            
            if not hourly_metric:
                hourly_metric = UsageMetricHourly(
                    project_id=proj['id'],
                    timestamp_hour=hour_dt,
                    event_count=metrics['events'],
                    data_size_bytes=metrics['size']
                )
                session.add(hourly_metric)
            else:
                hourly_metric.event_count = metrics['events']
                hourly_metric.data_size_bytes = metrics['size']
        
        # Update daily metrics
        for date_obj, metrics in usage_by_date.items():
            logger.info(f"  - {date_obj}: {metrics['events']} events, {metrics['size']/1024/1024:.2f} MB")
            
            # Update DB
            daily_metric = session.query(UsageMetricDaily).filter(
                UsageMetricDaily.project_id == proj['id'],
                func.date(UsageMetricDaily.date) == date_obj
            ).first()
            
            if not daily_metric:
                daily_metric = UsageMetricDaily(
                    project_id=proj['id'],
                    date=datetime(date_obj.year, date_obj.month, date_obj.day),
                    event_count=metrics['events'],
                    total_data_size_bytes=metrics['size']
                )
                session.add(daily_metric)
            else:
                daily_metric.event_count = metrics['events']
                daily_metric.total_data_size_bytes = metrics['size']
        
        # Update last_event_at if we found data
        if usage_by_hour:
            latest_hour = max(m['datetime'] for m in usage_by_hour.values())
            db_project.last_event_at = latest_hour
        elif usage_by_date:
            latest_date = max(usage_by_date.keys())
            db_project.last_event_at = datetime(latest_date.year, latest_date.month, latest_date.day)
            
        session.commit()
        logger.info(f"  Total events processed: {total_events_all_time}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scan projects and backfill usage data")
    parser.add_argument("--database", required=True, help="Database URL")
    parser.add_argument("--base-dir", default="/host_home", help="Base directory to scan for projects")
    args = parser.parse_args()
    
    session = get_db_session(args.database)
    try:
        projects = scan_projects(args.base_dir)
        logger.info(f"Found {len(projects)} project directories")
        backfill_usage(session, projects)
        logger.info("Backfill complete")
    finally:
        session.close()
