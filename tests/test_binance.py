import pytest
from src.data.binance_fetch import BinanceFetcher


def test_binance_fetch_top_pairs():
    fetcher = BinanceFetcher()
    pairs = fetcher.get_top_usdt_pairs(limit=10)
    assert len(pairs) > 0
    assert "BTCUSDT" in pairs


def test_binance_fetch_klines():
    fetcher = BinanceFetcher()
    res = fetcher.fetch_klines("BTCUSDT", "1D", limit=160)
    assert res is not None
    highs, lows, closes, latest_price = res
    assert len(highs) >= 150
    assert len(lows) == len(highs)
    assert latest_price > 0.0
