"""
Telegram Bot Alert Dispatcher.
Sends instant notifications on state changes with anti-spam rate limiting and batching.
"""

import logging
import os
import time
from typing import Dict, List, Optional
import requests

from src.alerts.formatter import format_single_alert, format_batch_alert
from src.engine.smma import LarssonState

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        batch_threshold: int = 5,
    ):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.batch_threshold = batch_threshold
        self.session = requests.Session()

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_raw_message(self, text: str) -> bool:
        """Sends an HTML formatted message via Telegram Bot API."""
        if not self.is_configured:
            logger.info(f"[DRY-RUN] Telegram not configured. Message would be:\n{text}")
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = self.session.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def dispatch_alerts(self, alerts: List[dict]):
        """
        Dispatches a list of detected state change events.
        If the number of changes exceeds batch_threshold, combines them into a digest.
        """
        if not alerts:
            return

        if len(alerts) <= self.batch_threshold:
            for item in alerts:
                msg = format_single_alert(
                    ticker=item["ticker"],
                    timeframe=item["timeframe"],
                    old_state=item["old_state"],
                    new_state=item["new_state"],
                    price=item["price"],
                    tv_symbol=item["tv_symbol"],
                )
                self.send_raw_message(msg)
                time.sleep(0.05)  # Small breather between messages
        else:
            batch_msg = format_batch_alert(alerts)
            self.send_raw_message(batch_msg)
