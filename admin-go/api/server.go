package api

import (
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mithrillog/admin/config"
	"github.com/mithrillog/admin/db"
	"github.com/mithrillog/admin/docker"
	"github.com/mithrillog/admin/enforcer"
	log "github.com/sirupsen/logrus"
)

// Server represents the API server
type Server struct {
	db       *db.Database
	configMgr *config.Manager
	dockerMgr *docker.Manager
	enforcer  *enforcer.LimitEnforcer
}

// NewServer creates a new API server
func NewServer(database *db.Database, configMgr *config.Manager, dockerMgr *docker.Manager, enforcer *enforcer.LimitEnforcer) *Server {
	return &Server{
		db:        database,
		configMgr: configMgr,
		dockerMgr: dockerMgr,
		enforcer:  enforcer,
	}
}

// RegisterRoutes registers all API routes
func (s *Server) RegisterRoutes(router *gin.Engine) {
	// Admin dashboard
	router.GET("/", s.adminDashboard)
	
	// Health check (both paths for compatibility, both GET and HEAD methods)
	router.GET("/health", s.healthCheck)
	router.HEAD("/health", s.healthCheck)
	router.GET("/api/health", s.healthCheck)
	router.HEAD("/api/health", s.healthCheck)
	
	// Suspend page
	router.GET("/suspended", s.suspendedPage)
	
	// API routes
	api := router.Group("/api/admin")
	{
		// Dashboard stats
		api.GET("/stats/overview", s.getStatsOverview)
		
		// Projects
		api.GET("/projects", s.listProjects)
		api.GET("/projects/:id", s.getProject)
		api.PUT("/projects/:id/settings", s.updateProjectSettings)
		api.PUT("/projects/:id/status", s.updateProjectStatus)
		api.PUT("/projects/:id/plan", s.updateProjectPlan)
		api.PUT("/projects/:id/quota", s.updateProjectQuota)
		api.GET("/projects/:id/usage/hourly", s.getProjectUsageHourly)
		
		// Plans
		api.GET("/plans", s.listPlans)
		
		// Settings
		api.GET("/settings", s.getSettings)
		api.PUT("/settings", s.updateSettings)
		
		// Docker operations
		api.POST("/docker/:id/restart", s.restartProject)
		api.POST("/docker/:id/stop", s.stopProject)
		api.POST("/docker/:id/start", s.startProject)
		api.GET("/docker/:id/status", s.getDockerStatus)
		api.GET("/docker/:id/logs", s.getDockerLogs)
		
		// Config operations
		api.POST("/config/:id/sync", s.syncConfig)
		api.GET("/config/templates", s.getTemplates)
		
		// Limit operations
		api.GET("/limits/status", s.getLimitsStatus)
		api.POST("/limits/check", s.checkLimits)
		api.POST("/limits/:id/suspend", s.manualSuspend)
		api.POST("/limits/:id/resume", s.manualResume)
	}
}

// healthCheck returns service health status
func (s *Server) healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"service": "mithrillog-admin-go",
		"time":    time.Now().Format(time.RFC3339),
	})
}

// suspendedPage serves the suspend page
func (s *Server) suspendedPage(c *gin.Context) {
	projectID := c.Query("project")
	
	if projectID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "project parameter required"})
		return
	}
	
	project, err := s.db.GetProject(projectID)
	if err != nil || project == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Project not found"})
		return
	}
	
	plan, _ := s.db.GetPlan(project.PlanID)
	
	dailyLimit := plan.EventsPerDayLimit
	if project.CustomQuotaEventsPerDay != nil {
		dailyLimit = *project.CustomQuotaEventsPerDay
	}
	
	// Get today's usage
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	today := time.Now().In(tehranLoc)
	usage, _ := s.db.GetTodayUsage(projectID, today)
	
	// Calculate reset time (midnight tomorrow)
	tomorrow := today.AddDate(0, 0, 1)
	resetTime := time.Date(tomorrow.Year(), tomorrow.Month(), tomorrow.Day(), 0, 0, 0, 0, tehranLoc)
	
	usagePercent := float64(usage) / float64(dailyLimit) * 100
	
	c.HTML(http.StatusOK, "suspended.html", gin.H{
		"ProjectName":  project.Name,
		"PlanName":     plan.Name,
		"CurrentUsage": usage,
		"DailyLimit":   dailyLimit,
		"UsagePercent": fmt.Sprintf("%.1f", usagePercent),
		"ResetTime":    resetTime.Format("15:04 MST"),
		"SupportEmail": "support@mithrillog.com",
	})
}

