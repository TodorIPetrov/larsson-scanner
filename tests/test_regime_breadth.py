"""
Unit tests for Cross-Asset Regime Breadth Index Engine.
Verifies calculation of aggregate breadth, sector breakdowns, macro regime
classifications, SQLite persistence, and Telegram formatters.
"""

import os
import tempfile
import pytest

from src.engine.regime_breadth import (
    RegimeBreadthEngine,
    RegimeBreadthSnapshot,
    SectorBreadth,
)


class TestRegimeBreadthEngine:
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

    def test_classify_macro_regime(self, temp_db):
        engine = RegimeBreadthEngine(db_path=temp_db)

        # 1. Broad Liquidity Drain (Bear market)
        assert engine.classify_macro_regime(global_gold=15.0, global_blue=65.0) == "BROAD_LIQUIDITY_DRAIN"

        # 2. Aggressive Risk-On (Equities + Crypto both booming)
        assert engine.classify_macro_regime(
            global_gold=70.0, global_blue=10.0, crypto_gold=65.0, equities_gold=75.0
        ) == "AGGRESSIVE_RISK_ON"

        # 3. Equity selective bull (Equities up, Crypto weak)
        assert engine.classify_macro_regime(
            global_gold=55.0, global_blue=20.0, crypto_gold=25.0, equities_gold=65.0
        ) == "EQUITY_SELECTIVE_BULL"

        # 4. Chop / Consolidation
        assert engine.classify_macro_regime(
            global_gold=25.0, global_blue=25.0
        ) == "CONSOLIDATION_CHOP"

    def test_compute_snapshot_and_persistence(self, temp_db):
        engine = RegimeBreadthEngine(db_path=temp_db)

        scan_results = [
            {"ticker": "BTCUSDT", "asset_class": "crypto", "state": "GOLD"},
            {"ticker": "ETHUSDT", "asset_class": "crypto", "state": "GOLD"},
            {"ticker": "SOLUSDT", "asset_class": "crypto", "state": "BLUE"},
            {"ticker": "SPY", "asset_class": "us_stocks", "state": "GOLD"},
            {"ticker": "QQQ", "asset_class": "us_stocks", "state": "NEUTRAL"},
            {"ticker": "GC=F", "asset_class": "commodities", "state": "GOLD"},
        ]

        snapshot = engine.compute_snapshot(scan_results)

        assert snapshot.total_assets == 6
        assert snapshot.global_gold_pct == round((4 / 6) * 100.0, 1)  # 66.7%
        assert snapshot.global_blue_pct == round((1 / 6) * 100.0, 1)  # 16.7%
        assert "Crypto" in snapshot.sectors
        assert "US Equities" in snapshot.sectors
        assert "Commodities" in snapshot.sectors

        # Check sector level
        crypto_sec = snapshot.sectors["Crypto"]
        assert crypto_sec.total == 3
        assert crypto_sec.gold_count == 2
        assert crypto_sec.blue_count == 1
        assert crypto_sec.gold_pct == round((2 / 3) * 100.0, 1)

        # Test persistence
        saved = engine.save_snapshot(snapshot)
        assert saved is True

        history = engine.load_history(limit=5)
        assert len(history) == 1
        loaded = history[0]
        assert loaded.total_assets == 6
        assert loaded.global_gold_pct == snapshot.global_gold_pct
        assert "Crypto" in loaded.sectors

    def test_format_telegram_summary(self, temp_db):
        engine = RegimeBreadthEngine(db_path=temp_db)

        scan_results = [
            {"ticker": "BTCUSDT", "asset_class": "crypto", "state": "GOLD"},
            {"ticker": "SPY", "asset_class": "us_stocks", "state": "GOLD"},
        ]

        snapshot = engine.compute_snapshot(scan_results)
        msg = engine.format_telegram_summary(snapshot)

        assert "CROSS-ASSET REGIME BREADTH INDEX" in msg
        assert "Gold Breadth" in msg
        assert "Секторно Разпределение" in msg
