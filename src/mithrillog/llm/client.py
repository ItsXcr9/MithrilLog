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
        context_limit = max(self.config.context_length, 1024)
        reserved_tokens = 200  # system prompt + safety margin
        min_prompt_tokens = 512
        raw_max_tokens = max(1, self.config.max_tokens)
        max_completion_cap = max(256, context_limit - reserved_tokens - min_prompt_tokens)
        effective_max_tokens = min(raw_max_tokens, max_completion_cap)
        if effective_max_tokens < raw_max_tokens:
            logger.debug(
                "Clamped max_tokens from %s to %s to fit context window (%s tokens)",
                raw_max_tokens,
                effective_max_tokens,
                context_limit,
            )
        prompt_budget = max(min_prompt_tokens, context_limit - reserved_tokens - effective_max_tokens)
        max_chars = prompt_budget * 3  # Conservative: 3 chars per token
        if len(user_prompt) > max_chars:
            user_prompt = (
                user_prompt[: max_chars - 50]
                + "\n... [truncated] ..."
            )
        if len(system_prompt) > 200:
            system_prompt = system_prompt[:200] + "..."
        try:
            if self._backend == "llama_cpp" and self._llama is not None:
                return self._generate_llama(system_prompt, user_prompt, effective_max_tokens)
            if self._backend == "openai" and self._openai_client is not None:
                return self._generate_openai(system_prompt, user_prompt, effective_max_tokens)
            if self._backend == "gemini" and self._gemini_model is not None:
                return self._generate_gemini(system_prompt, user_prompt, effective_max_tokens)
        except Exception:
            logger.exception("LLM invocation failed; falling back to deterministic summary")
        return self._fallback_summary(variables)

    def _generate_llama(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self._llama.create_chat_completion(  # type: ignore[union-attr]
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=max_tokens,
        )
        return response["choices"][0]["message"]["content"].strip()

    def _generate_openai(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        request_kwargs: Dict[str, Any] = {
            "model": self.config.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        # gpt-5 class models renamed `max_tokens` to `max_completion_tokens`.
        # Call once with the legacy name, then retry with the new name if needed.
        request_kwargs["max_tokens"] = max_tokens
        response = self._call_openai_with_token_retry(request_kwargs, max_tokens)
        return self._extract_openai_text(response)

    def _call_openai_with_token_retry(self, request_kwargs: Dict[str, Any], max_tokens: int) -> Any:
        bad_request_error = None
        try:
            from openai import BadRequestError as _BadRequestError  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            _BadRequestError = None  # type: ignore
        if _BadRequestError:
            bad_request_error = _BadRequestError
        while True:
            try:
                return self._openai_client.chat.completions.create(  # type: ignore[union-attr]
                    **request_kwargs,
                )
            except Exception as exc:
                if not (bad_request_error and isinstance(exc, bad_request_error)):
                    raise
                message = str(getattr(exc, "message", exc))
                handled = False
                if "max_tokens" in message and "max_completion_tokens" in message and "max_tokens" in request_kwargs:
                    request_kwargs.pop("max_tokens", None)
                    request_kwargs["max_completion_tokens"] = max_tokens
                    handled = True
                elif "temperature" in message and "support" in message and "temperature" in request_kwargs:
                    request_kwargs.pop("temperature", None)
                    handled = True
                elif "top_p" in message and "support" in message and "top_p" in request_kwargs:
                    request_kwargs.pop("top_p", None)
                    handled = True
                if not handled:
                    raise

    def _extract_openai_text(self, response: Any) -> str:
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = content or ""
        return text.strip()

    def _generate_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        generation_config = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_output_tokens": max_tokens,
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

