"""
Full-Universe Institutional Backtester and Optimizer across all assets in config/assets.yaml.
Uses concurrent.futures across all 16 CPU threads, caches all data locally in Parquet/CSV,
and generates rankings and breakdowns.
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
logger = logging.getLogger("FullUniverseBacktest")


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


def run_strategy_simulation(
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
    strategy: str,
    fundamental_bullish: bool = False,
    warmup: int = 40,
) -> Optional[dict]:
    n = len(closes)
    if n <= warmup + 10:
        return None

    bnh_return = ((closes[-1] - closes[warmup]) / closes[warmup]) * 100.0

    in_position = False
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    trades_pnl: List[float] = []

    equity = 10000.0
    equity_curve = [equity]

    for i in range(warmup, n):
        curr_open = opens[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_state = states[i - 1]
        curr_atr = atr[i - 1] if not np.isnan(atr[i - 1]) else curr_close * 0.02

        # 1. Manage position
        if in_position:
            exited = False
            exit_price = 0.0

            if strategy in ["pure_larsson", "quantamental_timing"]:
                if prev_state != 1:  # Exit when GOLD ends
                    exit_price = curr_open
                    exited = True
            elif strategy == "pure_value_dip":
                if curr_high >= take_profit:
                    exit_price = take_profit
                    exited = True
                elif curr_low <= stop_loss:
                    exit_price = stop_loss
                    exited = True
            elif strategy == "larsson_trailing_v2":
                # Trailing stop by v2 ribbon
                curr_sl = v2[i - 1] if not np.isnan(v2[i - 1]) else entry_price * 0.90
                if curr_low <= curr_sl or prev_state == -1:
                    exit_price = min(curr_open, curr_sl)
                    exited = True

            if exited:
                pnl = (exit_price - entry_price) / entry_price
                trades_pnl.append(pnl)
                equity *= (1.0 + pnl)
                in_position = False

        # 2. Check entries
        if not in_position and i < n - 1:
            should_enter = False
            curr_sl = 0.0
            curr_tp = 0.0

            if strategy == "pure_larsson":
                if prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            elif strategy == "larsson_trailing_v2":
                # Pullback or Gold flip with trailing stop
                if prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            elif strategy == "pure_value_dip":
                if fundamental_bullish and prev_state == -1:
                    should_enter = True
                    curr_sl = curr_close * 0.85
                    curr_tp = curr_close * 1.25

            elif strategy == "quantamental_timing":
                if fundamental_bullish and prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            if should_enter:
                in_position = True
                entry_price = curr_open
                stop_loss = curr_sl
                take_profit = curr_tp

        equity_curve.append(equity)

    if in_position:
        pnl = (closes[-1] - entry_price) / entry_price
        trades_pnl.append(pnl)
        equity *= (1.0 + pnl)

    total_trades = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    total_return = ((equity - 10000.0) / 10000.0) * 100.0

    years = max(1.0, (n - warmup) / 252.0)
    cagr = (((equity / 10000.0) ** (1.0 / years)) - 1.0) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1e-6
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

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


def process_asset(args):
    symbol, asset_class, df, fundamental_bullish = args
    if df is None or len(df) < 60:
        return []

    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)

    hl2 = (highs + lows) / 2.0
    v1 = fast_compute_smma(hl2, 15)
    m1 = fast_compute_smma(hl2, 19)
    m2 = fast_compute_smma(hl2, 25)
    v2 = fast_compute_smma(hl2, 29)
    states = evaluate_larsson_states(v1, m1, m2, v2)
    atr = fast_compute_atr(highs, lows, closes, 14)

    results = []
    for strat in ["pure_larsson", "larsson_trailing_v2", "pure_value_dip", "quantamental_timing"]:
        res = run_strategy_simulation(
            symbol=symbol,
            asset_class=asset_class,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            states=states,
            v1=v1,
            v2=v2,
            atr=atr,
            strategy=strat,
            fundamental_bullish=fundamental_bullish,
        )
        if res:
            results.append(res)
    return results


def fetch_worker(item):
    cat, sym, dm = item
    try:
        if "USDT" in sym:
            df = dm.fetch_binance_history(sym, start_date="2021-09-01", timeframe="1D")
        else:
            df = dm.fetch_yfinance_history(sym, start_date="2021-09-01", timeframe="1D")
        prof = get_fundamental_profile(sym)
        fund_bullish = prof.is_bullish if prof else (True if sym in ["BTCUSDT", "ETHUSDT", "NVDA", "MSFT", "AAPL", "PLTR", "LLY"] else False)
        return (sym, cat, df, fund_bullish)
    except Exception as e:
        logger.warning(f"Failed to fetch {sym}: {e}")
        return None


def main():
    logger.info("Loading asset configuration from config/assets.yaml...")
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

    logger.info(f"Identified {len(fetch_tasks)} unique assets across all categories. Fetching data...")

    # Fetch in parallel with 16 workers
    t0 = time.time()
    valid_tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as fetch_pool:
        results = fetch_pool.map(fetch_worker, fetch_tasks)
        for r in results:
            if r is not None and r[2] is not None and len(r[2]) >= 60:
                valid_tasks.append(r)

    fetch_time = time.time() - t0
    logger.info(f"Fetched and cached {len(valid_tasks)} assets in {fetch_time:.2f}s. Running backtest simulation...")

    t1 = time.time()
    all_results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(16, os.cpu_count() or 8)) as proc_pool:
        for res_list in proc_pool.map(process_asset, valid_tasks):
            all_results.extend(res_list)

    sim_time = time.time() - t1
    logger.info(f"Simulation completed across {len(all_results)} strategy runs in {sim_time:.2f}s!")

    df_out = pd.DataFrame(all_results)
    out_csv = os.path.join(BASE_DIR, "full_universe_backtest_results.csv")
    df_out.to_csv(out_csv, index=False)
    logger.info(f"Exported complete results to {out_csv}")

    # Aggregated Summary by Strategy
    print("\n" + "=" * 115)
    print(f"FULL UNIVERSE BACKTEST SUMMARY: {len(valid_tasks)} ASSETS | 1D TIMEFRAME")
    print("=" * 115)
    summary = df_out.groupby("strategy").agg({
        "total_return_pct": "mean",
        "cagr_pct": "mean",
        "win_rate": "mean",
        "max_drawdown_pct": "mean",
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
    }).round(2)
    print("\n--- Strategy Averages across ALL Assets ---")
    print(summary.to_string())

    print("\n--- Top 20 Most Profitable Assets with Pure Larsson (by Sharpe Ratio) ---")
    pl_df = df_out[df_out["strategy"] == "pure_larsson"].sort_values("sharpe_ratio", ascending=False).head(20)
    print(pl_df[["symbol", "asset_class", "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate", "profit_factor"]].to_string(index=False))

    print("\n--- Top 10 Best Assets with Quantamental Timing (Strong Fundamentals + Larsson GOLD) ---")
    qt_df = df_out[df_out["strategy"] == "quantamental_timing"].sort_values("sharpe_ratio", ascending=False).head(10)
    print(qt_df[["symbol", "asset_class", "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate", "profit_factor"]].to_string(index=False))

    print("\n--- Breakdown of Pure Larsson Performance by Asset Class ---")
    cat_summary = df_out[df_out["strategy"] == "pure_larsson"].groupby("asset_class").agg({
        "total_return_pct": "mean",
        "cagr_pct": "mean",
        "max_drawdown_pct": "mean",
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
    }).round(2)
    print(cat_summary.to_string())
    print("=" * 115)


if __name__ == "__main__":
    main()
