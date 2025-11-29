package enforcer

import (
	"time"

	"github.com/mithrillog/admin/db"
	"github.com/mithrillog/admin/docker"
	"github.com/robfig/cron/v3"
	log "github.com/sirupsen/logrus"
)

// LimitEnforcer monitors project usage and enforces limits
type LimitEnforcer struct {
	db        *db.Database
	dockerMgr *docker.Manager
	cron      *cron.Cron
}

// NewLimitEnforcer creates a new limit enforcer
func NewLimitEnforcer(database *db.Database, dockerMgr *docker.Manager) *LimitEnforcer {
	return &LimitEnforcer{
		db:        database,
		dockerMgr: dockerMgr,
		cron:      cron.New(),
	}
}

// Start begins monitoring projects
func (le *LimitEnforcer) Start() {
	log.Info("Starting limit enforcer")
	
	// Run every minute
	le.cron.AddFunc("@every 1m", func() {
		le.CheckAllProjects()
	})
	
	// Also run immediately on startup
	go le.CheckAllProjects()
	
	le.cron.Start()
}

// Stop stops the enforcer
func (le *LimitEnforcer) Stop() {
	log.Info("Stopping limit enforcer")
	le.cron.Stop()
}

// CheckAllProjects checks all active projects for limit violations
func (le *LimitEnforcer) CheckAllProjects() {
	projects, err := le.db.GetAllProjects()
	if err != nil {
		log.Errorf("Failed to get projects: %v", err)
		return
	}
	
	// Get today's date in Asia/Tehran timezone
	tehranLoc, err := time.LoadLocation("Asia/Tehran")
	if err != nil {
		log.Errorf("Failed to load timezone: %v", err)
		tehranLoc = time.UTC
	}
	
	today := time.Now().In(tehranLoc)
	
	for _, project := range projects {
		le.checkProject(project, today)
	}
}

// checkProject checks a single project
func (le *LimitEnforcer) checkProject(project *db.Project, today time.Time) {
	// Get project's plan
	plan, err := le.db.GetPlan(project.PlanID)
	if err != nil || plan == nil {
		log.Errorf("Failed to get plan for project %s: %v", project.ID, err)
		return
	}
	
	// Get effective daily limit
	dailyLimit := plan.EventsPerDayLimit
	if project.CustomQuotaEventsPerDay != nil {
		dailyLimit = *project.CustomQuotaEventsPerDay
	}
	
	// Get today's usage
	usage, err := le.db.GetTodayUsage(project.ID, today)
	if err != nil {
		log.Errorf("Failed to get usage for project %s: %v", project.ID, err)
		return
	}
	
	usagePercent := float64(usage) / float64(dailyLimit) * 100
	
	// Check if limit exceeded
	if usage >= dailyLimit && project.Status == "active" {
		log.Warnf("Project %s exceeded limit: %d/%d (%.1f%%)", 
			project.ID, usage, dailyLimit, usagePercent)
		
		// Suspend project
		if err := le.SuspendProject(project.ID); err != nil {
			log.Errorf("Failed to suspend project %s: %v", project.ID, err)
		}
	} else if usage < dailyLimit && project.Status == "suspended" {
		// Auto-resume if under limit (new day)
		log.Infof("Project %s under limit, auto-resuming: %d/%d (%.1f%%)", 
			project.ID, usage, dailyLimit, usagePercent)
		
		if err := le.ResumeProject(project.ID); err != nil {
			log.Errorf("Failed to resume project %s: %v", project.ID, err)
		}
	}
}

// SuspendProject suspends a project that exceeded limits
func (le *LimitEnforcer) SuspendProject(projectID string) error {
	log.Infof("Suspending project %s", projectID)
	
	// Update status in database
	if err := le.db.UpdateProjectStatus(projectID, "suspended"); err != nil {
		return err
	}
	
	// Stop Docker containers (optional - saves resources)
	// Comment out if you want to keep containers running
	// if err := le.dockerMgr.StopProject(projectID); err != nil {
	// 	log.Warnf("Failed to stop containers for project %s: %v", projectID, err)
	// }
	
	log.Infof("Project %s suspended successfully", projectID)
	return nil
}

// ResumeProject resumes a suspended project
func (le *LimitEnforcer) ResumeProject(projectID string) error {
	log.Infof("Resuming project %s", projectID)
	
	// Update status in database
	if err := le.db.UpdateProjectStatus(projectID, "active"); err != nil {
		return err
	}
	
	// Start Docker containers
	// if err := le.dockerMgr.StartProject(projectID); err != nil {
	// 	log.Warnf("Failed to start containers for project %s: %v", projectID, err)
	// }
	
	log.Infof("Project %s resumed successfully", projectID)
	return nil
}

// ManualCheck manually checks a specific project
func (le *LimitEnforcer) ManualCheck(projectID string) error {
	project, err := le.db.GetProject(projectID)
	if err != nil || project == nil {
		return err
	}
	
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	today := time.Now().In(tehranLoc)
	
	le.checkProject(project, today)
	return nil
}
