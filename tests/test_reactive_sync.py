"""
Tests for end-to-end reactive data propagation across scanners, caches,
fundamental filing detection, lifecycle sync, dashboard generator, server, and PWA.
All filesystem/DB tests are strictly isolated in temporary paths.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.storage.database import Database
from src.scanner import _update_symbol_daily_cache
from src.engine.smma import LarssonState
from src.engine.quantamental import QuantamentalRegistry
from src.engine import lifecycle_sync
from src.dashboard.generator import export_dashboard_data
import src.scanner as scanner_mod


def _make_sample_df(start_date: str = "2025-01-01", bars: int = 230, base_price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(start=start_date, periods=bars, freq="B").strftime("%Y-%m-%d").tolist()
    closes = [base_price + i * 0.25 for i in range(bars)]
    opens = [c - 0.3 for c in closes]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    vols = [100000 + i * 10 for i in range(bars)]
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
    })


def test_update_symbol_daily_cache_merges_multiday_bars(tmp_path):
    """Multi-day OHLCV tail updates append and deduplicate cleanly without shrinking 5y history."""
    cache_dir = tmp_path / "backtest_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cache_dir / "TEST_1D.csv"

    df_init = _make_sample_df(bars=25, base_price=100.0)
    df_init.to_csv(csv_path, index=False)

    # Tail window overlaps last 15 bars + 2 brand-new bars
    df_new_tail = _make_sample_df(start_date=df_init["date"].iloc[-15], bars=20, base_price=float(df_init["close"].iloc[-15]))
    df_new_tail["close"] = df_new_tail["close"] + 1.5

    with patch.object(scanner_mod, "CACHE_DIR", str(cache_dir)):
        _update_symbol_daily_cache(
            "TEST",
            highs=df_new_tail["high"].to_numpy(dtype=np.float64),
            lows=df_new_tail["low"].to_numpy(dtype=np.float64),
            closes=df_new_tail["close"].to_numpy(dtype=np.float64),
            volumes=df_new_tail["volume"].to_numpy(dtype=np.float64),
            opens=df_new_tail["open"].to_numpy(dtype=np.float64),
            dates=df_new_tail["date"].tolist(),
        )

    merged = pd.read_csv(csv_path)
    assert len(merged) > len(df_init)
    assert str(merged["date"].iloc[-1]) == str(df_new_tail["date"].iloc[-1])
    assert float(merged["close"].iloc[-1]) == pytest.approx(float(df_new_tail["close"].iloc[-1]), rel=1e-4)
    # First 10 earlier historical bars remained preserved!
    assert str(merged["date"].iloc[0]) == str(df_init["date"].iloc[0])


def test_refresh_active_technical_profiles_updates_dynamic_indicators(tmp_path):
    """Cached 1D OHLCV updates trigger fresh SMA200, RSI14, swing low, and ribbon state."""
    cache_dir = tmp_path / "backtest_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    profiles_path = tmp_path / "asset_optimal_profiles.json"

    df = _make_sample_df(bars=240, base_price=100.0)
    df.to_csv(cache_dir / "ACME_1D.csv", index=False)

    profiles_path.write_text(json.dumps({
        "ACME": {
            "symbol": "ACME",
            "asset_class": "us_stocks",
            "recommended_strategy": "CLASSIC_BLUE_EXIT",
            "latest_sma200": 50.0,
            "latest_rsi14": 20.0,
            "latest_swing_low_20d": 10.0,
            "ribbon_state": "BLUE",
            "last_technical_update": "2024-01-01",
        }
    }), encoding="utf-8")

    db = Database(db_path=str(tmp_path / "tech.db"))
    db.upsert_symbols([("ACME", "Acme Corp", "us_stocks")])
    db.update_state(
        ticker="ACME",
        timeframe="1D",
        v1=155.0,
        m1=153.0,
        m2=150.0,
        v2=148.0,
        new_state=LarssonState.GOLD,
        price=159.75,
    )

    with patch.object(lifecycle_sync, "CACHE_DIR", str(cache_dir)), \
         patch.object(lifecycle_sync, "PROFILES_PATH", str(profiles_path)):
        updated = lifecycle_sync.refresh_active_technical_profiles(db=db)

    assert updated == 1
    saved = json.loads(profiles_path.read_text(encoding="utf-8"))["ACME"]
    assert saved["ribbon_state"] == "GOLD"
    assert saved["latest_sma200"] > 120.0
    assert saved["latest_rsi14"] > 60.0
    assert saved["last_technical_update"] == str(df["date"].iloc[-1])


def test_filing_detection_cascades_verdicts_registry_and_db(tmp_path):
    """Detected newer filing updates both verdicts files and cascades DB trade suggestions."""
    dash_verdicts = tmp_path / "dashboard_verdicts.json"
    research_verdicts = tmp_path / "research_verdicts.json"
    dossiers_dir = tmp_path / "dossiers"
    profiles_path = tmp_path / "profiles.json"
    dossiers_dir.mkdir(parents=True, exist_ok=True)
    profiles_path.write_text("{}", encoding="utf-8")

    initial_verdict = {
        "ticker": "NVDA",
        "name": "NVIDIA Corp",
        "sector": "Technology",
        "price": 120.0,
        "fair_value_base": 140.0,
        "mos_pct": 14.3,
        "moat": "Wide",
        "verdict": "BUY / ACCUMULATE",
        "action": "BUY",
        "latest_filing_date": "2026-06-30",
        "last_fundamental_update": "2026-10-01",
    }
    payload = {"timestamp": "2026-10-01 00:00:00", "verdicts": [initial_verdict]}
    dash_verdicts.write_text(json.dumps(payload), encoding="utf-8")
    research_verdicts.write_text(json.dumps(payload), encoding="utf-8")

    db = Database(db_path=str(tmp_path / "fund.db"))
    db.upsert_symbols([("NVDA", "NVIDIA Corp", "us_stocks")])
    db.update_state(
        ticker="NVDA",
        timeframe="1D",
        v1=118.0,
        m1=115.0,
        m2=110.0,
        v2=106.0,
        new_state=LarssonState.GOLD,
        price=125.0,
    )

    updated_eval = {
        "ticker": "NVDA",
        "name": "NVIDIA Corp",
        "sector": "Technology",
        "price": 125.0,
        "fair_value_base": 175.0,
        "mos_pct": 28.6,
        "moat": "Wide",
        "verdict": "STRONG BUY",
        "action": "BUY",
        "latest_filing_date": "2026-09-30 (10-Q TTM)",
    }

    with patch.object(lifecycle_sync, "VERDICTS_PATH", str(dash_verdicts)), \
         patch.object(lifecycle_sync, "RESEARCH_VERDICTS_PATH", str(research_verdicts)), \
         patch.object(lifecycle_sync, "DOSSIERS_DIR", str(dossiers_dir)), \
         patch.object(lifecycle_sync, "PROFILES_PATH", str(profiles_path)), \
         patch.object(lifecycle_sync, "_has_newer_filing_or_earnings", return_value=(True, "New quarter filing 2026-09-30 > 2026-06-30")), \
         patch("scripts.generate_institutional_research.analyze_company_with_proper_model", return_value=updated_eval), \
         patch("scripts.generate_asset_dossiers.generate_single_asset_dossier", return_value=None):
        res = lifecycle_sync.refresh_existing_fundamentals(
            max_age_days=30,
            force=False,
            limit=5,
            target_tickers=["NVDA"],
            db=db,
            check_filings=True,
        )

    assert res["refreshed_count"] == 1
    assert res["changed_count"] == 1
    assert res["tickers"] == ["NVDA"]

    saved_dash = json.loads(dash_verdicts.read_text(encoding="utf-8"))
    saved_res = json.loads(research_verdicts.read_text(encoding="utf-8"))
    assert saved_dash["verdicts"][0]["fair_value_base"] == 175.0
    assert saved_res["verdicts"][0]["latest_filing_date"] == "2026-09-30 (10-Q TTM)"

    sug = db.get_trade_suggestion("NVDA", "1D")
    assert sug is not None


def test_sync_verdicts_mark_to_market_updates_mos_and_verdict(tmp_path):
    """Live price changes recalculate MoS% and downgrade/upgrade verdict dynamically."""
    dash_verdicts = tmp_path / "dashboard_verdicts.json"
    research_verdicts = tmp_path / "research_verdicts.json"
    payload = {
        "timestamp": "2026-10-01 00:00:00",
        "verdicts": [
            {
                "ticker": "XYZ",
                "name": "XYZ Inc",
                "price": 100.0,
                "fair_value_base": 150.0,
                "mos_pct": 33.3,
                "moat": "None",
                "verdict": "BUY / ACCUMULATE",
                "action": "BUY",
            }
        ],
    }
    dash_verdicts.write_text(json.dumps(payload), encoding="utf-8")
    research_verdicts.write_text(json.dumps(payload), encoding="utf-8")

    db = Database(db_path=str(tmp_path / "mtm.db"))
    db.upsert_symbols([("XYZ", "XYZ Inc", "us_stocks")])
    db.update_state(
        ticker="XYZ",
        timeframe="1D",
        v1=170.0,
        m1=168.0,
        m2=165.0,
        v2=160.0,
        new_state=LarssonState.GOLD,
        price=180.0,
    )

    with patch.object(lifecycle_sync, "VERDICTS_PATH", str(dash_verdicts)), \
         patch.object(lifecycle_sync, "RESEARCH_VERDICTS_PATH", str(research_verdicts)):
        count = lifecycle_sync.sync_verdicts_mark_to_market(db)

    assert count == 1
    upd = json.loads(dash_verdicts.read_text(encoding="utf-8"))["verdicts"][0]
    assert upd["price"] == 180.0
    assert upd["mos_pct"] == pytest.approx(-20.0, rel=1e-2)
    assert "REDUCE" in upd["verdict"]


def test_quantamental_registry_reloads_when_verdicts_mtime_changes(tmp_path):
    """QuantamentalRegistry detects updated verdicts file timestamp and reloads profiles."""
    verdict_file = tmp_path / "fundamental_verdicts.json"
    verdict_file.write_text(json.dumps({
        "verdicts": [
            {"ticker": "ALV.DE", "name": "Allianz", "price": 200.0, "fair_value_base": 300.0, "mos_pct": 33.3, "verdict": "STRONG BUY", "action": "BUY", "moat": "Wide"}
        ]
    }), encoding="utf-8")

    reg = QuantamentalRegistry(verdicts_path=str(verdict_file))
    prof1 = reg.get_profile("ALV.DE")
    assert prof1.target_price == 300.0

    # Rewrite file with bumped mtime
    st = os.stat(verdict_file)
    verdict_file.write_text(json.dumps({
        "verdicts": [
            {"ticker": "ALV.DE", "name": "Allianz", "price": 200.0, "fair_value_base": 360.0, "mos_pct": 44.4, "verdict": "STRONG BUY", "action": "BUY", "moat": "Wide"}
        ]
    }), encoding="utf-8")
    os.utime(verdict_file, (st.st_atime, st.st_mtime + 5))

    prof2 = reg.get_profile("ALV.DE")
    assert prof2.target_price == 360.0


def test_generator_export_uses_real_correlation_and_respects_test_guard(tmp_path):
    """export_dashboard_data exports dynamic metrics without mutating production paths on test output."""
    cache_dir = tmp_path / "backtest_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_sample_df(bars=60, base_price=90000.0).to_csv(cache_dir / "BTCUSDT_1D.csv", index=False)
    df_eth = _make_sample_df(bars=60, base_price=3000.0)
    df_eth["close"] = df_eth["close"] + np.sin(np.arange(60)) * 20.0
    df_eth.to_csv(cache_dir / "ETHUSDT_1D.csv", index=False)

    db = Database(db_path=str(tmp_path / "dash_test.db"))
    db.upsert_symbols([("BTCUSDT", "Bitcoin", "crypto"), ("ETHUSDT", "Ethereum", "crypto")])
    db.update_state(
        ticker="BTCUSDT",
        timeframe="1D",
        v1=90000.0,
        m1=89000.0,
        m2=88000.0,
        v2=87000.0,
        new_state=LarssonState.GOLD,
        price=95000.0,
    )
    db.update_state(
        ticker="ETHUSDT",
        timeframe="1D",
        v1=3100.0,
        m1=3050.0,
        m2=3000.0,
        v2=2950.0,
        new_state=LarssonState.GOLD,
        price=3300.0,
    )
    db.open_real_position(
        position_id="REAL_TEST_1",
        ticker="BTCUSDT",
        asset_class="crypto",
        entry_price=90000.0,
        units=0.1,
        position_size_usd=9000.0,
        stop_loss=85000.0,
    )
    db.open_real_position(
        position_id="REAL_TEST_2",
        ticker="ETHUSDT",
        asset_class="crypto",
        entry_price=3000.0,
        units=1.0,
        position_size_usd=3000.0,
        stop_loss=2800.0,
    )

    out_file = tmp_path / "data.json"
    with patch("src.dashboard.generator.CACHE_DIR_PATH", str(cache_dir)):
        data = export_dashboard_data(db, output_path=str(out_file))

    assert out_file.exists()
    assert data["summary"]["total"] == 2
    assert "risk_budget" in data and "cluster_allocations" in data["risk_budget"]
    assert data["risk_budget"]["current_open_risk_pct"] > 0.0
    assert "data_health" in data and "guard_active" in data["data_health"]
    assert "live_track_record" in data and "closed_trades" in data["live_track_record"]
    corr = data.get("correlation", {})
    assert isinstance(corr, dict) and "matrix" in corr
    assert "BTCUSDT" in corr["matrix"] and "ETHUSDT" in corr["matrix"]


def test_server_api_candles_returns_ohlcv_and_larsson_ribbon():
    """DashboardRequestHandler.handle_api_candles returns OHLCV + SMMA states cleanly."""
    import io
    from src.dashboard.server import DashboardRequestHandler

    df = _make_sample_df(bars=210, base_price=250.0)
    written = io.BytesIO()
    status_codes = []

    class DummyHandler:
        def send_response(self, code):
            status_codes.append(code)
        def send_header(self, k, v):
            pass
        def end_headers(self):
            pass
        wfile = written

    with patch("src.backtest.data_manager.BacktestDataManager.get_symbol_data", return_value=df):
        DashboardRequestHandler.handle_api_candles(DummyHandler(), {"ticker": ["ABEC.DE"], "timeframe": ["1D"]})

    assert status_codes == [200]
    resp = json.loads(written.getvalue().decode("utf-8"))
    assert resp["success"] is True
    assert resp["ticker"] == "ABEC.DE"
    assert len(resp["candles"]) == 210
    assert resp["state"] in ("GOLD", "BLUE", "NEUTRAL")
    assert resp["v1"] is not None and resp["v2"] is not None


def test_frontend_and_sw_reactive_contracts():
    """Verifies Service Worker cache-busting, history safety, portfolio current_value, and chart hooks."""
    sw_text = open(os.path.join(PROJECT_ROOT, "dashboard", "sw.js"), "r", encoding="utf-8").read()
    assert "fundamental_verdicts.json" in sw_text
    assert "/dossiers/" in sw_text
    assert "/modules/" in sw_text
    assert "no-store" in sw_text

    app_text = open(os.path.join(PROJECT_ROOT, "dashboard", "app.js"), "r", encoding="utf-8").read()
    assert "switchTab(currentTab, false)" in app_text
    assert "pos.current_value = curP * units;" in app_text
    assert "/api/candles?" in app_text
    assert "triggerFundamentalsRefresh" in app_text
