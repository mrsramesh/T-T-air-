"""
Free Real-Time Alerting Engine (Telegram Bot & Generic Webhooks).
Provides 100% free notifications for:
- Carrier portal breaking changes / circuit breaker trips.
- AutoPilot cycle summary (newly delivered shipments count).
- Critical system errors.
"""

import os
import json
import logging
import urllib.request
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger("notifier")


class NotificationManager:
    """Dispatches free alerts via Telegram Bot or Discord/Slack/HTTP Webhooks."""

    def __init__(self):
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.webhook_url = os.environ.get("WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL")

    def send_alert_async(self, title: str, message: str, level: str = "warning"):
        """Dispatches an alert in a non-blocking background thread."""
        t = threading.Thread(
            target=self._send_alert_worker,
            args=(title, message, level),
            daemon=True,
            name="Notifier-Worker",
        )
        t.start()

    def _send_alert_worker(self, title: str, message: str, level: str):
        # 1. Telegram Bot (100% Free)
        if self.telegram_bot_token and self.telegram_chat_id:
            emoji = "🚨" if level == "error" else ("⚠️" if level == "warning" else "✅")
            tg_text = f"{emoji} *{title}*\n\n{message}"
            tg_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": tg_text,
                "parse_mode": "Markdown",
            }
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    tg_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"[Notifier] Telegram alert dispatched: {title}")
            except Exception as e:
                logger.warning(f"[Notifier] Failed to send Telegram alert: {e}")

        # 2. Webhook (Discord / Slack / Generic)
        if self.webhook_url:
            try:
                wb_payload = {
                    "text": f"*{title}*\n{message}",
                    "content": f"**{title}**\n{message}",
                }
                data = json.dumps(wb_payload).encode("utf-8")
                req = urllib.request.Request(
                    self.webhook_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.info(f"[Notifier] Webhook alert dispatched: {title}")
            except Exception as e:
                logger.warning(f"[Notifier] Failed to send webhook alert: {e}")


# Singleton instance
notifier = NotificationManager()
