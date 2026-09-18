import os
import tempfile
import pytest
from src.alerts.telegram import TelegramNotifier
from src.data.binance_fetch import BinanceFetcher
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import LarssonState
from src.scanner import LarssonScanner
from src.storage.database import Database


@pytest.fixture
def temp_scanner():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    notifier = TelegramNotifier()  # dry run mode
    b_fetcher = BinanceFetcher()
    yf_fetcher = YFinanceFetcher(chunk_size=5)
    scanner = LarssonScanner(db=db, binance_fetcher=b_fetcher, yf_fetcher=yf_fetcher, notifier=notifier)
    yield scanner
    scanner.db.close()
    if os.path.exists(db_path):
        os.remove(db_path)


def test_scanner_real_crypto_run(temp_scanner):
    test_symbols = ["BTCUSDT", "ETHUSDT"]
    res = temp_scanner.scan_crypto_symbols(test_symbols, timeframe="1D", delay_s=0.0)

    assert res["total_scanned"] == 2
    assert res["failed_count"] == 0
    assert len(res["state_changes"]) == 0
    assert (res["gold_count"] + res["blue_count"] + res["neutral_count"]) == 2

    states = temp_scanner.db.get_all_states()
    assert len(states) == 2
    tickers = [s["ticker"] for s in states]
    assert "BTCUSDT" in tickers
    assert "ETHUSDT" in tickers


def test_scanner_real_yfinance_run(temp_scanner):
    res = temp_scanner.scan_yfinance_assets(
        asset_class="commodities",
        tickers=["GC=F", "SI=F"],
        timeframe="1D",
    )
    assert res["total_scanned"] == 2
    assert res["failed_count"] == 0
    assert (res["gold_count"] + res["blue_count"] + res["neutral_count"]) == 2

    states = temp_scanner.db.get_all_states()
    tickers = [s["ticker"] for s in states]
    assert "GC=F" in tickers
    assert "SI=F" in tickers
