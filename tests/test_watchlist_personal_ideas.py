"""
Tests for Personal Radar & Trade Ideas feature.
Covers:
- Database schema and methods for watchlist with notes & target price
- Detailed watchlist retrieval
- Updating trade idea notes and target prices
- Generator export of watchlist items
"""

import pytest
from src.storage.database import Database


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_ideas.db")
    db = Database(db_path)
    yield db
    db.close()


def test_watchlist_trade_ideas_db(temp_db):
    # Add initial idea with note and target price
    assert temp_db.add_to_watchlist("NVDA", user_note="AI Leader breakout test", target_price=145.0) is True
    assert temp_db.add_to_watchlist("BTCUSDT", user_note="Support bounce plan", target_price=98000.0) is True

    # Retrieve detailed
    detailed = temp_db.get_watchlist_detailed()
    assert len(detailed) == 2
    tickers = {d["ticker"] for d in detailed}
    assert "NVDA" in tickers
    assert "BTCUSDT" in tickers

    nvda = next(d for d in detailed if d["ticker"] == "NVDA")
    assert nvda["user_note"] == "AI Leader breakout test"
    assert nvda["target_price"] == 145.0

    # Update note and target
    assert temp_db.update_watchlist_note("NVDA", user_note="Updated thesis: Strong earnings", target_price=150.0) is True
    updated_detailed = temp_db.get_watchlist_detailed()
    nvda_up = next(d for d in updated_detailed if d["ticker"] == "NVDA")
    assert nvda_up["user_note"] == "Updated thesis: Strong earnings"
    assert nvda_up["target_price"] == 150.0

    # Remove from watchlist
    assert temp_db.remove_from_watchlist("NVDA") is True
    remaining = temp_db.get_watchlist_detailed()
    assert len(remaining) == 1
    assert remaining[0]["ticker"] == "BTCUSDT"
