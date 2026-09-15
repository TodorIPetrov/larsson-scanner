import os
import pytest
from src.data.sp500_loader import load_sp500_tickers, LOCAL_CACHE_PATH


def test_sp500_loader():
    tickers = load_sp500_tickers(refresh=True, limit=25)
    assert len(tickers) == 25
    assert "ABBV" in tickers or "ADBE" in tickers
    assert os.path.exists(LOCAL_CACHE_PATH)

    # Test reading from cache
    cached = load_sp500_tickers(refresh=False)
    assert len(cached) >= 400
    assert "AAPL" in cached
    assert "MSFT" in cached
