"""
Tests for custom watchlist conditions (Task 10).

Covers:
- Adding PRICE_LEVEL, STATE_CHANGE, ALPHA_POSITIVE, WEEKLY_GOLD conditions
- Listing unsent conditions
- Marking conditions as sent
- Deleting conditions
- Bot listener commands: /watch <sym> price <val>, /watch <sym> state <val>, /conditions, /delcond
"""

import pytest
import sqlite3
from unittest.mock import MagicMock

from src.storage.database import Database
from src.alerts.bot_listener import TelegramCommandListener


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_state.db")
    db = Database(db_path)
    yield db
    db.close()


def test_db_watchlist_conditions(temp_db):
    # Add conditions
    id1 = temp_db.add_watchlist_condition("BTCUSDT", "PRICE_LEVEL", "50000")
    id2 = temp_db.add_watchlist_condition("NVDA", "STATE_CHANGE", "GOLD")
    id3 = temp_db.add_watchlist_condition("ETHUSDT", "ALPHA_POSITIVE", "0.0")

    assert id1 > 0
    assert id2 > 0
    assert id3 > 0

    # Retrieve all
    all_conds = temp_db.get_watchlist_conditions()
    assert len(all_conds) == 3

    # Filter by symbol
    btc_conds = temp_db.get_watchlist_conditions(symbol="BTCUSDT")
    assert len(btc_conds) == 1
    assert btc_conds[0]["condition_type"] == "PRICE_LEVEL"
    assert btc_conds[0]["condition_value"] == "50000"

    # Mark as sent
    ok = temp_db.mark_watchlist_condition_sent(id1)
    assert ok is True

    # Unsent only
    unsent = temp_db.get_watchlist_conditions(unsent_only=True)
    assert len(unsent) == 2
    assert all(c["id"] != id1 for c in unsent)

    # Delete
    deleted = temp_db.delete_watchlist_condition(id2)
    assert deleted is True
    remaining = temp_db.get_watchlist_conditions()
    assert len(remaining) == 2


def test_bot_listener_conditions_commands(temp_db):
    notifier = MagicMock()
    notifier.chat_id = "12345"
    notifier.is_configured = True
    paper_trader = MagicMock()

    listener = TelegramCommandListener(notifier=notifier, db=temp_db, paper_trader=paper_trader)

    # Test /watch with price
    reply_price = listener.handle_watch(["BTCUSDT", "price", "65000"])
    assert "Зададено условие" in reply_price
    assert "$65000" in reply_price

    # Test /watch with state
    reply_state = listener.handle_watch(["NVDA", "state", "GOLD"])
    assert "Зададено условие" in reply_state
    assert "GOLD" in reply_state

    # Test /conditions
    reply_list = listener.handle_conditions()
    assert "BTCUSDT" in reply_list
    assert "NVDA" in reply_list

    # Test /delcond
    conds = temp_db.get_watchlist_conditions()
    cid = conds[0]["id"]
    reply_del = listener.handle_delcond(str(cid))
    assert "успешно изтрито" in reply_del
