package docker

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	log "github.com/sirupsen/logrus"
)

// Manager handles Docker Compose operations for projects
type Manager struct{}

// NewManager creates a new Docker manager
func NewManager() *Manager {
	return &Manager{}
}

// RestartProject restarts all containers for a project
func (m *Manager) RestartProject(projectID string) error {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	log.Infof("Restarting project %s", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "restart")
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		log.Errorf("Failed to restart project %s: %v, output: %s", projectID, err, string(output))
		return fmt.Errorf("failed to restart project: %w", err)
	}
	
	log.Infof("Successfully restarted project %s", projectID)
	return nil
}

// StopProject stops all containers for a project
func (m *Manager) StopProject(projectID string) error {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	log.Infof("Stopping project %s", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "stop")
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		log.Errorf("Failed to stop project %s: %v, output: %s", projectID, err, string(output))
		return fmt.Errorf("failed to stop project: %w", err)
	}
	
	log.Infof("Successfully stopped project %s", projectID)
	return nil
}

// StartProject starts all containers for a project
func (m *Manager) StartProject(projectID string) error {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	log.Infof("Starting project %s", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "up", "-d")
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		log.Errorf("Failed to start project %s: %v, output: %s", projectID, err, string(output))
		return fmt.Errorf("failed to start project: %w", err)
	}
	
	log.Infof("Successfully started project %s", projectID)
	return nil
}

// GetStatus gets the status of project containers
func (m *Manager) GetStatus(projectID string) (string, error) {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "ps", "--format", "json")
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		return "", fmt.Errorf("failed to get status: %w", err)
	}
	
	return string(output), nil
}

// GetLogs gets logs from project containers
func (m *Manager) GetLogs(projectID string,  tail int) (string, error) {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "logs", "--tail", fmt.Sprintf("%d", tail))
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		return "", fmt.Errorf("failed to get logs: %w", err)
	}
	
	return string(output), nil
}

// GenerateComposeFile creates docker-compose.yml from template
func (m *Manager) GenerateComposeFile(projectID string) error {
	templatePath := "./docker/compose-template.yml"
	
	template, err := os.ReadFile(templatePath)
	if err != nil {
		return fmt.Errorf("failed to read compose template: %w", err)
	}
	
	outputPath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	// Write template as-is (environment variables will be substituted by Docker Compose)
	if err := os.WriteFile(outputPath, template, 0644); err != nil {
		return fmt.Errorf("failed to write compose file: %w", err)
	}
	
	log.Infof("Generated docker-compose.yml for project %s", projectID)
	return nil
}


// RestartWithHealthCheck restarts and waits for healthy status
func (m *Manager) RestartWithHealthCheck(projectID string, timeoutSeconds int) error {
	if err := m.RestartProject(projectID); err != nil {
		return err
	}
	
	// Wait for services to be running
	return m.WaitForHealthy(projectID, timeoutSeconds)
}

// WaitForHealthy waits for all project containers to be in running state
func (m *Manager) WaitForHealthy(projectID string, timeoutSeconds int) error {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	for i := 0; i < timeoutSeconds; i++ {
		cmd := exec.Command("docker", "compose", "-f", composePath, "ps", "--format", "json")
		output, err := cmd.CombinedOutput()
		
		if err != nil {
			log.Warnf("Failed to check container status (attempt %d/%d): %v", i+1, timeoutSeconds, err)
			time.Sleep(time.Second)
			continue
		}
		
		// Simple check: if output is not empty and no "exited" status
		statusStr := string(output)
		if len(statusStr) > 0 && !strings.Contains(strings.ToLower(statusStr), "exited") {
			log.Infof("Project %s containers are healthy", projectID)
			return nil
		}
		
		time.Sleep(time.Second)
	}
	
	return fmt.Errorf("timeout waiting for project %s containers to be healthy", projectID)
}

