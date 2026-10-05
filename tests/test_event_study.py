"""
Unit tests for Event Study and Base Rates Validation Engine.
Verifies detection of state transitions, forward return calculations,
MFE/MAE tracking, and statistical base-rate aggregation.
"""

import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest

from src.backtest.event_study import (
    BaseRateMetrics,
    EventStudyEngine,
    TransitionEvent,
    calendar_block_bootstrap,
    lookup_base_rate,
    simulate_multi_exit_policy,
)


def _generate_synthetic_ohlcv(n_bars: int = 300) -> pd.DataFrame:
    """Generates synthetic trend and pullback price series."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="D").strftime("%Y-%m-%d").tolist()

    # Create distinct regimes: Flat -> Strong Uptrend -> Downtrend
    prices = [100.0]
    for i in range(1, n_bars):
        if i < 80:
            drift = 0.01 * np.random.randn()
        elif i < 180:
            drift = 0.8 + 0.3 * np.random.randn()  # Strong rally (triggers GOLD)
        else:
            drift = -0.9 + 0.3 * np.random.randn()  # Sharp selloff (triggers BLUE)
        prices.append(max(10.0, prices[-1] + drift))

    prices = np.array(prices)
    highs = prices + np.random.uniform(0.5, 2.0, size=n_bars)
    lows = prices - np.random.uniform(0.5, 2.0, size=n_bars)
    closes = prices + np.random.uniform(-0.5, 0.5, size=n_bars)
    opens = prices - np.random.uniform(-0.5, 0.5, size=n_bars)
    volumes = np.random.uniform(1000, 5000, size=n_bars)

    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


class TestEventStudyEngine:
    def test_detect_events_for_asset(self):
        engine = EventStudyEngine(horizons=[5, 10, 20], cost_bps=10.0, min_warmup=60)
        df = _generate_synthetic_ohlcv(250)

        events = engine.detect_events_for_asset(
            symbol="TEST_ASSET",
            df=df,
            asset_class="crypto",
            timeframe="1D",
        )

        assert len(events) > 0
        for ev in events:
            assert isinstance(ev, TransitionEvent)
            assert ev.symbol == "TEST_ASSET"
            assert ev.asset_class == "crypto"
            assert ev.timeframe == "1D"
            assert ev.prev_state != ev.new_state
            assert ev.transition_type == f"{ev.prev_state}_TO_{ev.new_state}"
            assert ev.entry_price > 0

            # Verify forward returns populated
            for h in [5, 10, 20]:
                if h in ev.forward_returns:
                    assert isinstance(ev.forward_returns[h], float)
                    assert isinstance(ev.forward_mfe[h], float)
                    assert isinstance(ev.forward_mae[h], float)
                    assert ev.forward_mfe[h] >= ev.forward_mae[h]

    def test_calculate_base_rates(self):
        engine = EventStudyEngine(horizons=[5, 10], cost_bps=10.0, min_warmup=60)
        df = _generate_synthetic_ohlcv(250)
        events = engine.detect_events_for_asset("TEST_SYM", df, "stocks", "1D")

        metrics = engine.calculate_base_rates(events, group_by_asset_class=True)
        assert len(metrics) > 0

        for m in metrics:
            assert isinstance(m, BaseRateMetrics)
            assert m.sample_size > 0
            assert 0.0 <= m.win_rate <= 1.0
            assert m.profit_factor >= 0.0
            assert m.edge_ratio >= 0.0
            assert isinstance(m.statistically_significant, bool)

    def test_export_base_rates_json(self):
        engine = EventStudyEngine(horizons=[5], cost_bps=10.0)
        df = _generate_synthetic_ohlcv(200)
        events = engine.detect_events_for_asset("TEST_JSON", df, "crypto", "1D")
        metrics = engine.calculate_base_rates(events, group_by_asset_class=False)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            exported_path = engine.export_base_rates_json(metrics, filepath=tmp_path)
            assert os.path.exists(exported_path)

            with open(exported_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert isinstance(data, list)
            if metrics:
                assert "transition_type" in data[0]
                assert "win_rate" in data[0]
                assert "profit_factor" in data[0]
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_format_terminal_report(self):
        engine = EventStudyEngine(horizons=[5, 20], cost_bps=10.0)
        df = _generate_synthetic_ohlcv(220)
        events = engine.detect_events_for_asset("REPORT_TEST", df, "crypto", "1D")
        metrics = engine.calculate_base_rates(events, group_by_asset_class=True)

        report = engine.format_terminal_report(metrics)
        assert "[QUANT AUDIT] LARSSON SCANNER" in report
        assert "Transition" in report
        assert "Live WinRate" in report
        assert "Excess Alpha" in report

    def test_benjamini_hochberg_correction(self):
        from src.backtest.event_study import benjamini_hochberg_correction
        p_vals = [0.01, 0.04, 0.03, 0.20]
        adj = benjamini_hochberg_correction(p_vals)
        assert len(adj) == 4
        # FDR adjusted p-values are monotonic with respect to sorted ranks
        assert adj[0] <= adj[2] <= adj[1] <= adj[3]
        # Empty case
        assert benjamini_hochberg_correction([]) == []

    def test_live_rule_and_benchmark_excess(self):
        engine = EventStudyEngine(horizons=[5, 20], cost_bps=10.0)
        df = _generate_synthetic_ohlcv(250)
        benchmark_df = _generate_synthetic_ohlcv(250)

        events = engine.detect_events_for_asset(
            "TEST_SYM", df, "stocks", "1D", benchmark_df=benchmark_df
        )
        assert len(events) > 0
        ev = events[0]
        assert ev.live_rule_returns is not None
        assert ev.excess_returns is not None
        for h in [5, 20]:
            if h in ev.live_rule_returns:
                assert isinstance(ev.live_rule_returns[h], float)
            if h in ev.excess_returns:
                assert isinstance(ev.excess_returns[h], float)

    def test_lookup_base_rate(self):
        engine = EventStudyEngine(horizons=[10], cost_bps=10.0)
        df = _generate_synthetic_ohlcv(220)
        events = engine.detect_events_for_asset("TEST_LOOKUP", df, "crypto", "1D")
        metrics = engine.calculate_base_rates(events, group_by_asset_class=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            engine.export_base_rates_json(metrics, filepath=tmp_path)
            if metrics:
                target_type = metrics[0].transition_type
                target_class = metrics[0].asset_class
                record = lookup_base_rate(target_type, asset_class=target_class, timeframe="1D", horizon=10, filepath=tmp_path)
                assert record is not None
                assert record["transition_type"] == target_type
                assert record["asset_class"] == target_class
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_simulate_multi_exit_gap_down(self):
        # Entry at 100, SL at 95 (Stop distance = 5).
        # Bar 1 opens at 93 (gap down through 95).
        entry = 100.0
        sl = 95.0
        tp1 = 109.0
        opens = np.array([100.0, 93.0, 92.0])
        highs = np.array([101.0, 94.0, 93.0])
        lows = np.array([99.0, 91.0, 90.0])
        closes = np.array([100.0, 92.0, 91.0])
        trailing = np.array([95.0, 95.0, 95.0])

        sim = simulate_multi_exit_policy(
            entry_price=entry,
            initial_sl=sl,
            tp1=tp1,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            trailing_stops=trailing,
            start_idx=0,
            horizon=2,
            asset_class="crypto",
        )

        assert sim["exit1_reason"] == "GAP_DISASTER_STOP"
        assert sim["exit2_reason"] == "GAP_DISASTER_STOP"
        assert sim["exit1_price"] == 93.0  # Filled at open (min(open, SL))
        # Raw R = (93 - 100) / 5 = -7 / 5 = -1.40R
        assert sim["raw_r"] == -1.4
        # Net R includes friction, so net_r < -1.40R
        assert sim["net_r"] < -1.40

    def test_simulate_multi_exit_ambiguous_bar(self):
        # Entry at 100, SL at 95, TP1 at 105.
        # Bar 1 has High = 106 (touches TP1) and Low = 94 (touches SL).
        # Opus rule: SL must fire FIRST.
        entry = 100.0
        sl = 95.0
        tp1 = 105.0
        opens = np.array([100.0, 100.0])
        highs = np.array([100.0, 106.0])
        lows = np.array([100.0, 94.0])
        closes = np.array([100.0, 102.0])
        trailing = np.array([95.0, 95.0])

        sim = simulate_multi_exit_policy(
            entry_price=entry,
            initial_sl=sl,
            tp1=tp1,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            trailing_stops=trailing,
            start_idx=0,
            horizon=1,
            asset_class="crypto",
        )

        assert sim["exit1_reason"] == "AMBIGUOUS_BAR_SL_FIRST"
        assert sim["exit2_reason"] == "AMBIGUOUS_BAR_SL_FIRST"
        assert sim["exit1_price"] == 95.0
        assert sim["raw_r"] == -1.0

    def test_simulate_multi_exit_next_open_execution(self):
        # Entry at 100, SL at 90, TP1 at 120.
        # Bar 1: Closes at 93 < trailing stop 94 (fires signal).
        # Bar 2: Opens at 91 -> Execution happens at Bar 2 Open (91.0), not Bar 1 Close.
        entry = 100.0
        sl = 90.0
        tp1 = 120.0
        opens = np.array([100.0, 98.0, 91.0])
        highs = np.array([101.0, 99.0, 92.0])
        lows = np.array([99.0, 92.0, 89.0])
        closes = np.array([100.0, 93.0, 90.0])
        trailing = np.array([94.0, 94.0, 94.0])

        sim = simulate_multi_exit_policy(
            entry_price=entry,
            initial_sl=sl,
            tp1=tp1,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            trailing_stops=trailing,
            start_idx=0,
            horizon=2,
            asset_class="crypto",
        )

        assert sim["exit2_reason"] == "TRAIL_NEXT_OPEN"
        assert sim["exit1_reason"] == "TRAIL_FALLBACK_NEXT_OPEN"
        assert sim["exit2_price"] == 91.0
        assert sim["exit1_price"] == 91.0

    def test_calendar_block_bootstrap(self):
        # Multiple events across calendar dates
        dates = [
            "2023-01-05", "2023-01-15", "2023-01-20",  # Block 0 (within 60 days)
            "2023-03-20", "2023-04-01",                # Block 1
            "2023-06-10", "2023-06-25",                # Block 2
            "2023-09-01", "2023-09-15",                # Block 3
        ]
        r_multiples = [0.5, 0.4, 0.6, 1.2, 0.8, -0.5, -0.3, 0.9, 1.1]

        boot = calendar_block_bootstrap(dates, r_multiples, block_days=60, n_resamples=1000)
        assert boot["effective_n"] >= 4
        assert boot["mean_r"] > 0
        assert boot["ci_lower_r"] <= boot["mean_r"] <= boot["ci_upper_r"]
