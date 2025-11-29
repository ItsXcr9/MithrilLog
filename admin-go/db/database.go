package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// Database represents the SQLite database connection
type Database struct {
	conn *sql.DB
}

// Project represents a MithrilLog project
type Project struct {
	ID                        string                 `json:"id"`
	Name                      string                 `json:"name"`
	PasswordHash              string                 `json:"-"`
	UpstreamURL               string                 `json:"upstream_url"`
	PlanID                    string                 `json:"plan_id"`
	BillingEmail              string                 `json:"billing_email"`
	CustomerStripeID          string                 `json:"customer_stripe_id"`
	CustomQuotaEventsPerDay   *int                   `json:"custom_quota_events_per_day"`
	CustomQuotaEventsPerMonth *int                   `json:"custom_quota_events_per_month"`
	Settings                  map[string]interface{} `json:"settings"`
	Status                    string                 `json:"status"`
	CreatedAt                 time.Time              `json:"created_at"`
	UpdatedAt                 time.Time              `json:"updated_at"`
	LastEventAt               *time.Time             `json:"last_event_at"`
}

// SubscriptionPlan represents a pricing tier
type SubscriptionPlan struct {
	ID                    string    `json:"id"`
	Name                  string    `json:"name"`
	Description           string    `json:"description"`
	PriceMonthly          float64   `json:"price_monthly"`
	PriceAnnual           float64   `json:"price_annual"`
	EventsPerDayLimit     int       `json:"events_per_day_limit"`
	EventsPerMonthLimit   int       `json:"events_per_month_limit"`
	RetentionDays         int       `json:"retention_days"`
	AlertChannelsLimit    int       `json:"alert_channels_limit"`
	Features              string    `json:"features"` // JSON string
	IsActive              bool      `json:"is_active"`
	CreatedAt             time.Time `json:"created_at"`
	UpdatedAt             time.Time `json:"updated_at"`
}

// UsageMetricDaily represents daily aggregated usage
type UsageMetricDaily struct {
	ID                  int       `json:"id"`
	ProjectID           string    `json:"project_id"`
	Date                time.Time `json:"date"`
	EventCount          int       `json:"event_count"`
	ErrorCount          int       `json:"error_count"`
	PeakEventsPerHour   int       `json:"peak_events_per_hour"`
	TotalDataSizeBytes  int64     `json:"total_data_size_bytes"`
	StorageBytes        int64     `json:"storage_bytes"`
	CreatedAt           time.Time `json:"created_at"`
	UpdatedAt           time.Time `json:"updated_at"`
}

// NewDatabase creates a new database connection
func NewDatabase(dbURL string) (*Database, error) {
	// Parse SQLite URL (remove sqlite:// prefix if present)
	dbPath := dbURL
	if len(dbURL) > 9 && dbURL[:9] == "sqlite://" {
		dbPath = dbURL[9:]
	}
	
	conn, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}
	
	// Test connection
	if err := conn.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}
	
	db := &Database{conn: conn}
	
	// Run migrations
	if err := db.migrate(); err != nil {
		return nil, fmt.Errorf("failed to run migrations: %w", err)
	}
	
	return db, nil
}

// Close closes the database connection
func (db *Database) Close() error {
	return db.conn.Close()
}

// migrate runs database migrations
func (db *Database) migrate() error {
	// For now, just check if tables exist
	// In production, use proper migration tool
	return nil
}

// GetProject retrieves a project by ID
func (db *Database) GetProject(projectID string) (*Project, error) {
	query := `
		SELECT id, name, password_hash, upstream_url, plan_id, billing_email,
		       customer_stripe_id, custom_quota_events_per_day, custom_quota_events_per_month,
		       settings, status, created_at, updated_at, last_event_at
		FROM projects WHERE id = ?
	`
	
	var project Project
	var settingsJSON sql.NullString
	var lastEventAt sql.NullTime
	var customQuotaDay, customQuotaMonth sql.NullInt64
	var billingEmail, customerStripeID sql.NullString
	
	err := db.conn.QueryRow(query, projectID).Scan(
		&project.ID, &project.Name, &project.PasswordHash, &project.UpstreamURL,
		&project.PlanID, &billingEmail, &customerStripeID,
		&customQuotaDay, &customQuotaMonth, &settingsJSON, &project.Status,
		&project.CreatedAt, &project.UpdatedAt, &lastEventAt,
	)
	
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to query project: %w", err)
	}
	
	// Parse settings JSON
	if settingsJSON.Valid && settingsJSON.String != "" {
		if err := json.Unmarshal([]byte(settingsJSON.String), &project.Settings); err != nil {
			project.Settings = make(map[string]interface{})
		}
	} else {
		project.Settings = make(map[string]interface{})
	}
	
	// Handle nullable fields
	if billingEmail.Valid {
		project.BillingEmail = billingEmail.String
	}
	if customerStripeID.Valid {
		project.CustomerStripeID = customerStripeID.String
	}
	if lastEventAt.Valid {
		project.LastEventAt = &lastEventAt.Time
	}
	if customQuotaDay.Valid {
		val := int(customQuotaDay.Int64)
		project.CustomQuotaEventsPerDay = &val
	}
	if customQuotaMonth.Valid {
		val := int(customQuotaMonth.Int64)
		project.CustomQuotaEventsPerMonth = &val
	}
	
	return &project, nil
}

