"""
Tests for src/alerts/discord_bot.py and src/alerts/notification_bus.py (Task 14).

Covers:
- DiscordNotifier configuration check
- Webhook dispatch with mock session
- State flip formatting and embed fields
- Trade proposal embed formatting
- NotificationBus multi-channel broadcasting
"""

import pytest
from unittest.mock import MagicMock

from src.alerts.discord_bot import DiscordNotifier, COLOR_GOLD, COLOR_BLUE
from src.alerts.notification_bus import NotificationBus


def test_discord_notifier_not_configured():
    notifier = DiscordNotifier(webhook_url="", bot_token="", channel_id="")
    assert notifier.is_configured is False
    assert notifier.send_embed("Title", "Desc") is False


def test_discord_webhook_dispatch():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_session.post.return_value = mock_resp

    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/test",
        session=mock_session,
    )
    assert notifier.is_configured is True

    ok = notifier.send_embed(
        title="Test Alert",
        description="Testing Discord embed",
        color=COLOR_GOLD,
    )
    assert ok is True
    assert mock_session.post.called


def test_discord_state_flip():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_session.post.return_value = mock_resp

    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/test",
        session=mock_session,
    )

    ok = notifier.send_state_flip(
        symbol="BTCUSDT",
        timeframe="1D",
        old_state="BLUE",
        new_state="GOLD",
        price=65000.0,
        confluence_info="TRIPLE_GOLD (Score 3/3)",
    )
    assert ok is True

    args, kwargs = mock_session.post.call_args
    embed = kwargs["json"]["embeds"][0]
    assert "BTCUSDT" in embed["title"]
    assert embed["color"] == COLOR_GOLD
    field_names = [f["name"] for f in embed["fields"]]
    assert "Price" in field_names
    assert "Confluence" in field_names


def test_discord_proposal():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_session.post.return_value = mock_resp

    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/test",
        session=mock_session,
    )

    proposal = {
        "ticker": "NVDA",
        "direction": "LONG",
        "entry_price": 125.0,
        "stop_loss": 118.0,
        "tp1": 135.0,
        "tier": "A+",
        "score": 92,
    }
    ok = notifier.send_proposal(proposal)
    assert ok is True

    args, kwargs = mock_session.post.call_args
    embed = kwargs["json"]["embeds"][0]
    assert "NVDA" in embed["title"]
    assert "Tier A+" in embed["title"]


def test_notification_bus():
    mock_tg = MagicMock()
    mock_tg.is_configured = True
    mock_dc = MagicMock()
    mock_dc.is_configured = True

    bus = NotificationBus(telegram=mock_tg, discord=mock_dc)
    assert bus.has_active_channel is True

    bus.broadcast_state_flip(
        symbol="SOLUSDT",
        timeframe="1D",
        old_state="NEUTRAL",
        new_state="GOLD",
        price=180.0,
        confluence_info="TRIPLE_GOLD",
    )

    assert mock_tg.send_state_change_alert.called
    assert mock_dc.send_state_flip.called
