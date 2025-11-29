package scheduler

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	log "github.com/sirupsen/logrus"
)

// Project represents a scanned project directory
type Project struct {
	ID      string
	Path    string
	DataDir string
}

// ScanProjects scans for project directories matching MithrilLog-* pattern
func ScanProjects(baseDir string) ([]Project, error) {
	var projects []Project
	
	pattern := filepath.Join(baseDir, "MithrilLog-*")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil, fmt.Errorf("failed to glob pattern: %w", err)
	}
	
	for _, path := range matches {
		info, err := os.Stat(path)
		if err != nil || !info.IsDir() {
			continue
		}
		
		projectID := filepath.Base(path)
		projectID = projectID[len("MithrilLog-"):]
		
		projects = append(projects, Project{
			ID:      projectID,
			Path:    path,
			DataDir: filepath.Join(path, "data"),
		})
	}
	
	return projects, nil
}

// MetaFile represents the structure of the .meta.json file
type MetaFile struct {
	TotalEvents int `json:"total_events"`
}

// CountNDJSONEvents returns the total events (from meta file) and file size
func CountNDJSONEvents(filePath string) (events int, size int64, err error) {
	info, err := os.Stat(filePath)
	if err != nil {
		return 0, 0, err
	}
	size = info.Size()
	
	// Try to read from .meta.json first
	metaPath := strings.TrimSuffix(filePath, ".ndjson") + ".meta.json"
	if metaData, err := os.ReadFile(metaPath); err == nil {
		var meta MetaFile
		if err := json.Unmarshal(metaData, &meta); err == nil {
			return meta.TotalEvents, size, nil
		}
		log.Warnf("Failed to parse meta file %s: %v", metaPath, err)
	}
	
	// Fallback to counting lines in .ndjson if meta file missing or invalid
	file, err := os.Open(filePath)
	if err != nil {
		return 0, size, err
	}
	defer file.Close()
	
	scanner := bufio.NewScanner(file)
	count := 0
	for scanner.Scan() {
		count++
	}
	
	if err := scanner.Err(); err != nil {
		return count, size, err
	}
	
	return count, size, nil
}

// HourlyUsage represents usage aggregated by hour
type HourlyUsage struct {
	DateTime time.Time
	Events   int
	Size     int64
}

// DailyUsage represents usage aggregated by date
type DailyUsage struct {
	Date  time.Time
	Events int
	Size   int64
}

// CalculateUsageByHour scans bucket directories and aggregates by hour
func CalculateUsageByHour(dataDir string) (map[string]HourlyUsage, error) {
	usage := make(map[string]HourlyUsage)
	
	bucketsDir := filepath.Join(dataDir, "buckets")
	if _, err := os.Stat(bucketsDir); os.IsNotExist(err) {
		return usage, nil
	}
	
	// Walk through buckets/YYYY/MM/DD/HH-MM.ndjson
	err := filepath.Walk(bucketsDir, func(filePath string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Skip errors
		}
		
		if info.IsDir() || filepath.Ext(filePath) != ".ndjson" {
			return nil
		}
		
		// Extract date and hour from path
		// Structure: .../buckets/2025/11/29/10/14.ndjson
		relPath, err := filepath.Rel(bucketsDir, filePath)
		if err != nil {
			return nil
		}
		
		// Split path by directory separator (not filepath.SplitList which splits on :)
		parts := strings.Split(relPath, string(filepath.Separator))
		if len(parts) < 5 {
			return nil
		}
		
		// parts[0] = year, parts[1] = month, parts[2] = day, parts[3] = hour, parts[4] = filename
		year, err1 := strconv.Atoi(parts[0])
		month, err2 := strconv.Atoi(parts[1])
		day, err3 := strconv.Atoi(parts[2])
		hour, err4 := strconv.Atoi(parts[3])
		if err1 != nil || err2 != nil || err3 != nil || err4 != nil {
			return nil
		}
		
		dateTime := time.Date(year, time.Month(month), day, hour, 0, 0, 0, time.UTC)
		hourKey := fmt.Sprintf("%d-%02d-%02d-%02d", year, month, day, hour)
		
		events, size, err := CountNDJSONEvents(filePath)
		if err != nil {
			log.Warnf("Error counting events in %s: %v", filePath, err)
			return nil
		}
		
		if existing, ok := usage[hourKey]; ok {
			existing.Events += events
			existing.Size += size
			usage[hourKey] = existing
		} else {
			usage[hourKey] = HourlyUsage{
				DateTime: dateTime,
				Events:   events,
				Size:     size,
			}
		}
		
		return nil
	})
	
	return usage, err
}

// CalculateUsageByDate scans bucket directories and aggregates by date
func CalculateUsageByDate(dataDir string) (map[string]DailyUsage, error) {
	usage := make(map[string]DailyUsage)
	
	bucketsDir := filepath.Join(dataDir, "buckets")
	if _, err := os.Stat(bucketsDir); os.IsNotExist(err) {
		return usage, nil
	}
	
	// Walk through buckets/YYYY/MM/DD/
	err := filepath.Walk(bucketsDir, func(filePath string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		
		if info.IsDir() || filepath.Ext(filePath) != ".ndjson" {
			return nil
		}
		
		relPath, err := filepath.Rel(bucketsDir, filePath)
		if err != nil {
			return nil
		}
		
		// Split path by directory separator
		parts := strings.Split(relPath, string(filepath.Separator))
		if len(parts) < 4 {
			return nil
		}
		
		year, err1 := strconv.Atoi(parts[0])
		month, err2 := strconv.Atoi(parts[1])
		day, err3 := strconv.Atoi(parts[2])
		if err1 != nil || err2 != nil || err3 != nil {
			return nil
		}
		
		date := time.Date(year, time.Month(month), day, 0, 0, 0, 0, time.UTC)
		dateKey := date.Format("2006-01-02")
		
		events, size, err := CountNDJSONEvents(filePath)
		if err != nil {
			log.Warnf("Error counting events in %s: %v", filePath, err)
			return nil
		}
		
		if existing, ok := usage[dateKey]; ok {
			existing.Events += events
			existing.Size += size
			usage[dateKey] = existing
		} else {
			usage[dateKey] = DailyUsage{
				Date:   date,
				Events: events,
				Size:   size,
			}
		}
		
		return nil
	})
	
	return usage, err
}

// CalculateProjectStorage calculates total storage used by a project in bytes
func CalculateProjectStorage(projectPath string) (int64, error) {
	var totalSize int64
	
	err := filepath.Walk(projectPath, func(filePath string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Skip errors
		}
		
		if !info.IsDir() {
			totalSize += info.Size()
		}
		
		return nil
	})
	
	return totalSize, err
}

