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


def test_calculate_bars_since_flip_logic():
    from src.scanner import calculate_bars_since_flip
    from src.engine.smma import LarssonState

    # Empty / short series
    assert calculate_bars_since_flip([]) is None
    assert calculate_bars_since_flip([LarssonState.GOLD]) is None

    # Just flipped on latest bar (0 bars elapsed)
    states_0 = [LarssonState.BLUE, LarssonState.NEUTRAL, LarssonState.GOLD]
    assert calculate_bars_since_flip(states_0) == 0

    # Flipped 1 bar ago
    states_1 = [LarssonState.BLUE, LarssonState.GOLD, LarssonState.GOLD]
    assert calculate_bars_since_flip(states_1) == 1

    # Flipped 3 bars ago
    states_3 = [LarssonState.NEUTRAL, LarssonState.GOLD, LarssonState.GOLD, LarssonState.GOLD, LarssonState.GOLD]
    assert calculate_bars_since_flip(states_3) == 3

    # Sustained trend that never changed
    states_sustained = [LarssonState.GOLD] * 50
    assert calculate_bars_since_flip(states_sustained) == 50


def test_database_bars_since_flip_persistence(temp_scanner):
    db = temp_scanner.db
    db.upsert_symbols([("NVDA", "us_stocks", "NASDAQ:NVDA")])
    
    # Store NVDA with 34 bars since flip
    db.update_state(
        ticker="NVDA",
        timeframe="1D",
        v1=120.0,
        m1=118.0,
        m2=116.0,
        v2=114.0,
        new_state=LarssonState.GOLD,
        price=122.0,
        bars_since_flip=34,
    )
    
    row = db.get_current_state("NVDA", "1D")
    assert row is not None
    assert row["bars_since_flip"] == 34
    
    all_rows = db.get_all_states()
    nvda_row = next(r for r in all_rows if r["ticker"] == "NVDA")
    assert nvda_row["bars_since_flip"] == 34

