import pytest
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series


def test_yfinance_batch_fetch():
    fetcher = YFinanceFetcher(chunk_size=10)
    test_tickers = ["AAPL", "GC=F", "^GSPC"]
    data = fetcher.fetch_batch(test_tickers, timeframe="1D")

    assert len(data) >= 2  # At least 2 of 3 should always succeed live
    for sym in data:
        highs, lows, closes, price = data[sym]
        assert len(highs) >= 150
        assert price > 0.0

        # Verify Larsson Line can be computed cleanly
        v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
        assert states[-1] in ["GOLD", "BLUE", "NEUTRAL"]


def test_yfinance_weekly_fetch():
    fetcher = YFinanceFetcher(chunk_size=5)
    data = fetcher.fetch_batch(["AAPL"], timeframe="1W")
    assert "AAPL" in data
    highs, lows, closes, price = data["AAPL"]
    assert len(highs) >= 100
