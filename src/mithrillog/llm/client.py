from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import LLMConfig

logger = logging.getLogger("mithrillog.llm")


@dataclass
class PromptTemplate:
    name: str
    system: str
    user: str

    def render(self, variables: Dict[str, Any]) -> Dict[str, str]:
        return {
            "system": self.system.format(**variables),
            "user": self.user.format(**variables),
        }


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._llama = self._load_llama()

    def _load_llama(self):
        if self.config.backend != "llama_cpp":
            return None
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError:
            logger.warning("llama_cpp not installed; falling back to deterministic summaries")
            return None
        if not self.config.model_path:
            logger.warning("No model_path configured; falling back to deterministic summaries")
            return None
        model_path = Path(self.config.model_path)
        if not model_path.exists():
            logger.warning("Model path %s not found; falling back to deterministic summaries", model_path)
            return None
        llama = Llama(
            model_path=str(model_path),
            n_ctx=self.config.context_length,
            n_threads=4,
            seed=42,
        )
        logger.info("Loaded local model %s", model_path.name)
        return llama

    def generate(self, template: PromptTemplate, variables: Dict[str, Any]) -> str:
        rendered = template.render(variables)
        system_prompt = rendered["system"]
        user_prompt = rendered["user"]
        if self._llama is None:
            return self._fallback_summary(variables)
        response = self._llama.create_chat_completion(  # type: ignore[union-attr]
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
        )
        return response["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _fallback_summary(variables: Dict[str, Any]) -> str:
        stats = variables.get("stats", {})
        highlights = variables.get("highlights", [])
        lines = [
            "Local model unavailable, generated deterministic summary.",
            f"Total events: {stats.get('total_events', 'n/a')}",
        ]
        for severity, count in stats.get("by_severity", {}).items():
            lines.append(f"{severity}: {count}")
        if highlights:
            lines.append("Key samples:")
            for item in highlights[:5]:
                host = item.get("host", "unknown")
                app = item.get("app", "-")
                msg = item.get("message", "")
                lines.append(f"- {host}/{app}: {msg[:120]}")
        return "\n".join(lines)

