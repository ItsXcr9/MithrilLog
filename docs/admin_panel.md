# MithrilLog Admin Panel Documentation

## Overview

The **MithrilLog Admin Panel** is the centralized management interface for the MithrilLog SaaS platform. It allows administrators to manage tenants (projects), subscription plans, quotas, and billing.

## Architecture

-   **Backend**: FastAPI application (`admin/app/main.py`).
-   **Database**: SQLite (`admin.db`) using SQLAlchemy ORM.
-   **Frontend**: Server-side rendered HTML templates (`admin/app/templates/`) with modern CSS/JS.
-   **Port**: Runs on port `9999` by default.

## Features

### 1. Project Management
-   **List Projects**: View all tenant projects with their status (Active, Suspended, Cancelled).
-   **Usage Tracking**: Real-time view of event counts (hourly/daily) and storage usage.
-   **Quota Monitoring**: Color-coded indicators (Green/Yellow/Orange/Red) based on daily limit usage.
-   **Lifecycle Management**: Suspend or activate projects instantly.

### 2. Subscription Plans
-   **Tiered Pricing**: Define plans (e.g., Starter, Professional, Business) with different limits.
-   **Resource Limits**:
    -   Events per day
    -   Retention period (days)
    -   Alert channels
-   **Plan Changes**: Upgrade or downgrade project plans dynamically.

### 3. Quota Enforcement
-   **Plan Defaults**: Projects inherit limits from their assigned plan.
-   **Custom Quotas**: Overwrite plan limits for specific projects (e.g., temporary boost).
-   **Enforcement**: The ingestion pipeline checks these limits to accept or reject logs.

### 4. Global Configuration
-   **System Prompts**: Update the default LLM prompts for summarization and trend analysis across all tenants.
-   **LLM Settings**: Configure default model backend (Gemini/OpenAI) and parameters.

## Database Schema

### `SubscriptionPlan`
Defines the available pricing tiers.
-   `id`: Unique identifier (e.g., `professional`).
-   `events_per_day_limit`: Max events allowed per day.
-   `retention_days`: How long logs are kept.
-   `price_monthly`: Cost per month.

### `Project`
Represents a tenant.
-   `id`: Unique project ID.
-   `password_hash`: Used for API authentication.
-   `upstream_url`: Internal URL of the tenant's MithrilLog container.
-   `plan_id`: Link to `SubscriptionPlan`.
-   `custom_quota_events_per_day`: Optional override for plan limit.
-   `status`: `active`, `suspended`, or `cancelled`.

### `UsageMetricDaily` / `UsageMetricHourly`
Stores historical usage data.
-   `event_count`: Total logs ingested.
-   `error_count`: Number of error-level logs.
-   `storage_bytes`: Disk space used.

### `Invoice`
Records billing information.
-   `period_start` / `period_end`: Billing cycle.
-   `total_amount`: Calculated from base plan + overages.
-   `status`: `pending`, `paid`, `failed`.

## API Reference

### Projects
-   `GET /api/admin/projects`: List all projects.
-   `GET /api/admin/projects/{id}`: Get details for a specific project.
-   `PUT /api/admin/projects/{id}/plan`: Change subscription plan.
-   `PUT /api/admin/projects/{id}/quota`: Set custom quota.
-   `PUT /api/admin/projects/{id}/status`: Change status (suspend/activate).

### Stats
-   `GET /api/admin/stats/overview`: Dashboard aggregate statistics.
-   `GET /api/admin/projects/{id}/usage/daily`: Historical daily usage.

### Settings
-   `GET /api/admin/settings`: Get global configuration.
-   `PUT /api/admin/settings`: Update global prompts and LLM settings.

## Usage Guide

### Starting the Admin Panel
```bash
cd admin
python3 app/main.py
```
Access at `http://localhost:9999`.

### Creating Plans (Seeding)
Run the seed script to populate default plans:
```bash
python3 scripts/seed_plans.py
```

### Migrating Projects
To import existing `config.yaml` projects into the database:
```bash
python3 scripts/migrate_projects_to_db.py
```
