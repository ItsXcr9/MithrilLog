# MithrilLog Admin Panel - Go Migration Proposal

## Executive Summary

This document proposes migrating the MithrilLog admin panel from Python to **Go** to enable complete multi-tenant management including Docker orchestration, config synchronization, limit enforcement, and automatic project suspension.

## Current State Analysis

### Existing Stack
- **Admin Backend**: Python (FastAPI) on port 9999
- **Database**: SQLite (`admin.db`)
- **Ingester**: Rust (high-performance log processing)
- **Gateway**: Python + Nginx

### Current Capabilities ✅
- Project management (CRUD)
- Usage tracking (hourly/daily metrics)
- Settings persistence in database
- Basic config file updates
- Storage calculation
- Subscription plan management

### Missing Critical Features ❌
- Docker Compose lifecycle management
- Automatic project restart after config changes
- Suspend page serving for over-limit projects
- Real-time limit enforcement
- Multi-project orchestration
- Nginx upstream switching

---

## Why Go?

### Comparison Matrix

| Feature | Python | **Go (Recommended)** | Rust |
|---------|--------|---------------------|------|
| Docker SDK | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Config Management | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Web Framework | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Dev Speed | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| Performance | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Concurrency | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Binary Size | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Maintenance | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **TOTAL** | 25/40 | **37/40** ✅ | 30/40 |

### Go Advantages

1. **Native Docker Support**: Official Docker SDK (`github.com/docker/docker/client`)
2. **Superior Concurrency**: Goroutines for monitoring multiple projects simultaneously
3. **Single Binary**: ~15MB executable, no Python dependencies
4. **Built for DevOps**: Docker, Kubernetes, Terraform all use Go
5. **Excellent YAML Libraries**: Type-safe config parsing with `gopkg.in/yaml.v3`
6. **Fast Compilation**: Quick iteration cycles
7. **Strong Stdlib**: HTTP server, JSON, file ops built-in

---

## Proposed Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Go Admin Panel                          │
│                   (Port 9999)                            │
├──────────────────────────────────────────────────────────┤
│  Core Services:                                          │
│  • REST API (Gin/Fiber)                                  │
│  • Project Manager                                       │
│  • Config Synchronizer                                   │
│  • Docker Orchestrator                                   │
│  • Limit Enforcer                                        │
│  • Suspend Page Server                                   │
└──────────────────────────────────────────────────────────┘
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  Project XCR9 │ │ Project TEBYAN│ │ Project MJ    │
├───────────────┤ ├───────────────┤ ├───────────────┤
│ • Rust Ingest │ │ • Rust Ingest │ │ • Rust Ingest │
│ • Python API  │ │ • Python API  │ │ • Python API  │
│ • Orchestrator│ │ • Orchestrator│ │ • Orchestrator│
└───────────────┘ └───────────────┘ └───────────────┘
      9900              9800              9600
```

---

## Core Features Implementation

### 1. Config Management System

**Flow:**
```
Global Templates          Per-Project Overrides        Final Config
─────────────────         ─────────────────────        ────────────
configs/default.yaml      admin.db (settings JSON)     /home/MithrilLog-{id}/
configs/ingester.yaml  →         +                  →   configs/default.yaml
                          Project-specific values        configs/ingester.yaml
```

**Go Implementation:**
```go
type ConfigManager struct {
    defaultConfig   DefaultConfig
    ingesterConfig  IngesterConfig
    db             *sql.DB
}