// enrichProject adds computed fields to project for UI
func (s *Server) enrichProject(project *db.Project) gin.H {
	plan, _ := s.db.GetPlan(project.PlanID)
	
	dailyLimit := 0
	if plan != nil {
		dailyLimit = plan.EventsPerDayLimit
	}
	if project.CustomQuotaEventsPerDay != nil {
		dailyLimit = *project.CustomQuotaEventsPerDay
	}
	
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	today := time.Now().In(tehranLoc)
	usage, _ := s.db.GetTodayUsage(project.ID, today)
	
	usagePercent := float64(0)
	if dailyLimit > 0 {
		usagePercent = float64(usage) / float64(dailyLimit) * 100
	}
	
	quotaStatus := "green"
	if usagePercent >= 100 {
		quotaStatus = "red"
	} else if usagePercent >= 90 {
		quotaStatus = "orange"
	} else if usagePercent >= 80 {
		quotaStatus = "yellow"
	}
	
	planName := "N/A"
	if plan != nil {
		planName = plan.Name
	}
	
	// Get current hour usage (simplified - just use today's for now)
	currentHourEvents := 0
	hourStart := time.Date(today.Year(), today.Month(), today.Day(), today.Hour(), 0, 0, 0, tehranLoc)
	hourEnd := hourStart.Add(time.Hour)
	hourUsage, _ := s.db.GetUsageInRange(project.ID, hourStart, hourEnd)
	currentHourEvents = int(hourUsage)
	
	// Get storage
	storageMB, _ := s.db.GetProjectStorage(project.ID)
	
	result := gin.H{
		"id":                    project.ID,
		"name":                  project.Name,
		"upstream_url":          project.UpstreamURL,
		"plan_id":               project.PlanID,
		"plan_name":             planName,
		"billing_email":         project.BillingEmail,
		"status":                project.Status,
		"settings":              project.Settings,
		"current_day_events":    usage,
		"current_hour_events":   currentHourEvents,
		"daily_limit":           dailyLimit,
		"usage_percent":         usagePercent,
		"quota_status":          quotaStatus,
		"storage_mb":            storageMB,
		"custom_quota_events_per_day": project.CustomQuotaEventsPerDay,
		"created_at":            project.CreatedAt,
		"updated_at":            project.UpdatedAt,
		"last_event_at":         project.LastEventAt,
	}
	
	return result
}

// listProjects returns all projects
func (s *Server) listProjects(c *gin.Context) {
	status := c.Query("status")
	
	var projects []*db.Project
	var err error
	
	if status != "" {
		projects, err = s.db.GetProjectsByStatus(status)
	} else {
		projects, err = s.db.GetAllProjects()
	}
	
	if err != nil {
		log.Errorf("Failed to get projects: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get projects"})
		return
	}
	
	enriched := make([]gin.H, len(projects))
	for i, project := range projects {
		enriched[i] = s.enrichProject(project)
	}
	
	c.JSON(http.StatusOK, enriched)
}

// getProject returns a specific project
func (s *Server) getProject(c *gin.Context) {
	projectID := c.Param("id")
	
	project, err := s.db.GetProject(projectID)
	if err != nil {
		log.Errorf("Failed to get project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get project"})
		return
	}
	
	if project == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Project not found"})
		return
	}
	
	enriched := s.enrichProject(project)
	c.JSON(http.StatusOK, enriched)
}

// updateProjectSettings updates project settings and syncs config
func (s *Server) updateProjectSettings(c *gin.Context) {
	projectID := c.Param("id")
	
	var request struct {
		Settings map[string]interface{} `json:"settings"`
	}
	
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}
	
	// Update settings in database
	if err := s.db.UpdateProjectSettings(projectID, request.Settings); err != nil {
		log.Errorf("Failed to update settings for project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update settings"})
		return
	}
	
	// Sync config file
	if err := s.configMgr.SyncProjectConfig(projectID, request.Settings); err != nil {
		log.Errorf("Failed to sync config for project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to sync config"})
		return
	}
	
	// Restart project to apply changes
	if err := s.dockerMgr.RestartProject(projectID); err != nil {
		log.Warnf("Failed to restart project %s: %v", projectID, err)
		// Not a fatal error - settings are saved
	}
	
	c.JSON(http.StatusOK, gin.H{
		"message": "Settings updated and config synced",
		"settings": request.Settings,
	})
}

