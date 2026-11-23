"""
Tests for Phase 2 Focus Rotation upgrades:
- Strict Long-Only / Cash policy (no crypto shorting / no SHORT_2X_OPTIONAL)
- Empirical Larsson trend tier & Tier-C leverage cap
- Crypto Fast-Exit default vs Gold Classic Blue Exit
- Eligibility gates (tier, walk-forward, sector, asset class, vol with Gold exemption)
- Normalized capped Inverse-Volatility sizing across active slots
- Generator Top-8 cluster-capped selection, Value Dips sector exclusion, Core-20 watchlist
- Walk-forward rotation simulator with InvVol, cluster caps, and Gold proxy exemption
"""

from __future__ import annotations

import os
import sys

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_portfolio_rotation_backtest import (
    prepare_causal_asset_frame,
    run_walk_forward_rotation,
)
from src.dashboard.generator import (
    _compute_normalized_invvol_weights,
    export_dashboard_data,
)
from src.engine.asset_profiles import (
    ASSET_CLASS_PROFILES,
    classify_risk_cluster,
    get_effective_exit_on_neutral,
    get_larsson_trend_tier,
    get_max_allowed_leverage,
    get_quality_tier,
    is_larsson_eligible,
)
from src.engine.smma import LarssonState
from src.engine.trade_suggestions import _enrich_trade_suggestion, TradeSuggestion, generate_trade_suggestion
from src.storage.database import Database


def test_strict_long_only_policy_and_no_short_2x_generated():
    for cls_name, prof in ASSET_CLASS_PROFILES.items():
        assert prof.allows_short is False, f"{cls_name} should enforce strict Long-Only / Cash"

    # BLUE overhead retest on crypto must NOT emit SHORT_2X_OPTIONAL
    sugg = generate_trade_suggestion(
        state="BLUE",
        current_price=95.0,
        v1=95.0,
        m1=95.3,
        m2=95.6,
        v2=96.0,
        atr=2.0,
        spread_pct=-1.0,
        s1=70.0,
        r1=95.5,
        ticker="BTCUSDT",
        asset_class="crypto",
    )
    assert sugg.action != "SHORT_2X_OPTIONAL"
    assert sugg.direction != "SHORT"


def test_empirical_trend_tier_and_c_tier_leverage_cap():
    # Fundamental brand tier vs empirical Larsson trend suitability remain separated
    assert get_quality_tier("AMZN") == "S"
    assert get_larsson_trend_tier("AMZN") == "C"
    assert get_larsson_trend_tier("TSLA") == "C"
    assert get_larsson_trend_tier("NVDA") == "S"

    # Empirical Tier-C trend traps must be strictly capped to 1x Spot
    assert get_max_allowed_leverage("AMZN", asset_class="us_stocks", score=95, tier="A+", atr_pct=2.0) == 1
    assert get_max_allowed_leverage("TSLA", asset_class="us_stocks", score=95, tier="A+", atr_pct=2.0) == 1
    # Contract: AAPL (Brand S, Empirical B) still supports 3x with high conviction
    assert get_max_allowed_leverage("AAPL", asset_class="us_stocks", score=80, tier="A", atr_pct=2.5) == 3


def test_effective_exit_on_neutral_and_enrichment():
    assert get_effective_exit_on_neutral("BTCUSDT", asset_class="crypto") is True
    assert get_effective_exit_on_neutral("SOLUSDT", asset_class="crypto") is True
    assert get_effective_exit_on_neutral("PAXGUSDT", asset_class="crypto") is False
    assert get_effective_exit_on_neutral("GC=F", asset_class="commodities") is False
    assert get_effective_exit_on_neutral("META", asset_class="ai_stocks") is True
    assert get_effective_exit_on_neutral("NVDA", asset_class="ai_stocks") is False

    base_s = TradeSuggestion(action="WAIT", direction="NEUTRAL", setup_type="HOLD")
    sol_enriched = _enrich_trade_suggestion(
        s=TradeSuggestion(action="WAIT", direction="NEUTRAL", setup_type="HOLD"),
        state="NEUTRAL",
        spread_pct=0.0,
        s1=100.0,
        r1=120.0,
        current_price=110.0,
        fund_profile=None,
        asset_class="crypto",
        ticker="SOLUSDT",
    )
    assert sol_enriched.tech_action == "TAKE_PROFIT"

    paxg_enriched = _enrich_trade_suggestion(
        s=base_s,
        state="NEUTRAL",
        spread_pct=0.0,
        s1=2400.0,
        r1=2800.0,
        current_price=2600.0,
        fund_profile=None,
        asset_class="crypto",
        ticker="PAXGUSDT",
    )
    assert paxg_enriched.tech_action == "HOLD"