func (cm *ConfigManager) SyncProjectConfig(projectID string) error {
    // 1. Load global templates
    globalDefault := cm.loadTemplate("configs/default.yaml")
    globalIngester := cm.loadTemplate("configs/ingester.yaml")
    
    // 2. Fetch project overrides from DB
    overrides := cm.fetchProjectSettings(projectID)
    
    // 3. Merge configs
    finalDefault := cm.merge(globalDefault, overrides)
    
    // 4. Write to project directory
    targetPath := fmt.Sprintf("/home/MithrilLog-%s/configs/default.yaml", projectID)
    return cm.writeYAML(targetPath, finalDefault)
}
```

**Config Mapping:**

| DB Field | Global Config Path | Per-Project Override |
|----------|-------------------|----------------------|
| `llm.backend` | `configs/default.yaml` → `llm.backend` | ✅ |
| `llm.gemini_api_key` | `configs/default.yaml` → `llm.gemini_api_key` | ✅ |
| `ingest.retention_days` | `configs/default.yaml` → `ingest.retention_days` | ✅ |
| `alert.telegram_bot_token` | `configs/default.yaml` → `alert.telegram_bot_token` | ✅ |
| `web.title` | `configs/default.yaml` → `web.title` | ✅ |
| Prompts | `/prompts/*.txt` | ✅ Per-project prompts |

### 2. Docker Compose Orchestration

```go
type DockerManager struct {
    client *docker.Client
}

// Restart project after config change
func (dm *DockerManager) RestartProject(projectID string) error {
    composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
    
    cmd := exec.Command("docker", "compose", "-f", composePath, "restart")
    return cmd.Run()
}

// Stop over-limit project
func (dm *DockerManager) SuspendProject(projectID string) error {
    composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
    
    cmd := exec.Command("docker", "compose", "-f", composePath, "stop")
    return cmd.Run()
}

// Resume project
func (dm *DockerManager) ResumeProject(projectID string) error {
    composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
    
    cmd := exec.Command("docker", "compose", "-f", composePath, "up", "-d")
    return cmd.Run()
}
```

### 3. Limit Enforcement & Auto-Suspension

```go
type LimitEnforcer struct {
    db            *sql.DB
    dockerMgr     *DockerManager
    nginxMgr      *NginxManager
    ticker        *time.Ticker
}

func (le *LimitEnforcer) Start() {
    le.ticker = time.NewTicker(1 * time.Minute)
    
    go func() {
        for range le.ticker.C {
            le.checkAllProjects()
        }
    }()
}

func (le *LimitEnforcer) checkAllProjects() {
    projects := le.fetchActiveProjects()
    
    for _, project := range projects {
        usage := le.getUsageToday(project.ID)
        
        if usage >= project.DailyLimit && project.Status == "active" {
            log.Printf("Project %s exceeded limit: %d/%d", 
                project.ID, usage, project.DailyLimit)
            
            // 1. Update status in DB
            le.updateProjectStatus(project.ID, "suspended")
            
            // 2. Switch Nginx upstream to suspend page
            le.nginxMgr.RedirectToSuspendPage(project.ID)
            
            // 3. Optional: Stop Docker containers to save resources
            le.dockerMgr.SuspendProject(project.ID)
        }
        
        // Auto-resume if usage resets (new day)
        if usage < project.DailyLimit && project.Status == "suspended" {
            le.resumeProject(project.ID)
        }
    }
}
```

### 4. Suspend Page Serving

```go
func (api *AdminAPI) SuspendedPageHandler(c *gin.Context) {
    projectID := c.Query("project")
    
    project := api.db.GetProject(projectID)
    if project == nil {
        c.JSON(404, gin.H{"error": "Project not found"})
        return
    }
    
    // Calculate reset time (midnight Tehran time)
    tehranTZ, _ := time.LoadLocation("Asia/Tehran")
    now := time.Now().In(tehranTZ)
    tomorrow := now.AddDate(0, 0, 1)
    resetTime := time.Date(tomorrow.Year(), tomorrow.Month(), tomorrow.Day(), 
        0, 0, 0, 0, tehranTZ)
    
    c.HTML(200, "suspended.html", gin.H{
        "ProjectName":  project.Name,
        "PlanName":     project.PlanName,
        "CurrentUsage": project.CurrentDayEvents,
        "DailyLimit":   project.DailyLimit,
        "UsagePercent": (float64(project.CurrentDayEvents) / float64(project.DailyLimit)) * 100,
        "ResetTime":    resetTime.Format("15:04 MST"),
        "SupportEmail": "support@mithrillog.com",
    })
}
```

**Suspend Page Design:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Service Temporarily Suspended - MithrilLog</title>
    <style>
        /* Glassmorphism dark theme matching your dashboard */
        body { 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            font-family: 'Inter', sans-serif;
        }
        .container {
            max-width: 600px;
            margin: 100px auto;
            padding: 40px;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .usage-bar {
            width: 100%;
            height: 30px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            overflow: hidden;
        }
        .usage-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff6b6b, #ee5a6f);
            transition: width 0.3s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ Daily Limit Reached</h1>
        <p>Project <strong>{{ .ProjectName }}</strong> has reached its daily event limit.</p>
        
        <div class="stats">
            <p>Plan: <strong>{{ .PlanName }}</strong></p>
            <p>Usage Today: <strong>{{ .CurrentUsage }} / {{ .DailyLimit }}</strong> events</p>
        </div>
        
        <div class="usage-bar">
            <div class="usage-fill" style="width: {{ .UsagePercent }}%"></div>
        </div>
        
        <p>Service will automatically resume at <strong>{{ .ResetTime }}</strong></p>
        <p>To increase your limit, upgrade your plan or contact {{ .SupportEmail }}</p>
    </div>
</body>
</html>
```

### 5. Nginx Dynamic Reconfiguration

```go
type NginxManager struct {
    configPath string
}

func (nm *NginxManager) RedirectToSuspendPage(projectID string) error {
    // Read current nginx.conf
    config := nm.readConfig()
    
    // Find location block for this project
    // Replace upstream with admin suspend endpoint
    config = nm.replaceUpstream(
        projectID,
        fmt.Sprintf("http://admin:9999/suspended?project=%s", projectID),
    )
    
    // Write back
    nm.writeConfig(config)
    
    // Reload nginx
    return exec.Command("nginx", "-s", "reload").Run()
}

func (nm *NginxManager) RestoreUpstream(projectID string, upstreamURL string) error {
    config := nm.readConfig()
    config = nm.replaceUpstream(projectID, upstreamURL)
    nm.writeConfig(config)
    return exec.Command("nginx", "-s", "reload").Run()
}
```

---

## API Endpoints (Go Implementation)

### Admin Management
```
GET    /api/admin/stats/overview          - Dashboard stats
GET    /api/admin/projects                - List all projects
GET    /api/admin/projects/:id            - Get project details
PUT    /api/admin/projects/:id/settings   - Update settings (syncs config + restarts)
PUT    /api/admin/projects/:id/status     - Change status (active/suspended)
POST   /api/admin/projects/:id/restart    - Manual restart
```

### Config Operations
```
POST   /api/admin/projects/:id/sync-config  - Force config sync
GET    /api/admin/config/templates          - Get global templates
PUT    /api/admin/config/templates          - Update global templates
```

### Docker Operations
```
POST   /api/admin/docker/:id/restart        - Restart project containers
POST   /api/admin/docker/:id/stop           - Stop project
POST   /api/admin/docker/:id/start          - Start project
GET    /api/admin/docker/:id/status         - Get container status
GET    /api/admin/docker/:id/logs           - Get container logs
```

### Limit Enforcement
```
GET    /api/admin/limits/status             - Get all projects limit status
POST   /api/admin/limits/check              - Force limit check
POST   /api/admin/limits/:id/suspend        - Manual suspend
POST   /api/admin/limits/:id/resume         - Manual resume
```

---

## Project Structure

```
admin/
├── main.go                      # Entry point
├── go.mod                       # Dependencies
├── go.sum
├── config/
│   ├── config.go               # Config structs
│   ├── manager.go              # Config sync logic
│   └── templates.go            # Template loading
├── docker/
│   ├── manager.go              # Docker operations
│   └── compose.go              # Compose wrapper
├── api/
│   ├── server.go               # Gin setup
│   ├── handlers.go             # HTTP handlers
│   └── middleware.go           # Auth, logging
├── models/
│   ├── project.go              # Project model
│   ├── usage.go                # Usage tracking
│   └── plan.go                 # Subscription plans
├── db/
│   ├── sqlite.go               # Database layer
│   └── migrations.go           # Schema migrations
├── enforcer/
│   ├── limits.go               # Limit checking
│   └── scheduler.go            # Background jobs
├── nginx/
│   └── manager.go              # Nginx reconfig
├── templates/
│   └── suspended.html          # Suspend page
└── Dockerfile
```

---

## Dependencies (go.mod)

```go
module github.com/mithrillog/admin

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1           // Web framework
    github.com/docker/docker v24.0.7+incompatible // Docker SDK
    gopkg.in/yaml.v3 v3.0.1                   // YAML parsing
    github.com/mattn/go-sqlite3 v1.14.18      // SQLite driver
    github.com/robfig/cron/v3 v3.0.1          // Scheduled jobs
    github.com/sirupsen/logrus v1.9.3         // Logging
)
```

---

## Migration Plan

### Phase 1: Prototype (1-2 days)
- [ ] Set up Go project structure
- [ ] Implement config manager (read default.yaml, ingester.yaml)
- [ ] Create basic REST API with Gin
- [ ] Migrate database models
- [ ] Test config merging logic

### Phase 2: Docker Integration (2-3 days)
- [ ] Implement DockerManager
- [ ] Test restart/stop/start operations
- [ ] Add container status monitoring
- [ ] Create health check system

### Phase 3: Limit Enforcement (2-3 days)
- [ ] Build LimitEnforcer service
- [ ] Implement background monitoring
- [ ] Add auto-suspend logic
- [ ] Create suspend page template
- [ ] Test Nginx upstream switching

### Phase 4: API Migration (2 days)
- [ ] Port all existing Python endpoints
- [ ] Add new Docker/Config endpoints
- [ ] Implement authentication
- [ ] Add admin logging

### Phase 5: Testing & Deployment (2 days)
- [ ] Integration tests
- [ ] Load testing
- [ ] Documentation
- [ ] Gradual rollout

**Total Estimated Time: 9-12 days**

---

## Benefits Summary

### Performance
- ✅ 10-50x faster than Python for system operations
- ✅ Concurrent monitoring of all projects with goroutines
- ✅ Lower memory footprint (~50MB vs ~200MB)

### Deployment
- ✅ Single 15MB binary (vs 100MB+ Python image)
- ✅ No dependency hell
- ✅ Fast startup (~100ms vs ~2s)

### Features
- ✅ Native Docker control
- ✅ Real-time limit enforcement
- ✅ Automatic config synchronization
- ✅ Suspend page serving
- ✅ Better error handling

### Maintenance
- ✅ Type-safe config management
- ✅ Better IDE support
- ✅ Easier debugging
- ✅ Industry-standard for DevOps tools

---

## Risk Mitigation

### Risk 1: Learning Curve
- **Mitigation**: Go is simpler than Rust, large stdlib, excellent docs
- **Timeframe**: 1-2 days to be productive

### Risk 2: Migration Bugs
- **Mitigation**: Run Python and Go admin in parallel during testing
- **Rollback**: Keep Python version as backup

### Risk 3: Docker SDK Issues
- **Mitigation**: Official Docker client, battle-tested, fallback to CLI

---

## Decision Criteria

Choose **Go** if:
- ✅ You need robust Docker orchestration
- ✅ Multi-project monitoring is critical
- ✅ You want better performance
- ✅ Single binary deployment is valuable
- ✅ You're building for production scale

Keep **Python** if:
- ❌ Team has zero Go experience
- ❌ Only simple config updates needed
- ❌ No Docker management required
- ❌ Prototype/MVP stage only

**Recommendation: Go is the clear winner for this use case** 🚀

---

## Next Steps

1. **Review & Approve**: Discuss this proposal
2. **Proof of Concept**: Build minimal Go admin (2 days)
   - Config sync
   - Docker restart
   - Basic API
3. **Evaluate**: Test POC with one project
4. **Full Migration**: If approved, complete implementation
5. **Deploy**: Gradual rollout to production

---

## Appendix: Sample Code

### Complete Config Sync Example

```go
package config

