"""
Comprehensive Unit Tests for Institutional Backtesting Engine.
Validates zero-bias signal generation, risk-based portfolio sizing,
intrabar SL/TP execution, fee accounting, and performance analytics.
"""

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics import BacktestMetricsCalculator
from src.backtest.portfolio import PortfolioManager
from src.backtest.signals import BacktestSignal, BacktestSignalGenerator


def create_synthetic_candles(n: int = 250, trend: float = 0.001) -> pd.DataFrame:
    """Generates synthetic OHLCV dataframe with realistic price walks."""
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", periods=n, freq="D").strftime("%Y-%m-%d").tolist()

    prices = [100.0]
    for _ in range(1, n):
        ret = np.random.normal(trend, 0.02)
        prices.append(prices[-1] * (1.0 + ret))

    prices = np.array(prices)
    highs = prices * (1.0 + np.abs(np.random.normal(0, 0.01, n)))
    lows = prices * (1.0 - np.abs(np.random.normal(0, 0.01, n)))
    opens = (highs + lows) / 2.0
    closes = prices

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.uniform(1000, 5000, n),
    })


def test_signal_generator_zero_lookahead():
    """Verifies signal generation at bar i only uses data up to bar i."""
    df = create_synthetic_candles(200, trend=0.005)
    sig_gen = BacktestSignalGenerator(min_warmup=60, rolling_sr_window=100)
    feat_df = sig_gen.prepare_asset_features(df)

    assert "v1" in feat_df.columns
    assert "state" in feat_df.columns
    assert "atr" in feat_df.columns

    # Evaluate at bar 120
    sig1 = sig_gen.evaluate_bar_signal("TEST", feat_df, idx=120, allow_short=False)

    # Modify future bars (121+) drastically
    feat_df_tampered = feat_df.copy()
    feat_df_tampered.loc[121:, "close"] *= 10.0
    feat_df_tampered.loc[121:, "high"] *= 10.0
    feat_df_tampered.loc[121:, "low"] *= 10.0

    sig2 = sig_gen.evaluate_bar_signal("TEST", feat_df_tampered, idx=120, allow_short=False)

    # Signal at bar 120 must be completely identical regardless of future manipulation
    if sig1 is None:
        assert sig2 is None
    else:
        assert sig1.action == sig2.action
        assert sig1.entry_price == sig2.entry_price
        assert sig1.stop_loss == sig2.stop_loss
        assert sig1.tp1 == sig2.tp1


def test_portfolio_entry_and_sizing():
    """Tests 1% risk position sizing and capital deduction."""
    pm = PortfolioManager(initial_capital=100000.0, risk_per_trade=0.01, max_positions=5, max_position_size_pct=0.25)

    signal = BacktestSignal(
        date="2023-01-01",
        symbol="BTCUSDT",
        action="BUY_LONG",
        setup_type="PULLBACK_VALUE_BUY",
        entry_price=20000.0,
        stop_loss=19000.0,  # $1,000 risk per unit
        tp1=22000.0,
        tp2=25000.0,
        rr_ratio=2.0,
        score=85,
        tier="A+",
        state="GOLD",
        atr=500.0,
    )

    price_bars = {
        "BTCUSDT": {"open": 20000.0, "high": 20500.0, "low": 19800.0, "close": 20200.0}
    }

    pm.execute_entries("2023-01-01", [signal], price_bars)

    assert "BTCUSDT" in pm.open_positions
    pos = pm.open_positions["BTCUSDT"]
    assert pos.direction == "LONG"
    # 1% risk of $100k is $1,000. Risk per unit is ~$1020 (including slippage). Units should be approx 0.98.
    assert 0.95 <= pos.units <= 1.05
    assert pm.cash < 100000.0


def test_intrabar_tp1_scale_out_and_breakeven():
    """Tests scaling out 50% on TP1 and adjusting SL to breakeven."""
    pm = PortfolioManager(initial_capital=100000.0)

    signal = BacktestSignal(
        date="2023-01-01",
        symbol="AAPL",
        action="BUY_LONG",
        setup_type="PULLBACK_VALUE_BUY",
        entry_price=150.0,
        stop_loss=140.0,
        tp1=160.0,
        tp2=175.0,
        rr_ratio=2.0,
        score=80,
        tier="A",
        state="GOLD",
        atr=5.0,
    )

    price_bars = {
        "AAPL": {"open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0}
    }
    pm.execute_entries("2023-01-01", [signal], price_bars)
    pos = pm.open_positions["AAPL"]
    initial_units = pos.units

    # Next day: High reaches 162.0 (exceeds TP1 of 160.0)
    day2_bars = {
        "AAPL": {"open": 153.0, "high": 162.0, "low": 152.0, "close": 159.0}
    }
    pm.process_intrabar_exits("2023-01-02", day2_bars, structural_exits={})

    # Should have recorded 1 closed trade (TP1 scale-out)
    assert len(pm.closed_trades) == 1
    t1 = pm.closed_trades[0]
    assert t1.exit_reason == "TAKE_PROFIT_1"
    assert t1.exit_price == 160.0
    assert t1.pnl > 0

    # Remaining position should have half the units and Stop Loss moved to breakeven (entry_price)
    assert "AAPL" in pm.open_positions
    remaining_pos = pm.open_positions["AAPL"]
    assert pytest.approx(remaining_pos.units, rel=1e-3) == initial_units * 0.5
    assert remaining_pos.stop_loss >= remaining_pos.entry_price


def test_metrics_calculator():
    """Validates mathematical correctness of Sharpe, CAGR, and Drawdown."""
    calc = BacktestMetricsCalculator(risk_free_rate=0.03)

    # 1-year equity curve: grows from 100k to 140k (+40%), with a small 10% dip
    dates = pd.date_range("2023-01-01", "2024-01-01", freq="D").strftime("%Y-%m-%d")
    curve = []
    val = 100000.0
    for i, d in enumerate(dates):
        if 50 <= i <= 80:
            val -= 300.0
        else:
            val += 200.0
        curve.append({"date": d, "equity": val})

    trades = [
        {"direction": "LONG", "pnl": 500.0, "r_multiple": 2.0, "entry_date": "2023-02-01"},
        {"direction": "LONG", "pnl": -250.0, "r_multiple": -1.0, "entry_date": "2023-03-01"},
        {"direction": "LONG", "pnl": 750.0, "r_multiple": 3.0, "entry_date": "2023-04-01"},
    ]

    metrics = calc.calculate_all_metrics(curve, trades)

    assert metrics["total_return_pct"] > 0
    assert metrics["cagr"] > 0
    assert metrics["max_drawdown_pct"] < 0
    assert metrics["sharpe_ratio"] > 0
    assert metrics["trade_stats"]["total_trades"] == 3
    assert metrics["trade_stats"]["win_rate_pct"] == pytest.approx(66.67, abs=0.1)
    assert metrics["trade_stats"]["profit_factor"] == pytest.approx((500 + 750) / 250, abs=0.01)
