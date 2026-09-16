import pytest
from src.alerts.bot_listener import TelegramCommandListener
from src.alerts.telegram import TelegramNotifier
from src.engine.smma import LarssonState
from src.storage.database import Database


def test_command_listener_replies(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("AAPL", "us_stocks", "NASDAQ:AAPL"),
    ])
    db.update_state("BTCUSDT", "1D", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 70000.0)
    db.update_state("AAPL", "1D", 7.0, 8.0, 9.0, 10.0, LarssonState.BLUE, 220.0)

    listener = TelegramCommandListener(db=db)

    # Test /status reply
    status_text = listener.handle_status()
    assert "Пазарен Баланс" in status_text
    assert "Gold" in status_text
    assert "Blue" in status_text

    # Test /gold reply
    gold_text = listener.handle_state_list("GOLD", "🟡")
    assert "BTCUSDT" in gold_text

    # Test /blue reply
    blue_text = listener.handle_state_list("BLUE", "🔵")
    assert "AAPL" in blue_text

    # Test timeframe filter
    db.update_state("BTCUSDT", "4H", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 70500.0)
    status_4h = listener.handle_status("4h")
    assert "[4H]" in status_4h

    gold_4h = listener.handle_state_list("GOLD", "🟡", "4h")
    assert "[4H]" in gold_4h
    assert "BTCUSDT" in gold_4h
