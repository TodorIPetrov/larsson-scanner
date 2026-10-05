"""
Unit tests for Data Health Guard & Feed Integrity Engine (src/data/health_guard.py).
Verifies detection of stale feeds, empty datasets, missing price columns, and valid fresh feeds.
"""

from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest

from src.data.health_guard import DataHealthGuard, DataHealthResult


def _make_dummy_ohlcv(n_bars: int = 50, end_hours_ago: float = 2.0) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    end_time = now - timedelta(hours=end_hours_ago)
    dates = [
        (end_time - timedelta(days=n_bars - 1 - i)).strftime("%Y-%m-%d %H:%M:%S")
        for i in range(n_bars)
    ]
    return pd.DataFrame({
        "date": dates,
        "open": [100.0 + i for i in range(n_bars)],
        "high": [102.0 + i for i in range(n_bars)],
        "low": [99.0 + i for i in range(n_bars)],
        "close": [101.0 + i for i in range(n_bars)],
        "volume": [1000.0 for _ in range(n_bars)],
    })


class TestDataHealthGuard:
    def test_empty_dataset(self):
        guard = DataHealthGuard()
        res = guard.validate_ohlcv(pd.DataFrame(), symbol="EMPTY_TEST")
        assert res.is_healthy is False
        assert "EMPTY_DATASET" in res.issues

    def test_missing_columns(self):
        guard = DataHealthGuard()
        df = pd.DataFrame({"price": [100.0, 101.0]})
        res = guard.validate_ohlcv(df, symbol="MISSING_COLS")
        assert res.is_healthy is False
        assert "MISSING_PRICE_COLUMNS" in res.issues

    def test_fresh_feed_passes(self):
        guard = DataHealthGuard()
        # 50 bars, last candle is 2 hours old
        df = _make_dummy_ohlcv(n_bars=50, end_hours_ago=2.0)
        res = guard.validate_ohlcv(df, symbol="BTCUSDT", timeframe="1D", asset_class="crypto")
        assert res.is_healthy is True
        assert len(res.issues) == 0
        assert res.age_hours <= 5.0

    def test_stale_crypto_feed_blocked(self):
        guard = DataHealthGuard(max_stale_hours_crypto_1d=36.0)
        # Last candle is 50 hours old
        df = _make_dummy_ohlcv(n_bars=50, end_hours_ago=50.0)
        res = guard.validate_ohlcv(df, symbol="BTCUSDT", timeframe="1D", asset_class="crypto")
        assert res.is_healthy is False
        assert "STALE_DATA_FEED" in res.issues
        assert "Feed failed health checks" in res.warning_message

    def test_stale_crypto_4h_feed_blocked(self):
        guard = DataHealthGuard(max_stale_hours_crypto_4h=8.0)
        # Last candle is 12 hours old
        df = _make_dummy_ohlcv(n_bars=50, end_hours_ago=12.0)
        res = guard.validate_ohlcv(df, symbol="SOLUSDT", timeframe="4H", asset_class="crypto")
        assert res.is_healthy is False
        assert "STALE_DATA_FEED" in res.issues
