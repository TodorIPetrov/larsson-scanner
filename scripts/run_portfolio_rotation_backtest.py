"""
Top 15 Momentum Portfolio Rotation Simulator ($100,000 Capital).
Dynamically rebalances into the Top 15 S-Tier / A-Tier assets currently in GOLD state,
holding according to each asset's empirical optimal exit strategy from data/asset_optimal_profiles.json.
Deducts 0.10% commission on every entry and exit.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from scripts.run_master_universe_optimization import fast_compute_smma, evaluate_larsson_states

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PortfolioRotation")

COMMISSION_PCT = 0.001


def run_portfolio_simulation():
    logger.info("Initializing Top 15 Portfolio Rotation Backtest ($100,000 Capital)...")
    dm = BacktestDataManager()

    profiles_file = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
    with open(profiles_file, "r", encoding="utf-8") as f:
        optimal_profiles = json.load(f)

    # Focus on S-Tier and A-Tier candidates
    valid_tickers = [
        sym for sym, p in optimal_profiles.items()
        if p.get("empirical_tier") in ["S", "A"] and p.get("walk_forward_stable", True)
    ]
    logger.info(f"Identified {len(valid_tickers)} candidate assets in S-Tier and A-Tier.")

    # Load price datasets and precompute states
    datasets = {}
    for sym in valid_tickers:
        clean_sym = sym.replace("=", "_").replace("^", "_").replace(":", "_")
        cache_file = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                if len(df) >= 200:
                    hl2 = (df["high"].to_numpy() + df["low"].to_numpy()) / 2.0
                    v1 = fast_compute_smma(hl2, 15)
                    m1 = fast_compute_smma(hl2, 19)
                    m2 = fast_compute_smma(hl2, 25)
                    v2 = fast_compute_smma(hl2, 29)
                    states = evaluate_larsson_states(v1, m1, m2, v2)
                    df["state"] = states
                    df["v2"] = v2
                    datasets[sym] = df
            except Exception:
                pass

    logger.info(f"Preloaded {len(datasets)} verified datasets into memory. Extracting calendar...")
    calendar = dm.extract_unified_calendar(datasets)
    logger.info(f"Unified trading days: {len(calendar)}")

    # Index lookups
    date_to_idx = {sym: {str(d): i for i, d in enumerate(df["date"])} for sym, df in datasets.items()}

    # Portfolio state
    initial_capital = 100000.0
    cash = initial_capital
    max_positions = 15
    slot_allocation = initial_capital / max_positions

    # Open positions: sym -> {shares, entry_price, entry_date}
    open_positions: Dict[str, dict] = {}
    equity_curve = []
    trades = []

    last_known_close: Dict[str, float] = {}

    for day_idx, date in enumerate(calendar):
        if day_idx < 60:
            continue

        # Update latest known closing prices for all assets that traded today
        for sym, df in datasets.items():
            idx = date_to_idx[sym].get(date)
            if idx is not None:
                last_known_close[sym] = df["close"].iloc[idx]

        # 1. Manage exits
        closed_today = []
        for sym, pos in list(open_positions.items()):
            df = datasets[sym]
            idx = date_to_idx[sym].get(date)
            if idx is not None and idx > 0:
                prev_state = df["state"].iloc[idx - 1]
                curr_open = df["open"].iloc[idx]
                exit_on_neutral = optimal_profiles[sym].get("exit_on_neutral", False)

                should_exit = False
                if exit_on_neutral and prev_state != 1:
                    should_exit = True
                elif not exit_on_neutral and prev_state == -1:
                    should_exit = True

                # Strict Stop-Loss Invariant: Exit immediately if price breached below v2 line
                prev_close = df["close"].iloc[idx - 1]
                prev_v2 = df["v2"].iloc[idx - 1]
                if prev_close <= prev_v2 and prev_v2 > 0:
                    should_exit = True

                if should_exit:
                    proceeds = pos["shares"] * curr_open * (1.0 - COMMISSION_PCT)
                    trade_pnl = (proceeds - pos["cost"]) / pos["cost"]
                    cash += proceeds
                    trades.append({"symbol": sym, "pnl": trade_pnl, "return_pct": trade_pnl * 100.0})
                    closed_today.append(sym)

        for sym in closed_today:
            del open_positions[sym]

        # 2. Score potential new entrants currently in GOLD state
        available_slots = max_positions - len(open_positions)
        if available_slots > 0:
            candidates = []
            for sym, df in datasets.items():
                if sym not in open_positions:
                    idx = date_to_idx[sym].get(date)
                    if idx is not None and idx >= 60:
                        prev_state = df["state"].iloc[idx - 1]
                        prev_close = df["close"].iloc[idx - 1]
                        prev_v2 = df["v2"].iloc[idx - 1]
                        # Only enter if in GOLD and price strictly above stop loss v2
                        if prev_state == 1 and (prev_v2 <= 0 or prev_close > prev_v2):
                            # 60-day momentum score
                            p_curr = prev_close
                            p_past = df["close"].iloc[idx - 60]
                            mom = (p_curr - p_past) / p_past if p_past > 0 else 0.0
                            sharpe = optimal_profiles[sym].get("sharpe_ratio", 0.0)
                            score = (sharpe * 50.0) + mom
                            candidates.append((sym, score, df["open"].iloc[idx]))

            # Sort by highest momentum & Sharpe score
            candidates.sort(key=lambda c: c[1], reverse=True)

            # Reallocate freed cash into available slots based on true mark-to-market valuation
            current_portfolio_val = cash + sum(
                pos["shares"] * last_known_close.get(s, pos["entry_price"])
                for s, pos in open_positions.items()
            )
            target_slot_val = current_portfolio_val / max_positions

            for sym, score, open_px in candidates[:available_slots]:
                invest_usd = min(cash, target_slot_val)
                if invest_usd >= 1000.0 and open_px > 0:
                    shares = (invest_usd * (1.0 - COMMISSION_PCT)) / open_px
                    cost = shares * open_px * (1.0 + COMMISSION_PCT)
                    cash -= cost
                    open_positions[sym] = {
                        "shares": shares,
                        "entry_price": open_px,
                        "cost": cost,
                        "entry_date": date,
                    }

        # 3. Mark to market daily equity with forward-fill for closed weekend markets
        pos_val = sum(
            pos["shares"] * last_known_close.get(sym, pos["entry_price"])
            for sym, pos in open_positions.items()
        )

        daily_equity = cash + pos_val
        equity_curve.append({"date": date, "equity": daily_equity})

    # Portfolio metrics
    final_eq = equity_curve[-1]["equity"]
    total_ret = ((final_eq - initial_capital) / initial_capital) * 100.0
    years = len(equity_curve) / 252.0
    cagr = (((final_eq / initial_capital) ** (1.0 / years)) - 1.0) * 100.0

    eq_arr = np.array([e["equity"] for e in equity_curve])
    peaks = np.maximum.accumulate(eq_arr)
    dds = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(dds)) * 100.0

    daily_rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252)) if len(daily_rets) > 1 and np.std(daily_rets) > 0 else 0.0
    sortino = (np.mean(daily_rets) / np.std(daily_rets[daily_rets < 0]) * np.sqrt(252)) if len(daily_rets[daily_rets < 0]) > 0 else 0.0

    win_trades = [t for t in trades if t["pnl"] > 0]
    win_rate = (len(win_trades) / len(trades) * 100.0) if trades else 0.0

    print("\n" + "=" * 110)
    print(f"TOP 15 MOMENTUM PORTFOLIO ROTATION BACKTEST (5 YEARS | CAPITAL: ${initial_capital:,.2f})")
    print("=" * 110)
    print(f"Final Portfolio Equity:     ${final_eq:,.2f}")
    print(f"Total Portfolio Return:     +{total_ret:,.2f}%")
    print(f"Portfolio CAGR:             +{cagr:.2f}% per year")
    print(f"Portfolio Sharpe Ratio:      {sharpe:.2f}")
    print(f"Portfolio Sortino Ratio:     {sortino:.2f}")
    print(f"Portfolio Max Drawdown:     -{max_dd:.2f}%")
    print(f"Total Completed Trades:      {len(trades)}")
    print(f"Trade Win Rate:              {win_rate:.2f}%")
    print(f"Current Open Positions:      {len(open_positions)} (actively diversified in Top 15)")
    print("=" * 110)


if __name__ == "__main__":
    run_portfolio_simulation()
