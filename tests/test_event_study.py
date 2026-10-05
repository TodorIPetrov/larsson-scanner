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
    lookup_base_rate,
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
        assert "[QUANT AUDIT] LARSSON SCANNER: REALISTIC LIVE-RULE BASE RATES" in report
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