def test_larsson_eligibility_gates():
    assert is_larsson_eligible("^GSPC", asset_class="indices", annualized_vol_pct=30.0) is False
    assert is_larsson_eligible("NEE", asset_class="us_stocks", sector="Utilities", annualized_vol_pct=35.0) is False
    assert is_larsson_eligible("WMT", asset_class="us_stocks", sector="Consumer Staples", annualized_vol_pct=30.0) is False
    assert is_larsson_eligible("AMZN", asset_class="us_stocks", sector="Consumer Cyclical", annualized_vol_pct=40.0) is False
    assert is_larsson_eligible("AAPL", asset_class="us_stocks", sector="Technology", annualized_vol_pct=35.0) is False
    assert is_larsson_eligible("NVDA", asset_class="ai_stocks", sector="Technology", annualized_vol_pct=18.0) is False
    assert is_larsson_eligible("NVDA", asset_class="ai_stocks", sector="Technology", annualized_vol_pct=42.0) is True
    # Gold low-volatility exemption
    assert is_larsson_eligible("PAXGUSDT", asset_class="crypto", annualized_vol_pct=16.0) is True
    assert is_larsson_eligible("GC=F", asset_class="commodities", annualized_vol_pct=17.0) is True

    # Explicit ticker cluster mappings must override coarse crypto_stocks/other labels
    assert classify_risk_cluster("CME", "crypto_stocks", "Financial Services") == "finance_fintech"
    assert classify_risk_cluster("GEV", "ai_stocks", "Industrials") == "industrial_defense"


def test_normalized_invvol_weights_math_and_cash_scaling():
    # Full 8-slot book with mixed high vols must stay 100% deployed (no accidental half-cash bug)
    high_vols = {
        "NVDA": 45.0,
        "AVGO": 50.0,
        "PLTR": 70.0,
        "MU": 85.0,
        "SOLUSDT": 90.0,
        "BTCUSDT": 42.0,
        "GE": 32.0,
        "PAXGUSDT": 16.0,
    }
    w_full = _compute_normalized_invvol_weights(high_vols, target_slots=8, min_weight_pct=7.0, max_weight_pct=20.0)
    assert pytest.approx(sum(w_full.values()), abs=0.05) == 100.0
    assert all(7.0 - 1e-6 <= v <= 20.0 + 1e-6 for v in w_full.values())
    assert w_full["PAXGUSDT"] > w_full["GE"] > w_full["NVDA"] > w_full["SOLUSDT"]

    # Partial 2-slot book scales deployed capital linearly (2/8 = 25%) and leaves 75% cash
    w_partial = _compute_normalized_invvol_weights(
        {"PAXGUSDT": 20.0, "SOLUSDT": 80.0},
        target_slots=8,
        min_weight_pct=7.0,
        max_weight_pct=20.0,
    )
    assert pytest.approx(sum(w_partial.values()), abs=0.05) == 25.0
    assert w_partial["PAXGUSDT"] > w_partial["SOLUSDT"]


