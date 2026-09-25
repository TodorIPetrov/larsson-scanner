"""
Discord Alert Notifier for Larsson Scanner (Task 14).

Dispatches alerts, flips, proposals, and digests to Discord via webhooks or bot token.
Uses Discord rich embeds with color-coded ribbons:
  - GOLD flip: 0xFFD700 (Gold)
  - BLUE flip: 0x1E90FF (Dodger Blue)
  - NEUTRAL / Digest: 0xA9A9A9 (Gray)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

COLOR_GOLD = 0xFFD700
COLOR_BLUE = 0x1E90FF
COLOR_NEUTRAL = 0xA9A9A9


class DiscordNotifier:
    """Dispatches alerts to Discord using Webhooks or Bot API."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        channel_id: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN", "")
        self.channel_id = channel_id or os.getenv("DISCORD_CHANNEL_ID", "")
        self.session = session or requests.Session()

    @property
    def is_configured(self) -> bool:
        """Returns True if webhook URL or bot credentials are provided."""
        return bool(self.webhook_url or (self.bot_token and self.channel_id))

    def send_embed(
        self,
        title: str,
        description: str,
        color: int = COLOR_NEUTRAL,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: str = "Larsson Scanner",
    ) -> bool:
        """Sends a rich Discord embed."""
        if not self.is_configured:
            logger.debug("Discord not configured. Skipping embed dispatch.")
            return False

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                    "fields": fields or [],
                    "footer": {"text": footer},
                }
            ]
        }

        try:
            if self.webhook_url:
                resp = self.session.post(self.webhook_url, json=payload, timeout=8)
                return resp.status_code in (200, 204)
            elif self.bot_token and self.channel_id:
                url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
                headers = {"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"}
                resp = self.session.post(url, headers=headers, json=payload, timeout=8)
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False
        return False

    def send_state_flip(
        self,
        symbol: str,
        timeframe: str,
        old_state: str,
        new_state: str,
        price: float,
        confluence_info: Optional[str] = None,
    ) -> bool:
        """Sends a formatted state flip notification to Discord."""
        color = COLOR_GOLD if new_state == "GOLD" else (COLOR_BLUE if new_state == "BLUE" else COLOR_NEUTRAL)
        emoji = "🟡" if new_state == "GOLD" else ("🔵" if new_state == "BLUE" else "⚪")

        title = f"{emoji} {symbol} ({timeframe}) — State Flip: {new_state}"
        desc = f"**{symbol}** transitioned from `{old_state}` to **`{new_state}`** at **${price:,.2f}**."

        fields = [
            {"name": "Price", "value": f"${price:,.2f}", "inline": True},
            {"name": "Timeframe", "value": timeframe, "inline": True},
            {"name": "State", "value": new_state, "inline": True},
        ]
        if confluence_info:
            fields.append({"name": "Confluence", "value": confluence_info, "inline": False})

        return self.send_embed(title=title, description=desc, color=color, fields=fields)

    def send_proposal(self, proposal: dict) -> bool:
        """Sends a trade proposal embed to Discord."""
        symbol = proposal.get("ticker", "UNKNOWN")
        direction = proposal.get("direction", "LONG")
        entry = float(proposal.get("entry_price") or 0.0)
        sl = float(proposal.get("stop_loss") or 0.0)
        tp1 = float(proposal.get("tp1") or 0.0)
        tier = proposal.get("tier", "B")
        score = proposal.get("score", 0)

        color = COLOR_GOLD if direction == "LONG" else COLOR_BLUE
        title = f"⚡ Trade Proposal: {direction} {symbol} (Tier {tier})"
        desc = f"New quantitative signal generated with Institutional Confluence Score: **{score}/100**."

        fields = [
            {"name": "Entry", "value": f"${entry:,.2f}", "inline": True},
            {"name": "Stop Loss", "value": f"${sl:,.2f}", "inline": True},
            {"name": "Target 1", "value": f"${tp1:,.2f}", "inline": True},
        ]

        return self.send_embed(title=title, description=desc, color=color, fields=fields)
