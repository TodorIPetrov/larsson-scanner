"""
Recomputes data/base_rates.json across all 797 cached assets.
Extracts empirical forward returns, win rates, hit rates, and profit factors
for all state transitions (GOLD_TO_NEUTRAL, NEUTRAL_TO_GOLD, NEUTRAL_TO_BLUE, etc.).
"""

import glob
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from scripts.run_master_universe_optimization import fast_compute_smma, evaluate_larsson_states

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BaseRatesRecompute")


def recompute_all_base_rates():
    logger.info("Initializing Master Base Rates Recomputation across all 797 cached assets...")
    dm = BacktestDataManager()

    profiles_file = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
    with open(profiles_file, "r", encoding="utf-8") as f:
        optimal_profiles = json.load(f)

    cache_files = glob.glob(os.path.join(dm.cache_dir, "*_1D.csv"))
    logger.info(f"Found {len(cache_files)} cached asset datasets.")

    # Horizon windows to evaluate
    horizons = [5, 10, 20, 60]

    # transition_type -> asset_class -> horizon -> list of net returns
    transition_data = {}

    state_names = {1: "GOLD", 0: "NEUTRAL", -1: "BLUE"}

    t0 = time.time()
    total_events = 0

    for f_path in cache_files:
        try:
            df = pd.read_csv(f_path)
            if len(df) < 150:
                continue

            ticker = os.path.basename(f_path).replace("_1D.csv", "").replace("_F", "=F")
            prof = optimal_profiles.get(ticker, {})
            asset_class = prof.get("asset_class", "us_stocks")

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

            n = len(closes)
            for i in range(50, n - 60):
                prev_st = states[i - 1]
                curr_st = states[i]

                if curr_st != prev_st:
                    p_name = state_names[prev_st]
                    c_name = state_names[curr_st]
                    trans_type = f"{p_name}_TO_{c_name}"

                    entry_px = opens[i + 1] if i + 1 < n else closes[i]
                    if entry_px <= 0:
                        continue

                    total_events += 1

                    for h in horizons:
                        exit_idx = min(i + 1 + h, n - 1)
                        exit_px = closes[exit_idx]
                        ret = (exit_px - entry_px) / entry_px

                        key = (trans_type, asset_class, h)
                        if key not in transition_data:
                            transition_data[key] = []
                        transition_data[key].append(ret)
        except Exception:
            pass

    elapsed = time.time() - t0
    logger.info(f"Processed {total_events} transition events across universe in {elapsed:.2f}s!")

    # Format base rates list
    base_rates_list = []
    for (trans_type, asset_class, h), rets in transition_data.items():
        arr = np.array(rets)
        sample_size = len(arr)
        if sample_size < 10:
            continue

        wins = arr[arr > 0]
        losses = arr[arr <= 0]
        win_rate = len(wins) / sample_size
        mean_ret = float(np.mean(arr))
        med_ret = float(np.median(arr))
        std_dev = float(np.std(arr)) if len(arr) > 1 else 0.0

        gross_win = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 1e-6
        pf = min(20.0, gross_win / gross_loss) if gross_loss > 0 else 20.0

        t_stat = (mean_ret / (std_dev / np.sqrt(sample_size))) if std_dev > 0 else 0.0
        is_sig = bool(abs(t_stat) >= 2.0 and sample_size >= 30)

        base_rates_list.append({
            "transition_type": trans_type,
            "asset_class": asset_class,
            "timeframe": "1D",
            "horizon": h,
            "sample_size": sample_size,
            "win_rate": round(win_rate, 4),
            "mean_return": round(mean_ret, 4),
            "median_return": round(med_ret, 4),
            "std_dev": round(std_dev, 4),
            "profit_factor": round(pf, 2),
            "expectancy": round(mean_ret, 4),
            "t_stat": round(t_stat, 2),
            "statistically_significant": is_sig,
        })

    out_file = os.path.join(BASE_DIR, "data", "base_rates.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(base_rates_list, f, indent=2)
    logger.info(f"Exported {len(base_rates_list)} robust empirical base rates to {out_file}!")

    # Summary preview
    df_br = pd.DataFrame(base_rates_list)
    print("\n" + "=" * 110)
    print("EMPIRICAL BASE RATES SUMMARY (SAMPLE OF HORIZON = 60 DAYS)")
    print("=" * 110)
    h60 = df_br[df_br["horizon"] == 60].sort_values("sample_size", ascending=False)
    print(h60[["transition_type", "asset_class", "sample_size", "win_rate", "mean_return", "profit_factor", "statistically_significant"]].head(15).to_string(index=False))
    print("=" * 110)


if __name__ == "__main__":
    recompute_all_base_rates()
