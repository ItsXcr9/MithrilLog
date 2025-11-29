package docker

import (
	"fmt"
	"os/exec"

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
func (m *Manager) GetLogs(projectID string, tail int) (string, error) {
	composePath := fmt.Sprintf("/home/MithrilLog-%s/docker-compose.yml", projectID)
	
	cmd := exec.Command("docker", "compose", "-f", composePath, "logs", "--tail", fmt.Sprintf("%d", tail))
	output, err := cmd.CombinedOutput()
	
	if err != nil {
		return "", fmt.Errorf("failed to get logs: %w", err)
	}
	
	return string(output), nil
}
