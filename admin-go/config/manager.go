package config

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// DefaultConfig matches configs/default.yaml structure
type DefaultConfig struct {
	Environment string `yaml:"environment"`
	Timezone    string `yaml:"timezone"`
	
	LLM struct {
		Backend        string  `yaml:"backend"`
		ModelPath      string  `yaml:"model_path"`
		ContextLength  int     `yaml:"context_length"`
		Temperature    float64 `yaml:"temperature"`
		TopP           float64 `yaml:"top_p"`
		MaxTokens      int     `yaml:"max_tokens"`
		OpenAIAPIKey   string  `yaml:"openai_api_key"`
		OpenAIModel    string  `yaml:"openai_model"`
		OpenAIBaseURL  string  `yaml:"openai_base_url"`
		GeminiAPIKey   string  `yaml:"gemini_api_key"`
		GeminiModel    string  `yaml:"gemini_model"`
	} `yaml:"llm"`
	
	Ingest struct {
		Host              string  `yaml:"host"`
		UDPPort           int     `yaml:"udp_port"`
		TCPPort           int     `yaml:"tcp_port"`
		BucketDir         string  `yaml:"bucket_dir"`
		MaxBucketMinutes  int     `yaml:"max_bucket_minutes"`
		BloomErrorRate    float64 `yaml:"bloom_error_rate"`
		ReservoirSize     int     `yaml:"reservoir_size"`
		RetentionDays     int     `yaml:"retention_days"`
		ForwardToHost     string  `yaml:"forward_to_host"`
		ForwardToPort     int     `yaml:"forward_to_port"`
		UsePythonIngester bool    `yaml:"use_python_ingester"`
	} `yaml:"ingest"`
	
	Summary struct {
		HourlyAtMinute int    `yaml:"hourly_at_minute"`
		DailyAtHour    int    `yaml:"daily_at_hour"`
		DailyAtMinute  int    `yaml:"daily_at_minute"`
		ReportDir      string `yaml:"report_dir"`
		AnalysisLevels []string `yaml:"analysis_levels"`
	} `yaml:"summary"`
	
	Storage struct {
		SQLitePath string `yaml:"sqlite_path"`
	} `yaml:"storage"`
	
	Prompts struct {
		Hourly             string `yaml:"hourly"`
		Daily              string `yaml:"daily"`
		Anomaly            string `yaml:"anomaly"`
		HighlightAnalysis  string `yaml:"highlight_analysis"`
		Trend              string `yaml:"trend"`
	} `yaml:"prompts"`
	
	Web struct {
		Title string `yaml:"title"`
	} `yaml:"web"`
	
	Alert struct {
		Enabled          bool   `yaml:"enabled"`
		TelegramBotToken string `yaml:"telegram_bot_token"`
		TelegramChatID   string `yaml:"telegram_chat_id"`
		ErrorThreshold   int    `yaml:"error_threshold"`
	} `yaml:"alert"`
	
	CORS struct {
		AllowedOrigins []string `yaml:"allowed_origins"`
	} `yaml:"cors"`
	
	Logging struct {
		Patterns []struct {
			Pattern     string            `yaml:"pattern"`
			Action      string            `yaml:"action"`
			NewLevel    string            `yaml:"new_level,omitempty"`
			ExtraFields map[string]string `yaml:"extra_fields,omitempty"`
		} `yaml:"patterns"`
	} `yaml:"logging"`
	
	RemoteLogging struct {
		Enabled  bool   `yaml:"enabled"`
		Host     string `yaml:"host"`
		Port     int    `yaml:"port"`
		Protocol string `yaml:"protocol"`
	} `yaml:"remote_logging"`
}

