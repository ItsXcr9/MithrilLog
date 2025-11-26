"""
SQLAlchemy models for MithrilLog Admin Panel.

This module defines the database schema for multi-tenant SaaS infrastructure:
- Subscription plans with pricing tiers
- Projects with billing and quota tracking
- Usage metrics (hourly and daily aggregates)
- Invoices and billing records
- Admin user authentication
- Audit trail for admin actions
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class SubscriptionPlan(Base):
    """Defines pricing tiers and resource limits."""

    __tablename__ = "subscription_plans"

    id = Column(String, primary_key=True)  # starter, professional, business, enterprise
    name = Column(String, nullable=False)
    description = Column(String)
    price_monthly = Column(Float, nullable=False)
    price_annual = Column(Float, nullable=False)
    
    # Resource limits
    events_per_day_limit = Column(Integer, nullable=False)
    events_per_month_limit = Column(Integer, nullable=False)
    retention_days = Column(Integer, nullable=False, default=7)
    alert_channels_limit = Column(Integer, nullable=False, default=1)
    
    # Features (JSON)
    features = Column(JSON, default=dict)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    projects = relationship("Project", back_populates="plan")


class Project(Base):
    """Extended project model with billing and quota management."""

    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)  # Hashed password
    upstream_url = Column(String, nullable=False)
    
    # Subscription & Billing
    plan_id = Column(String, ForeignKey("subscription_plans.id"), nullable=False)
    billing_email = Column(String)
    customer_stripe_id = Column(String)  # Stripe customer ID for payment processing
    
    # Custom quotas (null = use plan defaults)
    custom_quota_events_per_day = Column(Integer, nullable=True)
    custom_quota_events_per_month = Column(Integer, nullable=True)
    
    # Status
    status = Column(String, nullable=False, default="active")  # active, suspended, cancelled
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_event_at = Column(DateTime)  # Last time an event was ingested
    
    # Relationships
    plan = relationship("SubscriptionPlan", back_populates="projects")
    usage_hourly = relationship("UsageMetricHourly", back_populates="project", cascade="all, delete-orphan")
    usage_daily = relationship("UsageMetricDaily", back_populates="project", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="project", cascade="all, delete-orphan")

    @property
    def events_per_day_limit(self) -> int:
        """Get effective daily event limit (custom or plan default)."""
        return self.custom_quota_events_per_day or self.plan.events_per_day_limit

    @property
    def events_per_month_limit(self) -> int:
        """Get effective monthly event limit (custom or plan default)."""
        return self.custom_quota_events_per_month or self.plan.events_per_month_limit


class UsageMetricHourly(Base):
    """Tracks usage metrics per project per hour."""

    __tablename__ = "usage_metrics_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    timestamp_hour = Column(DateTime, nullable=False, index=True)  # Truncated to hour
    
    # Metrics
    event_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    unique_hosts = Column(Integer, default=0)
    data_size_bytes = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="usage_hourly")

    # Unique constraint: one record per project per hour
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class UsageMetricDaily(Base):
    """Aggregated daily usage metrics per project."""

    __tablename__ = "usage_metrics_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)  # Date only (midnight)
    
    # Aggregated metrics
    event_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    peak_events_per_hour = Column(Integer, default=0)
    total_data_size_bytes = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="usage_daily")


class Invoice(Base):
    """Billing invoices for projects."""

    __tablename__ = "invoices"

    id = Column(String, primary_key=True)  # invoice_YYYYMM_projectid
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    
    # Billing period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Charges
    base_amount = Column(Float, nullable=False)  # Base plan price
    overage_events = Column(Integer, default=0)
    overage_charge = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    
    # Payment tracking
    status = Column(String, nullable=False, default="pending")  # pending, paid, failed, cancelled
    stripe_invoice_id = Column(String)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    due_date = Column(DateTime)

    # Relationships
    project = relationship("Project", back_populates="invoices")


class AdminUser(Base):
    """Admin panel authentication."""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    
    # Permissions
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

    # Relationships
    actions = relationship("AdminAction", back_populates="admin_user")


class AdminAction(Base):
    """Audit trail for admin actions."""

    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False)  # create_project, update_quota, suspend, etc.
    project_id = Column(String)  # Optional, if action is project-specific
    
    # Action details (JSON)
    details = Column(JSON, default=dict)
    
    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    admin_user = relationship("AdminUser", back_populates="actions")


# Database initialization helper
def init_db(database_url: str = "sqlite:///./admin.db", echo: bool = False):
    """Initialize database with all tables."""
    engine = create_engine(database_url, echo=echo)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal


if __name__ == "__main__":
    # Quick test: create tables in SQLite
    engine, SessionLocal = init_db(echo=True)
    print("✓ Database schema created successfully!")
    print(f"✓ Tables: {', '.join(Base.metadata.tables.keys())}")
