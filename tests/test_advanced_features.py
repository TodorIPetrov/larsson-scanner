"""
Unit tests for the 5 advanced institutional engine improvements:
1. MTF 1W context & Squeeze filter
2. Dynamic ATR Chandelier Trailing Stop & SMMA15 momentum exit
3. Volatility-Adjusted Sizing (Fixed Fractional Risk) & Cluster Risk Cap
4. Realistic Execution Slippage & Spread Model
5. Data Sanity Guard in Data Fetchers
"""

import numpy as np
import pytest

from src.data.binance_fetch import BinanceFetcher
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.trade_suggestions import (
    calculate_confluence_score,
    generate_trade_suggestion,
)
from src.storage.database import Database
from src.trading.paper_trader import PaperTrader


class MockNotifier:
    def __init__(self):
        self.sent_messages = []
        self.edited_messages = []

    def send_message_with_markup(self, text, reply_markup=None):
        self.sent_messages.append({"text": text, "reply_markup": reply_markup})
        return 9999

    def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None):
        self.edited_messages.append({"message_id": message_id, "text": text})
        return True

    def send_raw_message(self, text):
        self.sent_messages.append({"text": text, "raw": True})
        return True


# -------------------------------------------------------------------------
# 1. MTF Context + Volatility Squeeze Filter Tests
# -------------------------------------------------------------------------
def test_mtf_1w_alignment_and_penalty():
    # 1. Aligned: 1D GOLD + 1W GOLD
    score_aligned, tier_aligned = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.2,
        htf_aligned=True,
    )

    # 2. Counter-trend: 1D GOLD + 1W BLUE
    score_counter, tier_counter = calculate_confluence_score(
        is_mtf_aligned=False,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.2,
        htf_aligned=False,
    )

    # Counter-trend should be penalized significantly (-15 vs +20)
    assert score_aligned > score_counter
    assert (score_aligned - score_counter) >= 35


def test_volatility_squeeze_bonus_and_exhaustion_penalty():
    # Squeeze breakout setup
    score_sqz, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=False,
        rr_ratio=2.0,
        is_squeeze=True,
    )

    # Normal setup without squeeze
    score_norm, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=False,
        rr_ratio=2.0,
        is_squeeze=False,
    )

    assert score_sqz == score_norm + 10

    # Exhaustion spike penalty
    score_spike, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.0,
        volatility_regime="HIGH_VOL_SPIKE",
    )
    assert score_spike < score_norm + 10


# -------------------------------------------------------------------------
# 2. Dynamic ATR Chandelier Trailing Stop Tests
# -------------------------------------------------------------------------
def test_chandelier_trailing_stop_exit(tmp_path):
    db_file = str(tmp_path / "trailing_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 1000.0,
                "default_position_size_usd": 100.0,
                "trailing_stop_atr_mult": 2.5,
            }
        },
    )

    # Open LONG position at 100.0 with SL at 90.0, ATR=2.0
    db.open_paper_position(
        position_id="pos_TRAIL_1",
        ticker="TRAIL",
        entry_price=100.0,
        units=1.0,
        position_size_usd=100.0,
        stop_loss=90.0,
        tp1=130.0,
        tp2=150.0,
        opened_at="2026-10-27T10:00:00",
        direction="LONG",
    )
    # Manually seed atr_at_entry
    with db._get_connection() as conn:
        conn.cursor().execute("UPDATE paper_positions SET atr_at_entry = 2.0 WHERE position_id = 'pos_TRAIL_1'")

    # Price moves up to 120.0: Chandelier stop should trail up to 120 - (2.5 * 2) = 115.0
    closed = trader.evaluate_open_positions(prices={"TRAIL": 120.0}, states={"TRAIL": "GOLD"})
    assert len(closed) == 0

    pos = db.get_open_paper_position_by_ticker("TRAIL")
    assert pos["highest_price_seen"] == 120.0
    assert pos["chandelier_stop"] == 115.0

    # Price drops to 114.0 (below 115.0 trailing stop): triggers CHANDELIER_TRAILING_STOP
    closed = trader.evaluate_open_positions(prices={"TRAIL": 114.0}, states={"TRAIL": "GOLD"})
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "CHANDELIER_TRAILING_STOP"
    assert closed[0]["exit_price"] == 115.0
    assert closed[0]["pnl_usd"] > 14.0  # Locked in handsome profit!


