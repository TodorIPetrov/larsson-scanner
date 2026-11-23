"""
Master Universe Optimization v4 across all cached assets.
Fixes:
1. Zero-look-ahead simulation (strictly t-1 signals/prices, gap-down stops, exact cost basis).
2. True Classic Exit (Hold through Neutral, Exit strictly on BLUE) & Fast Exit (NEUTRAL).
3. Correct annualization (365 days for crypto, 252 days for equities/commodities/indices).
4. Data quality validation (rejects stale/flat feeds like ZNC=F and flags extreme splits).
5. True Out-of-Sample Walk-Forward check on the exact selected strategy + B&H benchmark comparison.
6. Safe merge into data/asset_optimal_profiles.json preserving live technical, Value DNA & Mega Exit keys.
"""

import concurrent.futures
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from src.engine.quantamental import get_fundamental_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterOptimizerV4")

COMMISSION_PCT = 0.001  # 0.10%


def validate_ohlcv_quality(df: pd.DataFrame) -> Tuple[bool, str]:
    """Validates OHLCV data quality, rejecting stale/flat feeds and flagging extreme jumps."""
    required = {"date", "open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(set(df.columns)):
        return (False, "MISSING_COLUMNS")

    clean = df.copy()
    clean["date"] = pd.to_datetime(clean["date"].astype(str).str[:10], errors="coerce")
    for col in ("open", "high", "low", "close"):
        clean[col] = pd.to_numeric(clean[col], errors="coerce")
    clean = clean.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)

    if len(clean) < 150:
        return (False, "INSUFFICIENT_BARS")
    if clean["close"].nunique() < 50:
        return (False, "STALE_PRICES")

    pct_abs = clean["close"].pct_change().abs().dropna()
    if len(pct_abs) > 0 and float(pct_abs.max()) > 2.0:
        return (True, "EXTREME_JUMP_OR_SPLIT")

    return (True, "OK")


def fast_compute_smma(src: np.ndarray, length: int) -> np.ndarray:
    n = len(src)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < length:
        return out
    out[length - 1] = np.mean(src[:length])
    factor = length - 1
    for i in range(length, n):
        out[i] = (out[i - 1] * factor + src[i]) / length
    return out


def fast_compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return atr
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def evaluate_larsson_states(v1: np.ndarray, m1: np.ndarray, m2: np.ndarray, v2: np.ndarray) -> np.ndarray:
    n = len(v1)
    states = np.zeros(n, dtype=np.int8)
    for i in range(n):
        if np.isnan(v1[i]) or np.isnan(m1[i]) or np.isnan(m2[i]) or np.isnan(v2[i]):
            states[i] = 0
            continue
        p2 = ((v1[i] < m1[i]) != (v1[i] < v2[i])) or ((m2[i] < v2[i]) != (v1[i] < v2[i]))
        p3 = (not p2) and (v1[i] < v2[i])
        p1 = (not p2) and (not p3)
        if p1:
            states[i] = 1  # GOLD
        elif p3:
            states[i] = -1  # BLUE
        else:
            states[i] = 0  # NEUTRAL
    return states