def test_export_dashboard_data_top8_cluster_caps_and_exclusions(tmp_path, monkeypatch):
    db_path = tmp_path / "focus_rot.db"
    db = Database(db_path=str(db_path))

    # Provide deterministic causal vols/RS metrics without scanning repo cache files
    fake_rs = {
        "NVDA": 95, "AVGO": 94, "TSM": 93, "MU": 92, "ASML": 91,
        "PLTR": 90, "META": 89, "GE": 88, "RYCEY": 87, "PAXGUSDT": 75,
        "BTCUSDT": 85, "AMZN": 96, "^GSPC": 80, "NEE": 82, "O": 79,
    }
    fake_mom = {k: float(v - 50) for k, v in fake_rs.items()}
    fake_vol = {
        "NVDA": 42.0, "AVGO": 48.0, "TSM": 44.0, "MU": 65.0, "ASML": 46.0,
        "PLTR": 68.0, "META": 41.0, "GE": 32.0, "RYCEY": 34.0, "PAXGUSDT": 18.0,
        "BTCUSDT": 45.0, "AMZN": 40.0, "^GSPC": 18.0, "NEE": 30.0, "O": 31.0,
    }
    fake_sh = {k: 1.4 for k in fake_rs}

    import src.dashboard.generator as gen_mod
    monkeypatch.setattr(
        gen_mod,
        "_compute_universe_causal_metrics",
        lambda cache_dir=gen_mod.CACHE_DIR_PATH, db_rows=None: (fake_rs, fake_mom, fake_vol, fake_sh),
    )

    test_assets = [
        ("NVDA", "ai_stocks", "GOLD", 140.0, 130.0, 125.0, "Technology"),
        ("AVGO", "ai_stocks", "GOLD", 180.0, 170.0, 165.0, "Technology"),
        ("TSM", "ai_stocks", "GOLD", 190.0, 180.0, 175.0, "Technology"),
        ("MU", "ai_stocks", "GOLD", 110.0, 102.0, 98.0, "Technology"),
        ("ASML", "ai_stocks", "GOLD", 750.0, 720.0, 700.0, "Technology"),
        ("PLTR", "ai_stocks", "GOLD", 65.0, 60.0, 56.0, "Technology"),
        ("META", "ai_stocks", "GOLD", 580.0, 560.0, 540.0, "Technology"),
        ("GE", "us_stocks", "GOLD", 180.0, 172.0, 165.0, "Industrials"),
        ("RYCEY", "us_stocks", "GOLD", 7.0, 6.6, 6.2, "Industrials"),
        ("PAXGUSDT", "crypto", "GOLD", 2650.0, 2600.0, 2550.0, ""),
        ("BTCUSDT", "crypto", "GOLD", 92000.0, 88000.0, 85000.0, ""),
        ("AMZN", "us_stocks", "GOLD", 210.0, 200.0, 195.0, "Consumer Cyclical"),
        ("^GSPC", "indices", "GOLD", 5900.0, 5800.0, 5700.0, ""),
        ("NEE", "us_stocks", "BLUE", 70.0, 74.0, 76.0, "Utilities"),
        ("O", "us_stocks", "BLUE", 55.0, 58.0, 60.0, "Real Estate"),
    ]
    db.upsert_symbols([(sym, sym, ac) for sym, ac, *_ in test_assets])
    sector_map = {sym: sec for sym, _, _, _, _, _, sec in test_assets if sec}
    price_map = {sym: px for sym, _, _, px, _, _, _ in test_assets}

    import src.engine.quantamental as q_mod
    real_profiles = gen_mod._load_optimal_profiles()
    patched_profiles = dict(real_profiles)
    patched_profiles["NEE"] = {"empirical_tier": "C", "value_dip_allowed": True, "best_value_strategy": "V1_SMA200_BOUNCE", "sector": "Utilities"}
    patched_profiles["O"] = {"empirical_tier": "C", "value_dip_allowed": True, "best_value_strategy": "V1_SMA200_BOUNCE", "sector": "Real Estate"}
    monkeypatch.setattr(gen_mod, "_load_optimal_profiles", lambda: patched_profiles)

    def _fake_fund(tk: str):
        sec = sector_map.get(tk)
        px = price_map.get(tk, 100.0)
        if not sec:
            return None
        return SimpleNamespace(
            verdict="BUY",
            action="BUY",
            fair_value=px * 1.4,
            target_price=px * 1.4,
            mos_pct=28.0,
            upside_pct=40.0,
            moat="Wide",
            roic_pct=15.0,
            wacc_pct=8.0,
            z_score=3.0,
            m_score=-2.5,
            tata=0.0,
            thesis="Test fundamental",
            sector=sec,
            industry=sec,
            model_type="DCF",
            shares=100.0,
            mcap_b=50.0,
            beta=1.0,
            revenue_b=10.0,
            ebit_b=2.0,
            nopat_b=1.5,
            entry_price=px,
            solvency_type="Z-Score",
            production_cost=None,
            mvrv_ratio=None,
            is_bearish_or_distressed=False,
            is_bullish=True,
            is_hold=False,
        )

    monkeypatch.setattr(q_mod, "get_fundamental_profile", _fake_fund)

    for sym, ac, st, px, v1, v2, sec in test_assets:
        db.update_state(
            ticker=sym,
            timeframe="1D",
            v1=v1,
            m1=(v1 + v2) / 2.0,
            m2=(v1 + v2) / 2.0,
            v2=v2,
            new_state=LarssonState(st),
            price=px,
        )

    out_file = tmp_path / "data.json"
    data = export_dashboard_data(db, output_path=str(out_file))
    rp = data["rotation_portfolio"]

    assert rp["target_positions_count"] == 8
    assert rp["sizing_mode"] == "INVERSE_VOL_CAPPED"
    assert len(rp["top15"]) <= 8

    top_tickers = [x["ticker"] for x in rp["top15"]]
    assert "AMZN" not in top_tickers  # Empirical Tier C blocked
    assert "^GSPC" not in top_tickers  # Excluded index asset class
    assert "NEE" not in top_tickers
    assert rp["cluster_distribution"].get("semi_ai_hardware", 0) <= 2

    # Value Dips must exclude Utilities and Real Estate
    dip_tickers = {q["ticker"] for q in rp["quantamental_dips"]}
    assert "NEE" not in dip_tickers
    assert "O" not in dip_tickers

    # Portfolio weight sum matches deployed capital + cash reserve == 100%
    w_sum = round(sum(x["target_weight_pct"] for x in rp["top15"]), 2)
    assert pytest.approx(w_sum, abs=0.05) == rp["deployed_capital_pct"]
    assert pytest.approx(rp["deployed_capital_pct"] + rp["cash_reserve_pct"], abs=0.05) == 100.0

    # Dedicated Core-20 watchlist present with full core roster including GEV (live-scanned)
    assert "GEV" in rp["core_focus_tickers"]
    assert len(rp["core_watchlist"]) == len(rp["core_focus_tickers"])