# -------------------------------------------------------------------------
# 3. Volatility-Adjusted Sizing & Cluster Risk Cap
# -------------------------------------------------------------------------
def test_volatility_adjusted_sizing(tmp_path):
    db_file = str(tmp_path / "vol_size_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 10000.0,
                "volatility_sizing_enabled": True,
                "risk_per_trade_pct": 0.015,  # $150 risk on $10k
                "default_position_size_usd": 100.0,
            }
        },
    )

    # Tight stop setup: Entry 100, Stop 95 (Risk per share = $5)
    # Target risk: $150 -> Units = 150 / 5 = 30 -> Position Size = 30 * 100 = $3000
    res_tight = trader.handle_new_signal(
        ticker="TIGHTUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "tp1": 115.0,
            "score": 80,
            "tier": "A",
        },
        current_price=100.0,
    )
    assert res_tight is not None
    # Position size should be scaled up due to tight risk
    assert res_tight["position_size_usd"] > 1000.0

    # Wide stop setup: Entry 100, Stop 70 (Risk per share = $30)
    # Target risk: $150 -> Units = 150 / 30 = 5 -> Position Size = 5 * 100 = $500
    res_wide = trader.handle_new_signal(
        ticker="WIDEUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 100.0,
            "stop_loss": 70.0,
            "tp1": 150.0,
            "score": 80,
            "tier": "A",
        },
        current_price=100.0,
    )
    assert res_wide is not None
    assert res_wide["position_size_usd"] < res_tight["position_size_usd"]


def test_cluster_risk_cap_limits_crypto(tmp_path):
    db_file = str(tmp_path / "cluster_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 10000.0,
                "max_crypto_positions": 2,
                "max_active_positions": 5,
            }
        },
    )

    # Open 2 crypto positions
    db.open_paper_position("pos_c1", "BTCUSDT", 60000.0, 0.01, 600.0, 58000.0, 65000.0, None, "2026-10-27T10:00:00")
    db.open_paper_position("pos_c2", "ETHUSDT", 3000.0, 0.2, 600.0, 2800.0, 3500.0, None, "2026-10-27T10:00:00")

    # Propose 3rd crypto position (SOLUSDT)
    res = trader.handle_new_signal(
        ticker="SOLUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 150.0,
            "stop_loss": 140.0,
            "tp1": 180.0,
            "score": 80,
            "tier": "A",
        },
        current_price=150.0,
    )
    assert res is not None

    # Attempt to approve 3rd crypto position: should be blocked by cluster risk cap!
    app_res = trader.approve_proposal(res["proposal_id"])
    assert app_res["success"] is False
    assert "секторна експозиция" in app_res["error"]


# -------------------------------------------------------------------------
# 4. Realistic Execution Slippage Model
# -------------------------------------------------------------------------
def test_execution_slippage_model(tmp_path):
    db_file = str(tmp_path / "slip_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 10000.0,
                "slippage_model_enabled": True,
                "slippage_pct_crypto": 0.0020,  # 20 bps slippage
            }
        },
    )

    res = trader.handle_new_signal(
        ticker="BNBUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 600.0,
            "stop_loss": 550.0,
            "tp1": 700.0,
            "score": 80,
            "tier": "A",
        },
        current_price=600.0,
    )
    app = trader.approve_proposal(res["proposal_id"])
    assert app["success"] is True

    # Position in DB should have fill_price = 600 * 1.0020 = 601.20
    pos = db.get_open_paper_position_by_ticker("BNBUSDT")
    assert pos["entry_price"] == 601.20


# -------------------------------------------------------------------------
# 5. Data Sanity Guard in Data Fetchers
# -------------------------------------------------------------------------
def test_binance_data_sanity_guard(monkeypatch):
    fetcher = BinanceFetcher()

    # Corrupt klines containing NaN or zero
    bad_klines = [
        [1600000000000, "100.0", "105.0", "0.0", "102.0", "1000", 1600086400000] for _ in range(50)
    ]

    class FakeResp:
        status_code = 200
        def json(self): return bad_klines
        def raise_for_status(self): pass

    monkeypatch.setattr(fetcher.session, "get", lambda *args, **kwargs: FakeResp())

    res = fetcher.fetch_klines("BTCUSDT", "1D")
    assert res is None  # Data sanity guard rejected non-positive prices!