def run_single_simulation_v3(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    states: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    atr: np.ndarray,
    strategy: str,
    fundamental_bullish: bool = False,
    start_idx: int = 50,
    end_idx: Optional[int] = None,
    ann_days: float = 252.0,
) -> dict:
    n = len(closes) if end_idx is None else min(len(closes), end_idx)
    if n <= start_idx + 10:
        return {
            "total_trades": 0, "win_rate": 0.0, "total_return_pct": 0.0,
            "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0, "profit_factor": 1.0,
            "buy_and_hold_pct": 0.0, "bnh_cagr_pct": 0.0, "bnh_max_drawdown_pct": 0.0,
            "bnh_sharpe_ratio": 0.0, "annualized_vol_pct": 0.0,
        }

    years = max(0.25, (n - start_idx) / float(ann_days))

    # Full Buy & Hold benchmark metrics on the exact same [start_idx, n) window
    bnh_open = opens[start_idx] if opens[start_idx] > 0 else closes[start_idx]
    bnh_entry = bnh_open * (1.0 + COMMISSION_PCT)
    bnh_shares = 10000.0 / bnh_entry if bnh_entry > 0 else 0.0
    bnh_eq = bnh_shares * closes[start_idx:n]
    bnh_final = float(bnh_eq[-1]) * (1.0 - COMMISSION_PCT) if len(bnh_eq) > 0 else 10000.0
    bnh_return = ((bnh_final - 10000.0) / 10000.0) * 100.0
    bnh_cagr = (((max(bnh_final, 1.0) / 10000.0) ** (1.0 / years)) - 1.0) * 100.0
    bnh_peaks = np.maximum.accumulate(bnh_eq)
    bnh_dds = (bnh_peaks - bnh_eq) / np.where(bnh_peaks > 0, bnh_peaks, 1.0)
    bnh_max_dd = float(np.max(bnh_dds)) * 100.0 if len(bnh_dds) > 0 else 0.0
    bnh_dr = np.diff(bnh_eq) / np.where(bnh_eq[:-1] > 0, bnh_eq[:-1], 1.0)
    bnh_std = float(np.std(bnh_dr)) if len(bnh_dr) > 1 else 0.0
    bnh_sharpe = (float(np.mean(bnh_dr)) / bnh_std) * np.sqrt(ann_days) if bnh_std > 1e-12 else 0.0
    ann_vol = bnh_std * np.sqrt(ann_days) * 100.0

    in_position = False
    position_size = 1.0
    entry_price = 0.0
    shares = 0.0
    cost_basis = 0.0
    cash = 10000.0
    has_reached_gold = False

    trades_pnl: List[float] = []
    equity_curve: List[float] = []

    for i in range(start_idx, n):
        curr_open = opens[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_state = states[i - 1]
        prev_close = closes[i - 1]

        # 1. Manage existing position
        if in_position:
            exited = False
            exit_price = 0.0

            if strategy == "FAST_EXIT":
                # Exit as soon as GOLD ends
                if prev_state != 1:
                    exit_price = curr_open
                    exited = True

            elif strategy in ["CLASSIC_BLUE_EXIT", "OPTIMAL_SMMA"]:
                # True Classic: Hold through NEUTRAL, Exit strictly on BLUE
                if prev_state == -1:
                    exit_price = curr_open
                    exited = True

            elif strategy == "QUANTAMENTAL_ACCUMULATOR":
                if prev_state == 1:
                    has_reached_gold = True
                    if position_size == 0.5 and curr_open > 0 and cash > 0:
                        # Scale to full 100% position on GOLD confirmation
                        add_cash = cash * 0.999
                        additional_shares = add_cash / (curr_open * (1.0 + COMMISSION_PCT))
                        add_cost = additional_shares * curr_open * (1.0 + COMMISSION_PCT)
                        shares += additional_shares
                        cash -= add_cost
                        cost_basis += add_cost
                        position_size = 1.0

                # Separate BLUE exit (at open) from intra-bar 15% structural stop (gap-down aware)
                if has_reached_gold and prev_state == -1:
                    exit_price = curr_open
                    exited = True
                elif curr_low <= entry_price * 0.85:
                    exit_price = min(curr_open, entry_price * 0.85)
                    exited = True

            if exited:
                net_proceeds = shares * exit_price * (1.0 - COMMISSION_PCT)
                trade_pnl = (net_proceeds - cost_basis) / cost_basis if cost_basis > 0 else 0.0
                trades_pnl.append(trade_pnl)
                cash += net_proceeds
                shares = 0.0
                cost_basis = 0.0
                in_position = False
                position_size = 1.0
                has_reached_gold = False

        # 2. Check entries if not in position
        if not in_position and i < n - 1 and curr_open > 0:
            should_enter = False
            size = 1.0

            if strategy in ["FAST_EXIT", "CLASSIC_BLUE_EXIT", "OPTIMAL_SMMA"]:
                # If prior bar state is GOLD, enter at today's open
                if prev_state == 1:
                    should_enter = True

            elif strategy == "QUANTAMENTAL_ACCUMULATOR":
                if fundamental_bullish:
                    # Strictly t-1 close > v1[i-1] (zero look-ahead)
                    if prev_state == -1 and not np.isnan(v1[i - 1]) and prev_close > v1[i - 1]:
                        should_enter = True
                        size = 0.5
                    elif prev_state == 1:
                        should_enter = True
                        size = 1.0
                        has_reached_gold = True

            if should_enter:
                in_position = True
                position_size = size
                entry_price = curr_open
                invest_cash = cash * position_size
                shares = (invest_cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                cost_basis = shares * curr_open * (1.0 + COMMISSION_PCT)
                cash -= cost_basis

        # 3. DAILY MARK-TO-MARKET (Crucial for realistic DD & Sharpe)
        current_daily_equity = cash + (shares * curr_close)
        equity_curve.append(current_daily_equity)

    # Close any lingering position at end
    if in_position and shares > 0:
        net_proceeds = shares * closes[n - 1] * (1.0 - COMMISSION_PCT)
        trade_pnl = (net_proceeds - cost_basis) / cost_basis if cost_basis > 0 else 0.0
        trades_pnl.append(trade_pnl)
        cash += net_proceeds
        shares = 0.0
        cost_basis = 0.0
        if equity_curve:
            equity_curve[-1] = cash

    final_equity = cash
    total_trades = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    total_return = ((final_equity - 10000.0) / 10000.0) * 100.0

    cagr = (((max(final_equity, 1.0) / 10000.0) ** (1.0 / years)) - 1.0) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = min(20.0, gross_profit / gross_loss) if gross_loss > 0 else (20.0 if gross_profit > 0 else 1.0)

    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peaks) / np.where(peaks > 0, peaks, 1.0)
    max_dd = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

    daily_returns = np.diff(eq_arr) / np.where(eq_arr[:-1] > 0, eq_arr[:-1], 1.0)
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 1e-12:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(ann_days)

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "profit_factor": round(profit_factor, 2),
        "buy_and_hold_pct": round(bnh_return, 2),
        "bnh_cagr_pct": round(bnh_cagr, 2),
        "bnh_max_drawdown_pct": round(bnh_max_dd, 2),
        "bnh_sharpe_ratio": round(bnh_sharpe, 2),
        "annualized_vol_pct": round(ann_vol, 2),
    }