// GetAllProjects retrieves all projects
func (db *Database) GetAllProjects() ([]*Project, error) {
	query := `
		SELECT id, name, password_hash, upstream_url, plan_id, billing_email,
		       customer_stripe_id, custom_quota_events_per_day, custom_quota_events_per_month,
		       settings, status, created_at, updated_at, last_event_at
		FROM projects ORDER BY created_at DESC
	`
	
	rows, err := db.conn.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to query projects: %w", err)
	}
	defer rows.Close()
	
	var projects []*Project
	
	for rows.Next() {
		var project Project
		var settingsJSON sql.NullString
		var lastEventAt sql.NullTime
		var customQuotaDay, customQuotaMonth sql.NullInt64
		var billingEmail, customerStripeID sql.NullString
		
		err := rows.Scan(
			&project.ID, &project.Name, &project.PasswordHash, &project.UpstreamURL,
			&project.PlanID, &billingEmail, &customerStripeID,
			&customQuotaDay, &customQuotaMonth, &settingsJSON, &project.Status,
			&project.CreatedAt, &project.UpdatedAt, &lastEventAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan project: %w", err)
		}
		
		// Parse settings JSON
		if settingsJSON.Valid && settingsJSON.String != "" {
			json.Unmarshal([]byte(settingsJSON.String), &project.Settings)
		}
		if project.Settings == nil {
			project.Settings = make(map[string]interface{})
		}
		
		// Handle nullable fields
		if billingEmail.Valid {
			project.BillingEmail = billingEmail.String
		}
		if customerStripeID.Valid {
			project.CustomerStripeID = customerStripeID.String
		}
		if lastEventAt.Valid {
			project.LastEventAt = &lastEventAt.Time
		}
		if customQuotaDay.Valid {
			val := int(customQuotaDay.Int64)
			project.CustomQuotaEventsPerDay = &val
		}
		if customQuotaMonth.Valid {
			val := int(customQuotaMonth.Int64)
			project.CustomQuotaEventsPerMonth = &val
		}
		
		projects = append(projects, &project)
	}
	
	return projects, nil
}

// GetProjectsByStatus retrieves projects by status
func (db *Database) GetProjectsByStatus(status string) ([]*Project, error) {
	query := `
		SELECT id, name, password_hash, upstream_url, plan_id, billing_email,
		       customer_stripe_id, custom_quota_events_per_day, custom_quota_events_per_month,
		       settings, status, created_at, updated_at, last_event_at
		FROM projects WHERE status = ? ORDER BY created_at DESC
	`
	
	rows, err := db.conn.Query(query, status)
	if err != nil {
		return nil, fmt.Errorf("failed to query projects: %w", err)
	}
	defer rows.Close()
	
	var projects []*Project
	
	for rows.Next() {
		var project Project
		var settingsJSON sql.NullString
		var lastEventAt sql.NullTime
		var customQuotaDay, customQuotaMonth sql.NullInt64
		var billingEmail, customerStripeID sql.NullString
		
		err := rows.Scan(
			&project.ID, &project.Name, &project.PasswordHash, &project.UpstreamURL,
			&project.PlanID, &billingEmail, &customerStripeID,
			&customQuotaDay, &customQuotaMonth, &settingsJSON, &project.Status,
			&project.CreatedAt, &project.UpdatedAt, &lastEventAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan project: %w", err)
		}
		
		// Parse settings JSON
		if settingsJSON.Valid && settingsJSON.String != "" {
			json.Unmarshal([]byte(settingsJSON.String), &project.Settings)
		}
		if project.Settings == nil {
			project.Settings = make(map[string]interface{})
		}
		
		// Handle nullable fields
		if billingEmail.Valid {
			project.BillingEmail = billingEmail.String
		}
		if customerStripeID.Valid {
			project.CustomerStripeID = customerStripeID.String
		}
		if lastEventAt.Valid {
			project.LastEventAt = &lastEventAt.Time
		}
		if customQuotaDay.Valid {
			val := int(customQuotaDay.Int64)
			project.CustomQuotaEventsPerDay = &val
		}
		if customQuotaMonth.Valid {
			val := int(customQuotaMonth.Int64)
			project.CustomQuotaEventsPerMonth = &val
		}
		
		projects = append(projects, &project)
	}
	
	return projects, nil
}