// IngesterConfig matches configs/ingester.yaml structure
type IngesterConfig struct {
	Ingester struct {
		Host             string  `yaml:"host"`
		UDPPort          int     `yaml:"udp_port"`
		TCPPort          int     `yaml:"tcp_port"`
		BucketDir        string  `yaml:"bucket_dir"`
		MaxBucketMinutes int     `yaml:"max_bucket_minutes"`
		BloomErrorRate   float64 `yaml:"bloom_error_rate"`
		ReservoirSize    int     `yaml:"reservoir_size"`
		ForwardToHost    string  `yaml:"forward_to_host"`
		ForwardToPort    int     `yaml:"forward_to_port"`
		Timezone         string  `yaml:"timezone"`
	} `yaml:"ingester"`
}

// Manager handles config templates and per-project syncing
type Manager struct {
	defaultTemplatePath  string
	ingesterTemplatePath string
	promptsSourcePath    string
	defaultTemplate      DefaultConfig
	ingesterTemplate     IngesterConfig
}

// NewManager creates a new config manager
func NewManager(defaultPath, ingesterPath, promptsPath string) *Manager {
	mgr := &Manager{
		defaultTemplatePath:  defaultPath,
		ingesterTemplatePath: ingesterPath,
		promptsSourcePath:    promptsPath,
	}
	
	// Load templates on init
	if err := mgr.LoadTemplates(); err != nil {
		panic(fmt.Sprintf("Failed to load config templates: %v", err))
	}
	
	return mgr
}

// LoadTemplates loads the global config templates
func (m *Manager) LoadTemplates() error {
	// Load default.yaml
	defaultData, err := os.ReadFile(m.defaultTemplatePath)
	if err != nil {
		return fmt.Errorf("failed to read default.yaml: %w", err)
	}
	
	if err := yaml.Unmarshal(defaultData, &m.defaultTemplate); err != nil {
		return fmt.Errorf("failed to parse default.yaml: %w", err)
	}
	
	// Load ingester.yaml
	ingesterData, err := os.ReadFile(m.ingesterTemplatePath)
	if err != nil {
		return fmt.Errorf("failed to read ingester.yaml: %w", err)
	}
	
	if err := yaml.Unmarshal(ingesterData, &m.ingesterTemplate); err != nil {
		return fmt.Errorf("failed to parse ingester.yaml: %w", err)
	}
	
	return nil
}

