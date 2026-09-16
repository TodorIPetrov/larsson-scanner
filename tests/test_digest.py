import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.alerts.bot_listener import TelegramCommandListener
from src.alerts.digest import generate_digest_data, send_daily_digest
from src.alerts.formatter import format_daily_digest
from src.alerts.telegram import TelegramNotifier
from src.engine.smma import LarssonState
from src.storage.database import Database


def test_database_metadata_and_recent_alerts(tmp_path):
    db_file = str(tmp_path / "test_meta.db")
    db = Database(db_file)

    # Test metadata
    assert db.get_metadata("non_existent") is None
    db.set_metadata("test_key", "test_value")
    assert db.get_metadata("test_key") == "test_value"
    db.set_metadata("test_key", "updated_value")
    assert db.get_metadata("test_key") == "updated_value"

    # Test recent alerts
    db.log_alert("BTCUSDT", "1D", LarssonState.NEUTRAL, LarssonState.GOLD, 70000.0, "BINANCE:BTCUSDT")
    recent = db.get_recent_alerts(hours=24)
    assert len(recent) == 1
    assert recent[0]["ticker"] == "BTCUSDT"
    assert recent[0]["new_state"] == "GOLD"


def test_format_daily_digest():
    top_bullish = [{
        "ticker": "BTCUSDT",
        "name": "Bitcoin / USDT",
        "timeframe": "1D",
        "spread_pct": 12.5,
        "price": 68000.0,
        "tv_symbol": "BINANCE:BTCUSDT",
    }]
    top_bearish = [{
        "ticker": "INTC",
        "name": "Intel Corp",
        "timeframe": "1D",
        "spread_pct": -8.3,
        "price": 19.5,
        "tv_symbol": "NASDAQ:INTC",
    }]
    recent_changes = [{
        "ticker": "MSTR",
        "timeframe": "1D",
        "old_state": "NEUTRAL",
        "new_state": "GOLD",
        "price": 135.0,
        "tv_symbol": "NASDAQ:MSTR",
    }]

    msg = format_daily_digest(
        total=10,
        gold_count=6,
        blue_count=3,
        neutral_count=1,
        top_bullish=top_bullish,
        top_bearish=top_bearish,
        recent_changes=recent_changes,
        date_str="16.09.2026",
    )

    assert "Larsson Line Сутрешен Бюлетин" in msg
    assert "16.09.2026" in msg
    assert "6 (60.0%)" in msg
    assert "BTCUSDT" in msg
    assert "+12.5%" in msg
    assert "INTC" in msg
    assert "-8.3%" in msg
    assert "MSTR" in msg
    assert "https://todoripetrov.github.io/larsson-scanner/" in msg


def test_generate_digest_data(tmp_path):
    db_file = str(tmp_path / "test_digest_data.db")
    db = Database(db_file)
    db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("ETHUSDT", "crypto", "BINANCE:ETHUSDT"),
        ("MSTR", "crypto_stocks", "NASDAQ:MSTR"),
        ("NVDA", "us_stocks", "NASDAQ:NVDA"),
    ])

    # v1=120, v2=100 -> spread +20%
    db.update_state("BTCUSDT", "1D", 120.0, 115.0, 110.0, 100.0, LarssonState.GOLD, 70000.0)
    # v1=110, v2=100 -> spread +10%
    db.update_state("ETHUSDT", "1D", 110.0, 108.0, 105.0, 100.0, LarssonState.GOLD, 2500.0)
    # v1=80, v2=100 -> spread -20%
    db.update_state("MSTR", "1D", 80.0, 85.0, 90.0, 100.0, LarssonState.BLUE, 130.0)
    # Neutral
    db.update_state("NVDA", "1D", 100.0, 100.0, 100.0, 100.0, LarssonState.NEUTRAL, 120.0)

    data = generate_digest_data(db)
    assert data["total"] == 4
    assert data["gold_count"] == 2
    assert data["blue_count"] == 1
    assert data["neutral_count"] == 1

    # BTC should be top bullish (+20%)
    assert len(data["top_bullish"]) >= 1
    assert data["top_bullish"][0]["ticker"] == "BTCUSDT"
    assert data["top_bullish"][0]["spread_pct"] == 20.0

    # MSTR should be top bearish (-20%)
    assert len(data["top_bearish"]) >= 1
    assert data["top_bearish"][0]["ticker"] == "MSTR"
    assert data["top_bearish"][0]["spread_pct"] == -20.0


def test_send_daily_digest_deduplication(tmp_path):
    db_file = str(tmp_path / "test_send_digest.db")
    db = Database(db_file)
    db.upsert_symbols([("BTCUSDT", "crypto", "BINANCE:BTCUSDT")])
    db.update_state("BTCUSDT", "1D", 110.0, 105.0, 102.0, 100.0, LarssonState.GOLD, 70000.0)

    mock_notifier = MagicMock(spec=TelegramNotifier)
    mock_notifier.send_raw_message.return_value = True

    # 1. First send: should succeed
    sent = send_daily_digest(mock_notifier, db, force=False)
    assert sent is True
    assert mock_notifier.send_raw_message.call_count == 1

    # Check that metadata was recorded
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert db.get_metadata("last_daily_digest_date") == today_key

    # 2. Second send today without force: should be skipped
    sent_again = send_daily_digest(mock_notifier, db, force=False)
    assert sent_again is False
    assert mock_notifier.send_raw_message.call_count == 1  # Not called again

    # 3. Third send with force=True: should send anyway
    sent_forced = send_daily_digest(mock_notifier, db, force=True)
    assert sent_forced is True
    assert mock_notifier.send_raw_message.call_count == 2


def test_bot_listener_digest_command(tmp_path):
    db_file = str(tmp_path / "test_listener_digest.db")
    db = Database(db_file)
    db.upsert_symbols([("BTCUSDT", "crypto", "BINANCE:BTCUSDT")])
    db.update_state("BTCUSDT", "1D", 110.0, 105.0, 102.0, 100.0, LarssonState.GOLD, 70000.0)

    mock_notifier = MagicMock(spec=TelegramNotifier)
    mock_notifier.chat_id = "12345"
    mock_notifier.send_raw_message.return_value = True

    listener = TelegramCommandListener(notifier=mock_notifier, db=db)

    # Test handle_digest
    digest_text = listener.handle_digest()
    assert "Сутрешен Бюлетин" in digest_text
    assert "BTCUSDT" in digest_text

    # Test process_update with /digest command
    update = {
        "update_id": 100,
        "message": {
            "chat": {"id": 12345},
            "text": "/digest",
        },
    }
    listener.process_update(update)
    assert mock_notifier.send_raw_message.called
    sent_arg = mock_notifier.send_raw_message.call_args[0][0]
    assert "Сутрешен Бюлетин" in sent_arg
