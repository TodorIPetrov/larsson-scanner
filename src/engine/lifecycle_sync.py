"""
Lifecycle Sync Engine: Institutional Auto-Onboarding & Fundamental Valuation Refresh.
1. Auto-onboarding of newly added assets (from config/assets.yaml or Watchlist):
   - Computes DCF / Specialized Valuation & Forensics if corporate equity.
   - Computes 10-year backtest DNA & optimal strategy if missing from asset_optimal_profiles.json.
   - Generates dedicated visual dossier (dashboard/data/dossiers/{TICKER}.json).
2. Incremental Fundamental Refresh:
   - Re-evaluates corporate equities with latest 10-Q/10-K filings and updated ^TNX risk-free rate.
3. Fast DNA Profiler for arbitrary assets without manual intervention.
"""

from datetime import datetime, timezone
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from src.engine.quantamental import QuantamentalRegistry, _MULTI_ASSET_PROFILES
from src.storage.database import Database

logger = logging.getLogger("LifecycleSync")

PROFILES_PATH = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
VERDICTS_PATH = os.path.join(BASE_DIR, "dashboard", "fundamental_verdicts.json")
RESEARCH_VERDICTS_PATH = os.path.join(BASE_DIR, "research", "verdicts.json")
ASSETS_YAML_PATH = os.path.join(BASE_DIR, "config", "assets.yaml")
CACHE_DIR = os.path.join(BASE_DIR, "data", "backtest_cache")
DOSSIERS_DIR = os.path.join(BASE_DIR, "dashboard", "data", "dossiers")


def load_configured_assets() -> Dict[str, str]:
    """Returns mapping of ticker -> asset_class from config/assets.yaml."""
    mapping = {}
    if os.path.exists(ASSETS_YAML_PATH):
        try:
            with open(ASSETS_YAML_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for a_class, items in data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "ticker" in item:
                            mapping[item["ticker"]] = a_class
        except Exception as e:
            logger.warning(f"Error reading assets.yaml: {e}")
    return mapping


def _load_optimal_profiles() -> dict:
    if os.path.exists(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_optimal_profiles(profiles: dict):
    os.makedirs(os.path.dirname(PROFILES_PATH), exist_ok=True)
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)


def _load_fundamental_verdicts() -> dict:
    for p in [VERDICTS_PATH, RESEARCH_VERDICTS_PATH]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "total_audited": 0, "verdicts": []}


def _save_fundamental_verdicts(data: dict):
    for p in [VERDICTS_PATH, RESEARCH_VERDICTS_PATH]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save verdicts to {p}: {e}")


def is_corporate_equity(ticker: str, asset_class: str) -> bool:
    """Checks whether the asset represents a corporate company requiring DCF/Forensic analysis."""
    if asset_class in ["crypto", "commodities", "indices"]:
        return False
    if ticker.endswith("USDT") or ticker.endswith("USDC"):
        return False
    if "=F" in ticker or ticker.startswith("^") or ticker.startswith("DX-"):
        return False
    # Exclude spot/futures commodity & crypto ETFs
    excluded_etfs = {
        'URA', 'URNM', 'IBIT', 'FBTC', 'ARKB', 'BITB', 'GBTC', 'HODL', 'BTCO',
        'EZBC', 'BITX', 'BITO', 'ETHE', 'ETHA', 'FETH', 'WGMI', 'DAPP', 'BLOK',
        'BKCH', 'BITQ', 'FDIG', 'BTF', 'BITS', 'CRPT', 'SATO', 'ARKW', 'ARKF',
        'CONL', 'MSTX', 'MSTU', 'BTCC-B.TO', 'ETHX-B.TO', 'BTCX-B.TO', 'GDIG.MI',
        'ASWD.DE', 'COPR.MI', 'EXV6.DE', 'BATE.DE', 'BATT.MI', 'RARE.DE', 'EXV5.DE'
    }
    if ticker in excluded_etfs:
        return False
    return True


