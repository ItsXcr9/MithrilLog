from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import yaml
from pydantic import BaseModel, Field


_LOADED_ENV_PATHS: set[Path] = set()


def _load_env_file(path: Path) -> None:
    try:
        resolved = path.expanduser().resolve()
    except FileNotFoundError:
        return
    if resolved in _LOADED_ENV_PATHS or not resolved.is_file():
        return
    with resolved.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
    _LOADED_ENV_PATHS.add(resolved)


def _ensure_env_loaded(extra_candidates: Iterable[Path] | None = None) -> None:
    candidates: list[Path] = []
    env_override = os.getenv("MITHRILLOG_ENV_FILE")
    if env_override:
        candidates.append(Path(env_override))
    project_root = Path(__file__).resolve().parent.parent.parent
    candidates.append(project_root / ".env")
    candidates.append(Path.cwd() / ".env")
    if extra_candidates:
        candidates.extend(extra_candidates)
    for candidate in candidates:
        _load_env_file(candidate)


def _apply_llm_env_overrides(llm_config: "LLMConfig") -> None:
    env_overrides = {
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "OPENAI_BASE_URL": "openai_base_url",
        "GEMINI_API_KEY": "gemini_api_key",
        "GEMINI_MODEL": "gemini_model",
    }
    for env_name, attr in env_overrides.items():
        value = os.getenv(env_name)
        if not value:
            continue
        if attr in {"gemini_model", "openai_model"} and not value.strip():
            continue
        setattr(llm_config, attr, value)


class LLMConfig(BaseModel):
    backend: Literal["llama_cpp", "local", "openai", "gemini"] = "llama_cpp"
    model_path: Optional[Path] = Field(
        default=None,
        description="Path to GGUF file for llama-cpp backend.",
    )
    context_length: int = 4096
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024
    openai_api_key: Optional[str] = Field(
        default=None,
        description="API key for OpenAI/ChatGPT requests.",
    )
    openai_model: str = "gpt-4o-mini"
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Optional custom base URL for OpenAI-compatible endpoints.",
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="API key for Google Gemini requests.",
    )
    gemini_model: str = "gemini-1.5-flash"


class IngestConfig(BaseModel):
    host: str = "0.0.0.0"
    udp_port: int = 5514
    tcp_port: int = 5614
    bucket_dir: Path = Path("data/buckets")
    max_bucket_minutes: int = 1
    bloom_error_rate: float = 1e-4
    reservoir_size: int = 200
    retention_days: int = 30
    forward_to_host: Optional[str] = None
    forward_to_port: Optional[int] = None


class SummaryConfig(BaseModel):
    hourly_at_minute: int = 5
    daily_at_hour: int = 0
    daily_at_minute: int = 10
    report_dir: Path = Path("data/reports")
    analysis_levels: list[str] = Field(
        default=["ERROR", "CRITICAL"],
        description="Log severity levels to analyze with AI. Supported: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )


class StorageConfig(BaseModel):
    sqlite_path: Path = Path("data/mithrillog.db")


class PromptsConfig(BaseModel):
    hourly: Path = Path("prompts/hourly_summary.txt")
    daily: Path = Path("prompts/daily_summary.txt")
    anomaly: Path = Path("prompts/anomaly_report.txt")
    highlight_analysis: Path = Path("prompts/highlight_analysis.txt")
    trend: Path = Path("prompts/trend_analysis.txt")


class WebConfig(BaseModel):
    title: str = "Observability Console MITHRILLOG"


class AlertConfig(BaseModel):
    enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    error_threshold: int = 10


class CorsConfig(BaseModel):
    allowed_origins: list[str] = ["*"]


class LoggingPatternConfig(BaseModel):
    pattern: str
    action: Literal["SUPPRESS", "ALLOW", "RECLASSIFY"]
    new_level: Optional[str] = None
    extra_fields: dict[str, Any] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    patterns: list[LoggingPatternConfig] = Field(default_factory=list)


class RemoteLoggingConfig(BaseModel):
    enabled: bool = False
    host: Optional[str] = None
    port: int = 5514
    protocol: Literal["udp", "tcp"] = "udp"


class Settings(BaseModel):
    environment: Literal["dev", "prod"] = "dev"
    llm: LLMConfig = LLMConfig()
    ingest: IngestConfig = IngestConfig()
    summary: SummaryConfig = SummaryConfig()
    storage: StorageConfig = StorageConfig()
    prompts: PromptsConfig = PromptsConfig()
    web: WebConfig = WebConfig()
    alert: AlertConfig = AlertConfig()
    cors: CorsConfig = CorsConfig()
    logging: LoggingConfig = LoggingConfig()
    remote_logging: RemoteLoggingConfig = RemoteLoggingConfig()
    timezone: str = "UTC"

    @classmethod
    def load(cls, path: Path | str) -> "Settings":
        config_path = Path(path).expanduser().resolve()
        extra_env_files = [
            config_path.parent / ".env",
            config_path.parent.parent / ".env" if config_path.parent.parent != config_path.parent else None,
        ]
        _ensure_env_loaded(path for path in extra_env_files if path is not None)
        with config_path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle) or {}
        settings = cls.model_validate(data)
        _apply_llm_env_overrides(settings.llm)
        return settings


_ensure_env_loaded(None)

# Load default settings from config file if it exists
try:
    from pathlib import Path
    default_config_path = Path(__file__).parent.parent.parent / "configs" / "default.yaml"
    if default_config_path.exists():
        default_settings = Settings.load(default_config_path)
    else:
        default_settings = Settings()
        _apply_llm_env_overrides(default_settings.llm)
except Exception:
    default_settings = Settings()
    _apply_llm_env_overrides(default_settings.llm)