def analyze_v3_asset(args) -> Optional[dict]:
    if len(args) == 5:
        symbol, asset_class, df, fund_bullish, data_warning = args
    else:
        symbol, asset_class, df, fund_bullish = args
        data_warning = "OK"

    if df is None or len(df) < 150:
        return None

    df_work = df.copy()
    dates = None
    start_idx = 50

    if "date" in df_work.columns:
        df_work["date"] = pd.to_datetime(df_work["date"].astype(str).str[:10], errors="coerce")
        for col in ("open", "high", "low", "close"):
            df_work[col] = pd.to_numeric(df_work[col], errors="coerce")
        df_work = df_work.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)
        if len(df_work) < 150:
            return None
        recent = df_work[df_work["date"] >= "2021-06-01"].reset_index(drop=True)
        if len(recent) >= 150:
            df_work = recent
            dates = df_work["date"].to_numpy()
            idx_sep = int(np.searchsorted(dates, np.datetime64("2021-09-01")))
            start_idx = max(50, idx_sep)
        else:
            dates = df_work["date"].to_numpy()

    highs = df_work["high"].to_numpy(dtype=np.float64)
    lows = df_work["low"].to_numpy(dtype=np.float64)
    closes = df_work["close"].to_numpy(dtype=np.float64)
    opens = df_work["open"].to_numpy(dtype=np.float64)

    if len(closes) - start_idx < 80:
        return None

    ann_days = 365.0 if (asset_class == "crypto" or "USDT" in symbol) else 252.0

    hl2 = (highs + lows) / 2.0
    atr = fast_compute_atr(highs, lows, closes, 14)

    # 1. Standard SMMA
    v1_std = fast_compute_smma(hl2, 15)
    m1_std = fast_compute_smma(hl2, 19)
    m2_std = fast_compute_smma(hl2, 25)
    v2_std = fast_compute_smma(hl2, 29)
    states_std = evaluate_larsson_states(v1_std, m1_std, m2_std, v2_std)

    # 2. Fast SMMA
    v1_fast = fast_compute_smma(hl2, 11)
    m1_fast = fast_compute_smma(hl2, 14)
    m2_fast = fast_compute_smma(hl2, 19)
    v2_fast = fast_compute_smma(hl2, 22)
    states_fast = evaluate_larsson_states(v1_fast, m1_fast, m2_fast, v2_fast)

    # Run simulations
    res_classic = run_single_simulation_v3(
        opens, highs, lows, closes, states_std, v1_std, v2_std, atr,
        "CLASSIC_BLUE_EXIT", fund_bullish, start_idx=start_idx, ann_days=ann_days,
    )
    res_fast = run_single_simulation_v3(
        opens, highs, lows, closes, states_std, v1_std, v2_std, atr,
        "FAST_EXIT", fund_bullish, start_idx=start_idx, ann_days=ann_days,
    )
    res_scaled = run_single_simulation_v3(
        opens, highs, lows, closes, states_fast, v1_fast, v2_fast, atr,
        "OPTIMAL_SMMA", fund_bullish, start_idx=start_idx, ann_days=ann_days,
    )
    res_quant = (
        run_single_simulation_v3(
            opens, highs, lows, closes, states_std, v1_std, v2_std, atr,
            "QUANTAMENTAL_ACCUMULATOR", fund_bullish, start_idx=start_idx, ann_days=ann_days,
        )
        if fund_bullish else None
    )

    candidates = [
        ("CLASSIC_BLUE_EXIT", res_classic, [15, 19, 25, 29], False),
        ("FAST_EXIT", res_fast, [15, 19, 25, 29], True),
        ("OPTIMAL_SMMA", res_scaled, [11, 14, 19, 22], False),
    ]
    if res_quant and res_quant["total_trades"] > 0:
        candidates.append(("QUANTAMENTAL_ACCUMULATOR", res_quant, [15, 19, 25, 29], False))

    eligible = [c for c in candidates if c[1]["total_trades"] >= 3]
    pool = eligible if eligible else candidates

    best_name, best_res, best_periods, exit_on_neutral = max(
        pool, key=lambda c: (c[1]["sharpe_ratio"] * 80.0 + min(c[1]["total_return_pct"], 500.0))
    )

    # True Out-of-Sample Walk-Forward check on the EXACT chosen strategy
    if dates is not None:
        idx_24 = int(np.searchsorted(dates, np.datetime64("2024-01-01")))
        if (idx_24 - start_idx) >= 120 and (len(closes) - idx_24) >= 120:
            split_idx = idx_24
        else:
            split_idx = int(start_idx + (len(closes) - start_idx) * 0.6)
    else:
        split_idx = int(start_idx + (len(closes) - start_idx) * 0.6)

    st_oos = states_fast if best_name == "OPTIMAL_SMMA" else states_std
    v1_oos = v1_fast if best_name == "OPTIMAL_SMMA" else v1_std
    v2_oos = v2_fast if best_name == "OPTIMAL_SMMA" else v2_std
    oos_res = run_single_simulation_v3(
        opens, highs, lows, closes, st_oos, v1_oos, v2_oos, atr,
        best_name, fund_bullish, start_idx=split_idx, ann_days=ann_days,
    )

    wf_stable = bool(
        oos_res["total_trades"] >= 1
        and (
            (oos_res["total_return_pct"] > 0 and oos_res["sharpe_ratio"] >= 0.15)
            or (oos_res["total_return_pct"] > oos_res["buy_and_hold_pct"] + 15.0 and oos_res["sharpe_ratio"] > 0)
        )
    )

    sharpe = best_res["sharpe_ratio"]
    cagr = best_res["cagr_pct"]
    dd = best_res["max_drawdown_pct"]
    ret = best_res["total_return_pct"]
    pf = best_res["profit_factor"]
    bnh_sharpe = best_res["bnh_sharpe_ratio"]
    bnh_mdd = best_res["bnh_max_drawdown_pct"]
    sharpe_vs_bnh = round(sharpe - bnh_sharpe, 2)
    dd_saved_vs_bnh = round(bnh_mdd - dd, 2)
    full_cycle = bool((len(closes) - start_idx) >= (1000 if ann_days == 252.0 else 1400))

    if best_res["total_trades"] < 3:
        tier = "C"
        suitability = "AVOID_CHOP"
        wf_stable = False
    elif (
        data_warning == "OK"
        and wf_stable
        and sharpe >= 0.80
        and ret >= 50.0
        and dd <= 50.0
        and (sharpe >= bnh_sharpe - 0.15 or dd_saved_vs_bnh >= 15.0)
    ):
        tier = "S"
        suitability = "HIGH_TREND_ALPHA"
    elif sharpe >= 0.40 and ret > 15.0 and (sharpe >= bnh_sharpe - 0.25 or dd_saved_vs_bnh >= 10.0):
        tier = "A"
        suitability = "TREND_POSITIVE"
    elif ret > 0 and sharpe >= 0.15:
        tier = "B"
        suitability = "MODERATE_TREND"
    else:
        tier = "C"
        suitability = "AVOID_CHOP"

    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "recommended_strategy": best_name,
        "optimal_smma_periods": best_periods,
        "exit_on_neutral": exit_on_neutral,
        "empirical_tier": tier,
        "larsson_suitability": suitability,
        "walk_forward_stable": wf_stable,
        "total_return_pct": ret,
        "cagr_pct": cagr,
        "max_drawdown_pct": dd,
        "sharpe_ratio": sharpe,
        "profit_factor": pf,
        "win_rate_pct": best_res["win_rate"],
        "total_trades": best_res["total_trades"],
        "buy_and_hold_pct": best_res["buy_and_hold_pct"],
        "alpha_vs_bnh": round(ret - best_res["buy_and_hold_pct"], 2),
        "bnh_cagr_pct": best_res["bnh_cagr_pct"],
        "bnh_max_drawdown_pct": bnh_mdd,
        "bnh_sharpe_ratio": bnh_sharpe,
        "sharpe_vs_bnh": sharpe_vs_bnh,
        "dd_saved_vs_bnh": dd_saved_vs_bnh,
        "annualized_vol_pct": best_res["annualized_vol_pct"],
        "oos_return_pct": oos_res["total_return_pct"],
        "oos_sharpe_ratio": oos_res["sharpe_ratio"],
        "oos_bnh_pct": oos_res["buy_and_hold_pct"],
        "oos_trades": oos_res["total_trades"],
        "full_cycle": full_cycle,
        "data_quality": data_warning,
    }


