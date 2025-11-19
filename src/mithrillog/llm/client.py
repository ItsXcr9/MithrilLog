from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

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
        self._backend = "llama_cpp" if config.backend == "local" else config.backend
        self._llama = None
        self._openai_client = None
        self._gemini_model = None

        if self._backend == "llama_cpp":
            self._llama = self._load_llama()
        elif self._backend == "openai":
            self._openai_client = self._load_openai()
        elif self._backend == "gemini":
            self._gemini_model = self._load_gemini()
        else:
            logger.warning("Unknown LLM backend %s; falling back to deterministic summaries", self._backend)

    def _load_llama(self):
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

    def _load_openai(self):
        if not self.config.openai_api_key:
            logger.warning("OpenAI backend selected but openai_api_key is not configured")
            return None
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            logger.warning("openai SDK not installed; run `pip install openai` to enable ChatGPT backend")
            return None
        client_kwargs: Dict[str, Any] = {"api_key": self.config.openai_api_key}
        if self.config.openai_base_url:
            client_kwargs["base_url"] = self.config.openai_base_url
        logger.info("Initialized OpenAI client targeting model %s", self.config.openai_model)
        return OpenAI(**client_kwargs)

    def _load_gemini(self):
        if not self.config.gemini_api_key:
            logger.warning("Gemini backend selected but gemini_api_key is not configured")
            return None
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            logger.warning(
                "google-generativeai SDK not installed; run `pip install google-generativeai` to enable Gemini backend",
            )
            return None
        genai.configure(api_key=self.config.gemini_api_key)
        logger.info("Initialized Gemini client targeting model %s", self.config.gemini_model)
        return genai.GenerativeModel(self.config.gemini_model)

    def generate(self, template: PromptTemplate, variables: Dict[str, Any]) -> str:
        rendered = template.render(variables)
        system_prompt = rendered["system"]
        user_prompt = rendered["user"]
        # Conservative estimate: ~4 chars per token, leave room for system prompt and response
        # Reserve ~200 tokens for system + response, so max input tokens = context_length - 200 - max_tokens
        max_input_tokens = self.config.context_length - 200 - self.config.max_tokens
        max_chars = max_input_tokens * 3  # Conservative: 3 chars per token
        if len(user_prompt) > max_chars:
            user_prompt = (
                user_prompt[: max_chars - 50]
                + "\n... [truncated] ..."
            )
        if len(system_prompt) > 200:
            system_prompt = system_prompt[:200] + "..."
        try:
            if self._backend == "llama_cpp" and self._llama is not None:
                return self._generate_llama(system_prompt, user_prompt)
            if self._backend == "openai" and self._openai_client is not None:
                return self._generate_openai(system_prompt, user_prompt)
            if self._backend == "gemini" and self._gemini_model is not None:
                return self._generate_gemini(system_prompt, user_prompt)
        except Exception:
            logger.exception("LLM invocation failed; falling back to deterministic summary")
        return self._fallback_summary(variables)

    def _generate_llama(self, system_prompt: str, user_prompt: str) -> str:
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

    def _generate_openai(self, system_prompt: str, user_prompt: str) -> str:
        response = self._openai_client.chat.completions.create(  # type: ignore[union-attr]
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = content or ""
        return text.strip()

    def _generate_gemini(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        generation_config = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_output_tokens": self.config.max_tokens,
        }
        try:
            response = self._gemini_model.generate_content(  # type: ignore[union-attr]
                prompt,
                generation_config=generation_config,
            )
        except Exception as exc:  # pragma: no cover - third-party errors
            resource_exhausted = False
            try:
                from google.api_core.exceptions import ResourceExhausted  # type: ignore
            except Exception:  # pragma: no cover - optional dep
                ResourceExhausted = None  # type: ignore
            if ResourceExhausted and isinstance(exc, ResourceExhausted):
                retry = getattr(exc, "retry_delay", None)
                delay = getattr(retry, "seconds", None) if retry else None
                logger.warning(
                    "Gemini quota exceeded (retry in ~%ss); falling back to deterministic summary",
                    delay or "?",
                )
                return ""
            raise
        text = None
        try:
            text = getattr(response, "text", None)
        except ValueError:
            logger.info("Gemini response missing direct text; inspecting candidates")
        if text:
            return text.strip()
        candidates = getattr(response, "candidates", None)
        if candidates:
            for candidate in candidates:
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason and int(getattr(finish_reason, "value", finish_reason)) == 2:
                    logger.warning("Gemini generation blocked (finish_reason=SAFETY). Falling back.")
                    continue
                parts = getattr(candidate, "content", None)
                if parts and getattr(parts, "parts", None):
                    joined = "".join(getattr(part, "text", "") for part in parts.parts)
                    if joined:
                        return joined.strip()
        return ""

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

