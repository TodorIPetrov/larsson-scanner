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


def _atomic_write_json(path: str, payload: dict):
    import time
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    for attempt in range(5):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 4:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                return
            time.sleep(0.05 * (attempt + 1))


def _save_optimal_profiles(profiles: dict):
    _atomic_write_json(PROFILES_PATH, profiles)


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
            _atomic_write_json(p, data)
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

            hl2 = (highs + lows) / 2.0
            v1 = fast_compute_smma(hl2, 15)
            m1 = fast_compute_smma(hl2, 19)
            m2 = fast_compute_smma(hl2, 25)
            v2 = fast_compute_smma(hl2, 29)
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

            bnh_pct = round(((closes[-1] - closes[s_idx]) / closes[s_idx]) * 100.0, 1) if closes[s_idx] > 0 else 0.0
            latest_sma_val = round(float(sma200[-1]), 4) if len(sma200) > 0 and not np.isnan(sma200[-1]) else None
            latest_rsi_val = round(float(rsi[-1]), 1) if len(rsi) > 0 and not np.isnan(rsi[-1]) else 50.0
            latest_swing_val = round(float(np.min(lows[-20:])), 4) if len(lows) >= 20 else round(float(np.min(lows)), 4)
            latest_state_str = "GOLD" if states[-1] == 1 else ("BLUE" if states[-1] == -1 else "NEUTRAL")

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
                "buy_and_hold_pct": best.get("buy_and_hold_pct", bnh_pct),
                "alpha_vs_bnh": round(best["total_return_pct"] - best.get("buy_and_hold_pct", bnh_pct), 1),
                "latest_sma200": latest_sma_val,
                "latest_rsi14": latest_rsi_val,
                "latest_swing_low_20d": latest_swing_val,
                "ribbon_state": latest_state_str,
                "last_technical_update": str(dates[-1])[:10] if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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

    try:
        refresh_active_technical_profiles(db=db)
    except Exception as e:
        logger.debug(f"Technical profile refresh notice: {e}")

    return {
        "universe_size": len(all_universe),
        "total_requiring_onboarding": len(all_missing),
        "onboarded_count": len(onboarded),
        "onboarded_tickers": onboarded,
    }


def refresh_active_technical_profiles(db: Optional[Database] = None) -> int:
    """
    Recomputes latest technical snapshot fields (latest_sma200, latest_rsi14,
    latest_swing_low_20d, ribbon_state) in data/asset_optimal_profiles.json
    using the freshest cached 1D candles and live DB states.
    """
    profiles = _load_optimal_profiles()
    if not profiles:
        return 0

    try:
        from scripts.generate_asset_dossiers import (
            fast_compute_smma,
            fast_compute_sma,
            fast_compute_rsi,
            evaluate_larsson_states,
        )
    except Exception as e:
        logger.debug(f"Could not import dossier indicator helpers: {e}")
        return 0

    db_1d_states: Dict[str, str] = {}
    if db is not None:
        try:
            for r in db.get_all_states():
                if r["timeframe"] == "1D":
                    db_1d_states[r["ticker"]] = r["current_state"]
        except Exception:
            pass

    updated_count = 0
    for sym, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        clean_sym = sym.replace("=", "_").replace("^", "_").replace(":", "_").replace("/", "_")
        csv_path = os.path.join(CACHE_DIR, f"{clean_sym}_1D.csv")
        if not os.path.exists(csv_path):
            if sym in db_1d_states and prof.get("ribbon_state") != db_1d_states[sym]:
                prof["ribbon_state"] = db_1d_states[sym]
                updated_count += 1
            continue

        try:
            df = pd.read_csv(csv_path)
            if len(df) < 30 or "close" not in df.columns:
                continue
            closes = df["close"].to_numpy(dtype=np.float64)
            highs = df["high"].to_numpy(dtype=np.float64) if "high" in df else closes
            lows = df["low"].to_numpy(dtype=np.float64) if "low" in df else closes
            last_date = str(df["date"].iloc[-1])[:10] if "date" in df.columns else ""

            sma200 = fast_compute_sma(closes, 200)
            rsi = fast_compute_rsi(closes, 14)
            hl2 = (highs + lows) / 2.0
            v1 = fast_compute_smma(hl2, 15)
            m1 = fast_compute_smma(hl2, 19)
            m2 = fast_compute_smma(hl2, 25)
            v2 = fast_compute_smma(hl2, 29)
            states = evaluate_larsson_states(v1, m1, m2, v2)

            sma_val = round(float(sma200[-1]), 4) if len(sma200) > 0 and not np.isnan(sma200[-1]) else prof.get("latest_sma200")
            rsi_val = round(float(rsi[-1]), 1) if len(rsi) > 0 and not np.isnan(rsi[-1]) else prof.get("latest_rsi14", 50.0)
            swing_val = round(float(np.min(lows[-20:])), 4) if len(lows) >= 20 else round(float(np.min(lows)), 4)
            state_str = db_1d_states.get(sym) or ("GOLD" if states[-1] == 1 else ("BLUE" if states[-1] == -1 else "NEUTRAL"))

            if (
                prof.get("latest_sma200") != sma_val
                or prof.get("latest_rsi14") != rsi_val
                or prof.get("latest_swing_low_20d") != swing_val
                or prof.get("ribbon_state") != state_str
                or prof.get("last_technical_update") != last_date
            ):
                prof["latest_sma200"] = sma_val
                prof["latest_rsi14"] = rsi_val
                prof["latest_swing_low_20d"] = swing_val
                prof["ribbon_state"] = state_str
                if last_date:
                    prof["last_technical_update"] = last_date
                updated_count += 1
        except Exception:
            continue

    if updated_count > 0:
        _save_optimal_profiles(profiles)
        logger.info(f"🔄 Refreshed technical DNA indicators (SMA200/RSI14/Swing20) for {updated_count} profiled assets.")
    return updated_count