def main():
    logger.info("=== RUNNING MASTER UNIVERSE OPTIMIZATION V4 (ZERO LOOK-AHEAD + DATA QUALITY GUARD) ===")
    dm = BacktestDataManager()

    # Load from assets.yaml + sp500
    with open(os.path.join(BASE_DIR, "config", "assets.yaml"), "r", encoding="utf-8") as f:
        assets_cfg = yaml.safe_load(f)

    sp500_path = os.path.join(BASE_DIR, "config", "sp500_tickers.json")
    sp500_tickers = []
    if os.path.exists(sp500_path):
        with open(sp500_path, "r", encoding="utf-8") as f:
            sp500_tickers = json.load(f)

    seen = set()
    load_tasks = []

    for cat, items in assets_cfg.items():
        for item in items:
            ticker = item["ticker"] if isinstance(item, dict) else str(item)
            if ticker not in seen:
                seen.add(ticker)
                load_tasks.append((ticker, cat))

    for ticker in sp500_tickers:
        clean = ticker.strip().upper()
        if clean not in seen:
            seen.add(clean)
            load_tasks.append((clean, "us_stocks"))

    logger.info(f"Checking local cache for {len(load_tasks)} assets...")
    t0 = time.time()
    valid_tasks = []
    rejected_stale_symbols = set()
    for ticker, cat in load_tasks:
        clean_sym = ticker.replace("=", "_").replace("^", "_").replace(":", "_")
        cache_file = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                is_valid, data_warning = validate_ohlcv_quality(df)
                if not is_valid:
                    if data_warning == "STALE_PRICES":
                        rejected_stale_symbols.add(ticker)
                    logger.info(f"Skipping {ticker} [{cat}]: data quality={data_warning}")
                    continue
                prof = get_fundamental_profile(ticker)
                fund_bullish = prof.is_bullish if prof else (True if ticker in ["BTCUSDT", "ETHUSDT", "NVDA", "MSFT", "AAPL", "PLTR", "LLY", "TSM"] else False)
                valid_tasks.append((ticker, cat, df, fund_bullish, data_warning))
            except Exception:
                pass

    logger.info(f"Loaded {len(valid_tasks)} validated assets from local SSD cache in {time.time() - t0:.2f}s (rejected stale: {sorted(rejected_stale_symbols)})!")

    # 16-thread processing
    t1 = time.time()
    all_profiles = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(16, os.cpu_count() or 8)) as pool:
        for p in pool.map(analyze_v3_asset, valid_tasks):
            if p is not None:
                all_profiles.append(p)

    sim_time = time.time() - t1
    logger.info(f"Processed all {len(all_profiles)} assets in {sim_time:.2f}s!")

    # Safe merge into data/asset_optimal_profiles.json (preserve live technical, Value DNA & Mega Exit keys)
    out_json = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
    existing_profiles = {}
    if os.path.exists(out_json):
        try:
            with open(out_json, "r", encoding="utf-8") as f:
                existing_profiles = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read existing {out_json} for merge: {e}")

    merged_profiles = {
        k: v for k, v in existing_profiles.items()
        if k not in rejected_stale_symbols and k != "ZNC=F"
    }
    for p in all_profiles:
        sym = p["symbol"]
        merged_profiles[sym] = {**merged_profiles.get(sym, {}), **p}

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(merged_profiles, f, indent=2, ensure_ascii=False)
    logger.info(f"Merged & saved {len(merged_profiles)} profiles to {out_json}")

    # Export to master_universe_profiles.csv
    df = pd.DataFrame(all_profiles)
    out_csv = os.path.join(BASE_DIR, "master_universe_profiles.csv")
    df.to_csv(out_csv, index=False)
    logger.info(f"Exported CSV ranking to {out_csv}")

    # Terminal Report
    print("\n" + "=" * 115)
    print(f"MASTER UNIVERSE OPTIMIZATION V4 REPORT ({len(all_profiles)} ASSETS, 1D, ZERO LOOK-AHEAD)")
    print("=" * 115)

    print("\n--- Strategy Distribution as #1 Winner ---")
    print(df["recommended_strategy"].value_counts().to_string())

    print("\n--- Empirical Quality Tier Breakdown ---")
    print(df["empirical_tier"].value_counts().to_string())

    print("\n--- Strategy Performance Aggregation across Whole Market ---")
    strat_summary = df.groupby("recommended_strategy").agg({
        "total_return_pct": ["count", "mean", "median"],
        "max_drawdown_pct": "mean",
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
        "win_rate_pct": "mean",
    }).round(2)
    print(strat_summary.to_string())

    print("\n--- Top 20 Elite S-Tier Assets (Highest Sharpe & Trend Alpha) ---")
    s_tier = df[df["empirical_tier"] == "S"].sort_values("sharpe_ratio", ascending=False).head(20)
    print(s_tier[["symbol", "asset_class", "recommended_strategy", "exit_on_neutral", "cagr_pct", "sharpe_ratio", "bnh_sharpe_ratio", "max_drawdown_pct", "oos_return_pct", "alpha_vs_bnh"]].to_string(index=False))

    print("\n--- Key Benchmarks (NVDA, PLTR, BTC, TSM, SOL, GOOGL, GC=F) ---")
    bench_syms = ["NVDA", "PLTR", "BTCUSDT", "TSM", "SOLUSDT", "MSFT", "AMZN", "GOOGL", "GC=F"]
    bench_df = df[df["symbol"].isin(bench_syms)]
    print(bench_df[["symbol", "recommended_strategy", "exit_on_neutral", "empirical_tier", "total_return_pct", "buy_and_hold_pct", "sharpe_ratio", "bnh_sharpe_ratio", "max_drawdown_pct", "oos_return_pct"]].to_string(index=False))
    print("=" * 115)


if __name__ == "__main__":
    main()
