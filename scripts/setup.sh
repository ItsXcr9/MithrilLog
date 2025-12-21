#!/bin/bash
# Complete MithrilLog Setup Script
# Creates database, tables, deploys and verifies

set -e

SERVER="root@65.109.200.75"
CH_URL="http://127.0.0.1:6123"
CH_AUTH="user=AncientReport&password=AncientReport"

echo "============================================"
echo "MithrilLog Complete Setup"
echo "============================================"
echo ""

# Step 1: Create database
echo "Step 1: Creating mithrillog database..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d 'CREATE DATABASE IF NOT EXISTS mithrillog'"
echo "   ✅ Database created"

# Step 2: Create all tables
echo ""
echo "Step 2: Creating tables..."

# Process Events table
echo "   Creating process_events..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.process_events (
    event_id UUID DEFAULT generateUUIDv4(),
    case_id String,
    activity String,
    timestamp DateTime64(3),
    tenant_id String,
    resource String DEFAULT \"\",
    duration_ms UInt64 DEFAULT 0,
    attributes Map(String, String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (tenant_id, case_id, timestamp)
'"

# Data Enablement Plans
echo "   Creating data_enablement_plans..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.data_enablement_plans (
    dep_id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    status LowCardinality(String) DEFAULT \"draft\",
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),
    privacy_classification String DEFAULT \"\",
    data_handling_notes String DEFAULT \"\",
    approver String DEFAULT \"\"
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, dep_id)
'"

# Project Boards
echo "   Creating project_boards..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.project_boards (
    board_id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    description String DEFAULT \"\",
    created_at DateTime DEFAULT now(),
    workflows String DEFAULT \"{}\"
) ENGINE = ReplacingMergeTree()
ORDER BY (tenant_id, board_id)
'"

# Project Tasks
echo "   Creating project_tasks..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.project_tasks (
    task_id UUID DEFAULT generateUUIDv4(),
    board_id UUID,
    tenant_id String,
    title String,
    status String DEFAULT \"todo\",
    priority UInt8 DEFAULT 0,
    assignee String DEFAULT \"\",
    due_date Date DEFAULT toDate(\"1970-01-01\"),
    dependencies Array(UUID) DEFAULT [],
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, board_id, task_id)
'"

# Custom Dashboards
echo "   Creating custom_dashboards..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.custom_dashboards (
    id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    description String DEFAULT \"\",
    layout String DEFAULT \"[]\",
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, id)
'"

# Dashboard Widgets
echo "   Creating dashboard_widgets..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.dashboard_widgets (
    id UUID DEFAULT generateUUIDv4(),
    dashboard_id UUID,
    tenant_id String,
    widget_type String,
    title String,
    config String DEFAULT \"{}\",
    position Int32 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (dashboard_id, position)
'"

# Anomaly Results
echo "   Creating anomaly_results..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.anomaly_results (
    id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    tenant_id String,
    metric_name String,
    current_value Float64,
    expected_value Float64,
    lower_bound Float64 DEFAULT 0,
    upper_bound Float64 DEFAULT 0,
    deviation_score Float64,
    is_anomaly UInt8 DEFAULT 0,
    detection_method String DEFAULT \"zscore\"
) ENGINE = MergeTree()
ORDER BY (tenant_id, metric_name, timestamp)
'"

# Forecasts
echo "   Creating forecasts..."
ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}' -d '
CREATE TABLE IF NOT EXISTS mithrillog.forecasts (
    id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    tenant_id String,
    metric_name String,
    prediction_time DateTime,
    predicted_value Float64,
    confidence_lower Float64 DEFAULT 0,
    confidence_upper Float64 DEFAULT 0,
    method String DEFAULT \"linear\"
) ENGINE = MergeTree()
ORDER BY (tenant_id, metric_name, prediction_time)
'"

echo "   ✅ All tables created"

# Step 3: Verify tables
echo ""
echo "Step 3: Verifying tables..."
tables=$(ssh ${SERVER} "curl -sS '${CH_URL}/?${CH_AUTH}&database=mithrillog' -d 'SHOW TABLES'")
echo "   Tables in mithrillog:"
echo "$tables" | sed 's/^/      - /'

# Step 4: Deploy MithrilLog
echo ""
echo "Step 4: Deploying MithrilLog..."

echo "   Syncing app directory..."
rsync -az ./app/ ${SERVER}:/home/MithrilLog-xcr9/app/

echo "   Syncing src directory..."
rsync -az ./src/ ${SERVER}:/home/MithrilLog-xcr9/src/

echo "   Syncing config files..."
rsync -az ./docker-compose.yml ./\.env ${SERVER}:/home/MithrilLog-xcr9/

echo "   Restarting API container..."
ssh ${SERVER} "cd /home/MithrilLog-xcr9 && docker compose up -d --force-recreate api"

# Wait for container to start
echo "   Waiting for API to start..."
sleep 5

# Step 5: Verify API
echo ""
echo "Step 5: Verifying API health..."

# Test ClickHouse connection from API container
echo "   Testing ClickHouse connection from container..."
result=$(ssh ${SERVER} "docker exec mithrillog-xcr9-api-1 curl -sS 'http://65.109.200.75:6123/?user=AncientReport&password=AncientReport&query=SELECT+1'" 2>/dev/null || echo "failed")
if [ "$result" = "1" ]; then
    echo "   ✅ Container can reach ClickHouse"
else
    echo "   ⚠️  Container ClickHouse connection: $result"
fi

# Test analytics health
echo "   Testing analytics health..."
result=$(ssh ${SERVER} "curl -sS http://127.0.0.1:9900/api/analytics/health" 2>/dev/null || echo "failed")
echo "   Analytics health: $result"

# Test schemas
echo "   Testing analytics schemas..."
result=$(ssh ${SERVER} "curl -sS http://127.0.0.1:9900/api/analytics/schemas" 2>/dev/null || echo "failed")
echo "   Schemas: $result"

echo ""
echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo ""
echo "Access the dashboard at: http://65.109.200.75:9900/"
echo ""
