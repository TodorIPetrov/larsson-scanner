"""
Tests for X (Twitter) Monitor & NoLimits Recommendation Extraction.
"""

import pytest
from src.data.x_monitor import XMonitor
from src.storage.database import Database


def test_extract_tickers():
    text1 = "Страхотен отчет за $NVDA и $PLTR днес! Очаквам продължение."
    assert XMonitor.extract_tickers(text1) == ["NVDA", "PLTR"]

    text2 = "Отворих long TSLA на нива около $210. Също купувам BABA за дългосрочно."
    res2 = XMonitor.extract_tickers(text2)
    assert "TSLA" in res2
    assert "BABA" in res2

    # Verify acronyms like $USD, $CEO, $AI are ignored
    text3 = "Говорих с $CEO на фирмата, инвестират $100M в $AI и държат $USD в резерв. Харесвам само $SOUN."
    assert XMonitor.extract_tickers(text3) == ["SOUN"]


def test_x_monitor_db_integration(tmp_path):
    db_file = str(tmp_path / "x_test.db")
    db = Database(db_file)

    class MockAssetManager:
        def __init__(self):
            self.added = []

        def add_asset(self, ticker, asset_class=None, scan_now=True):
            self.added.append(ticker)
            return True, "Added", {"ticker": ticker, "name": f"{ticker} Corp", "price": 100.0, "state": "GOLD", "asset_class": "us_stocks"}

    mock_mgr = MockAssetManager()
    monitor = XMonitor(db=db, asset_manager=mock_mgr)

    tweet = "Нова топ позиция: $ARM и $CELH за следващите месеци!"
    results = monitor.process_tweet(tweet, tweet_id="tweet_12345", source_account="NoLimits")

    assert len(results) == 2
    tickers = [r["ticker"] for r in results]
    assert "ARM" in tickers
    assert "CELH" in tickers
    assert "ARM" in mock_mgr.added
    assert "CELH" in mock_mgr.added

    # Check DB table
    recs = db.get_x_recommendations()
    assert len(recs) == 2
    rec_tickers = [r["ticker"] for r in recs]
    assert "ARM" in rec_tickers
    assert "CELH" in rec_tickers


def test_add_historical_recommendations(tmp_path):
    db_file = str(tmp_path / "x_hist_test.db")
    db = Database(db_file)

    class MockAssetManager:
        def add_asset(self, ticker, asset_class=None, scan_now=True):
            if ticker == "EXISTING":
                return False, "Активът вече съществува в системата.", None
            return True, "Added", {"ticker": ticker, "name": f"{ticker} Inc"}

    monitor = XMonitor(db=db, asset_manager=MockAssetManager())
    res = monitor.add_historical_recommendations(["EXISTING", "NEW1", "NEW2"], source_account="NoLimits")

    assert len(res["added"]) == 2
    assert len(res["already_tracked"]) == 1
    assert "EXISTING" in res["already_tracked"]