// updateProjectStatus updates project status
func (s *Server) updateProjectStatus(c *gin.Context) {
	projectID := c.Param("id")
	
	var request struct {
		Status string `json:"status"`
	}
	
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}
	
	if request.Status != "active" && request.Status != "suspended" && request.Status != "cancelled" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid status"})
		return
	}
	
	if err := s.db.UpdateProjectStatus(projectID, request.Status); err != nil {
		log.Errorf("Failed to update status for project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update status"})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{
		"message": "Status updated",
		"status":  request.Status,
	})
}

// restartProject restarts a project's containers
func (s *Server) restartProject(c *gin.Context) {
	projectID := c.Param("id")
	
	if err := s.dockerMgr.RestartProject(projectID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Project restarted"})
}

// stopProject stops a project's containers
func (s *Server) stopProject(c *gin.Context) {
	projectID := c.Param("id")
	
	if err := s.dockerMgr.StopProject(projectID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Project stopped"})
}

// startProject starts a project's containers
func (s *Server) startProject(c *gin.Context) {
	projectID := c.Param("id")
	
	if err := s.dockerMgr.StartProject(projectID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Project started"})
}

// getDockerStatus gets container status
func (s *Server) getDockerStatus(c *gin.Context) {
	projectID := c.Param("id")
	
	status, err := s.dockerMgr.GetStatus(projectID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"status": status})
}

// getDockerLogs gets container logs
func (s *Server) getDockerLogs(c *gin.Context) {
	projectID := c.Param("id")
	tail := 100
	
	logs, err := s.dockerMgr.GetLogs(projectID, tail)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"logs": logs})
}

// syncConfig manually syncs config for a project
func (s *Server) syncConfig(c *gin.Context) {
	projectID := c.Param("id")
	
	project, err := s.db.GetProject(projectID)
	if err != nil || project == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Project not found"})
		return
	}
	
	if err := s.configMgr.SyncProjectConfig(projectID, project.Settings); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Config synced"})
}

// getTemplates returns global config templates
func (s *Server) getTemplates(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"default":  s.configMgr.GetDefaultTemplate(),
		"ingester": s.configMgr.GetIngesterTemplate(),
	})
}

// getLimitsStatus returns limit status for all projects
func (s *Server) getLimitsStatus(c *gin.Context) {
	projects, err := s.db.GetAllProjects()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get projects"})
		return
	}
	
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	today := time.Now().In(tehranLoc)
	
	var result []gin.H
	
	for _, project := range projects {
		plan, _ := s.db.GetPlan(project.PlanID)
		if plan == nil {
			continue
		}
		
		dailyLimit := plan.EventsPerDayLimit
		if project.CustomQuotaEventsPerDay != nil {
			dailyLimit = *project.CustomQuotaEventsPerDay
		}
		
		usage, _ := s.db.GetTodayUsage(project.ID, today)
		usagePercent := float64(usage) / float64(dailyLimit) * 100
		
		status := "green"
		if usagePercent >= 100 {
			status = "red"
		} else if usagePercent >= 90 {
			status = "orange"
		} else if usagePercent >= 80 {
			status = "yellow"
		}
		
		result = append(result, gin.H{
			"project_id":     project.ID,
			"project_name":   project.Name,
			"usage":          usage,
			"limit":          dailyLimit,
			"usage_percent":  fmt.Sprintf("%.1f", usagePercent),
			"quota_status":   status,
			"project_status": project.Status,
		})
	}
	
	c.JSON(http.StatusOK, result)
}

// checkLimits manually triggers limit check
func (s *Server) checkLimits(c *gin.Context) {
	s.enforcer.CheckAllProjects()
	c.JSON(http.StatusOK, gin.H{"message": "Limit check triggered"})
}

