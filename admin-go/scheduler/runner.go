package scheduler

import (
	"fmt"
	"time"

	"github.com/mithrillog/admin/db"
	log "github.com/sirupsen/logrus"
)

// Runner runs the usage scanning scheduler
type Runner struct {
	database *db.Database
	baseDir  string
}

// NewRunner creates a new scheduler runner
func NewRunner(database *db.Database, baseDir string) *Runner {
	return &Runner{
		database: database,
		baseDir:  baseDir,
	}
}

// RunScan performs a single scan of all projects
func (r *Runner) RunScan() error {
	log.Info("Starting usage scan...")
	
	// Scan for projects
	projects, err := ScanProjects(r.baseDir)
	if err != nil {
		return fmt.Errorf("failed to scan projects: %w", err)
	}
	
	log.Infof("Found %d project directories", len(projects))
	
	// Process each project
	for _, project := range projects {
		if err := r.processProject(project); err != nil {
			log.Errorf("Error processing project %s: %v", project.ID, err)
			continue
		}
	}
	
	log.Info("Usage scan complete")
	return nil
}

// processProject processes a single project and updates database
func (r *Runner) processProject(project Project) error {
	log.Infof("Processing project: %s", project.ID)
	
	// Ensure project exists in DB
	_, err := r.database.GetProject(project.ID)
	if err != nil {
		log.Warnf("Project %s not found in database, skipping", project.ID)
		return nil
	}
	
	// Calculate usage by hour and date
	hourlyUsage, err := CalculateUsageByHour(project.DataDir)
	if err != nil {
		return fmt.Errorf("failed to calculate hourly usage: %w", err)
	}
	
	dailyUsage, err := CalculateUsageByDate(project.DataDir)
	if err != nil {
		return fmt.Errorf("failed to calculate daily usage: %w", err)
	}
	
	// Update hourly metrics
	for hourKey, usage := range hourlyUsage {
		log.Infof("  - Hour %s: %d events", hourKey, usage.Events)
		if err := r.database.UpsertHourlyMetric(project.ID, usage.DateTime, usage.Events, usage.Size); err != nil {
			log.Errorf("Failed to upsert hourly metric: %v", err)
		}
	}
	
	// Update daily metrics
	for dateKey, usage := range dailyUsage {
		log.Infof("  - Date %s: %d events, %.2f MB", dateKey, usage.Events, float64(usage.Size)/1024/1024)
		if err := r.database.UpsertDailyMetric(project.ID, usage.Date, usage.Events, usage.Size); err != nil {
			log.Errorf("Failed to upsert daily metric: %v", err)
		}
	}
	
	// Calculate and update storage
	if len(dailyUsage) > 0 {
		storageBytes, err := CalculateProjectStorage(project.Path)
		if err != nil {
			log.Warnf("Failed to calculate storage for %s: %v", project.ID, err)
		} else {
			log.Infof("  Total storage: %.2f MB", float64(storageBytes)/1024/1024)
			
			// Update the most recent daily metric with storage
			var latestDate time.Time
			for _, usage := range dailyUsage {
				if usage.Date.After(latestDate) {
					latestDate = usage.Date
				}
			}
			
			if err := r.database.UpdateDailyMetricStorage(project.ID, latestDate, storageBytes); err != nil {
				log.Errorf("Failed to update storage: %v", err)
			}
		}
	}
	
	// Update last_event_at
	var latestTime time.Time
	for _, usage := range hourlyUsage {
		if usage.DateTime.After(latestTime) {
			latestTime = usage.DateTime
		}
	}
	
	if !latestTime.IsZero() {
		if err := r.database.UpdateProjectLastEvent(project.ID, latestTime); err != nil {
			log.Errorf("Failed to update last_event_at: %v", err)
		}
	}
	
	return nil
}

// GetSecondsUntilNextHour calculates seconds until the top of the next hour in Asia/Tehran timezone
func GetSecondsUntilNextHour() int64 {
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	now := time.Now().In(tehranLoc)
	nextHour := time.Date(now.Year(), now.Month(), now.Day(), now.Hour()+1, 0, 0, 0, tehranLoc)
	return int64(nextHour.Sub(now).Seconds())
}

// RunScheduler runs the scheduler in a loop, executing at the top of each hour in Asia/Tehran timezone
func (r *Runner) RunScheduler() {
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	now := time.Now().In(tehranLoc)
	log.Infof("Scheduler started (Asia/Tehran timezone: %s)", now.Format("2006-01-02 15:04:05 MST"))
	
	// Run immediately on start
	log.Info("Running initial scan...")
	if err := r.RunScan(); err != nil {
		log.Errorf("Initial scan failed: %v", err)
	}
	
	// Run at the top of every hour (Asia/Tehran time)
	for {
		sleepSeconds := GetSecondsUntilNextHour()
		nextRun := time.Now().In(tehranLoc).Add(time.Duration(sleepSeconds) * time.Second)
		log.Infof("Next scan in %d seconds (at %s Asia/Tehran)...", sleepSeconds, nextRun.Format("15:04:05"))
		time.Sleep(time.Duration(sleepSeconds) * time.Second)
		
		now := time.Now().In(tehranLoc)
		log.Infof("Starting hourly scan at %s (Asia/Tehran)", now.Format("2006-01-02 15:04:05 MST"))
		if err := r.RunScan(); err != nil {
			log.Errorf("Hourly scan failed: %v", err)
		}
		log.Info("Hourly scan completed")
	}
}

