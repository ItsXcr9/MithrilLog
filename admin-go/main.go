package main

import (
	"fmt"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/mithrillog/admin/api"
	"github.com/mithrillog/admin/config"
	"github.com/mithrillog/admin/db"
	"github.com/mithrillog/admin/docker"
	"github.com/mithrillog/admin/enforcer"
	log "github.com/sirupsen/logrus"
)

func main() {
	// Configure logging
	log.SetFormatter(&log.JSONFormatter{})
	log.SetLevel(log.InfoLevel)

	log.Info("Starting MithrilLog Admin Panel (Go)")

	// Initialize database
	dbPath := getEnv("DATABASE_URL", "sqlite:///app/data/admin.db")
	database, err := db.NewDatabase(dbPath)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer database.Close()

	log.Info("Database initialized")

	// Initialize config manager
	// Try Docker path first, then local dev path
	configPath := "configs/default.yaml"
	ingesterPath := "configs/ingester.yaml"
	promptsPath := "prompts"
	
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		configPath = "../configs/default.yaml"
		ingesterPath = "../configs/ingester.yaml"
		promptsPath = "../prompts"
	}
	
	configMgr := config.NewManager(configPath, ingesterPath, promptsPath)
	log.Info("Config manager initialized")

	// Initialize Docker manager
	dockerMgr := docker.NewManager()
	log.Info("Docker manager initialized")

	// Initialize limit enforcer
	limitEnforcer := enforcer.NewLimitEnforcer(database, dockerMgr)
	limitEnforcer.Start()
	log.Info("Limit enforcer started")

	// Initialize API server
	router := gin.Default()
	router.LoadHTMLGlob("templates/*")
	router.Static("/static", "./static")
	disableConfigTabs := getEnv("DISABLE_CONFIG_TABS", "false") == "true"
	apiServer := api.NewServer(database, configMgr, dockerMgr, limitEnforcer, disableConfigTabs)
	apiServer.RegisterRoutes(router)

	// Start server
	port := getEnv("PORT", "9999")
	log.Infof("Starting server on port %s", port)
	
	if err := router.Run(fmt.Sprintf("0.0.0.0:%s", port)); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
