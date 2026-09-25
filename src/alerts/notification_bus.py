"""
Unified Notification Bus for Larsson Scanner (Task 14).

Broadcasts market alerts, state flips, and trade proposals across all
configured alert channels (Telegram, Discord, etc.).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.alerts.telegram import TelegramNotifier
from src.alerts.discord_bot import DiscordNotifier

logger = logging.getLogger(__name__)


class NotificationBus:
    """Multi-channel notification dispatcher."""

    def __init__(
        self,
        telegram: Optional[TelegramNotifier] = None,
        discord: Optional[DiscordNotifier] = None,
    ):
        self.telegram = telegram or TelegramNotifier()
        self.discord = discord or DiscordNotifier()

    @property
    def has_active_channel(self) -> bool:
        """Returns True if at least one notification channel is active."""
        return self.telegram.is_configured or self.discord.is_configured

    def broadcast_state_flip(
        self,
        symbol: str,
        timeframe: str,
        old_state: str,
        new_state: str,
        price: float,
        tv_symbol: str = "",
        confluence_info: Optional[str] = None,
    ):
        """Broadcasts a ribbon state flip to all configured channels."""
        # 1. Telegram
        if self.telegram.is_configured:
            try:
                self.telegram.send_state_change_alert(
                    ticker=symbol,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=new_state,
                    price=price,
                    tv_symbol=tv_symbol or symbol,
                )
            except Exception as e:
                logger.error(f"Error broadcasting state flip to Telegram: {e}")

        # 2. Discord
        if self.discord.is_configured:
            try:
                self.discord.send_state_flip(
                    symbol=symbol,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=new_state,
                    price=price,
                    confluence_info=confluence_info,
                )
            except Exception as e:
                logger.error(f"Error broadcasting state flip to Discord: {e}")

    def broadcast_proposal(self, proposal: dict):
        """Broadcasts an actionable trade proposal to all configured channels."""
        if self.discord.is_configured:
            try:
                self.discord.send_proposal(proposal)
            except Exception as e:
                logger.error(f"Error broadcasting proposal to Discord: {e}")
