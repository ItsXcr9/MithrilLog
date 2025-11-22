from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from .config import AlertConfig

logger = logging.getLogger("mithrillog.alerting")


class AlertProvider(ABC):
    @abstractmethod
    async def send_alert(self, title: str, message: str) -> bool:
        """Send an alert. Returns True if successful."""
        pass


class TelegramProvider(AlertProvider):
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send_alert(self, title: str, message: str) -> bool:
        full_message = f"🚨 *{title}*\n\n{message}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json={
                        "chat_id": self.chat_id,
                        "text": full_message,
                        "parse_mode": "Markdown",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to send Telegram alert")
            return False


class AlertManager:
    def __init__(self, config: AlertConfig, web_title: str = "MithrilLog") -> None:
        self.config = config
        self.web_title = web_title
        self.providers: list[AlertProvider] = []
        
        if self.config.enabled:
            if self.config.telegram_bot_token and self.config.telegram_chat_id:
                self.providers.append(
                    TelegramProvider(
                        self.config.telegram_bot_token, 
                        self.config.telegram_chat_id
                    )
                )
                logger.info("Telegram alerting enabled")
            else:
                logger.warning("Alerting enabled but Telegram credentials missing")

    async def send_alert(self, title: str, message: str) -> None:
        """Send alert to all configured providers."""
        if not self.providers:
            return
            
        results = await asyncio.gather(
            *[p.send_alert(title, message) for p in self.providers],
            return_exceptions=True
        )
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Alert provider failed: {result}")

    async def check_and_alert(self, stats: dict, anomalies: str) -> None:
        """Check stats against thresholds and alert if necessary."""
        if not self.config.enabled:
            return

        alerts = []
        
        # Check error threshold
        total_errors = stats.get("total_errors", 0)
        if total_errors >= self.config.error_threshold:
            alerts.append(
                f"High Error Count: {total_errors} (Threshold: {self.config.error_threshold})"
            )

        # Check anomalies (simple heuristic: if LLM found something significant)
        if anomalies and "No anomalies detected" not in anomalies and "No notable anomalies" not in anomalies:
            # Truncate anomaly text for alert
            summary = anomalies.split("\n")[0][:100]
            alerts.append(f"Anomaly Detected: {summary}")

        if alerts:
            await self.send_alert(
                f"{self.web_title} Alert",
                "\n".join(alerts)
            )