// UpdateProjectStatus updates a project's status
func (db *Database) UpdateProjectStatus(projectID, status string) error {
	query := `UPDATE projects SET status = ?, updated_at = ? WHERE id = ?`
	_, err := db.conn.Exec(query, status, time.Now(), projectID)
	return err
}

// UpdateProjectSettings updates a project's settings
func (db *Database) UpdateProjectSettings(projectID string, settings map[string]interface{}) error {
	settingsJSON, err := json.Marshal(settings)
	if err != nil {
		return fmt.Errorf("failed to marshal settings: %w", err)
	}
	
	query := `UPDATE projects SET settings = ?, updated_at = ? WHERE id = ?`
	_, err = db.conn.Exec(query, string(settingsJSON), time.Now(), projectID)
	return err
}

// GetPlan retrieves a subscription plan by ID
func (db *Database) GetPlan(planID string) (*SubscriptionPlan, error) {
	query := `
		SELECT id, name, description, price_monthly, price_annual,
		       events_per_day_limit, events_per_month_limit, retention_days,
		       alert_channels_limit, features, is_active, created_at, updated_at
		FROM subscription_plans WHERE id = ?
	`
	
	var plan SubscriptionPlan
	err := db.conn.QueryRow(query, planID).Scan(
		&plan.ID, &plan.Name, &plan.Description, &plan.PriceMonthly, &plan.PriceAnnual,
		&plan.EventsPerDayLimit, &plan.EventsPerMonthLimit, &plan.RetentionDays,
		&plan.AlertChannelsLimit, &plan.Features, &plan.IsActive,
		&plan.CreatedAt, &plan.UpdatedAt,
	)
	
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to query plan: %w", err)
	}
	
	return &plan, nil
}

// GetTodayUsage gets today's event count for a project
func (db *Database) GetTodayUsage(projectID string, today time.Time) (int, error) {
	// Always use Asia/Tehran timezone for the date, regardless of input timezone
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	nowInTehran := time.Now().In(tehranLoc)
	
	// Format date as YYYY-MM-DD string for SQLite LIKE query
	dateStr := nowInTehran.Format("2006-01-02")
	
	// SQLite stores dates as strings like "2025-11-29 00:00:00.000000"
	// Use LIKE with wildcard to match any time on that date
	query := `SELECT event_count FROM usage_metrics_daily WHERE project_id = ? AND date LIKE ?`
	
	var eventCount sql.NullInt64
	pattern := dateStr + "%"
	err := db.conn.QueryRow(query, projectID, pattern).Scan(&eventCount)
	if err != nil {
		if err == sql.ErrNoRows {
			return 0, nil
		}
		return 0, fmt.Errorf("failed to query usage: %w", err)
	}
	
	if !eventCount.Valid {
		return 0, nil
	}
	
	return int(eventCount.Int64), nil
}

// GetAllPlans retrieves all subscription plans
func (db *Database) GetAllPlans() ([]*SubscriptionPlan, error) {
	query := `
		SELECT id, name, description, price_monthly, price_annual,
		       events_per_day_limit, events_per_month_limit, retention_days,
		       alert_channels_limit, features, is_active, created_at, updated_at
		FROM subscription_plans WHERE is_active = 1 ORDER BY price_monthly ASC
	`
	
	rows, err := db.conn.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to query plans: %w", err)
	}
	defer rows.Close()
	
	var plans []*SubscriptionPlan
	
	for rows.Next() {
		var plan SubscriptionPlan
		err := rows.Scan(
			&plan.ID, &plan.Name, &plan.Description, &plan.PriceMonthly, &plan.PriceAnnual,
			&plan.EventsPerDayLimit, &plan.EventsPerMonthLimit, &plan.RetentionDays,
			&plan.AlertChannelsLimit, &plan.Features, &plan.IsActive,
			&plan.CreatedAt, &plan.UpdatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan plan: %w", err)
		}
		plans = append(plans, &plan)
	}
	
	return plans, nil
}

// UpdateProjectPlan updates a project's plan
func (db *Database) UpdateProjectPlan(projectID, planID string) error {
	query := `UPDATE projects SET plan_id = ?, updated_at = ? WHERE id = ?`
	_, err := db.conn.Exec(query, planID, time.Now(), projectID)
	return err
}

// UpdateProjectCustomQuota updates a project's custom quota
func (db *Database) UpdateProjectCustomQuota(projectID string, dailyLimit, monthlyLimit *int) error {
	query := `UPDATE projects SET custom_quota_events_per_day = ?, custom_quota_events_per_month = ?, updated_at = ? WHERE id = ?`
	_, err := db.conn.Exec(query, dailyLimit, monthlyLimit, time.Now(), projectID)
	return err
}