// MergeOverrides applies per-project overrides to the global template
func (m *Manager) MergeOverrides(settings map[string]interface{}) DefaultConfig {
	// Start with global template
	merged := m.defaultTemplate
	
	// Apply LLM overrides
	if llm, ok := settings["llm"].(map[string]interface{}); ok {
		if backend, ok := llm["backend"].(string); ok {
			merged.LLM.Backend = backend
		}
		if model, ok := llm["model"].(string); ok && model != "" {
			if merged.LLM.Backend == "gemini" {
				merged.LLM.GeminiModel = model
			} else if merged.LLM.Backend == "openai" {
				merged.LLM.OpenAIModel = model
			}
		}
		if temp, ok := llm["temperature"].(float64); ok {
			merged.LLM.Temperature = temp
		}
		if geminiKey, ok := llm["gemini_key"].(string); ok && geminiKey != "" {
			merged.LLM.GeminiAPIKey = geminiKey
		}
		if openaiKey, ok := llm["openai_key"].(string); ok && openaiKey != "" {
			merged.LLM.OpenAIAPIKey = openaiKey
		}
	}
	
	// Apply Ingest overrides
	if ingest, ok := settings["ingest"].(map[string]interface{}); ok {
		if retentionDays, ok := ingest["retention_days"].(int); ok {
			merged.Ingest.RetentionDays = retentionDays
		}
	}
	
	// Apply Alert overrides
	if alert, ok := settings["alert"].(map[string]interface{}); ok {
		if token, ok := alert["telegram_token"].(string); ok {
			merged.Alert.TelegramBotToken = token
		}
		if chatID, ok := alert["telegram_chat"].(string); ok {
			merged.Alert.TelegramChatID = chatID
		}
		if enabled, ok := alert["enabled"].(bool); ok {
			merged.Alert.Enabled = enabled
		}
		if threshold, ok := alert["error_threshold"].(float64); ok {
			merged.Alert.ErrorThreshold = int(threshold)
		} else if threshold, ok := alert["error_threshold"].(int); ok {
			merged.Alert.ErrorThreshold = threshold
		}
	}
	
	// Apply Web title
	if webTitle, ok := settings["web_title"].(string); ok {
		merged.Web.Title = webTitle
	}

	// Apply Prompts overrides
	if prompts, ok := settings["prompts"].(map[string]interface{}); ok {
		if summary, ok := prompts["summary"].(string); ok && summary != "" {
			// In a real implementation we might write this to a file,
			// but for now we'll just keep the default path which points to the file
			// The actual content update would need to happen in the file itself
		}
	}
	
	// Apply Summary analysis_levels
	if summary, ok := settings["summary"].(map[string]interface{}); ok {
		if analysisLevels, ok := summary["analysis_levels"].([]interface{}); ok {
			levels := make([]string, 0, len(analysisLevels))
			for _, level := range analysisLevels {
				if levelStr, ok := level.(string); ok {
					levels = append(levels, levelStr)
				}
			}
			if len(levels) > 0 {
				merged.Summary.AnalysisLevels = levels
			}
		}
	}
	
	// Apply Logging patterns
	if logging, ok := settings["logging"].(map[string]interface{}); ok {
		if patterns, ok := logging["patterns"].([]interface{}); ok {
			patternRules := make([]struct {
				Pattern     string            `yaml:"pattern"`
				Action      string            `yaml:"action"`
				NewLevel    string            `yaml:"new_level,omitempty"`
				ExtraFields map[string]string `yaml:"extra_fields,omitempty"`
			}, 0, len(patterns))
			
			for _, pattern := range patterns {
				if patternMap, ok := pattern.(map[string]interface{}); ok {
					rule := struct {
						Pattern     string            `yaml:"pattern"`
						Action      string            `yaml:"action"`
						NewLevel    string            `yaml:"new_level,omitempty"`
						ExtraFields map[string]string `yaml:"extra_fields,omitempty"`
					}{}
					
					if p, ok := patternMap["pattern"].(string); ok {
						rule.Pattern = p
					}
					if a, ok := patternMap["action"].(string); ok {
						rule.Action = a
					}
					if nl, ok := patternMap["new_level"].(string); ok {
						rule.NewLevel = nl
					}
					if ef, ok := patternMap["extra_fields"].(map[string]interface{}); ok {
						rule.ExtraFields = make(map[string]string)
						for k, v := range ef {
							if vStr, ok := v.(string); ok {
								rule.ExtraFields[k] = vStr
							}
						}
					}
					
					patternRules = append(patternRules, rule)
				}
			}
			
			if len(patternRules) > 0 {
				merged.Logging.Patterns = patternRules
			}
		}
	}
	
	return merged
}

// MergeIngesterOverrides applies per-project overrides to the global ingester template
func (m *Manager) MergeIngesterOverrides(settings map[string]interface{}) IngesterConfig {
	// Start with global template
	merged := m.ingesterTemplate
	
	// Apply Ingest overrides
	if ingest, ok := settings["ingest"].(map[string]interface{}); ok {
		// retention_days is not in ingester.yaml structure based on file check
		
		if reservoirSize, ok := ingest["reservoir_size"].(float64); ok {
			merged.Ingester.ReservoirSize = int(reservoirSize)
		} else if reservoirSize, ok := ingest["reservoir_size"].(int); ok {
			merged.Ingester.ReservoirSize = reservoirSize
		}
		
		if maxBucketMinutes, ok := ingest["max_bucket_minutes"].(float64); ok {
			merged.Ingester.MaxBucketMinutes = int(maxBucketMinutes)
		} else if maxBucketMinutes, ok := ingest["max_bucket_minutes"].(int); ok {
			merged.Ingester.MaxBucketMinutes = maxBucketMinutes
		}
	}
	
	return merged
}