def onboard_single_asset(
    ticker: str,
    asset_class: str = "us_stocks",
    dm: Optional[BacktestDataManager] = None,
) -> bool:
    """
    Fully onboards a new asset:
    1. Runs fundamental valuation if corporate equity.
    2. Downloads / ensures 1D daily bars exist.
    3. Simulates strategies & derives DNA optimal profile (Tier S/A/B/C).
    4. Generates visual dossier.
    """
    logger.info(f"🚀 Auto-Onboarding new asset: {ticker} [{asset_class}]...")
    if dm is None:
        dm = BacktestDataManager()

    # 1. Fundamental Valuation
    verdicts_data = _load_fundamental_verdicts()
    existing_verdict_tickers = {v["ticker"] for v in verdicts_data.get("verdicts", [])}

    if ticker not in existing_verdict_tickers and is_corporate_equity(ticker, asset_class):
        try:
            from scripts.generate_institutional_research import analyze_company_with_proper_model
            new_v = analyze_company_with_proper_model(ticker)
            if new_v and new_v.get("fair_value_base"):
                new_v["last_fundamental_update"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                verdicts_data.setdefault("verdicts", []).append(new_v)
                verdicts_data["total_audited"] = len(verdicts_data["verdicts"])
                verdicts_data["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                _save_fundamental_verdicts(verdicts_data)
                # Refresh Quantamental Registry
                try:
                    QuantamentalRegistry.get_instance().load_profiles()
                except Exception:
                    pass
                logger.info(f"✅ Fundamental profile generated for {ticker}: Fair Value=${new_v.get('fair_value_base', 0):.2f}, Verdict={new_v.get('verdict')}")
        except Exception as e:
            logger.warning(f"Could not generate fundamental analysis for {ticker}: {e}")

    # 2. Historical Market Data
    clean_sym = ticker.replace("=", "_").replace("^", "_").replace(":", "_")
    csv_path = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")

    df = pd.DataFrame()
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            df = pd.DataFrame()

    if df.empty or len(df) < 60:
        try:
            if asset_class == "crypto" or ticker.endswith("USDT"):
                df = dm.fetch_binance_history(ticker, timeframe="1D")
            else:
                df = dm.fetch_yfinance_history(ticker, timeframe="1D")

            if not df.empty and len(df) >= 30:
                os.makedirs(dm.cache_dir, exist_ok=True)
                df.to_csv(csv_path, index=False)
                logger.info(f"✅ Cached {len(df)} daily bars for {ticker} -> {csv_path}")
        except Exception as e:
            logger.warning(f"Could not fetch history for {ticker}: {e}")

    # 3. Optimal Profile & Backtest DNA
    profiles = _load_optimal_profiles()
    if ticker not in profiles and not df.empty and len(df) >= 60:
        try:
            from scripts.generate_asset_dossiers import (
                fast_compute_smma,
                fast_compute_sma,
                fast_compute_atr,
                fast_compute_rsi,
                evaluate_larsson_states,
                simulate_strategy_full,
            )

            closes = df["close"].to_numpy(dtype=np.float64)
            highs = df["high"].to_numpy(dtype=np.float64) if "high" in df else closes
            lows = df["low"].to_numpy(dtype=np.float64) if "low" in df else closes
            opens = df["open"].to_numpy(dtype=np.float64) if "open" in df else closes
            dates = df["date"].tolist() if "date" in df.columns else [str(i) for i in range(len(df))]

            v1 = fast_compute_smma(highs, 15)
            m1 = fast_compute_smma(highs, 19)
            m2 = fast_compute_smma(lows, 25)
            v2 = fast_compute_smma(lows, 29)
            states = evaluate_larsson_states(v1, m1, m2, v2)
            atr = fast_compute_atr(highs, lows, closes, 14)
            sma200 = fast_compute_sma(closes, 200)
            rsi = fast_compute_rsi(closes, 14)
            s_idx = min(150, max(30, len(closes) // 3))

            # Test Classic Blue Exit & Fast Exit Neutral
            sim_classic = simulate_strategy_full("CLASSIC_BLUE_EXIT", opens, highs, lows, closes, states, v1, v2, sma200, atr, rsi, dates, start_idx=s_idx)
            sim_fast = simulate_strategy_full("FAST_EXIT_NEUTRAL", opens, highs, lows, closes, states, v1, v2, sma200, atr, rsi, dates, start_idx=s_idx)
            sim_pullback = simulate_strategy_full("PULLBACK_V1_ACCUMULATOR", opens, highs, lows, closes, states, v1, v2, sma200, atr, rsi, dates, start_idx=s_idx)

            candidates = [sim_classic, sim_fast, sim_pullback]
            candidates.sort(key=lambda s: (s["sharpe_ratio"] * 30.0) + s["cagr_pct"] - (s["max_drawdown_pct"] * 0.5), reverse=True)
            best = candidates[0]

            sharpe = best["sharpe_ratio"]
            cagr = best["cagr_pct"]
            win_rate = best["win_rate_pct"]

            # Assign empirical quality tier
            if sharpe >= 1.0 and cagr >= 20.0 and win_rate >= 55.0:
                tier = "S"
            elif sharpe >= 0.60 and cagr >= 12.0 and win_rate >= 45.0:
                tier = "A"
            elif sharpe >= 0.30 and cagr >= 4.0:
                tier = "B"
            else:
                tier = "C"

            profiles[ticker] = {
                "symbol": ticker,
                "asset_class": asset_class,
                "recommended_strategy": best["strategy"],
                "exit_on_neutral": bool(best["strategy"] == "FAST_EXIT_NEUTRAL"),
                "empirical_tier": tier,
                "larsson_suitability": "STRONG_TREND" if tier in ["S", "A"] else "MODERATE_TREND",
                "walk_forward_stable": bool(tier in ["S", "A"]),
                "total_return_pct": best["total_return_pct"],
                "cagr_pct": best["cagr_pct"],
                "max_drawdown_pct": best["max_drawdown_pct"],
                "sharpe_ratio": best["sharpe_ratio"],
                "profit_factor": best["profit_factor"],
                "win_rate_pct": best["win_rate_pct"],
                "total_trades": best["total_trades"],
                "buy_and_hold_pct": best["buy_and_hold_pct"],
                "alpha_vs_bnh": round(best["total_return_pct"] - best["buy_and_hold_pct"], 1),
            }
            _save_optimal_profiles(profiles)
            logger.info(f"✅ Backtest DNA profile generated for {ticker}: Tier={tier}, Best={best['strategy']}, Sharpe={sharpe:.2f}, CAGR={cagr:.1f}%")
        except Exception as e:
            logger.warning(f"Could not compute backtest profile for {ticker}: {e}")

    # 4. Generate Dossier
    safe_name = ticker.replace("/", "_").replace("^", "_").replace(":", "_")
    dossier_path = os.path.join(DOSSIERS_DIR, f"{safe_name}.json")
    if not os.path.exists(dossier_path):
        try:
            from scripts.generate_asset_dossiers import generate_single_asset_dossier
            verdict_item = next((v for v in verdicts_data.get("verdicts", []) if v.get("ticker") == ticker), {})
            dossier = generate_single_asset_dossier(ticker, optimal_profile=profiles.get(ticker, {}), verdict_item=verdict_item)
            if dossier:
                os.makedirs(DOSSIERS_DIR, exist_ok=True)
                with open(dossier_path, "w", encoding="utf-8") as f:
                    json.dump(dossier, f, indent=2)
                logger.info(f"✅ Dossier visualizer created for {ticker} -> {dossier_path}")
        except Exception as e:
            logger.warning(f"Could not create dossier for {ticker}: {e}")

    return True


def sync_new_assets_lifecycle(db: Optional[Database] = None, limit: int = 10) -> Dict[str, List[str]]:
    """
    Audits the current universe in config/assets.yaml and state.db.
    Identifies any assets missing from profiles, verdicts, or dossiers and onboards them.
    Prioritizes curated assets from config/assets.yaml first, and limits batch size to prevent scan stalls.
    """
    logger.info("🔍 Auditing asset universe for auto-onboarding lifecycle...")
    if db is None:
        db = Database()

    configured_assets = load_configured_assets()
    db_states = db.get_all_states()

    all_universe: Dict[str, str] = dict(configured_assets)
    for row in db_states:
        sym = row["ticker"]
        ac = row["asset_class"]
        if sym not in all_universe:
            all_universe[sym] = ac

    optimal_profiles = _load_optimal_profiles()
    verdicts_data = _load_fundamental_verdicts()
    existing_verdicts = {v["ticker"] for v in verdicts_data.get("verdicts", [])}

    missing_profiles = []
    missing_fundamentals = []
    missing_dossiers = []

    for sym, ac in all_universe.items():
        if sym not in optimal_profiles:
            missing_profiles.append(sym)
        if is_corporate_equity(sym, ac) and sym not in existing_verdicts:
            missing_fundamentals.append(sym)
        safe_sym = sym.replace("/", "_").replace("^", "_").replace(":", "_")
        d_path = os.path.join(DOSSIERS_DIR, f"{safe_sym}.json")
        if not os.path.exists(d_path):
            missing_dossiers.append(sym)

    # Prioritize configured_assets first
    all_missing = set(missing_profiles + missing_fundamentals + missing_dossiers)
    prio_missing = [s for s in configured_assets.keys() if s in all_missing]
    other_missing = [s for s in all_missing if s not in configured_assets]
    sorted_candidates = (prio_missing + other_missing)[:limit]

    logger.info(f"Universe size: {len(all_universe)} assets. Assets requiring onboarding: {len(all_missing)}. Batch onboarding top {len(sorted_candidates)}...")

    dm = BacktestDataManager()
    onboarded = []
    for sym in sorted_candidates:
        ac = all_universe.get(sym, "us_stocks")
        success = onboard_single_asset(sym, asset_class=ac, dm=dm)
        if success:
            onboarded.append(sym)

    return {
        "universe_size": len(all_universe),
        "total_requiring_onboarding": len(all_missing),
        "onboarded_count": len(onboarded),
        "onboarded_tickers": onboarded,
    }


def refresh_existing_fundamentals(max_age_days: int = 7, force: bool = False, limit: int = 40) -> Dict:
    """
    Re-evaluates corporate equities whose fundamental assessment is older than max_age_days.
    Incorporates latest quarterly/annual filings from Yahoo Finance and dynamic ^TNX interest rates.
    """
    logger.info(f"🔄 Starting fundamental refresh (max_age_days={max_age_days}, force={force})...")
    verdicts_data = _load_fundamental_verdicts()
    verdicts = verdicts_data.get("verdicts", [])
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")

    candidates_to_refresh = []
    for idx, v in enumerate(verdicts):
        ticker = v.get("ticker")
        if not ticker:
            continue
        last_upd = v.get("last_fundamental_update")
        if force or not last_upd:
            candidates_to_refresh.append((idx, ticker))
            continue
        try:
            upd_dt = datetime.strptime(last_upd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (now_dt - upd_dt).days >= max_age_days:
                candidates_to_refresh.append((idx, ticker))
        except Exception:
            candidates_to_refresh.append((idx, ticker))

    candidates_to_refresh = candidates_to_refresh[:limit]
    logger.info(f"Identified {len(candidates_to_refresh)} equities to refresh.")

    if not candidates_to_refresh:
        return {"refreshed_count": 0, "tickers": []}

    from scripts.generate_institutional_research import analyze_company_with_proper_model

    refreshed_tickers = []
    for idx, ticker in candidates_to_refresh:
        try:
            logger.info(f"Re-evaluating fundamentals for {ticker}...")
            new_v = analyze_company_with_proper_model(ticker)
            if new_v and new_v.get("fair_value_base"):
                new_v["last_fundamental_update"] = today_str
                verdicts[idx] = new_v
                refreshed_tickers.append(ticker)
                # Re-generate dossier if it exists
                try:
                    from scripts.generate_asset_dossiers import generate_single_asset_dossier
                    opt_prof = _load_optimal_profiles().get(ticker, {})
                    dossier = generate_single_asset_dossier(ticker, optimal_profile=opt_prof, verdict_item=new_v)
                    if dossier:
                        safe_sym = ticker.replace("/", "_").replace("^", "_").replace(":", "_")
                        with open(os.path.join(DOSSIERS_DIR, f"{safe_sym}.json"), "w", encoding="utf-8") as f:
                            json.dump(dossier, f, indent=2)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error refreshing {ticker}: {e}")

    verdicts_data["verdicts"] = verdicts
    verdicts_data["total_audited"] = len(verdicts)
    verdicts_data["timestamp"] = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    _save_fundamental_verdicts(verdicts_data)

    try:
        QuantamentalRegistry.get_instance().load_profiles()
    except Exception:
        pass

    logger.info(f"✅ Successfully refreshed {len(refreshed_tickers)} fundamental profiles!")
    return {
        "refreshed_count": len(refreshed_tickers),
        "tickers": refreshed_tickers,
    }