// GetUsageInRange gets usage count for a project within a time range
func (db *Database) GetUsageInRange(projectID string, start, end time.Time) (int64, error) {
	// This is a simplified implementation
	// In production, you'd query from usage_metrics_hourly or similar
	query := `
		SELECT COALESCE(SUM(event_count), 0) 
		FROM usage_metrics_daily 
		WHERE project_id = ? AND date >= ? AND date <= ?
	`
	
	var count int64
	err := db.conn.QueryRow(query, projectID, start, end).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to query usage range: %w", err)
	}
	
	return count, nil
}

// GetProjectStorage gets project storage in MB from latest daily metric
func (db *Database) GetProjectStorage(projectID string) (float64, error) {
	// Get most recent metric (within last 2 days)
	twoDaysAgo := time.Now().AddDate(0, 0, -2)
	
	query := `
		SELECT storage_bytes 
		FROM usage_metrics_daily 
		WHERE project_id = ? AND date >= ? 
		ORDER BY date DESC 
		LIMIT 1
	`
	
	var storageBytes sql.NullInt64
	err := db.conn.QueryRow(query, projectID, twoDaysAgo).Scan(&storageBytes)
	if err != nil {
		if err == sql.ErrNoRows {
			return 0.0, nil
		}
		return 0.0, fmt.Errorf("failed to query storage: %w", err)
	}
	
	if !storageBytes.Valid || storageBytes.Int64 == 0 {
		return 0.0, nil
	}
	
	// Convert bytes to MB
	return float64(storageBytes.Int64) / (1024 * 1024), nil
}

// UpsertHourlyMetric creates or updates an hourly usage metric
func (db *Database) UpsertHourlyMetric(projectID string, timestamp time.Time, eventCount int, dataSize int64) error {
	// Check if exists
	var exists bool
	err := db.conn.QueryRow(`SELECT EXISTS(SELECT 1 FROM usage_metrics_hourly WHERE project_id = ? AND timestamp_hour = ?)`, 
		projectID, timestamp).Scan(&exists)
	if err != nil {
		return fmt.Errorf("failed to check hourly metric: %w", err)
	}
	
	if exists {
		query := `UPDATE usage_metrics_hourly SET event_count = ?, data_size_bytes = ?, updated_at = ? WHERE project_id = ? AND timestamp_hour = ?`
		_, err = db.conn.Exec(query, eventCount, dataSize, time.Now(), projectID, timestamp)
	} else {
		query := `INSERT INTO usage_metrics_hourly (project_id, timestamp_hour, event_count, data_size_bytes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)`
		_, err = db.conn.Exec(query, projectID, timestamp, eventCount, dataSize, time.Now(), time.Now())
	}
	
	return err
}

// UpsertDailyMetric creates or updates a daily usage metric
func (db *Database) UpsertDailyMetric(projectID string, date time.Time, eventCount int, totalDataSize int64) error {
	// Truncate to date only
	dateOnly := time.Date(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, date.Location())
	
	// Check if exists
	var exists bool
	err := db.conn.QueryRow(`SELECT EXISTS(SELECT 1 FROM usage_metrics_daily WHERE project_id = ? AND date(date) = date(?))`, 
		projectID, dateOnly).Scan(&exists)
	if err != nil {
		return fmt.Errorf("failed to check daily metric: %w", err)
	}
	
	if exists {
		query := `UPDATE usage_metrics_daily SET event_count = ?, total_data_size_bytes = ?, updated_at = ? WHERE project_id = ? AND date(date) = date(?)`
		_, err = db.conn.Exec(query, eventCount, totalDataSize, time.Now(), projectID, dateOnly)
	} else {
		query := `INSERT INTO usage_metrics_daily (project_id, date, event_count, total_data_size_bytes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)`
		_, err = db.conn.Exec(query, projectID, dateOnly, eventCount, totalDataSize, time.Now(), time.Now())
	}
	
	return err
}

// UpdateDailyMetricStorage updates the storage_bytes field for a daily metric
func (db *Database) UpdateDailyMetricStorage(projectID string, date time.Time, storageBytes int64) error {
	dateOnly := time.Date(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, date.Location())
	
	query := `UPDATE usage_metrics_daily SET storage_bytes = ?, updated_at = ? WHERE project_id = ? AND date(date) = date(?)`
	_, err := db.conn.Exec(query, storageBytes, time.Now(), projectID, dateOnly)
	return err
}

// UpdateProjectLastEvent updates the last_event_at timestamp for a project
func (db *Database) UpdateProjectLastEvent(projectID string, lastEvent time.Time) error {
	query := `UPDATE projects SET last_event_at = ?, updated_at = ? WHERE id = ?`
	_, err := db.conn.Exec(query, lastEvent, time.Now(), projectID)
	return err
}
