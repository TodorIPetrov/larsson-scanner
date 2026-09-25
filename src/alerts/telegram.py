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
        self.chat_id = str(chat_id) if chat_id else os.environ.get("TELEGRAM_CHAT_ID")
        self.batch_threshold = batch_threshold
        self.session = requests.Session()

        if (not self.bot_token or not self.chat_id) and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                import yaml
                for p in ["config/settings.local.yaml", "config/settings.yaml"]:
                    if os.path.exists(p):
                        with open(p, "r", encoding="utf-8") as f:
                            cfg = yaml.safe_load(f) or {}
                            tg = cfg.get("telegram", {})
                            if not self.bot_token and tg.get("bot_token"):
                                self.bot_token = str(tg.get("bot_token"))
                            if not self.chat_id and tg.get("chat_id"):
                                self.chat_id = str(tg.get("chat_id"))
            except Exception as e:
                logger.debug(f"Could not load telegram settings from yaml: {e}")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message_with_markup(self, text: str, reply_markup: Optional[dict] = None) -> Optional[int]:
        """Sends an HTML formatted message and returns the Telegram message_id."""
        if not self.is_configured:
            logger.info(f"[DRY-RUN] Telegram not configured. Message would be:\n{text}\nMarkup: {reply_markup}")
            return 1  # Dummy message_id for dry-run

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            resp = self.session.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", {}).get("message_id")
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return None

    def send_raw_message(self, text: str, reply_markup: Optional[dict] = None) -> bool:
        """Sends an HTML formatted message via Telegram Bot API."""
        msg_id = self.send_message_with_markup(text, reply_markup=reply_markup)
        if not self.is_configured:
            return True
        return msg_id is not None

    def edit_message_text(
        self,
        message_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Edits an existing Telegram message text and updates/removes reply markup."""
        if not self.is_configured:
            logger.info(f"[DRY-RUN] edit_message_text id={message_id}:\n{text}")
            return True

        target_chat = chat_id or self.chat_id
        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload = {
            "chat_id": target_chat,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            resp = self.session.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram editMessageText error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to edit Telegram message: {e}")
            return False

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledges a Telegram callback query to dismiss loading state."""
        if not self.is_configured:
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text

        try:
            resp = self.session.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")
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
                    sr_data=item.get("sr_data"),
                    asset_class=item.get("asset_class", "crypto"),
                )
                self.send_raw_message(msg)

                time.sleep(0.05)  # Small breather between messages
        else:
            batch_msg = format_batch_alert(alerts)
            self.send_raw_message(batch_msg)

    def send_test_alert(self) -> bool:
        """Sends a mock alert to verify Telegram integration."""
        if not self.is_configured:
            return False

        test_item = {
            "ticker": "BTCUSDT",
            "timeframe": "1D",
            "old_state": LarssonState.NEUTRAL,
            "new_state": LarssonState.GOLD,
            "price": 77102.50,
            "tv_symbol": "BINANCE:BTCUSDT",
        }
        self.dispatch_alerts([test_item])
        return True