// manualSuspend manually suspends a project
func (s *Server) manualSuspend(c *gin.Context) {
	projectID := c.Param("id")
	
	if err := s.enforcer.SuspendProject(projectID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Project suspended"})
}

// manualResume manually resumes a project
func (s *Server) manualResume(c *gin.Context) {
	projectID := c.Param("id")
	
	if err := s.enforcer.ResumeProject(projectID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Project resumed"})
}

// adminDashboard serves the admin dashboard page
func (s *Server) adminDashboard(c *gin.Context) {
	c.HTML(http.StatusOK, "admin.html", nil)
}

// getStatsOverview returns dashboard statistics
func (s *Server) getStatsOverview(c *gin.Context) {
	projects, err := s.db.GetAllProjects()
	if err != nil {
		log.Errorf("Failed to get projects for stats: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get stats"})
		return
	}
	
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	today := time.Now().In(tehranLoc)
	
	totalProjects := len(projects)
	activeProjects := 0
	totalEventsToday := int64(0)
	totalMRR := 0.0
	
	for _, project := range projects {
		if project.Status == "active" {
			activeProjects++
		}
		
		usage, _ := s.db.GetTodayUsage(project.ID, today)
		totalEventsToday += int64(usage)
		
		plan, _ := s.db.GetPlan(project.PlanID)
		if plan != nil {
			totalMRR += float64(plan.PriceMonthly)
		}
	}
	
	c.JSON(http.StatusOK, gin.H{
		"total_projects":        totalProjects,
		"active_projects":       activeProjects,
		"total_events_today":    totalEventsToday,
		"monthly_recurring_revenue": totalMRR,
	})
}

// listPlans returns all subscription plans
func (s *Server) listPlans(c *gin.Context) {
	plans, err := s.db.GetAllPlans()
	if err != nil {
		log.Errorf("Failed to get plans: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get plans"})
		return
	}
	
	c.JSON(http.StatusOK, plans)
}

// updateProjectPlan updates a project's subscription plan
func (s *Server) updateProjectPlan(c *gin.Context) {
	projectID := c.Param("id")
	
	var request struct {
		PlanID string `json:"plan_id"`
	}
	
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}
	
	if err := s.db.UpdateProjectPlan(projectID, request.PlanID); err != nil {
		log.Errorf("Failed to update plan for project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update plan"})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Plan updated"})
}

// updateProjectQuota updates a project's custom quota
func (s *Server) updateProjectQuota(c *gin.Context) {
	projectID := c.Param("id")
	
	var request struct {
		DailyLimit int `json:"daily_limit"`
	}
	
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}
	
	if err := s.db.UpdateProjectCustomQuota(projectID, &request.DailyLimit, nil); err != nil {
		log.Errorf("Failed to update quota for project %s: %v", projectID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update quota"})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Quota updated"})
}

// getProjectUsageHourly returns hourly usage for a project
func (s *Server) getProjectUsageHourly(c *gin.Context) {
	projectID := c.Param("id")
	hoursStr := c.DefaultQuery("hours", "24")
	hours := 24
	fmt.Sscanf(hoursStr, "%d", &hours)
	
	if hours < 1 || hours > 168 {
		hours = 24
	}
	
	tehranLoc, _ := time.LoadLocation("Asia/Tehran")
	now := time.Now().In(tehranLoc)
	
	var usage []gin.H
	for i := hours - 1; i >= 0; i-- {
		hour := now.Add(time.Duration(-i) * time.Hour)
		hourStart := time.Date(hour.Year(), hour.Month(), hour.Day(), hour.Hour(), 0, 0, 0, tehranLoc)
		hourEnd := hourStart.Add(time.Hour)
		
		count, _ := s.db.GetUsageInRange(projectID, hourStart, hourEnd)
		usage = append(usage, gin.H{
			"hour":  hourStart.Format("2006-01-02T15:04:05"),
			"count": count,
		})
	}
	
	c.JSON(http.StatusOK, usage)
}

// getSettings returns global settings
func (s *Server) getSettings(c *gin.Context) {
	// Return default settings structure
	c.JSON(http.StatusOK, gin.H{
		"prompts": gin.H{
			"summary": "Analyze and summarize the following logs. Focus on errors, warnings, and patterns.",
			"trend":   "Compare these time periods and identify significant trends, anomalies, and changes in error patterns.",
		},
		"default_llm": gin.H{
			"backend":      "gemini",
			"gemini_key":   "",
			"openai_key":   "",
			"model":        "gemini-2.5-flash-lite",
			"temperature":  0.2,
		},
	})
}

// updateSettings updates global settings
func (s *Server) updateSettings(c *gin.Context) {
	var settings map[string]interface{}
	if err := c.ShouldBindJSON(&settings); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}
	
	// In a full implementation, this would save to database or config file
	// For now, just return success
	c.JSON(http.StatusOK, gin.H{"message": "Settings updated"})
}
