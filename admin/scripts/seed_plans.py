"""
Seed subscription plans into the database.

This script populates the database with the 4 pricing tiers from the business plan:
- Starter: $29/month
- Professional: $99/month  
- Business: $299/month
- Enterprise: Custom pricing
"""
import sys
from pathlib import Path

# Add admin app to path
sys.path.insert(0, str(Path(__file__).parent.parent / "admin"))

from app.models import SubscriptionPlan, init_db


PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "description": "Perfect for small projects and startups",
        "price_monthly": 29.0,
        "price_annual": 290.0,  # 2 months free
        "events_per_day_limit": 50_000,
        "events_per_month_limit": 1_500_000,
        "retention_days": 7,
        "alert_channels_limit": 1,
        "features": {
            "live_tail": True,
            "trend_analysis": "basic",
            "alert_channels": ["telegram"],
            "support": "email",
            "sla": None,
        },
    },
    {
        "id": "professional",
        "name": "Professional",
        "description": "For growing companies and SMBs",
        "price_monthly": 99.0,
        "price_annual": 990.0,
        "events_per_day_limit": 500_000,
        "events_per_month_limit": 15_000_000,
        "retention_days": 30,
        "alert_channels_limit": 3,
        "features": {
            "live_tail": True,
            "trend_analysis": "advanced",
            "alert_channels": ["telegram", "email"],
            "custom_alert_rules": True,
            "support": "priority_email",
            "sla": None,
        },
    },
    {
        "id": "business",
        "name": "Business",
        "description": "For medium businesses with high volume",
        "price_monthly": 299.0,
        "price_annual": 2990.0,
        "events_per_day_limit": 5_000_000,
        "events_per_month_limit": 150_000_000,
        "retention_days": 90,
        "alert_channels_limit": -1,  # Unlimited
        "features": {
            "live_tail": True,
            "trend_analysis": "advanced",
            "alert_channels": ["telegram", "email", "slack", "pagerduty"],
            "custom_alert_rules": True,
            "custom_integrations": True,
            "support": "24/7",
            "sla": "99.9%",
        },
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "description": "Custom solution for large organizations",
        "price_monthly": 999.0,  # Starting price
        "price_annual": 9990.0,
        "events_per_day_limit": 50_000_000,  # Very high default
        "events_per_month_limit": 1_500_000_000,
        "retention_days": 365,
        "alert_channels_limit": -1,  # Unlimited
        "features": {
            "live_tail": True,
            "trend_analysis": "advanced",
            "alert_channels": ["all"],
            "custom_alert_rules": True,
            "custom_integrations": True,
            "white_label": True,
            "dedicated_instance": True,
            "custom_development": True,
            "support": "dedicated_account_manager",
            "sla": "99.99%",
        },
    },
]


def seed_plans(engine, SessionLocal, force: bool = False):
    """Seed subscription plans into database."""
    session = SessionLocal()
    
    try:
        # Check if plans already exist
        existing_count = session.query(SubscriptionPlan).count()
        
        if existing_count > 0 and not force:
            print(f"⚠️  Found {existing_count} existing plans. Use --force to overwrite.")
            return
        
        if force and existing_count > 0:
            print(f"🗑️  Deleting {existing_count} existing plans...")
            session.query(SubscriptionPlan).delete()
            session.commit()
        
        # Insert plans
        print("📦 Seeding subscription plans...")
        for plan_data in PLANS:
            plan = SubscriptionPlan(**plan_data)
            session.add(plan)
            print(f"  ✓ {plan.name}: ${plan.price_monthly}/mo, {plan.events_per_day_limit:,} events/day")
        
        session.commit()
        print(f"\n✅ Successfully seeded {len(PLANS)} subscription plans!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error seeding plans: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed subscription plans")
    parser.add_argument(
        "--database",
        default="sqlite:///./admin.db",
        help="Database URL (default: sqlite:///./admin.db)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing plans",
    )
    args = parser.parse_args()
    
    # Initialize database
    print(f"🔌 Connecting to database: {args.database}")
    engine, SessionLocal = init_db(args.database)
    
    # Seed plans
    seed_plans(engine, SessionLocal, force=args.force)
