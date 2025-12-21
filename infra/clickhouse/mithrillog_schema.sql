-- MithrilLog Database Schema for ClickHouse
-- Run in AncientReport's ClickHouse instance

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS mithrillog;

-- ============================================
-- Process Mining Tables
-- ============================================

-- Process Mining Events
CREATE TABLE IF NOT EXISTS mithrillog.process_events (
    event_id UUID DEFAULT generateUUIDv4(),
    case_id String,
    activity String,
    timestamp DateTime64(3),
    tenant_id String,
    resource String DEFAULT '',
    duration_ms UInt64 DEFAULT 0,
    attributes Map(String, String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (tenant_id, case_id, timestamp)
TTL timestamp + INTERVAL 180 DAY;

-- ============================================
-- Data Governance Tables
-- ============================================

-- Data Enablement Plans (DEPs)
CREATE TABLE IF NOT EXISTS mithrillog.data_enablement_plans (
    dep_id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    status LowCardinality(String) DEFAULT 'draft',  -- draft/pending/approved/rejected
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),
    privacy_classification String DEFAULT '',
    data_handling_notes String DEFAULT '',
    approver String DEFAULT ''
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, dep_id);

-- ============================================
-- Project Management Tables
-- ============================================

-- Project Boards
CREATE TABLE IF NOT EXISTS mithrillog.project_boards (
    board_id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    description String DEFAULT '',
    created_at DateTime DEFAULT now(),
    workflows String DEFAULT '{}'  -- JSON
) ENGINE = ReplacingMergeTree()
ORDER BY (tenant_id, board_id);

-- Project Tasks
CREATE TABLE IF NOT EXISTS mithrillog.project_tasks (
    task_id UUID DEFAULT generateUUIDv4(),
    board_id UUID,
    tenant_id String,
    title String,
    status String DEFAULT 'todo',
    priority UInt8 DEFAULT 0,
    assignee String DEFAULT '',
    due_date Date DEFAULT toDate('1970-01-01'),
    dependencies Array(UUID) DEFAULT [],
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, board_id, task_id);

-- ============================================
-- Analytics Tables
-- ============================================

-- ML Anomaly Detection Results
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
    detection_method String DEFAULT 'zscore'
) ENGINE = MergeTree()
ORDER BY (tenant_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Forecast Predictions
CREATE TABLE IF NOT EXISTS mithrillog.forecasts (
    id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    tenant_id String,
    metric_name String,
    prediction_time DateTime,
    predicted_value Float64,
    confidence_lower Float64 DEFAULT 0,
    confidence_upper Float64 DEFAULT 0,
    method String DEFAULT 'linear'
) ENGINE = MergeTree()
ORDER BY (tenant_id, metric_name, prediction_time)
TTL timestamp + INTERVAL 7 DAY;

-- ============================================
-- Dashboard Tables
-- ============================================

-- Custom Dashboards
CREATE TABLE IF NOT EXISTS mithrillog.custom_dashboards (
    id UUID DEFAULT generateUUIDv4(),
    tenant_id String,
    name String,
    description String DEFAULT '',
    layout String DEFAULT '[]',  -- JSON for widget positions
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, id);

-- Dashboard Widgets
CREATE TABLE IF NOT EXISTS mithrillog.dashboard_widgets (
    id UUID DEFAULT generateUUIDv4(),
    dashboard_id UUID,
    tenant_id String,
    widget_type String,  -- chart, table, kpi, etc.
    title String,
    config String DEFAULT '{}',  -- JSON widget config
    position Int32 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (dashboard_id, position);
