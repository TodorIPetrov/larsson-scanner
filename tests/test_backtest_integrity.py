"""
Tests for backtest mathematical integrity, zero-look-ahead causality,
data-quality guards, annualization accuracy, and profile merge preservation.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_master_universe_optimization import (
    analyze_v3_asset,
    evaluate_larsson_states,
    fast_compute_atr,
    fast_compute_smma,
    run_single_simulation_v3,
    validate_ohlcv_quality,
)
from scripts.run_portfolio_rotation_backtest import (
    prepare_causal_asset_frame,
    run_walk_forward_rotation,
)
from scripts.run_quantamental_value_lab import simulate_quantamental_strategy


def test_run_single_simulation_v3_zero_lookahead_and_stop_fill():
    """
    1. QUANTAMENTAL_ACCUMULATOR must NOT enter on bar k using closes[k] > v1[k-1].
    2. Intra-bar 15% stop must fill at min(curr_open, entry_price * 0.85), including gap-downs.
    """
    n = 80
    opens = np.full(n, 95.0)
    highs = np.full(n, 96.0)
    lows = np.full(n, 94.0)
    closes = np.full(n, 95.0)
    v1 = np.full(n, 100.0)
    v2 = np.full(n, 105.0)
    atr = np.full(n, 2.0)
    states = np.full(n, -1, dtype=np.int8)  # BLUE everywhere

    # Bar 70 has curr_close > v1[69], while closes[69] == 95 <= 100.
    # With end_idx=72, bar 71 is the last bar (i < n-1 skips bar 71).
    # Causal engine MUST NOT trigger entry on bar 70.
    closes[70] = 150.0
    highs[70] = 155.0

    res = run_single_simulation_v3(
        opens, highs, lows, closes, states, v1, v2, atr,
        strategy="QUANTAMENTAL_ACCUMULATOR",
        fundamental_bullish=True,
        start_idx=50,
        end_idx=72,
    )
    assert res["total_trades"] == 0
    assert res["total_return_pct"] == 0.0

    # Test intra-bar 15% stop fill (NOT filled at curr_open above the stop)
    opens2 = np.full(n, 100.0)
    highs2 = np.full(n, 101.0)
    lows2 = np.full(n, 99.0)
    closes2 = np.full(n, 100.0)
    states2 = np.zeros(n, dtype=np.int8)
    states2[50] = 1  # Enters 100% at opens2[51] = 100.0
    states2[51:] = 0  # NEUTRAL after entry so no second entry or BLUE exit occurs
    opens2[52] = 98.0
    lows2[52] = 80.0  # Breaches 85.0 intra-bar stop

    res_stop = run_single_simulation_v3(
        opens2, highs2, lows2, closes2, states2, v1, v2, atr,
        strategy="QUANTAMENTAL_ACCUMULATOR",
        fundamental_bullish=True,
        start_idx=50,
        end_idx=65,
    )
    assert res_stop["total_trades"] == 1
    assert res_stop["total_return_pct"] < -14.0

    # Test gap-down below stop fills at curr_open (75.0), not stop level (85.0)
    opens2[52] = 75.0
    lows2[52] = 74.0
    res_gap = run_single_simulation_v3(
        opens2, highs2, lows2, closes2, states2, v1, v2, atr,
        strategy="QUANTAMENTAL_ACCUMULATOR",
        fundamental_bullish=True,
        start_idx=50,
        end_idx=65,
    )
    assert res_gap["total_trades"] == 1
    assert res_gap["total_return_pct"] < -24.0


def test_quantamental_value_lab_zero_lookahead_and_gap_stop():
    """
    Verifies V3_CAPITULATION_S1 uses strictly t-1 prices for stop calculation and 12% structural exit,
    and executes gap-down stops at min(curr_open, stop_loss).
    """
    n = 230
    opens = np.full(n, 100.0)
    highs = np.full(n, 102.0)
    lows = np.full(n, 98.0)
    closes = np.full(n, 100.0)
    states = np.full(n, -1, dtype=np.int8)
    v1 = np.full(n, 105.0)
    v2 = np.full(n, 110.0)
    sma200 = np.full(n, 105.0)
    atr = np.full(n, 2.0)
    rsi = np.full(n, 40.0)

    # Trigger V3 entry on bar 205 (prev_rsi = rsi[204] >= 32 and rsi[203] < 30)
    rsi[203] = 28.0
    rsi[204] = 33.0
    lows[204] = 94.0  # Causal stop = 94 - 1.5*2 = 91.0

    # Bar 206 dips to 92.5 (above 91.0 causal stop), then recovers to 130.0
    lows[206] = 92.5
    closes[206:] = 130.0
    opens[207:] = 130.0

    # Perturbing lows[205] between 99.0 and 93.0 MUST NOT alter the entry stop or exit
    lows_a = lows.copy()
    lows_a[205] = 99.0
    res_a = simulate_quantamental_strategy(
        "V3_CAPITULATION_S1", opens, highs, lows_a, closes, states, v1, v2, sma200, atr, rsi, start_idx=200
    )

    lows_b = lows.copy()
    lows_b[205] = 93.0
    res_b = simulate_quantamental_strategy(
        "V3_CAPITULATION_S1", opens, highs, lows_b, closes, states, v1, v2, sma200, atr, rsi, start_idx=200
    )
    assert res_a == res_b
    assert res_a["total_return_pct"] > 10.0

    # Test 12% close breach triggers at bar 207 open (85.0), NOT bar 206 open (95.0)
    opens_c = np.full(n, 100.0)
    lows_c = np.full(n, 98.0)
    closes_c = np.full(n, 100.0)
    lows_c[204] = 75.0  # Stop = 72.0 (won't hit intra-bar)
    opens_c[206] = 95.0
    lows_c[206] = 86.0
    closes_c[206] = 86.0  # < 88.0 triggers exit at bar 207 open
    opens_c[207:] = 85.0
    closes_c[207:] = 85.0

    res_exit = simulate_quantamental_strategy(
        "V3_CAPITULATION_S1", opens_c, highs, lows_c, closes_c, states, v1, v2, sma200, atr, rsi, start_idx=200
    )
    assert res_exit["trades"] == 1
    assert res_exit["total_return_pct"] < -6.0  # 50% tranche losing ~15.2% -> ~-7.6%

    # Test gap-down stop fill at 60.0 (50% tranche losing ~40.1% -> ~-20.0%)
    opens_c[206] = 60.0
    lows_c[206] = 59.0
    res_gap = simulate_quantamental_strategy(
        "V3_CAPITULATION_S1", opens_c, highs, lows_c, closes_c, states, v1, v2, sma200, atr, rsi, start_idx=200
    )
    assert res_gap["total_return_pct"] < -18.0


def test_annualization_365_vs_252_days():
    """Crypto (365d) and equity (252d) annualization scale CAGR and Sharpe accurately."""
    n = 300
    idx = np.arange(n, dtype=np.float64)
    closes = 100.0 * np.exp(0.001 * idx + 0.02 * np.sin(idx * 0.3))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.01
    lows = np.minimum(opens, closes) * 0.99
    hl2 = (highs + lows) / 2.0
    v1 = fast_compute_smma(hl2, 15)
    m1 = fast_compute_smma(hl2, 19)
    m2 = fast_compute_smma(hl2, 25)
    v2 = fast_compute_smma(hl2, 29)
    states = evaluate_larsson_states(v1, m1, m2, v2)
    atr = fast_compute_atr(highs, lows, closes, 14)

    r_252 = run_single_simulation_v3(
        opens, highs, lows, closes, states, v1, v2, atr, "CLASSIC_BLUE_EXIT", start_idx=50, ann_days=252.0
    )
    r_365 = run_single_simulation_v3(
        opens, highs, lows, closes, states, v1, v2, atr, "CLASSIC_BLUE_EXIT", start_idx=50, ann_days=365.0
    )
    assert r_252["total_return_pct"] == r_365["total_return_pct"]
    assert r_365["cagr_pct"] > r_252["cagr_pct"]
    assert r_365["sharpe_ratio"] == pytest.approx(r_252["sharpe_ratio"] * np.sqrt(365.0 / 252.0), abs=0.05)


def test_validate_ohlcv_quality_guards():
    """Rejects stale/flat feeds (<50 unique closes), short histories, and flags extreme jumps."""
    dates = pd.date_range("2022-01-01", periods=200, freq="B").strftime("%Y-%m-%d")

    # 1. Stale/flat feed (12 unique values like ZNC=F)
    flat_closes = [3000.0 + (i % 12) * 10.0 for i in range(200)]
    df_stale = pd.DataFrame({
        "date": dates, "open": flat_closes, "high": flat_closes, "low": flat_closes, "close": flat_closes,
    })
    ok_stale, reason_stale = validate_ohlcv_quality(df_stale)
    assert ok_stale is False
    assert reason_stale == "STALE_PRICES"

    # 2. Insufficient bars
    ok_short, reason_short = validate_ohlcv_quality(df_stale.iloc[:100])
    assert ok_short is False
    assert reason_short == "INSUFFICIENT_BARS"

    # 3. Normal trending feed
    trend_closes = [100.0 + i * 0.5 for i in range(200)]
    df_ok = pd.DataFrame({
        "date": dates, "open": trend_closes, "high": trend_closes, "low": trend_closes, "close": trend_closes,
    })
    ok_good, reason_good = validate_ohlcv_quality(df_ok)
    assert ok_good is True
    assert reason_good == "OK"

    # 4. Extreme >200% daily jump
    df_jump = df_ok.copy()
    df_jump.loc[150, "close"] = df_jump.loc[149, "close"] * 4.5
    ok_j, reason_j = validate_ohlcv_quality(df_jump)
    assert ok_j is True
    assert reason_j == "EXTREME_JUMP_OR_SPLIT"


def test_walk_forward_rotation_synthetic_causality():
    """Walk-forward rotation runs causally on synthetic data without reading profile files."""
    dates = pd.date_range("2022-01-01", periods=220, freq="B").strftime("%Y-%m-%d")
    idx = np.arange(220, dtype=np.float64)
    c1 = 100.0 * np.exp(0.002 * idx)
    c2 = 50.0 * np.exp(0.001 * idx + 0.03 * np.sin(idx * 0.15))

    def _mk(c):
        return pd.DataFrame({
            "date": dates,
            "open": c * 0.999,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
        })

    ds = {
        "SYNTH_AI": prepare_causal_asset_frame(_mk(c1), "SYNTH_AI", "ai_stocks"),
        "SYNTH_BTC": prepare_causal_asset_frame(_mk(c2), "SYNTH_BTC", "crypto"),
    }
    cal = sorted(set(ds["SYNTH_AI"]["dates"][80:]))
    res = run_walk_forward_rotation(ds, cal, max_positions=2, initial_capital=100000.0)
    assert res["final_equity"] > 100000.0
    assert res["total_return_pct"] > 0.0
    assert res["max_drawdown_pct"] >= 0.0
    assert res["sharpe_ratio"] > 0.0


def test_production_artifacts_remediation_integrity():
    """Verifies ZNC=F removal, preserved live/mega-exit/value keys, new OOS fields, and preserved Wilson report."""
    profiles_path = os.path.join(PROJECT_ROOT, "data", "asset_optimal_profiles.json")
    assets_path = os.path.join(PROJECT_ROOT, "config", "assets.yaml")
    report_path = os.path.join(PROJECT_ROOT, "research", "QUANTAMENTAL_VALUE_REPORT.md")

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert "ZNC=F" not in profiles
    assert "ZNC=F" not in open(assets_path, "r", encoding="utf-8").read()

    for sym in ("NVDA", "GOOGL"):
        p = profiles[sym]
        assert "optimal_exit_policy" in p
        assert "optimal_climax_mayer" in p
        assert "latest_sma200" in p
        assert "ribbon_state" in p
        assert "value_dip_allowed" in p

    btc = profiles["BTCUSDT"]
    assert btc.get("optimal_exit_policy") == "F1_FAST_SILVER"
    assert "latest_sma200" in btc

    for sym in ("NVDA", "GOOGL", "BTCUSDT", "PLTR", "GC=F"):
        p = profiles[sym]
        for k in (
            "bnh_sharpe_ratio",
            "bnh_max_drawdown_pct",
            "sharpe_vs_bnh",
            "dd_saved_vs_bnh",
            "oos_return_pct",
            "oos_sharpe_ratio",
            "annualized_vol_pct",
        ):
            assert k in p, f"Missing {k} on {sym}"

    report_txt = open(report_path, "r", encoding="utf-8").read()
    assert "Wilson" in report_txt