def _has_newer_filing_or_earnings(ticker: str, stored_filing_date: str, last_upd_str: str) -> Tuple[bool, str]:
    """
    Lightweight Yahoo metadata check to detect whether a company released a new
    quarterly/annual report or earnings announcement since the stored analysis.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        now_dt = datetime.now(timezone.utc)

        # 1. Check mostRecentQuarter epoch
        mrq_ts = info.get("mostRecentQuarter")
        if mrq_ts:
            mrq_str = datetime.fromtimestamp(float(mrq_ts), tz=timezone.utc).strftime("%Y-%m-%d")
            stored_clean = (stored_filing_date or "")[:10]
            if stored_clean and mrq_str > stored_clean:
                return True, f"New quarter filing {mrq_str} > {stored_clean}"

        # 2. Check recent earningsTimestamp within last 10 days after last_fundamental_update
        e_ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if e_ts:
            e_dt = datetime.fromtimestamp(float(e_ts), tz=timezone.utc)
            e_str = e_dt.strftime("%Y-%m-%d")
            if e_dt <= now_dt and (now_dt - e_dt).days <= 10:
                if not last_upd_str or e_str > last_upd_str[:10]:
                    return True, f"Recent earnings event on {e_str}"
    except Exception:
        pass
    return False, ""


def _collect_priority_equity_tickers(db: Optional[Database] = None) -> Set[str]:
    """Collects equities held in portfolios, watchlists, proposals, or top dips/leaders."""
    prio: Set[str] = {
        "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD", "AVGO",
        "NFLX", "ADBE", "CRM", "UBER", "PLTR", "ABEC.DE", "NVD.DE", "ASML.AS", "TSM",
    }
    if db is not None:
        try:
            for p in db.get_open_real_positions():
                prio.add(p["ticker"])
            for p in db.get_open_paper_positions():
                prio.add(p["ticker"])
            for w in db.get_watchlist():
                t = w["ticker"] if hasattr(w, "__getitem__") and not isinstance(w, str) else str(w)
                prio.add(t)
            for prop in db.get_pending_proposals():
                prio.add(prop["ticker"])
        except Exception:
            pass
    return prio


def _cascade_fundamental_to_db(ticker: str, db: Optional[Database]):
    """Re-evaluates DB trade suggestion for a ticker after its fundamental verdict changed."""
    if db is None:
        return
    try:
        row = db.get_current_state(ticker, "1D")
        if not row:
            return
        from src.engine.smma import LarssonState
        from src.engine.quantamental import get_fundamental_profile
        from src.engine.trade_suggestions import generate_trade_suggestion

        sr_row = None
        if hasattr(db, "get_sr_level"):
            sr_row = db.get_sr_level(ticker, "1D")
        elif hasattr(db, "get_sr_levels"):
            sr_row = db.get_sr_levels(ticker, "1D")
        sr_data = dict(sr_row) if sr_row else None
        st = LarssonState(row["current_state"])
        price = float(row["last_price"])
        v1 = float(row["v1"])
        m1 = float(row["m1"])
        m2 = float(row["m2"])
        v2 = float(row["v2"])
        v2_val = v2 if v2 > 0 else 1e-6
        spread_pct = ((v1 - v2_val) / v2_val) * 100.0

        atr = (sr_data.get("atr") or sr_data.get("atr14") or price * 0.02) if sr_data else (price * 0.02)
        s1 = (sr_data.get("s1_price") or sr_data.get("s1")) if sr_data else None
        s1_touches = sr_data.get("s1_touches", 0) if sr_data else 0
        s2 = (sr_data.get("s2_price") or sr_data.get("s2")) if sr_data else None
        r1 = (sr_data.get("r1_price") or sr_data.get("r1")) if sr_data else None
        r1_touches = sr_data.get("r1_touches", 0) if sr_data else 0
        r2 = (sr_data.get("r2_price") or sr_data.get("r2")) if sr_data else None

        sym_row = None
        try:
            for s in db.get_active_symbols():
                if s["ticker"] == ticker:
                    sym_row = s
                    break
        except Exception:
            pass
        ac = sym_row["asset_class"] if sym_row else "us_stocks"
        fund_profile = get_fundamental_profile(ticker, current_price=price)
        suggestion = generate_trade_suggestion(
            current_price=price,
            state=st.value,
            v1=v1,
            m1=m1,
            m2=m2,
            v2=v2,
            spread_pct=spread_pct,
            atr=float(atr),
            s1=s1,
            s1_touches=int(s1_touches or 0),
            s2=s2,
            r1=r1,
            r1_touches=int(r1_touches or 0),
            r2=r2,
            timeframe="1D",
            fund_profile=fund_profile,
            ticker=ticker,
            asset_class=ac,
            bars_since_flip=row["bars_since_flip"],
        )
        db.upsert_trade_suggestion(
            ticker=ticker,
            timeframe="1D",
            action=suggestion.action,
            direction=suggestion.direction,
            setup_type=suggestion.setup_type,
            entry_price=suggestion.entry_price,
            stop_loss=suggestion.stop_loss,
            tp1=suggestion.tp1,
            tp2=suggestion.tp2,
            rr_ratio=suggestion.rr_ratio,
            score=suggestion.score,
            tier=suggestion.tier,
            reason_bg=suggestion.reason_bg,
            reason_en=suggestion.reason_en,
            fund_verdict=suggestion.fund_verdict,
            fair_value=suggestion.fair_value,
            mos_pct=suggestion.mos_pct,
            moat=suggestion.moat,
            z_score=suggestion.z_score,
            quantamental_tag=suggestion.quantamental_tag,
            tech_action=suggestion.tech_action,
            tech_label_bg=suggestion.tech_label_bg,
            tech_thesis_bg=suggestion.tech_thesis_bg,
            fund_action=suggestion.fund_action,
            fund_label_bg=suggestion.fund_label_bg,
            fund_thesis_bg=suggestion.fund_thesis_bg,
            synthesis_badge_bg=suggestion.synthesis_badge_bg,
            synthesis_label_bg=suggestion.synthesis_label_bg,
            btc_ratio_state=suggestion.btc_ratio_state,
            btc_alpha_30d=suggestion.btc_alpha_30d,
            btc_alpha_7d=suggestion.btc_alpha_7d,
            btc_ratio_spread=suggestion.btc_ratio_spread,
            btc_verdict=suggestion.btc_verdict,
            btc_badge_bg=suggestion.btc_badge_bg,
            btc_thesis_bg=suggestion.btc_thesis_bg,
            btc_leverage_allowed=1 if getattr(suggestion, "btc_leverage_allowed", False) else 0,
        )
    except Exception as e:
        logger.warning(f"Could not cascade fundamental update to DB trade suggestion for {ticker}: {e}")


def refresh_existing_fundamentals(
    max_age_days: int = 7,
    force: bool = False,
    limit: int = 40,
    target_tickers: Optional[List[str]] = None,
    db: Optional[Database] = None,
    check_filings: bool = True,
) -> Dict:
    """
    Re-evaluates corporate equities with newly detected SEC/Yahoo 10-Q/10-K filings,
    recent earnings releases, or valuations older than max_age_days.
    Rotates by oldest check date so the entire equity universe stays fresh.
    """
    logger.info(f"🔄 Starting filing-aware fundamental refresh (max_age_days={max_age_days}, force={force}, limit={limit})...")
    verdicts_data = _load_fundamental_verdicts()
    verdicts = verdicts_data.get("verdicts", [])
    if not verdicts:
        return {"refreshed_count": 0, "changed_count": 0, "tickers": [], "changed_tickers": []}

    if db is None:
        try:
            db = Database()
        except Exception:
            db = None

    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")
    priority_set = _collect_priority_equity_tickers(db)
    target_upper = {t.strip().upper() for t in target_tickers} if target_tickers else set()

    # Build prioritized audit queue: explicit targets -> stale/unchecked priorities -> oldest checked globally
    scored_queue = []
    for idx, v in enumerate(verdicts):
        ticker = v.get("ticker")
        if not ticker:
            continue
        t_up = ticker.upper()
        last_upd = v.get("last_fundamental_update") or "1970-01-01"
        last_chk = v.get("last_filing_check") or last_upd

        if target_upper and t_up not in target_upper:
            continue

        is_target = t_up in target_upper
        is_prio = t_up in priority_set

        try:
            upd_dt = datetime.strptime(last_upd[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (now_dt - upd_dt).days
        except Exception:
            age_days = 9999

        needs_age_refresh = force or is_target or (age_days >= max_age_days)
        already_checked_today = (last_chk[:10] == today_str) and not force and not is_target

        if already_checked_today and not needs_age_refresh:
            continue

        # Sort key: explicit targets first, then overdue items, then oldest check date
        sort_rank = (
            0 if is_target else (1 if is_prio and age_days >= max_age_days else (2 if needs_age_refresh else (3 if is_prio else 4))),
            last_chk,
            -age_days,
        )
        scored_queue.append((sort_rank, idx, ticker, needs_age_refresh, v))

    scored_queue.sort(key=lambda x: x[0])
    batch = scored_queue[:limit]
    logger.info(f"Auditing {len(batch)} corporate equities for new filings / valuation drift...")

    if not batch:
        return {"refreshed_count": 0, "changed_count": 0, "tickers": [], "changed_tickers": []}

    from scripts.generate_institutional_research import analyze_company_with_proper_model

    opt_profiles = _load_optimal_profiles()
    refreshed_tickers = []
    changed_tickers = []
    checked_count = 0

    for _, idx, ticker, needs_age_refresh, old_v in batch:
        checked_count += 1
        do_refresh = needs_age_refresh
        reason = "age/force"

        if not do_refresh and check_filings:
            has_new, new_reason = _has_newer_filing_or_earnings(
                ticker,
                old_v.get("latest_filing_date", ""),
                old_v.get("last_fundamental_update", ""),
            )
            if has_new:
                do_refresh = True
                reason = new_reason

        verdicts[idx]["last_filing_check"] = today_str

        if not do_refresh:
            continue

        try:
            logger.info(f"Re-evaluating fundamentals for {ticker} ({reason})...")
            new_v = analyze_company_with_proper_model(ticker)
            if new_v and new_v.get("fair_value_base"):
                new_v["last_fundamental_update"] = today_str
                new_v["last_filing_check"] = today_str

                # Detect meaningful fundamental change
                if (
                    new_v.get("latest_filing_date") != old_v.get("latest_filing_date")
                    or new_v.get("verdict") != old_v.get("verdict")
                    or abs(float(new_v.get("fair_value_base") or 0) - float(old_v.get("fair_value_base") or 0)) > 0.05
                    or abs(float(new_v.get("roic_pct") or 0) - float(old_v.get("roic_pct") or 0)) > 0.2
                ):
                    changed_tickers.append(ticker)

                verdicts[idx] = new_v
                refreshed_tickers.append(ticker)
        except Exception as e:
            logger.warning(f"Error refreshing {ticker}: {e}")

    verdicts_data["verdicts"] = verdicts
    verdicts_data["total_audited"] = len(verdicts)
    verdicts_data["timestamp"] = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    _save_fundamental_verdicts(verdicts_data)

    # Cascade updates across Registry, DB suggestions, and visual dossiers
    if refreshed_tickers:
        try:
            QuantamentalRegistry.get_instance().load_profiles()
        except Exception:
            pass

        try:
            from scripts.generate_asset_dossiers import generate_single_asset_dossier
            os.makedirs(DOSSIERS_DIR, exist_ok=True)
            verdict_lookup = {v.get("ticker"): v for v in verdicts if v.get("ticker")}
            for ticker in refreshed_tickers:
                _cascade_fundamental_to_db(ticker, db)
                try:
                    opt_prof = opt_profiles.get(ticker, {})
                    v_item = verdict_lookup.get(ticker, {})
                    dossier = generate_single_asset_dossier(ticker, optimal_profile=opt_prof, verdict_item=v_item)
                    if dossier:
                        safe_sym = ticker.replace("/", "_").replace("^", "_").replace(":", "_")
                        _atomic_write_json(os.path.join(DOSSIERS_DIR, f"{safe_sym}.json"), dossier)
                except Exception as de:
                    logger.warning(f"Dossier regeneration notice for {ticker}: {de}")
        except Exception as e:
            logger.warning(f"Post-fundamental dossier cascade notice: {e}")

    logger.info(
        f"✅ Checked {checked_count} equities: refreshed {len(refreshed_tickers)} "
        f"({len(changed_tickers)} with updated filings/valuations)!"
    )
    return {
        "checked_count": checked_count,
        "refreshed_count": len(refreshed_tickers),
        "changed_count": len(changed_tickers),
        "tickers": refreshed_tickers,
        "changed_tickers": changed_tickers,
    }


def sync_verdicts_mark_to_market(db: Optional[Database] = None) -> int:
    """
    Synchronizes live 1D market prices from state.db into fundamental_verdicts.json
    and research/verdicts.json so MoS %, Upside %, and Verdicts reflect real-time prices
    across the Fundamental Screener and all dossiers even between quarterly filings.
    """
    if db is None:
        return 0
    verdicts_data = _load_fundamental_verdicts()
    verdicts = verdicts_data.get("verdicts", [])
    if not verdicts:
        return 0

    try:
        rows = db.get_all_states()
    except Exception:
        return 0

    live_prices: Dict[str, float] = {}
    for r in rows:
        if r["timeframe"] == "1D" and r["last_price"] and r["last_price"] > 0:
            live_prices[r["ticker"]] = float(r["last_price"])

    updated = 0
    for item in verdicts:
        t = item.get("ticker")
        lp = live_prices.get(t)
        if not lp or lp <= 0:
            continue
        fv = item.get("fair_value_base") or item.get("target_price")
        old_px = item.get("price")
        if old_px is not None and abs(float(old_px) - lp) < 1e-4:
            continue

        item["price"] = round(lp, 4)
        if fv and float(fv) > 0:
            fv_f = float(fv)
            live_mos = round(((fv_f - lp) / fv_f) * 100.0, 1)
            live_upside = round(((fv_f - lp) / lp) * 100.0, 1)
            item["mos_pct"] = live_mos
            item["actual_discount_pct"] = live_mos
            item["upside_pct"] = live_upside

            v_upper = str(item.get("verdict") or "").upper()
            z_sc = item.get("z_score")
            is_distressed = any(k in v_upper for k in ["FORENSIC", "AVOID", "CAPITAL EROSION", "DISTRESSED"]) or (
                z_sc is not None and float(z_sc) < 1.10
            )
            if not is_distressed and item.get("data_quality") != "INSUFFICIENT":
                moat_val = item.get("moat", "None")
                if live_mos >= 20.0:
                    item["verdict"] = "STRONG BUY" if moat_val == "Wide" else "BUY / ACCUMULATE"
                    item["action"] = "BUY"
                elif live_mos >= 5.0:
                    item["verdict"] = "BUY / ACCUMULATE"
                    item["action"] = "BUY"
                elif live_mos >= -15.0:
                    item["verdict"] = "HOLD / FAIRLY VALUED"
                    item["action"] = "HOLD"
                else:
                    item["verdict"] = "HOLD / SENSITIVITY REVIEW" if moat_val == "Wide" else "REDUCE / OVERVALUED"
                    item["action"] = "HOLD" if moat_val == "Wide" else "REDUCE"
        updated += 1

    if updated > 0:
        verdicts_data["verdicts"] = verdicts
        verdicts_data["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _save_fundamental_verdicts(verdicts_data)
        try:
            QuantamentalRegistry.get_instance().load_profiles()
        except Exception:
            pass
        logger.debug(f"Mark-to-market fundamental sync updated {updated} equity rows.")
    return updated
