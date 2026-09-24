"""
Unit tests for Real vs Paper Portfolio Isolation and Management.
Ensures strict separation between real money assets and paper simulation.
"""

import os
import tempfile
from datetime import datetime, timezone
import pytest

from src.storage.database import Database
from src.trading.portfolio_tracker import PortfolioTracker
from src.alerts.bot_listener import TelegramCommandListener


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


def test_real_vs_paper_database_isolation(temp_db):
    """Verify that real_positions and paper_positions are strictly separated."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Balances are isolated
    paper_bal = temp_db.get_paper_balance(initial_balance=10000.0)
    real_bal = temp_db.get_real_balance(initial_balance=5000.0)

    assert paper_bal["available_cash"] == 10000.0
    assert real_bal["available_cash"] == 5000.0

    temp_db.update_paper_balance(-1000.0)
    assert temp_db.get_paper_balance()["available_cash"] == 9000.0
    assert temp_db.get_real_balance()["available_cash"] == 5000.0  # Real cash untouched!

    temp_db.set_real_cash(7500.0)
    assert temp_db.get_real_balance()["available_cash"] == 7500.0
    assert temp_db.get_paper_balance()["available_cash"] == 9000.0  # Paper cash untouched!

    # 2. Open positions are isolated
    temp_db.open_paper_position(
        position_id="paper_pos_1",
        ticker="BTCUSDT",
        entry_price=60000.0,
        units=0.1,
        position_size_usd=6000.0,
        stop_loss=57000.0,
        tp1=66000.0,
        tp2=None,
        opened_at=now_iso,
    )

    temp_db.open_real_position(
        position_id="real_pos_1",
        ticker="NVDA",
        asset_class="us_stocks",
        entry_price=120.0,
        units=50.0,
        position_size_usd=6000.0,
        stop_loss=114.0,
        tp1=135.0,
        broker_exchange="Interactive Brokers",
        notes="Real fundamental breakout buy",
        fee_paid_usd=1.50,
        opened_at=now_iso,
    )

    open_paper = temp_db.get_open_paper_positions()
    open_real = temp_db.get_open_real_positions()

    assert len(open_paper) == 1
    assert open_paper[0]["ticker"] == "BTCUSDT"

    assert len(open_real) == 1
    assert open_real[0]["ticker"] == "NVDA"
    assert open_real[0]["broker_exchange"] == "Interactive Brokers"
    assert open_real[0]["fee_paid_usd"] == 1.50

    # 3. Closing positions is isolated
    temp_db.close_real_position(
        position_id="real_pos_1",
        exit_price=132.0,
        realized_pnl_usd=598.50,
        realized_pnl_pct=10.0,
        fee_paid_usd=1.50,
        notes="Hit target"
    )

    assert len(temp_db.get_open_real_positions()) == 0
    assert len(temp_db.get_closed_real_positions()) == 1
    assert len(temp_db.get_open_paper_positions()) == 1  # Paper position remains open!


def test_trade_log_portfolio_type_filtering(temp_db):
    """Verify that trade log entries can be partitioned by portfolio_type."""
    temp_db.add_trade_log_entry("p1", "BTCUSDT", "BUY", price=60000.0, quantity=0.1, portfolio_type="PAPER")
    temp_db.add_trade_log_entry("r1", "NVDA", "BUY", price=120.0, quantity=10.0, portfolio_type="REAL")
    temp_db.add_trade_log_entry("r1", "NVDA", "SELL", price=130.0, quantity=10.0, pnl_usd=100.0, portfolio_type="REAL")

    all_logs = temp_db.get_trade_log()
    real_logs = temp_db.get_trade_log(portfolio_type="REAL")
    paper_logs = temp_db.get_trade_log(portfolio_type="PAPER")

    assert len(all_logs) == 3
    assert len(real_logs) == 2
    assert len(paper_logs) == 1
    assert real_logs[0]["ticker"] == "NVDA"
    assert paper_logs[0]["ticker"] == "BTCUSDT"


def test_portfolio_tracker_dual_mode(temp_db):
    """Verify PortfolioTracker handles both real and paper portfolios with add and close."""
    tracker = PortfolioTracker(db=temp_db)

    # 1. Set initial real cash
    tracker.set_real_cash_balance(10000.0)
    real_summary_init = tracker.get_portfolio_summary(portfolio_type="REAL")
    assert real_summary_init["available_cash"] == 10000.0
    assert real_summary_init["total_invested"] == 0.0

    # 2. Add real position
    pos_id = tracker.add_real_position(
        ticker="AAPL",
        asset_class="us_stocks",
        entry_price=200.0,
        units=10.0,
        stop_loss=190.0,
        tp1=220.0,
        broker_exchange="Revolut",
        notes="Tech momentum entry",
        fee_paid_usd=2.0
    )
    assert pos_id.startswith("real_AAPL_")

    real_summary_after_buy = tracker.get_portfolio_summary(portfolio_type="REAL")
    assert real_summary_after_buy["available_cash"] == 10000.0 - (200.0 * 10.0 + 2.0)
    assert real_summary_after_buy["total_invested"] == 2000.0
    assert real_summary_after_buy["open_positions_count"] == 1

    # Check open positions detail
    open_details = tracker.get_open_positions_detail(portfolio_type="REAL")
    assert len(open_details) == 1
    assert open_details[0]["symbol"] == "AAPL"
    assert open_details[0]["broker_exchange"] == "Revolut"
    assert open_details[0]["portfolio_type"] == "REAL"

    # 3. Close real position
    closed_ok = tracker.close_real_position(
        identifier=pos_id,
        exit_price=220.0,
        notes="Take Profit reached",
        fee_paid_usd=2.0
    )
    assert closed_ok is True

    real_summary_after_close = tracker.get_portfolio_summary(portfolio_type="REAL")
    assert real_summary_after_close["open_positions_count"] == 0
    assert real_summary_after_close["closed_positions_count"] == 1
    # 200 * 10 = 2000 entry. 220 * 10 = 2200 exit. gross PnL = +200, fee = 2 => net = 198
    assert real_summary_after_close["total_realized_pnl"] == 198.0
    assert real_summary_after_close["win_rate"] == 100.0

    # Trade history
    hist = tracker.get_trade_history(portfolio_type="REAL")
    assert len(hist) == 1
    assert hist[0]["symbol"] == "AAPL"
    assert hist[0]["pnl_usd"] == 198.0


def test_telegram_bot_real_portfolio_commands(temp_db):
    """Verify TelegramCommandListener correctly executes real portfolio commands."""
    listener = TelegramCommandListener(db=temp_db)

    # 1. Set real cash
    cash_reply = listener.handle_cash_real("15000")
    assert "$15,000.00" in cash_reply

    # 2. Buy real position
    buy_reply = listener.handle_buy_real(["NVDA", "125.0", "20", "Binance"])
    assert "Записана РЕАЛНА Позиция: NVDA" in buy_reply
    assert "Binance" in buy_reply
    assert "$2,500.00" in buy_reply

    # 3. Check /real view
    real_summary = listener.handle_portfolio("real")
    assert "РЕАЛЕН КАПИТАЛ & АКТИВИ" in real_summary
    assert "NVDA" in real_summary

    # 4. Check /paper view is separate and empty
    paper_summary = listener.handle_portfolio("paper")
    assert "ТЕСТОВ СИМУЛАТОР" in paper_summary
    assert "NVDA" not in paper_summary

    # 5. Close real position
    close_reply = listener.handle_close_real(["NVDA", "140.0"])
    assert "успешно затворена" in close_reply
    assert "NVDA" in close_reply
