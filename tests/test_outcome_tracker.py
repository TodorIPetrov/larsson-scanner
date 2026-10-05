"""
Unit tests for Alert Outcome Tracker & Compounding Track Record (src/engine/outcome_tracker.py).
Verifies alert logging in SQLite, forward simulation of price bars, stopped-out triggers,
time-expired evaluation, and track record metric aggregation.
"""

import os
import tempfile
import numpy as np
import pandas as pd
import pytest

from src.engine.outcome_tracker import AlertOutcomeTracker


class TestAlertOutcomeTracker:
    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def test_log_and_load_alert(self, temp_db):
        tracker = AlertOutcomeTracker(db_path=temp_db)
        alert_id = tracker.log_alert(
            ticker="BTCUSDT",
            timeframe="1D",
            asset_class="crypto",
            transition_type="NEUTRAL_TO_GOLD",
            entry_price=65000.0,
            invalidation_price=62000.0,
            time_stop_bars=60,
        )

        assert alert_id is not None
        records = tracker.load_all_records()
        assert len(records) == 1
        assert records[0]["ticker"] == "BTCUSDT"
        assert records[0]["entry_price"] == 65000.0
        assert records[0]["invalidation_price"] == 62000.0
        assert records[0]["current_status"] == "OPEN"

    def test_evaluate_stopped_out_scenario(self, temp_db):
        tracker = AlertOutcomeTracker(db_path=temp_db)
        tracker.log_alert(
            ticker="ETHUSDT",
            timeframe="1D",
            asset_class="crypto",
            transition_type="NEUTRAL_TO_GOLD",
            entry_price=3000.0,
            invalidation_price=2800.0,
            time_stop_bars=60,
        )
        record = tracker.load_all_records()[0]

        # Simulate subsequent 5 bars where bar 3 drops to 2750 (violating 2800 SL)
        future_df = pd.DataFrame({
            "high": [3050.0, 3100.0, 2900.0, 2700.0, 2650.0],
            "low": [2950.0, 2900.0, 2750.0, 2600.0, 2550.0],
            "close": [3020.0, 2950.0, 2780.0, 2620.0, 2580.0],
        })

        updated = tracker.evaluate_alert_bars(record, future_df)
        assert updated["current_status"] == "STOPPED_OUT"
        assert updated["bars_elapsed"] == 3
        # Realized return: (2800 - 3000) / 3000 * 100 = -6.67%
        assert updated["realized_return_pct"] == pytest.approx(-6.67, 0.05)
        assert updated["mfe_pct"] > 3.0  # High hit 3100 on bar 2

        # Save and verify
        saved = tracker.save_evaluated_record(updated)
        assert saved is True

        reloaded = tracker.load_all_records(status_filter="STOPPED_OUT")
        assert len(reloaded) == 1
        assert reloaded[0]["current_status"] == "STOPPED_OUT"

    def test_evaluate_time_expired_scenario(self, temp_db):
        tracker = AlertOutcomeTracker(db_path=temp_db)
        tracker.log_alert(
            ticker="NVDA",
            timeframe="1D",
            asset_class="stocks",
            transition_type="NEUTRAL_TO_GOLD",
            entry_price=100.0,
            invalidation_price=90.0,
            time_stop_bars=5,
        )
        record = tracker.load_all_records()[0]

        # 5 bars without hitting 90 SL, ending at 115
        future_df = pd.DataFrame({
            "high": [105.0, 108.0, 110.0, 114.0, 118.0],
            "low": [98.0, 102.0, 105.0, 107.0, 112.0],
            "close": [103.0, 106.0, 109.0, 112.0, 115.0],
        })

        updated = tracker.evaluate_alert_bars(record, future_df)
        assert updated["current_status"] == "TIME_EXPIRED"
        assert updated["bars_elapsed"] == 5
        # Realized return: (115 - 100) / 100 * 100 = +15.0%
        assert updated["realized_return_pct"] == pytest.approx(15.0, 0.01)
        assert updated["mfe_pct"] == pytest.approx(18.0, 0.01)

        tracker.save_evaluated_record(updated)

        metrics = tracker.calculate_track_record_metrics()
        assert metrics["total_alerts"] == 1
        assert metrics["closed_count"] == 1
        assert metrics["win_rate"] == 100.0
        assert metrics["mean_return_pct"] == 15.0
        assert metrics["profit_factor"] == 99.0

        tg_summary = tracker.format_track_record_telegram()
        assert "AUDITED TRACK RECORD" in tg_summary
        assert "100.0%" in tg_summary
