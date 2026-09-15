"""
Interactive Telegram Bot Command Listener.
Listens for incoming commands (/status, /gold, /blue, /help) via long-polling (getUpdates)
and replies with instant market summaries and asset lists.
Requires no open ports, webhooks, or public IP.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Optional
import requests

from src.alerts.formatter import get_tradingview_link
from src.alerts.telegram import TelegramNotifier
from src.storage.database import Database

logger = logging.getLogger(__name__)


class TelegramCommandListener:
    def __init__(
        self,
        notifier: Optional[TelegramNotifier] = None,
        db: Optional[Database] = None,
    ):
        self.notifier = notifier or TelegramNotifier()
        self.db = db or Database()
        self.last_update_id = 0
        self.session = requests.Session()
        self.running = False

    def handle_status(self) -> str:
        """Generates overview summary message."""
        states = self.db.get_all_states()
        if not states:
            return "📊 Няма записани активи в базата данни."

        total = len(states)
        gold = [s for s in states if s["current_state"] == "GOLD"]
        blue = [s for s in states if s["current_state"] == "BLUE"]
        neutral = [s for s in states if s["current_state"] == "NEUTRAL"]

        gold_pct = round(len(gold) / total * 100, 1)
        blue_pct = round(len(blue) / total * 100, 1)
        neutral_pct = round(len(neutral) / total * 100, 1)

        msg = (
            f"📊 <b>Larsson Line Пазарен Баланс</b>\n\n"
            f"• Общо наблюдавани: <b>{total}</b>\n"
            f"• 🟡 <b>Gold (Бичи):</b> {len(gold)} ({gold_pct}%)\n"
            f"• 🔵 <b>Blue (Мечи):</b> {len(blue)} ({blue_pct}%)\n"
            f"• ⚪ <b>Neutral:</b> {len(neutral)} ({neutral_pct}%)\n\n"
            f"<i>За списък на активните инструменти: /gold или /blue</i>"
        )
        return msg

    def handle_state_list(self, target_state: str, emoji: str) -> str:
        """Generates list of symbols in a given state."""
        states = self.db.get_all_states()
        matches = [s for s in states if s["current_state"] == target_state]

        if not matches:
            return f"{emoji} В момента няма активи в състояние <b>{target_state}</b>."

        header = f"{emoji} <b>Активи в състояние {target_state} ({len(matches)}):</b>\n\n"
        lines = []
        # Group or list top 25
        for s in matches[:25]:
            ticker = s["ticker"]
            tf = s["timeframe"]
            price = s["last_price"]
            tv_sym = s["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)

            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): <code>{p_str}</code>")

        body = "\n".join(lines)
        if len(matches) > 25:
            body += f"\n\n<i>... и още {len(matches) - 25} инструмента. Виж всички в уеб дашборда: http://localhost:8080</i>"

        return header + body

    def handle_watch(self, ticker: str) -> str:
        """Adds symbol to watchlist."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/watch NVDA</code> или <code>/watch BTCUSDT</code>"
        ticker = ticker.upper()
        added = self.db.add_to_watchlist(ticker)
        if added:
            return f"✅ Добавен <b>{ticker}</b> към твоя личен Watchlist!"
        else:
            return f"ℹ️ <b>{ticker}</b> вече е в твоя Watchlist."

    def handle_unwatch(self, ticker: str) -> str:
        """Removes symbol from watchlist."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/unwatch NVDA</code>"
        ticker = ticker.upper()
        removed = self.db.remove_from_watchlist(ticker)
        if removed:
            return f"🗑️ Премахнат <b>{ticker}</b> от твоя Watchlist."
        else:
            return f"ℹ️ <b>{ticker}</b> не беше намерен в твоя Watchlist."

    def handle_watchlist(self) -> str:
        """Displays all symbols in personal watchlist."""
        rows = self.db.get_watchlist_states()
        tickers = self.db.get_watchlist()
        if not tickers:
            return "📋 Твоят Watchlist е празен. Добави символ с: <code>/watch AAPL</code>"

        header = f"⭐ <b>Твоят Watchlist ({len(tickers)} актива):</b>\n\n"
        if not rows:
            return header + f"Активи: {', '.join(tickers)}\n<i>(Ще се обновят при следващото сканиране)</i>"

        lines = []
        for s in rows:
            ticker = s["ticker"]
            tf = s["timeframe"]
            state = s["current_state"]
            price = s["last_price"]
            tv_sym = s["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)

            emoji = "🟡" if state == "GOLD" else ("🔵" if state == "BLUE" else "⚪")
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): {emoji} <b>{state}</b> @ <code>{p_str}</code>")

        return header + "\n".join(lines)

    def handle_help(self) -> str:
        return (
            "🤖 <b>Larsson Line Бот Команди:</b>\n\n"
            "/status - Общ пазарен баланс и брой активи по цвят\n"
            "/gold - Списък на всички бичи активи (Gold 🟡)\n"
            "/blue - Списък на всички мечи активи (Blue 🔵)\n"
            "/watchlist - Показва активите в твоя личен списък ⭐\n"
            "/watch [символ] - Добавя актив в Watchlist (напр. /watch NVDA)\n"
            "/unwatch [символ] - Премахва актив от Watchlist\n"
            "/help - Показва това съобщение"
        )

    def process_update(self, update: dict):
        """Processes a single incoming message from Telegram."""
        message = update.get("message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        # Only allow authorized user to interact
        if chat_id != str(self.notifier.chat_id):
            logger.warning(f"Ignored message from unauthorized chat_id: {chat_id}")
            return

        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"Received Telegram command: {text}")
        parts = text.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/status":
            reply = self.handle_status()
        elif cmd == "/gold":
            reply = self.handle_state_list("GOLD", "🟡")
        elif cmd == "/blue":
            reply = self.handle_state_list("BLUE", "🔵")
        elif cmd == "/watchlist":
            reply = self.handle_watchlist()
        elif cmd == "/watch":
            reply = self.handle_watch(arg)
        elif cmd == "/unwatch":
            reply = self.handle_unwatch(arg)
        elif cmd in ["/start", "/help"]:
            reply = self.handle_help()
        else:
            reply = "Непозната команда. Напиши /help за списък с наличните команди."

        self.notifier.send_raw_message(reply)

    def run_poll_loop(self):
        """Continuously polls for Telegram updates."""
        if not self.notifier.is_configured:
            logger.warning("Telegram not configured. Command listener stopped.")
            return

        self.running = True
        logger.info("Telegram Command Listener polling loop started.")
        url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getUpdates"

        while self.running:
            try:
                params = {"timeout": 20, "offset": self.last_update_id + 1}
                resp = self.session.get(url, params=params, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        self.process_update(update)
                else:
                    logger.warning(f"Telegram polling error {resp.status_code}: {resp.text}")
                    time.sleep(2)
            except requests.exceptions.Timeout:
                # Normal timeout from long-polling
                continue
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(3)
