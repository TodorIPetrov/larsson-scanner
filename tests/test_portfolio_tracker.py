import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
import pytest
from src.storage.database import Database


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    db = Database(temp_path)
    yield db
    db.close()
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except PermissionError:
            pass


def test_portfolio_equity_table(temp_db):
    today = datetime.now(timezone.utc).date()
    
    for i in range(3):
        date_str = (today - timedelta(days=2-i)).isoformat()
        temp_db.record_portfolio_equity(
            date=date_str,
            total_equity=10000.0 + i * 100,
            cash=8000.0,
            invested=2000.0 + i * 100,
            daily_pnl=100.0,
            daily_pnl_pct=1.0,
            open_positions_count=2,
            cumulative_win_rate=50.0 + i
        )

    history = temp_db.get_portfolio_equity_history(days=10)
    assert len(history) == 3
    # Ordered by date DESC, so the latest is first
    assert history[0]["total_equity"] == 10200.0
    assert history[1]["total_equity"] == 10100.0
    assert history[2]["total_equity"] == 10000.0

    latest = temp_db.get_latest_portfolio_equity()
    assert latest is not None
    assert latest["total_equity"] == 10200.0
    assert latest["cumulative_win_rate"] == 52.0


def test_trade_log_table(temp_db):
    temp_db.add_trade_log_entry("pos_1", "BTCUSDT", "OPEN", 60000.0, 0.1, 0.0, 0.0, "Opened pos_1")
    temp_db.add_trade_log_entry("pos_2", "ETHUSDT", "OPEN", 3000.0, 1.0, 0.0, 0.0, "Opened pos_2")
    temp_db.add_trade_log_entry("pos_1", "BTCUSDT", "CLOSE", 65000.0, 0.1, 500.0, 8.33, "Closed pos_1")

    log = temp_db.get_trade_log(limit=10)
    assert len(log) == 3
    # Most recent first
    assert log[0]["ticker"] == "BTCUSDT"
    assert log[0]["action"] == "CLOSE"

    btc_log = temp_db.get_trade_log(ticker="BTCUSDT", limit=10)
    assert len(btc_log) == 2

    pos_1_log = temp_db.get_trade_log_for_position("pos_1")
    assert len(pos_1_log) == 2
    # ASC order for position log
    assert pos_1_log[0]["action"] == "OPEN"
    assert pos_1_log[1]["action"] == "CLOSE"


def test_pending_setups_table(temp_db):
    # Upsert 3 setups
    temp_db.upsert_pending_setup("BTCUSDT", "crypto", "PULLBACK", "LONG", "HIGH", 85.0, "bg", "en", "[]", "[]", "soon", 65000.0, 64000.0, 62000.0, 70000.0, 63000.0, "1D", "A")
    temp_db.upsert_pending_setup("ETHUSDT", "crypto", "BREAKOUT", "LONG", "MEDIUM", 75.0, "bg", "en", "[]", "[]", "soon", 3000.0, 3100.0, 2900.0, 3500.0, 3050.0, "1D", "B")
    temp_db.upsert_pending_setup("SOLUSDT", "crypto", "REVERSAL", "SHORT", "LOW", 65.0, "bg", "en", "[]", "[]", "soon", 150.0, 155.0, 160.0, 140.0, 153.0, "4H", "C")

    setups = temp_db.get_active_pending_setups()
    assert len(setups) == 3
    # Sorted by quality_score DESC
    assert setups[0]["symbol"] == "BTCUSDT"
    assert setups[0]["quality_score"] == 85.0
    assert setups[2]["symbol"] == "SOLUSDT"

    # Upsert with updated score
    temp_db.upsert_pending_setup("BTCUSDT", "crypto", "PULLBACK", "LONG", "HIGH", 90.0, "bg2", "en2", "[]", "[]", "soon", 65000.0, 64000.0, 62000.0, 70000.0, 63000.0, "1D", "A")
    setups = temp_db.get_active_pending_setups()
    assert len(setups) == 3
    assert setups[0]["quality_score"] == 90.0

    # Mark triggered
    temp_db.mark_setup_triggered("BTCUSDT", "PULLBACK", "1D")
    setups = temp_db.get_active_pending_setups()
    assert len(setups) == 2

    # Expire stale setups (mock updated_at by raw SQL to test expiration)
    old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with temp_db._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE pending_setups SET last_updated = ? WHERE symbol = 'ETHUSDT'", (old_time,))
    
    temp_db.expire_stale_setups(max_age_hours=168)
    setups = temp_db.get_active_pending_setups()
    assert len(setups) == 1
    assert setups[0]["symbol"] == "SOLUSDT"


def test_portfolio_allocation(temp_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    
    temp_db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("NVDA", "stock", "NASDAQ:NVDA"),
        ("EURUSD", "forex", "OANDA:EURUSD"),
    ])

    temp_db.open_paper_position("pos_1", "BTCUSDT", 60000.0, 0.1, 6000.0, 50000.0, 70000.0, None, now_iso)
    temp_db.open_paper_position("pos_2", "NVDA", 100.0, 20.0, 2000.0, 90.0, 120.0, None, now_iso)
    temp_db.open_paper_position("pos_3", "EURUSD", 1.1, 1818.18, 2000.0, 1.0, 1.2, None, now_iso)

    allocations = temp_db.get_portfolio_allocation()
    assert "crypto" in allocations
    assert "stock" in allocations
    assert "forex" in allocations
    
    total = 6000.0 + 2000.0 + 2000.0
    assert allocations["crypto"] == (6000.0 / total) * 100.0
    assert allocations["stock"] == (2000.0 / total) * 100.0
    assert allocations["forex"] == (2000.0 / total) * 100.0


def test_portfolio_performance_stats(temp_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    
    temp_db.open_paper_position("pos_1", "BTCUSDT", 60000.0, 0.1, 6000.0, None, None, None, now_iso)
    temp_db.close_paper_position("pos_1", 66000.0, 600.0, 10.0, 5.0, "TAKE_PROFIT", now_iso)
    
    temp_db.open_paper_position("pos_2", "ETHUSDT", 3000.0, 1.0, 3000.0, None, None, None, now_iso)
    temp_db.close_paper_position("pos_2", 2850.0, -150.0, -5.0, 2.0, "STOP_LOSS", now_iso)
    
    temp_db.open_paper_position("pos_3", "SOLUSDT", 150.0, 10.0, 1500.0, None, None, None, now_iso)
    temp_db.close_paper_position("pos_3", 180.0, 300.0, 20.0, 3.0, "TAKE_PROFIT", now_iso)

    stats = temp_db.get_portfolio_performance_stats()
    
    assert stats["total_trades"] == 3
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["win_rate"] == round((2/3) * 100.0, 2)
    assert stats["avg_pnl_pct"] == round((10.0 - 5.0 + 20.0) / 3, 2)
    assert stats["best_trade"] == 20.0
    assert stats["worst_trade"] == -5.0
    assert stats["total_realized_pnl"] == 750.0
    assert stats["total_fees"] == 10.0