// SyncProjectConfig writes the merged config to a project directory
func (m *Manager) SyncProjectConfig(projectID string, settings map[string]interface{}) error {
	// 1. Sync default.yaml
	finalConfig := m.MergeOverrides(settings)
	
	output, err := yaml.Marshal(&finalConfig)
	if err != nil {
		return fmt.Errorf("failed to marshal default config: %w", err)
	}
	
	configDir := fmt.Sprintf("/home/MithrilLog-%s/configs", projectID)
	if err := os.MkdirAll(configDir, 0755); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}
	
	defaultPath := fmt.Sprintf("%s/default.yaml", configDir)
	if err := os.WriteFile(defaultPath, output, 0644); err != nil {
		return fmt.Errorf("failed to write default.yaml: %w", err)
	}
	
	// 2. Sync ingester.yaml
	finalIngesterConfig := m.MergeIngesterOverrides(settings)
	
	ingesterOutput, err := yaml.Marshal(&finalIngesterConfig)
	if err != nil {
		return fmt.Errorf("failed to marshal ingester config: %w", err)
	}
	
	ingesterPath := fmt.Sprintf("%s/ingester.yaml", configDir)
	if err := os.WriteFile(ingesterPath, ingesterOutput, 0644); err != nil {
		return fmt.Errorf("failed to write ingester.yaml: %w", err)
	}
	
	// 3. Copy prompts
	if err := m.CopyPrompts(projectID); err != nil {
		// Log error but don't fail the whole sync, as prompts might not be critical for all features
		fmt.Printf("Warning: Failed to copy prompts for project %s: %v\n", projectID, err)
	}
	
	return nil
}

// CopyPrompts copies the prompts directory to the project directory
func (m *Manager) CopyPrompts(projectID string) error {
	if m.promptsSourcePath == "" {
		return fmt.Errorf("prompts source path not set")
	}

	// Check if source exists
	if _, err := os.Stat(m.promptsSourcePath); os.IsNotExist(err) {
		return fmt.Errorf("prompts source directory does not exist: %s", m.promptsSourcePath)
	}

	projectDir := fmt.Sprintf("/home/MithrilLog-%s", projectID)
	targetDir := filepath.Join(projectDir, "prompts")

	// Create target directory
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return fmt.Errorf("failed to create target prompts directory: %w", err)
	}

	// Read source directory
	entries, err := os.ReadDir(m.promptsSourcePath)
	if err != nil {
		return fmt.Errorf("failed to read prompts source directory: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue // Skip subdirectories for now
		}

		sourcePath := filepath.Join(m.promptsSourcePath, entry.Name())
		targetPath := filepath.Join(targetDir, entry.Name())

		if err := copyFile(sourcePath, targetPath); err != nil {
			return fmt.Errorf("failed to copy %s: %w", entry.Name(), err)
		}
	}

	return nil
}

// copyFile copies a single file
func copyFile(src, dst string) error {
	sourceFile, err := os.Open(src)
	if err != nil {
		return err
	}
	defer sourceFile.Close()

	destFile, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer destFile.Close()

	_, err = io.Copy(destFile, sourceFile)
	return err
}

// GetDefaultTemplate returns the global default config
func (m *Manager) GetDefaultTemplate() DefaultConfig {
	return m.defaultTemplate
}

// GetIngesterTemplate returns the global ingester config
func (m *Manager) GetIngesterTemplate() IngesterConfig {
	return m.ingesterTemplate
}

// GenerateProjectEnv generates a .env file from project settings
func (m *Manager) GenerateProjectEnv(projectID string, settings map[string]interface{}) error {
	envContent := m.settingsToEnv(projectID, settings)
	
	envDir := fmt.Sprintf("/home/MithrilLog-%s", projectID)
	if err := os.MkdirAll(envDir, 0755); err != nil {
		return fmt.Errorf("failed to create project directory: %w", err)
	}
	
	envPath := fmt.Sprintf("%s/.env", envDir)
	// Use 0600 for security - only owner can read/write
	if err := os.WriteFile(envPath, []byte(envContent), 0600); err != nil {
		return fmt.Errorf("failed to write .env file: %w", err)
	}
	
	return nil
}

