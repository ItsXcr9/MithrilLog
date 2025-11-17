from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    backend: Literal["llama_cpp", "openai"] = "llama_cpp"
    model_path: Optional[Path] = Field(
        default=None,
        description="Path to GGUF file for llama-cpp backend.",
    )
    context_length: int = 4096
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024


class IngestConfig(BaseModel):
    host: str = "0.0.0.0"
    udp_port: int = 5514
    tcp_port: int = 5614
    bucket_dir: Path = Path("data/buckets")
    max_bucket_minutes: int = 1
    bloom_error_rate: float = 1e-4
    reservoir_size: int = 200


class SummaryConfig(BaseModel):
    hourly_at_minute: int = 5
    daily_at_hour: int = 0
    daily_at_minute: int = 10
    report_dir: Path = Path("data/reports")


class StorageConfig(BaseModel):
    sqlite_path: Path = Path("data/mithrillog.db")


class PromptsConfig(BaseModel):
    hourly: Path = Path("prompts/hourly_summary.txt")
    daily: Path = Path("prompts/daily_summary.txt")
    anomaly: Path = Path("prompts/anomaly_report.txt")


class Settings(BaseModel):
    environment: Literal["dev", "prod"] = "dev"
    llm: LLMConfig = LLMConfig()
    ingest: IngestConfig = IngestConfig()
    summary: SummaryConfig = SummaryConfig()
    storage: StorageConfig = StorageConfig()
    prompts: PromptsConfig = PromptsConfig()

    @classmethod
    def load(cls, path: Path | str) -> "Settings":
        config_path = Path(path).expanduser().resolve()
        with config_path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle) or {}
        return cls.model_validate(data)


default_settings = Settings()