import (
    "fmt"
    "os"
    "gopkg.in/yaml.v3"
)

type DefaultConfig struct {
    LLM struct {
        Backend      string  `yaml:"backend"`
        GeminiAPIKey string  `yaml:"gemini_api_key"`
        Temperature  float64 `yaml:"temperature"`
    } `yaml:"llm"`
    
    Ingest struct {
        RetentionDays int `yaml:"retention_days"`
    } `yaml:"ingest"`
    
    Alert struct {
        TelegramBotToken string `yaml:"telegram_bot_token"`
        TelegramChatID   string `yaml:"telegram_chat_id"`
    } `yaml:"alert"`
    
    Web struct {
        Title string `yaml:"title"`
    } `yaml:"web"`
}

func SyncProjectConfig(projectID string, overrides map[string]interface{}) error {
    // Load global template
    globalConfig := DefaultConfig{}
    data, err := os.ReadFile("configs/default.yaml")
    if err != nil {
        return fmt.Errorf("failed to read default config: %w", err)
    }
    
    if err := yaml.Unmarshal(data, &globalConfig); err != nil {
        return fmt.Errorf("failed to parse default config: %w", err)
    }
    
    // Apply overrides
    if llm, ok := overrides["llm"].(map[string]interface{}); ok {
        if backend, ok := llm["backend"].(string); ok {
            globalConfig.LLM.Backend = backend
        }
        if key, ok := llm["gemini_key"].(string); ok {
            globalConfig.LLM.GeminiAPIKey = key
        }
    }
    
    // Write to project directory
    output, err := yaml.Marshal(&globalConfig)
    if err != nil {
        return fmt.Errorf("failed to marshal config: %w", err)
    }
    
    targetPath := fmt.Sprintf("/home/MithrilLog-%s/configs/default.yaml", projectID)
    return os.WriteFile(targetPath, output, 0644)
}
```

---

**Document Version**: 1.1
**Date**: 2025-11-30
**Author**: Antigravity AI
**Status**: Implemented ✅

## Implemented Features

### Environment Variables
- `DISABLE_CONFIG_TABS`: Set to `true` to hide the **Settings** and **Configs** tabs in the UI, leaving only Monitoring, Billing, and Suspension controls. This is useful for restricted admin views.

### Deployment
The Go admin panel is now the standard implementation, deployed via `admin-go/docker-compose.yml`.

