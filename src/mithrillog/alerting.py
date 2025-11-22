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

        should_alert = False
        alert_parts = []
        
        # Build detailed statistics
        total_events = stats.get("total_events", 0)
        total_errors = stats.get("total_errors", 0)
        
        # Check error threshold
        if total_errors >= self.config.error_threshold:
            should_alert = True
            alert_parts.append(f"⚠️ *High Error Count*: {total_errors} errors")
        
        # Check anomalies (simple heuristic: if LLM found something significant)
        has_anomaly = anomalies and "No anomalies detected" not in anomalies and "No notable anomalies" not in anomalies
        if has_anomaly:
            should_alert = True
            # Extract first meaningful line from anomaly report
            anomaly_lines = [line.strip() for line in anomalies.split("\n") if line.strip()]
            anomaly_summary = anomaly_lines[0] if anomaly_lines else "Anomaly detected"
            # Limit to 150 chars for readability
            if len(anomaly_summary) > 150:
                anomaly_summary = anomaly_summary[:147] + "..."
            alert_parts.append(f"🔍 *Anomaly*: {anomaly_summary}")
        
        if not should_alert:
            return
        
        # Add statistics section
        stats_lines = [f"📊 *Statistics*:"]
        stats_lines.append(f"• Total Events: {total_events:,}")
        
        # Severity breakdown
        by_severity = stats.get("by_severity", {})
        if by_severity:
            error_severities = {k: v for k, v in by_severity.items() if k in {"emerg", "alert", "crit", "err"}}
            if error_severities:
                severity_str = ", ".join([f"{sev}: {count}" for sev, count in sorted(error_severities.items())])
                stats_lines.append(f"• Errors: {severity_str}")
        
        # Top hosts
        by_host = stats.get("by_host", {})
        if by_host:
            top_hosts = sorted(by_host.items(), key=lambda x: x[1], reverse=True)[:3]
            hosts_str = ", ".join([f"{host} ({count})" for host, count in top_hosts])
            stats_lines.append(f"• Top Hosts: {hosts_str}")
        
        alert_parts.append("\n".join(stats_lines))
        
        # Send the alert
        await self.send_alert(
            f"{self.web_title} Alert",
            "\n\n".join(alert_parts)
        )
