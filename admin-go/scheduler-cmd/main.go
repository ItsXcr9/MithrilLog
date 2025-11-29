package main

import (
	"os"

	"github.com/mithrillog/admin/db"
	"github.com/mithrillog/admin/scheduler"
	log "github.com/sirupsen/logrus"
)

func main() {
	// Configure logging
	log.SetFormatter(&log.JSONFormatter{})
	log.SetLevel(log.InfoLevel)
	
	log.Info("Starting MithrilLog Usage Scheduler")
	
	// Get configuration from environment
	dbPath := getEnv("DATABASE_URL", "sqlite:///app/data/admin.db")
	baseDir := getEnv("BASE_DIR", "/home")
	
	// Initialize database
	database, err := db.NewDatabase(dbPath)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer database.Close()
	
	log.Info("Database initialized")
	
	// Create scheduler runner
	runner := scheduler.NewRunner(database, baseDir)
	
	// Run scheduler loop
	runner.RunScheduler()
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

