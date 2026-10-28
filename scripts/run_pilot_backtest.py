"""
High-Performance Pilot Backtester and Parameter Optimizer.
Tests BTC, Mag7, and 12 diverse assets across 4 strategy variants on 1D timeframe.
Utilizes multi-processing across Ryzen AI 7 350 logical cores.
"""

import concurrent.futures
from dataclasses import dataclass
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add repo root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from src.engine.quantamental import get_fundamental_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PilotBacktest")

PILOT_UNIVERSE = {
    "crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "mag7": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    "diverse": ["SPY", "QQQ", "GC=F", "CL=F", "JPM", "LLY", "WMT", "KO", "XOM", "PLTR"],
}


def fast_compute_smma(src: np.ndarray, length: int) -> np.ndarray:
    """Vectorized / optimized SMMA."""
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
    """Returns integer array: 1 = GOLD, -1 = BLUE, 0 = NEUTRAL."""
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


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    total_trades: int
    win_rate: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    buy_and_hold_return_pct: float


def run_strategy_simulation(
    symbol: str,
    dates: List[str],
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
    atr_mult_sl: float = 1.5,
    rr_tp: float = 2.0,
    warmup: int = 40,
) -> BacktestResult:
    n = len(closes)
    bnh_return = ((closes[-1] - closes[warmup]) / closes[warmup]) * 100.0 if n > warmup else 0.0

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

        # 1. Manage open position
        if in_position:
            exited = False
            exit_price = 0.0

            if strategy in ["pure_larsson", "quantamental_timing"]:
                # Exit when state ceases to be GOLD
                if prev_state != 1:
                    exit_price = curr_open
                    exited = True
            elif strategy == "pure_value_dip":
                # Exit when gain reaches 20% or trailing stop
                if curr_high >= take_profit:
                    exit_price = take_profit
                    exited = True
                elif curr_low <= stop_loss:
                    exit_price = stop_loss
                    exited = True
            elif strategy == "larsson_sr_atr":
                # ATR stop-loss and R:R TP
                if curr_low <= stop_loss:
                    exit_price = stop_loss
                    exited = True
                elif curr_high >= take_profit:
                    exit_price = take_profit
                    exited = True
                elif prev_state == -1:  # Emergency exit on hard BLUE flip
                    exit_price = curr_open
                    exited = True

            if exited:
                pnl = (exit_price - entry_price) / entry_price
                trades_pnl.append(pnl)
                equity *= (1.0 + pnl)
                in_position = False

        # 2. Check entries if not in position
        if not in_position and i < n - 1:
            should_enter = False
            curr_sl = 0.0
            curr_tp = 0.0

            if strategy == "pure_larsson":
                if prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            elif strategy == "larsson_sr_atr":
                # Pullback entry in GOLD state
                if prev_state == 1 and curr_close <= v1[i - 1]:
                    should_enter = True
                    curr_sl = curr_close - (atr_mult_sl * curr_atr)
                    curr_tp = curr_close + (rr_tp * (curr_close - curr_sl))

            elif strategy == "pure_value_dip":
                # Buy on dips if fundamentally bullish
                if fundamental_bullish and prev_state == -1:
                    should_enter = True
                    curr_sl = curr_close * 0.85  # 15% stop
                    curr_tp = curr_close * 1.25  # 25% target

            elif strategy == "quantamental_timing":
                # Only enter when fundamental is bullish AND state turns GOLD
                if fundamental_bullish and prev_state == 1 and states[i - 2] != 1:
                    should_enter = True

            if should_enter:
                in_position = True
                entry_price = curr_open  # Fill on bar open
                stop_loss = curr_sl
                take_profit = curr_tp

        equity_curve.append(equity)

    # Close any lingering trade at end
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

    # Max Drawdown
    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

    # Approximate Sharpe
    daily_returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)

    return BacktestResult(
        symbol=symbol,
        strategy=strategy,
        total_trades=total_trades,
        win_rate=round(win_rate, 2),
        total_return_pct=round(total_return, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        profit_factor=round(profit_factor, 2),
        buy_and_hold_return_pct=round(bnh_return, 2),
    )


def test_single_asset(args) -> List[BacktestResult]:
    symbol, df, fundamental_bullish = args
    if len(df) < 60:
        return []

    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)
    dates = df["date"].astype(str).tolist()

    hl2 = (highs + lows) / 2.0
    v1 = fast_compute_smma(hl2, 15)
    m1 = fast_compute_smma(hl2, 19)
    m2 = fast_compute_smma(hl2, 25)
    v2 = fast_compute_smma(hl2, 29)
    states = evaluate_larsson_states(v1, m1, m2, v2)
    atr = fast_compute_atr(highs, lows, closes, 14)

    results = []
    strategies = ["pure_larsson", "larsson_sr_atr", "pure_value_dip", "quantamental_timing"]
    for strat in strategies:
        res = run_strategy_simulation(
            symbol=symbol,
            dates=dates,
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
        results.append(res)
    return results


def run_pilot():
    logger.info("Initializing Pilot Backtest across 20 Assets...")
    dm = BacktestDataManager()

    # Flatten universe
    symbols = []
    for cat, sym_list in PILOT_UNIVERSE.items():
        symbols.extend(sym_list)

    datasets = {}
    tasks_args = []
    for sym in symbols:
        try:
            if "USDT" in sym:
                df = dm.fetch_binance_history(sym, start_date="2021-09-01", timeframe="1D")
            else:
                df = dm.fetch_yfinance_history(sym, start_date="2021-09-01", timeframe="1D")

            if df is not None and not df.empty:
                # Check fundamental profile
                prof = get_fundamental_profile(sym)
                fund_bullish = prof.is_bullish if prof else (True if sym in ["BTCUSDT", "NVDA", "MSFT", "AAPL"] else False)
                tasks_args.append((sym, df, fund_bullish))
                datasets[sym] = df
        except Exception as e:
            logger.error(f"Error fetching {sym}: {e}")

    logger.info(f"Loaded datasets for {len(tasks_args)} assets. Launching multi-threaded backtest...")

    t0 = time.time()
    all_results: List[BacktestResult] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(16, os.cpu_count() or 8)) as executor:
        for res_list in executor.map(test_single_asset, tasks_args):
            all_results.extend(res_list)

    elapsed = time.time() - t0
    logger.info(f"Completed simulation in {elapsed:.2f} seconds!")

    # Format results into DataFrame
    data_dicts = [r.__dict__ for r in all_results]
    res_df = pd.DataFrame(data_dicts)

    out_csv = os.path.join(BASE_DIR, "pilot_backtest_results.csv")
    res_df.to_csv(out_csv, index=False)
    logger.info(f"Saved results to {out_csv}")

    # Generate Terminal Summary
    print("\n" + "=" * 105)
    print(f"PILOT BACKTEST SUMMARY: 20 ASSETS | TIMEFRAME: 1D | TIME: {elapsed:.2f}s")
    print("=" * 105)

    summary = res_df.groupby("strategy").agg({
        "total_return_pct": "mean",
        "cagr_pct": "mean",
        "win_rate": "mean",
        "max_drawdown_pct": "mean",
        "sharpe_ratio": "mean",
        "profit_factor": "mean",
    }).round(2)
    print("\n--- Strategy Averages across Universe ---")
    print(summary.to_string())

    print("\n--- Top 10 Best Asset/Strategy Performers by Sharpe ---")
    top10 = res_df.sort_values(by="sharpe_ratio", ascending=False).head(10)
    print(top10[["symbol", "strategy", "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate"]].to_string(index=False))

    print("\n--- Performance on BTCUSDT ---")
    btc_df = res_df[res_df["symbol"] == "BTCUSDT"]
    print(btc_df[["strategy", "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate"]].to_string(index=False))

    print("\n--- Performance on NVDA ---")
    nvda_df = res_df[res_df["symbol"] == "NVDA"]
    print(nvda_df[["strategy", "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_ratio", "win_rate"]].to_string(index=False))
    print("=" * 105)


if __name__ == "__main__":
    run_pilot()
