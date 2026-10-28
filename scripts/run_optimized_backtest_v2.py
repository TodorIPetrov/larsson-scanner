"""
Backtest v2.0 Optimizer and Strategy Comparator.
Executes improved Larsson rules, Chop filters, SMMA parameter sweep,
Quantamental Accumulator, and realistic commissions (0.10%).
Leverages 16 threads across Ryzen AI 7 350.
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
logger = logging.getLogger("BacktestV2")

COMMISSION_PCT = 0.001  # 0.10% commission & slippage per fill


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


def fast_compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    if n < period * 2:
        return np.full(n, 20.0, dtype=np.float64)

    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))

    # Smooth TR and DM
    atr = fast_compute_smma(tr, period)
    plus_di = 100.0 * (fast_compute_smma(plus_dm, period) / np.where(atr == 0, 1e-6, atr))
    minus_di = 100.0 * (fast_compute_smma(minus_dm, period) / np.where(atr == 0, 1e-6, atr))

    dx = 100.0 * (abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, 1e-6, (plus_di + minus_di)))
    adx_smooth = fast_compute_smma(dx, period)

    full_adx = np.full(n, 20.0, dtype=np.float64)
    full_adx[1:] = np.nan_to_num(adx_smooth, nan=20.0)
    return full_adx


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


def run_single_simulation(
    symbol: str,
    asset_class: str,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    states: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    atr: np.ndarray,
    adx: np.ndarray,
    strategy: str,
    fundamental_bullish: bool = False,
    warmup: int = 50,
) -> Optional[dict]:
    n = len(closes)
    if n <= warmup + 10:
        return None

    bnh_return = ((closes[-1] - closes[warmup]) / closes[warmup]) * 100.0

    in_position = False
    position_size = 1.0  # 1.0 = 100%, 0.5 = 50%
    entry_price = 0.0
    trades_pnl: List[float] = []

    equity = 10000.0
    equity_curve = [equity]

    for i in range(warmup, n):
        curr_open = opens[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_state = states[i - 1]
        prev_close = closes[i - 1]
        curr_adx = adx[i - 1]

        # 1. Manage open positions
        if in_position:
            exited = False
            exit_price = 0.0

            if strategy == "v1_fast_exit":
                # Exit as soon as GOLD ends (enters Silver/Neutral or Blue)
                if prev_state != 1:
                    exit_price = curr_open
                    exited = True

            elif strategy in ["v2_classic_blue_exit", "v2_filtered_chop", "v2_optimal_smma"]:
                # Classic Larsson: HOLD through Neutral, EXIT on hard BLUE flip or close below v2 by 1 ATR
                v2_val = v2[i - 1]
                v2_sl = v2_val - (1.0 * atr[i - 1]) if not np.isnan(v2_val) else entry_price * 0.85
                if prev_state == -1 or curr_low <= v2_sl:
                    exit_price = min(curr_open, v2_sl)
                    exited = True

            elif strategy == "v2_quantamental_accumulator":
                # If entered with 50% on dip, check if we can add second 50% on GOLD flip
                if position_size == 0.5 and prev_state == 1:
                    position_size = 1.0  # Scale to 100% position on confirmation

                # Exit when BLUE flip occurs or target reached
                if prev_state == -1:
                    exit_price = curr_open
                    exited = True

            if exited:
                # Deduct commission
                pnl = ((exit_price * (1.0 - COMMISSION_PCT)) - (entry_price * (1.0 + COMMISSION_PCT))) / entry_price
                net_pnl = pnl * position_size
                trades_pnl.append(net_pnl)
                equity *= (1.0 + net_pnl)
                in_position = False
                position_size = 1.0

        # 2. Check entries
        if not in_position and i < n - 1:
            should_enter = False
            size = 1.0

            if strategy in ["v1_fast_exit", "v2_classic_blue_exit", "v2_optimal_smma"]:
                # Gold Flip
                if prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            elif strategy == "v2_filtered_chop":
                # Gold Flip + ADX > 20 (avoid flat chop)
                if prev_state == 1 and states[i - 2] != 1 and curr_adx >= 20.0:
                    should_enter = True

            elif strategy == "v2_quantamental_accumulator":
                if fundamental_bullish:
                    # Tranched entry: If Blue dip with stabilization (close > v1), enter 50%
                    if prev_state == -1 and prev_close > v1[i - 1]:
                        should_enter = True
                        size = 0.5
                    elif prev_state == 1 and states[i - 2] != 1:
                        should_enter = True
                        size = 1.0

            if should_enter:
                in_position = True
                position_size = size
                entry_price = curr_open

        equity_curve.append(equity)

    if in_position:
        pnl = ((closes[-1] * (1.0 - COMMISSION_PCT)) - (entry_price * (1.0 + COMMISSION_PCT))) / entry_price
        net_pnl = pnl * position_size
        trades_pnl.append(net_pnl)
        equity *= (1.0 + net_pnl)

    total_trades = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    total_return = ((equity - 10000.0) / 10000.0) * 100.0

    years = max(1.0, (n - warmup) / 252.0)
    cagr = (((equity / 10000.0) ** (1.0 / years)) - 1.0) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    if gross_loss > 0:
        raw_pf = gross_profit / gross_loss
        profit_factor = min(20.0, raw_pf)
    else:
        profit_factor = 20.0 if gross_profit > 0 else 1.0

    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

    daily_returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)

    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "strategy": strategy,
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "profit_factor": round(profit_factor, 2),
        "buy_and_hold_return_pct": round(bnh_return, 2),
    }


def process_v2_asset(args):
    symbol, asset_class, df, fundamental_bullish = args
    if df is None or len(df) < 70:
        return []

    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)

    hl2 = (highs + lows) / 2.0
    atr = fast_compute_atr(highs, lows, closes, 14)
    adx = fast_compute_adx(highs, lows, closes, 14)

    # 1. Standard Larsson (15, 19, 25, 29)
    v1_std = fast_compute_smma(hl2, 15)
    m1_std = fast_compute_smma(hl2, 19)
    m2_std = fast_compute_smma(hl2, 25)
    v2_std = fast_compute_smma(hl2, 29)
    states_std = evaluate_larsson_states(v1_std, m1_std, m2_std, v2_std)

    # 2. Faster ribbon (11, 14, 19, 22) for crypto/volatile stocks, or slower for indices
    scale = 0.75 if asset_class in ["crypto", "crypto_stocks"] else (1.25 if asset_class == "indices" else 1.0)
    v1_opt = fast_compute_smma(hl2, int(round(15 * scale)))
    m1_opt = fast_compute_smma(hl2, int(round(19 * scale)))
    m2_opt = fast_compute_smma(hl2, int(round(25 * scale)))
    v2_opt = fast_compute_smma(hl2, int(round(29 * scale)))
    states_opt = evaluate_larsson_states(v1_opt, m1_opt, m2_opt, v2_opt)

    results = []

    # Strategy 1: v1_fast_exit (baseline)
    r1 = run_single_simulation(symbol, asset_class, opens, highs, lows, closes, states_std, v1_std, v2_std, atr, adx, "v1_fast_exit", fundamental_bullish)
    if r1: results.append(r1)

    # Strategy 2: v2_classic_blue_exit (Hold Neutral, Exit on Blue)
    r2 = run_single_simulation(symbol, asset_class, opens, highs, lows, closes, states_std, v1_std, v2_std, atr, adx, "v2_classic_blue_exit", fundamental_bullish)
    if r2: results.append(r2)

    # Strategy 3: v2_filtered_chop (Classic + ADX > 20)
    r3 = run_single_simulation(symbol, asset_class, opens, highs, lows, closes, states_std, v1_std, v2_std, atr, adx, "v2_filtered_chop", fundamental_bullish)
    if r3: results.append(r3)

    # Strategy 4: v2_optimal_smma (Scaled SMMA periods)
    r4 = run_single_simulation(symbol, asset_class, opens, highs, lows, closes, states_opt, v1_opt, v2_opt, atr, adx, "v2_optimal_smma", fundamental_bullish)
    if r4: results.append(r4)

    # Strategy 5: v2_quantamental_accumulator
    r5 = run_single_simulation(symbol, asset_class, opens, highs, lows, closes, states_std, v1_std, v2_std, atr, adx, "v2_quantamental_accumulator", fundamental_bullish)
    if r5: results.append(r5)

    return results


def fetch_worker(item):
    cat, sym, dm = item
    try:
        if "USDT" in sym:
            df = dm.fetch_binance_history(sym, start_date="2021-09-01", timeframe="1D")
        else:
            df = dm.fetch_yfinance_history(sym, start_date="2021-09-01", timeframe="1D")
        prof = get_fundamental_profile(sym)
        fund_bullish = prof.is_bullish if prof else (True if sym in ["BTCUSDT", "ETHUSDT", "NVDA", "MSFT", "AAPL", "PLTR", "LLY", "TSM"] else False)
        return (sym, cat, df, fund_bullish)
    except Exception as e:
        logger.warning(f"Failed to fetch {sym}: {e}")
        return None


def main():
    logger.info("Initializing Backtest v2.0 Optimizer across full universe...")
    with open(os.path.join(BASE_DIR, "config", "assets.yaml"), "r") as f:
        cfg = yaml.safe_load(f)

    dm = BacktestDataManager()
    fetch_tasks = []
    seen = set()

    for cat, items in cfg.items():
        for item in items:
            ticker = item["ticker"] if isinstance(item, dict) else str(item)
            if ticker not in seen:
                seen.add(ticker)
                fetch_tasks.append((cat, ticker, dm))

    logger.info(f"Identified {len(fetch_tasks)} unique assets across all categories. Loading datasets...")

    t0 = time.time()
    tasks_args = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as fetch_pool:
        results = fetch_pool.map(fetch_worker, fetch_tasks)
        for r in results:
            if r is not None and r[2] is not None and len(r[2]) >= 70:
                tasks_args.append(r)

    fetch_time = time.time() - t0
    logger.info(f"Loaded {len(tasks_args)} valid asset datasets in {fetch_time:.2f}s. Executing 16-thread multi-strategy comparison...")

    t0 = time.time()
    all_results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(16, os.cpu_count() or 8)) as executor:
        for res_list in executor.map(process_v2_asset, tasks_args):
            all_results.extend(res_list)

    elapsed = time.time() - t0
    logger.info(f"Completed Backtest v2.0 in {elapsed:.2f} seconds!")

    df = pd.DataFrame(all_results)
    out_csv = os.path.join(BASE_DIR, "backtest_v2_comparison_results.csv")
    df.to_csv(out_csv, index=False)
    logger.info(f"Saved Backtest v2.0 results to {out_csv}")

    # Terminal Report
    print("\n" + "=" * 115)
    print(f"BACKTEST V2.0 MULTI-STRATEGY COMPARISON ({len(tasks_args)} ASSETS, 1D)")
    print("=" * 115)

    summary = df.groupby("strategy").agg({
        "total_return_pct": ["mean", "median"],
        "cagr_pct": ["mean", "median"],
        "max_drawdown_pct": ["mean", "median"],
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
        "win_rate": "mean",
        "total_trades": "mean",
    }).round(2)
    print("\n--- Strategy Performance Comparison (Mean & Median) ---")
    print(summary.to_string())

    # Comparison on Fundamentally Bullish Subset
    print("\n--- Performance on the Fundamentally Bullish Subset (Active Fundamentals) ---")
    fund_syms = df[(df["strategy"] == "v2_quantamental_accumulator") & (df["total_trades"] > 0)]["symbol"].unique()
    sub = df[df["symbol"].isin(fund_syms)]
    fund_summary = sub.groupby("strategy").agg({
        "total_return_pct": ["mean", "median"],
        "max_drawdown_pct": ["mean", "median"],
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
        "win_rate": "mean",
    }).round(2)
    print(fund_summary.to_string())

    print("\n--- Direct Comparison: Classic Blue Exit vs Fast Exit on Top Assets ---")
    top_tickers = ["BTCUSDT", "NVDA", "PLTR", "MSFT", "AMZN", "ASTS", "SOLUSDT", "TSM"]
    comp_df = df[df["symbol"].isin(top_tickers) & df["strategy"].isin(["v1_fast_exit", "v2_classic_blue_exit", "v2_filtered_chop"])]
    print(comp_df.pivot(index="symbol", columns="strategy", values=["total_return_pct", "max_drawdown_pct"]).round(1).to_string())
    print("=" * 115)


if __name__ == "__main__":
    main()