// settingsToEnv converts project settings to .env file format
func (m *Manager) settingsToEnv(projectID string, settings map[string]interface{}) string {
	var lines []string
	
	lines = append(lines, "# MithrilLog Project Environment Variables")
	lines = append(lines, fmt.Sprintf("# Generated for project: %s", projectID))
	lines = append(lines, fmt.Sprintf("# Generated at: %s", time.Now().Format(time.RFC3339)))
	lines = append(lines, "")
	
	// Project Info
	lines = append(lines, "# Project Configuration")
	lines = append(lines, fmt.Sprintf("PROJECT_ID=%s", projectID))
	
	if webTitle, ok := settings["web_title"].(string); ok {
		lines = append(lines, fmt.Sprintf("PROJECT_NAME=%s", webTitle))
	} else {
		lines = append(lines, fmt.Sprintf("PROJECT_NAME=MithrilLog %s", projectID))
	}
	lines = append(lines, "")
	
	// LLM Settings - always include, use template defaults if not overridden
	lines = append(lines, "# LLM Configuration")
	
	llm, _ := settings["llm"].(map[string]interface{})
	
	if backend, ok := llm["backend"].(string); ok && backend != "" {
		lines = append(lines, fmt.Sprintf("LLM_BACKEND=%s", backend))
	} else {
		lines = append(lines, fmt.Sprintf("LLM_BACKEND=%s", m.defaultTemplate.LLM.Backend))
	}
	
	if geminiKey, ok := llm["gemini_key"].(string); ok && geminiKey != "" {
		lines = append(lines, fmt.Sprintf("GEMINI_API_KEY=%s", geminiKey))
	} else if m.defaultTemplate.LLM.GeminiAPIKey != "" {
		lines = append(lines, fmt.Sprintf("GEMINI_API_KEY=%s", m.defaultTemplate.LLM.GeminiAPIKey))
	}
	
	if openaiKey, ok := llm["openai_key"].(string); ok && openaiKey != "" {
		lines = append(lines, fmt.Sprintf("OPENAI_API_KEY=%s", openaiKey))
	} else if m.defaultTemplate.LLM.OpenAIAPIKey != "" {
		lines = append(lines, fmt.Sprintf("OPENAI_API_KEY=%s", m.defaultTemplate.LLM.OpenAIAPIKey))
	}
	
	if model, ok := llm["model"].(string); ok && model != "" {
		lines = append(lines, fmt.Sprintf("GEMINI_MODEL=%s", model))
		lines = append(lines, fmt.Sprintf("OPENAI_MODEL=%s", model))
	} else {
		lines = append(lines, fmt.Sprintf("GEMINI_MODEL=%s", m.defaultTemplate.LLM.GeminiModel))
		lines = append(lines, fmt.Sprintf("OPENAI_MODEL=%s", m.defaultTemplate.LLM.OpenAIModel))
	}
	
	if temp, ok := llm["temperature"].(float64); ok {
		lines = append(lines, fmt.Sprintf("LLM_TEMPERATURE=%.2f", temp))
	} else {
		lines = append(lines, fmt.Sprintf("LLM_TEMPERATURE=%.2f", m.defaultTemplate.LLM.Temperature))
	}
	lines = append(lines, "")
	
	// Alert Settings
	if alert, ok := settings["alert"].(map[string]interface{}); ok {
		lines = append(lines, "# Telegram Alert Configuration")
		
		if token, ok := alert["telegram_token"].(string); ok && token != "" {
			lines = append(lines, fmt.Sprintf("TELEGRAM_BOT_TOKEN=%s", token))
		} else if m.defaultTemplate.Alert.TelegramBotToken != "" {
			lines = append(lines, fmt.Sprintf("TELEGRAM_BOT_TOKEN=%s", m.defaultTemplate.Alert.TelegramBotToken))
		}
		
		if chatID, ok := alert["telegram_chat"].(string); ok && chatID != "" {
			lines = append(lines, fmt.Sprintf("TELEGRAM_CHAT_ID=%s", chatID))
		} else if m.defaultTemplate.Alert.TelegramChatID != "" {
			lines = append(lines, fmt.Sprintf("TELEGRAM_CHAT_ID=%s", m.defaultTemplate.Alert.TelegramChatID))
		}
		
		if enabled, ok := alert["enabled"].(bool); ok {
			lines = append(lines, fmt.Sprintf("ALERT_ENABLED=%t", enabled))
		} else {
			lines = append(lines, fmt.Sprintf("ALERT_ENABLED=%t", m.defaultTemplate.Alert.Enabled))
		}
		
		if threshold, ok := alert["error_threshold"].(int); ok {
			lines = append(lines, fmt.Sprintf("ALERT_ERROR_THRESHOLD=%d", threshold))
		} else if threshold, ok := alert["error_threshold"].(float64); ok {
			lines = append(lines, fmt.Sprintf("ALERT_ERROR_THRESHOLD=%d", int(threshold)))
		} else {
			lines = append(lines, fmt.Sprintf("ALERT_ERROR_THRESHOLD=%d", m.defaultTemplate.Alert.ErrorThreshold))
		}
		lines = append(lines, "")
	}
	
	// Ingest Settings
	if ingest, ok := settings["ingest"].(map[string]interface{}); ok {
		lines = append(lines, "# Ingestion Configuration")
		
		if retentionDays, ok := ingest["retention_days"].(int); ok {
			lines = append(lines, fmt.Sprintf("RETENTION_DAYS=%d", retentionDays))
		} else if retentionDays, ok := ingest["retention_days"].(float64); ok {
			lines = append(lines, fmt.Sprintf("RETENTION_DAYS=%d", int(retentionDays)))
		} else {
			lines = append(lines, fmt.Sprintf("RETENTION_DAYS=%d", m.defaultTemplate.Ingest.RetentionDays))
		}
		
		if reservoirSize, ok := ingest["reservoir_size"].(int); ok {
			lines = append(lines, fmt.Sprintf("RESERVOIR_SIZE=%d", reservoirSize))
		} else if reservoirSize, ok := ingest["reservoir_size"].(float64); ok {
			lines = append(lines, fmt.Sprintf("RESERVOIR_SIZE=%d", int(reservoirSize)))
		} else {
			lines = append(lines, fmt.Sprintf("RESERVOIR_SIZE=%d", m.defaultTemplate.Ingest.ReservoirSize))
		}
		
		if maxBucketMinutes, ok := ingest["max_bucket_minutes"].(int); ok {
			lines = append(lines, fmt.Sprintf("MAX_BUCKET_MINUTES=%d", maxBucketMinutes))
		} else if maxBucketMinutes, ok := ingest["max_bucket_minutes"].(float64); ok {
			lines = append(lines, fmt.Sprintf("MAX_BUCKET_MINUTES=%d", int(maxBucketMinutes)))
		} else {
			lines = append(lines, fmt.Sprintf("MAX_BUCKET_MINUTES=%d", m.defaultTemplate.Ingest.MaxBucketMinutes))
		}
		lines = append(lines, "")
	}
	
	// Default values from template
	lines = append(lines, "# Default Values from Template")
	lines = append(lines, fmt.Sprintf("UDP_PORT=%d", m.defaultTemplate.Ingest.UDPPort))
	lines = append(lines, fmt.Sprintf("TCP_PORT=%d", m.defaultTemplate.Ingest.TCPPort))
	lines = append(lines, fmt.Sprintf("TZ=%s", m.defaultTemplate.Timezone))
	lines = append(lines, fmt.Sprintf("ENVIRONMENT=%s", m.defaultTemplate.Environment))
	lines = append(lines, "")
	
	return strings.Join(lines, "\n")
}
