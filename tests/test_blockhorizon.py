"""
Unit tests for BlockHorizon Data Fetcher and CSV Ingestion Engine.
"""

import os
import tempfile
import pytest

from src.data.blockhorizon_fetch import (
    BlockHorizonFetcher,
    canonicalize_metric_name,
    parse_date_string,
)
from src.storage.database import Database


@pytest.fixture
def memory_db():
    return Database(":memory:")


def test_canonicalize_metric_name():
    assert canonicalize_metric_name("MVRV-Z") == "mvrv_z"
    assert canonicalize_metric_name("Cycle Signal") == "cycle_signal"
    assert canonicalize_metric_name("Puell Multiple") == "puell_multiple"
    assert canonicalize_metric_name("Net Unrealized Profit/Loss") == "nupl"
    assert canonicalize_metric_name("FNG") == "fear_and_greed"
    assert canonicalize_metric_name("custom_indicator") == "custom_indicator"


def test_parse_date_string():
    assert parse_date_string("2026-10-05") == "2026-10-05"
    assert parse_date_string("2026-10-05T14:30:00Z") == "2026-10-05"
    assert parse_date_string("05/10/2026") == "2026-10-05"
    assert parse_date_string("20261005") == "2026-10-05"
    assert parse_date_string("") is None
    assert parse_date_string("invalid_date") is None


def test_import_wide_format_csv(memory_db):
    csv_content = """Date,Cycle Signal,MVRV-Z,NUPL,Puell Multiple
2026-10-01,72.5,2.45,0.48,1.35
2026-10-02,74.0,2.55,0.51,1.42
2026-10-03,78.2,2.80,0.55,1.55
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "blockhorizon_wide.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        fetcher = BlockHorizonFetcher(db=memory_db, csv_dir=tmpdir)
        count = fetcher.import_csv_file(csv_path)
        assert count == 12  # 3 days * 4 metrics

        latest = memory_db.get_latest_onchain_metrics()
        assert latest["cycle_signal"] == 78.2
        assert latest["mvrv_z"] == 2.80
        assert latest["nupl"] == 0.55
        assert latest["puell_multiple"] == 1.55


def test_import_long_format_csv(memory_db):
    csv_content = """Date,Metric,Value
2026-10-01,Cycle Signal,65.0
2026-10-01,MVRV-Z,1.90
2026-10-02,Cycle Signal,67.5
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "blockhorizon_long.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        fetcher = BlockHorizonFetcher(db=memory_db, csv_dir=tmpdir)
        count = fetcher.import_csv_file(csv_path)
        assert count == 3

        history = memory_db.get_onchain_metrics("cycle_signal")
        assert len(history) == 2
        assert history[0]["value"] == 65.0
        assert history[1]["value"] == 67.5


def test_sync_auto_import_and_latest(memory_db):
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "signals.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("Date,cycle_signal\n2026-10-05,55.0\n")

        fetcher = BlockHorizonFetcher(db=memory_db, csv_dir=tmpdir)
        summary = fetcher.sync(source_preference="csv")
        assert summary["csv_records_imported"] == 1
        assert summary["latest_metrics_count"] >= 1

        latest = memory_db.get_latest_onchain_metrics()
        assert latest.get("cycle_signal") == 55.0
