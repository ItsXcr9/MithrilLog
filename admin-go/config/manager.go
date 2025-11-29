package config

import (
	"fmt"
	"os"

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
	defaultTemplate      DefaultConfig
	ingesterTemplate     IngesterConfig
}

// NewManager creates a new config manager
func NewManager(defaultPath, ingesterPath string) *Manager {
	mgr := &Manager{
		defaultTemplatePath:  defaultPath,
		ingesterTemplatePath: ingesterPath,
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
		if model, ok := llm["model"].(string); ok {
			if merged.LLM.Backend == "gemini" {
				merged.LLM.GeminiModel = model
			} else if merged.LLM.Backend == "openai" {
				merged.LLM.OpenAIModel = model
			}
		}
		if temp, ok := llm["temperature"].(float64); ok {
			merged.LLM.Temperature = temp
		}
		if geminiKey, ok := llm["gemini_key"].(string); ok {
			merged.LLM.GeminiAPIKey = geminiKey
		}
		if openaiKey, ok := llm["openai_key"].(string); ok {
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
	}
	
	// Apply Web title
	if webTitle, ok := settings["web_title"].(string); ok {
		merged.Web.Title = webTitle
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
	
	return nil
}

// GetDefaultTemplate returns the global default config
func (m *Manager) GetDefaultTemplate() DefaultConfig {
	return m.defaultTemplate
}

// GetIngesterTemplate returns the global ingester config
func (m *Manager) GetIngesterTemplate() IngesterConfig {
	return m.ingesterTemplate
}