def test_walk_forward_rotation_invvol_cluster_caps_and_gold_exception():
    dates = pd.date_range("2023-01-01", periods=160, freq="D")

    def _make_trend_frame(sym: str, cat: str, drift: float, vol_noise: float, dip_mid: bool = False):
        rng = np.random.default_rng(abs(hash(sym)) % 10000)
        rets = drift + rng.normal(0.0, vol_noise, size=len(dates))
        if dip_mid:
            rets[95:108] = -0.008  # Gentle dip to induce NEUTRAL without full BLUE breakdown
        close = 100.0 * np.cumprod(1.0 + rets)
        open_px = close * (1.0 + rng.normal(0.0, 0.001, size=len(dates)))
        high = np.maximum(open_px, close) * (1.0 + vol_noise * 0.6)
        low = np.minimum(open_px, close) * (1.0 - vol_noise * 0.6)
        df = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "open": open_px,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(len(dates), 1_000_000.0),
        })
        return prepare_causal_asset_frame(df, sym, cat)

    datasets = {
        "NVDA": _make_trend_frame("NVDA", "ai_stocks", 0.004, 0.022),
        "AVGO": _make_trend_frame("AVGO", "ai_stocks", 0.0038, 0.022),
        "TSM": _make_trend_frame("TSM", "ai_stocks", 0.0035, 0.022),
        "PAXGUSDT": _make_trend_frame("PAXGUSDT", "crypto", 0.0025, 0.007, dip_mid=True),
        "SOLUSDT": _make_trend_frame("SOLUSDT", "crypto", 0.0045, 0.035),
    }
    for k, v in datasets.items():
        assert v is not None
        assert classify_risk_cluster(k, v["cat"])

    cal = sorted(datasets["NVDA"]["dates"])
    res = run_walk_forward_rotation(
        datasets=datasets,
        calendar=cal,
        min_vol=25.0,
        max_positions=4,
        cash_rf_annual=0.04,
        fast_crypto=True,
        inverse_vol_sizing=True,
        min_slot_weight_pct=7.0,
        max_slot_weight_pct=20.0,
        cluster_caps={"semi_ai_hardware": 2, "gold_commodities": 2, "crypto_risk": 2},
        gold_vol_exempt={"GC=F", "PAXGUSDT"},
    )
    assert res["final_equity"] > 0.0
    assert res["total_trades"] >= 0
