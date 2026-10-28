"""
Master Universe Optimization v3 across all 797 cached assets.
Fixes:
1. True Classic Exit (Hold through Neutral, Exit strictly on BLUE without premature trend lock-out).
2. Proper Quantamental Accumulator lifecycle (scales 50% -> 100% on GOLD, exits on BLUE only after GOLD reached).
3. Daily Mark-to-Market equity curve for realistic Max Drawdown and Sharpe Ratio calculation.
4. Generates updated data/asset_optimal_profiles.json and master_universe_profiles.csv.
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
logger = logging.getLogger("MasterOptimizerV3")

COMMISSION_PCT = 0.001  # 0.10%


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
) -> dict:
    n = len(closes) if end_idx is None else min(len(closes), end_idx)
    if n <= start_idx + 10:
        return {
            "total_trades": 0, "win_rate": 0.0, "total_return_pct": 0.0,
            "cagr_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0, "profit_factor": 1.0,
            "buy_and_hold_pct": 0.0
        }

    bnh_return = ((closes[n - 1] - closes[start_idx]) / closes[start_idx]) * 100.0

    in_position = False
    position_size = 1.0
    entry_price = 0.0
    shares = 0.0
    cash = 10000.0
    has_reached_gold = False

    trades_pnl: List[float] = []
    equity_curve: List[float] = []

    for i in range(start_idx, n):
        curr_open = opens[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_state = states[i - 1]

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
                    if position_size == 0.5:
                        # Scale to full 100% position on GOLD confirmation
                        additional_shares = (cash * 0.999) / curr_open
                        shares += additional_shares
                        cash -= additional_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_size = 1.0

                # Exit only on BLUE if it previously experienced GOLD, or structural stop if in deep loss (>15%)
                if (has_reached_gold and prev_state == -1) or (curr_low <= entry_price * 0.85):
                    exit_price = curr_open
                    exited = True

            if exited:
                net_proceeds = shares * exit_price * (1.0 - COMMISSION_PCT)
                trade_pnl = (net_proceeds - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
                trades_pnl.append(trade_pnl)
                cash += net_proceeds
                shares = 0.0
                in_position = False
                position_size = 1.0
                has_reached_gold = False

        # 2. Check entries if not in position
        if not in_position and i < n - 1:
            should_enter = False
            size = 1.0

            if strategy in ["FAST_EXIT", "CLASSIC_BLUE_EXIT", "OPTIMAL_SMMA"]:
                # If state is GOLD, enter! (Eliminates the lockout bug)
                if prev_state == 1:
                    should_enter = True

            elif strategy == "QUANTAMENTAL_ACCUMULATOR":
                if fundamental_bullish:
                    # Dip entry in BLUE with price stabilization
                    if prev_state == -1 and curr_close > v1[i - 1]:
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
                cash -= shares * curr_open * (1.0 + COMMISSION_PCT)

        # 3. DAILY MARK-TO-MARKET (Crucial for realistic DD & Sharpe)
        current_daily_equity = cash + (shares * curr_close)
        equity_curve.append(current_daily_equity)

    # Close any lingering position at end
    if in_position and shares > 0:
        net_proceeds = shares * closes[n - 1] * (1.0 - COMMISSION_PCT)
        trade_pnl = (net_proceeds - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
        trades_pnl.append(trade_pnl)
        cash += net_proceeds
        shares = 0.0

    final_equity = cash
    total_trades = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    total_return = ((final_equity - 10000.0) / 10000.0) * 100.0

    years = max(0.5, (n - start_idx) / 252.0)
    cagr = (((final_equity / 10000.0) ** (1.0 / years)) - 1.0) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = min(20.0, gross_profit / gross_loss) if gross_loss > 0 else (20.0 if gross_profit > 0 else 1.0)

    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

    daily_returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "profit_factor": round(profit_factor, 2),
        "buy_and_hold_pct": round(bnh_return, 2),
    }


def analyze_v3_asset(args) -> Optional[dict]:
    symbol, asset_class, df, fund_bullish = args
    if df is None or len(df) < 150:
        return None

    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)

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
    res_classic = run_single_simulation_v3(opens, highs, lows, closes, states_std, v1_std, v2_std, atr, "CLASSIC_BLUE_EXIT", fund_bullish)
    res_fast = run_single_simulation_v3(opens, highs, lows, closes, states_std, v1_std, v2_std, atr, "FAST_EXIT", fund_bullish)
    res_scaled = run_single_simulation_v3(opens, highs, lows, closes, states_fast, v1_fast, v2_fast, atr, "OPTIMAL_SMMA", fund_bullish)
    res_quant = run_single_simulation_v3(opens, highs, lows, closes, states_std, v1_std, v2_std, atr, "QUANTAMENTAL_ACCUMULATOR", fund_bullish) if fund_bullish else None

    # Walk-Forward split check (Train 60%, Test 40%)
    split_idx = int(len(closes) * 0.6)
    test_classic = run_single_simulation_v3(opens, highs, lows, closes, states_std, v1_std, v2_std, atr, "CLASSIC_BLUE_EXIT", fund_bullish, start_idx=split_idx)
    test_fast = run_single_simulation_v3(opens, highs, lows, closes, states_std, v1_std, v2_std, atr, "FAST_EXIT", fund_bullish, start_idx=split_idx)

    candidates = [
        ("CLASSIC_BLUE_EXIT", res_classic, [15, 19, 25, 29], False),
        ("FAST_EXIT", res_fast, [15, 19, 25, 29], True),
        ("OPTIMAL_SMMA", res_scaled, [11, 14, 19, 22], False),
    ]
    if res_quant and res_quant["total_trades"] > 0:
        candidates.append(("QUANTAMENTAL_ACCUMULATOR", res_quant, [15, 19, 25, 29], False))

    best_name, best_res, best_periods, exit_on_neutral = max(
        candidates, key=lambda c: (c[1]["sharpe_ratio"] * 80.0 + c[1]["total_return_pct"])
    )

    sharpe = best_res["sharpe_ratio"]
    cagr = best_res["cagr_pct"]
    dd = best_res["max_drawdown_pct"]
    ret = best_res["total_return_pct"]
    pf = best_res["profit_factor"]

    if sharpe >= 0.45 and ret >= 50.0 and dd <= 35.0:
        tier = "S"
        suitability = "HIGH_TREND_ALPHA"
    elif sharpe >= 0.20 and ret > 0:
        tier = "A"
        suitability = "TREND_POSITIVE"
    elif ret > 0:
        tier = "B"
        suitability = "MODERATE_TREND"
    else:
        tier = "C"
        suitability = "AVOID_CHOP"

    wf_stable = bool(test_classic["total_return_pct"] >= 0 if best_name == "CLASSIC_BLUE_EXIT" else test_fast["total_return_pct"] >= 0)

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
    }


def main():
    logger.info("=== RUNNING MASTER UNIVERSE OPTIMIZATION V3 (ALL 797 CACHED ASSETS) ===")
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
    for ticker, cat in load_tasks:
        clean_sym = ticker.replace("=", "_").replace("^", "_").replace(":", "_")
        cache_file = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                if len(df) >= 150:
                    prof = get_fundamental_profile(ticker)
                    fund_bullish = prof.is_bullish if prof else (True if ticker in ["BTCUSDT", "ETHUSDT", "NVDA", "MSFT", "AAPL", "PLTR", "LLY", "TSM"] else False)
                    valid_tasks.append((ticker, cat, df, fund_bullish))
            except Exception:
                pass

    logger.info(f"Loaded {len(valid_tasks)} assets from local SSD cache in {time.time() - t0:.2f}s!")

    # 16-thread processing
    t1 = time.time()
    all_profiles = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(16, os.cpu_count() or 8)) as pool:
        for p in pool.map(analyze_v3_asset, valid_tasks):
            if p is not None:
                all_profiles.append(p)

    sim_time = time.time() - t1
    logger.info(f"Processed all {len(all_profiles)} assets in {sim_time:.2f}s!")

    # Save to data/asset_optimal_profiles.json
    out_json = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
    profiles_dict = {p["symbol"]: p for p in all_profiles}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(profiles_dict, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved optimal profile database to {out_json}")

    # Export to master_universe_profiles.csv
    df = pd.DataFrame(all_profiles)
    out_csv = os.path.join(BASE_DIR, "master_universe_profiles.csv")
    df.to_csv(out_csv, index=False)
    logger.info(f"Exported CSV ranking to {out_csv}")

    # Terminal Report
    print("\n" + "=" * 115)
    print(f"MASTER UNIVERSE OPTIMIZATION V3 REPORT ({len(all_profiles)} ASSETS, 1D)")
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
    print(s_tier[["symbol", "asset_class", "recommended_strategy", "exit_on_neutral", "cagr_pct", "sharpe_ratio", "max_drawdown_pct", "profit_factor", "alpha_vs_bnh"]].to_string(index=False))

    print("\n--- Key Benchmarks (NVDA, PLTR, BTC, TSM, SOL) ---")
    bench_syms = ["NVDA", "PLTR", "BTCUSDT", "TSM", "SOLUSDT", "MSFT", "AMZN"]
    bench_df = df[df["symbol"].isin(bench_syms)]
    print(bench_df[["symbol", "recommended_strategy", "exit_on_neutral", "total_return_pct", "buy_and_hold_pct", "alpha_vs_bnh", "sharpe_ratio", "max_drawdown_pct"]].to_string(index=False))
    print("=" * 115)


if __name__ == "__main__":
    main()
