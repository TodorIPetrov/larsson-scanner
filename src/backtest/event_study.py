"""
Event Study and Base Rates Validation Engine.
Calculates historical statistical distributions of forward returns, hit rates,
profit factors, and MFE/MAE excursions following Larsson Line state transitions.
Validates true systemic edge vs random walk noise across asset classes and timeframes.
"""

from dataclasses import asdict, dataclass
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import math
import numpy as np
import pandas as pd

from src.backtest.data_manager import BacktestDataManager, DEFAULT_UNIVERSE
from src.engine.smma import compute_larsson_series, LarssonState

logger = logging.getLogger(__name__)

BASE_RATES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "base_rates.json",
)


@dataclass
class TransitionEvent:
    symbol: str
    asset_class: str
    timeframe: str
    date: str
    bar_index: int
    prev_state: str
    new_state: str
    transition_type: str
    entry_price: float
    forward_returns: Dict[int, float]  # horizon -> net return (fraction)
    forward_mfe: Dict[int, float]      # horizon -> max favorable excursion
    forward_mae: Dict[int, float]      # horizon -> max adverse excursion
    live_rule_returns: Optional[Dict[int, float]] = None  # trailing SMMA-29 stop + time stop
    excess_returns: Optional[Dict[int, float]] = None     # net return minus benchmark return
    r_multiples: Optional[Dict[int, float]] = None        # Phase 2: net R return from multi-exit policy
    exit_details: Optional[Dict[int, Dict[str, Any]]] = None


@dataclass
class BaseRateMetrics:
    transition_type: str
    asset_class: str
    timeframe: str
    horizon: int
    sample_size: int
    win_rate: float
    mean_return: float
    median_return: float
    std_dev: float
    profit_factor: float
    expectancy: float
    avg_mfe: float
    avg_mae: float
    edge_ratio: float  # avg_mfe / abs(avg_mae)
    t_stat: float
    p_value: float
    statistically_significant: bool
    live_win_rate: Optional[float] = None
    live_mean_return: Optional[float] = None
    trimmed_mean_return: Optional[float] = None
    excess_mean_return: Optional[float] = None
    fdr_p_value: Optional[float] = None
    fdr_significant: Optional[bool] = None
    mean_r: Optional[float] = None
    median_r: Optional[float] = None
    ci_lower_r: Optional[float] = None
    ci_upper_r: Optional[float] = None
    effective_n: Optional[int] = None
    validation_status: Optional[str] = "PAPER"


def benjamini_hochberg_correction(p_values: List[float]) -> List[float]:
    """
    Computes FDR-adjusted p-values using the Benjamini-Hochberg procedure
    to prevent false discovery inflation across multiple hypothesis tests.
    """
    n = len(p_values)
    if n == 0:
        return []
    indexed_p = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [1.0] * n
    running_min = 1.0
    for rank in range(n, 0, -1):
        idx, p = indexed_p[rank - 1]
        adj_p = min(1.0, (n / rank) * p)
        running_min = min(running_min, adj_p)
        adjusted[idx] = running_min
    return adjusted


def simulate_multi_exit_policy(
    entry_price: float,
    initial_sl: float,
    tp1: float,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    trailing_stops: np.ndarray,
    start_idx: int,
    horizon: int = 60,
    asset_class: str = "crypto",
    direction: str = "LONG",
) -> Dict[str, Any]:
    """
    Realistic Multi-Exit Simulation Policy (Opus Phase 2 Specification):
    - Tranche 1 (50% weight): Limit TP1 fill.
    - Tranche 2 (50% weight): Trailing SMMA-29 stop on bar close, executing at NEXT OPEN.
    - Hard disaster initial stop: Active on all bars; gap fills at min(Open, SL).
    - Ambiguous bars (High >= TP1 and Low <= SL): SL hit FIRST (pessimistic institutional standard).
    - Tranche 1 fallback: If TP1 never reached before trail/stop exit, exit1 = exit2.
    - Time stop: at horizon bars (e.g. 60), open tranches exit at Close.
    - Asymmetric friction: 10 bps base fee, 5 bps TP limit slip, 15 bps market stop slip.
    - Funding/borrow cost: 1.0 bp/bar for crypto, 0.5 bp/bar for equities.
    - All returns and friction denominated in R units: R = (Exit - Entry) / Stop_Dist.
    """
    assert direction.upper() == "LONG", "Long-only sign convention enforced for Phase 2 simulation."

    stop_dist = entry_price - initial_sl
    if stop_dist <= 1e-6 or entry_price <= 0:
        return {
            "net_r": 0.0,
            "raw_r": 0.0,
            "friction_r": 0.0,
            "exit1_price": entry_price,
            "exit2_price": entry_price,
            "exit1_reason": "INVALID_STOP",
            "exit2_reason": "INVALID_STOP",
            "bars_held": 0,
        }

    r_stop = stop_dist / entry_price
    n_bars = len(closes)
    end_idx = min(start_idx + horizon, n_bars - 1)

    exit1_price: Optional[float] = None
    exit1_bar: Optional[int] = None
    exit1_reason: str = ""

    exit2_price: Optional[float] = None
    exit2_bar: Optional[int] = None
    exit2_reason: str = ""

    pending_trail_exit = False

    for k in range(start_idx + 1, end_idx + 1):
        # 1. Next-open execution for trailing stop triggered on previous bar close
        if pending_trail_exit:
            fill_p = opens[k]
            if exit2_price is None:
                exit2_price = fill_p
                exit2_bar = k
                exit2_reason = "TRAIL_NEXT_OPEN"
            if exit1_price is None:
                # Tranche 1 fallback when TP1 was never reached before trail exit
                exit1_price = fill_p
                exit1_bar = k
                exit1_reason = "TRAIL_FALLBACK_NEXT_OPEN"
            break

        o_k = opens[k]
        h_k = highs[k]
        l_k = lows[k]
        c_k = closes[k]
        trail_k = trailing_stops[k]

        # 2. Disaster Stop: Gap down through initial SL on open
        if o_k <= initial_sl:
            fill_p = min(o_k, initial_sl)
            if exit1_price is None:
                exit1_price = fill_p
                exit1_bar = k
                exit1_reason = "GAP_DISASTER_STOP"
            if exit2_price is None:
                exit2_price = fill_p
                exit2_bar = k
                exit2_reason = "GAP_DISASTER_STOP"
            break

        # 3. Ambiguous Bar: Both TP1 and initial SL breached in same bar -> SL fires first
        touches_tp1 = (exit1_price is None) and (h_k >= tp1)
        touches_sl = l_k <= initial_sl
        if touches_tp1 and touches_sl:
            fill_p = min(o_k, initial_sl)
            exit1_price = fill_p
            exit1_bar = k
            exit1_reason = "AMBIGUOUS_BAR_SL_FIRST"
            exit2_price = fill_p
            exit2_bar = k
            exit2_reason = "AMBIGUOUS_BAR_SL_FIRST"
            break

        # 4. Hard initial SL intrabar touch
        if touches_sl:
            fill_p = min(o_k, initial_sl)
            if exit1_price is None:
                exit1_price = fill_p
                exit1_bar = k
                exit1_reason = "HARD_DISASTER_STOP"
            if exit2_price is None:
                exit2_price = fill_p
                exit2_bar = k
                exit2_reason = "HARD_DISASTER_STOP"
            break

        # 5. Take Profit 1 limit hit (Tranche 1 exits)
        if exit1_price is None and h_k >= tp1:
            exit1_price = tp1
            exit1_bar = k
            exit1_reason = "TP1_LIMIT"

        # 6. Trailing stop evaluation on bar close (Close < SMMA-29)
        if c_k < trail_k:
            if k < end_idx:
                pending_trail_exit = True
            else:
                # Last bar of horizon: no next open available, fills on Close_k
                fill_p = c_k
                if exit2_price is None:
                    exit2_price = fill_p
                    exit2_bar = k
                    exit2_reason = "TRAIL_LAST_BAR_CLOSE"
                if exit1_price is None:
                    exit1_price = fill_p
                    exit1_bar = k
                    exit1_reason = "TRAIL_FALLBACK_LAST_BAR_CLOSE"
                break

    # 7. Horizon / Time Stop expiration if still open
    if exit1_price is None or exit2_price is None:
        last_k = end_idx
        fill_p = closes[last_k]
        if exit1_price is None:
            exit1_price = fill_p
            exit1_bar = last_k
            exit1_reason = "TIME_STOP_HORIZON"
        if exit2_price is None:
            exit2_price = fill_p
            exit2_bar = last_k
            exit2_reason = "TIME_STOP_HORIZON"

    # Friction calculation in R-units
    bars_held = max(exit1_bar or start_idx, exit2_bar or start_idx) - start_idx
    fee_base = 0.0010  # 10 bps round-trip

    # Asymmetric slippage: limit TP fill has 5 bps, stop market exit has 15 bps
    slip1 = 0.0005 if exit1_reason == "TP1_LIMIT" else 0.0015
    slip2 = 0.0010 if "TIME_STOP" in exit2_reason else 0.0015
    weighted_slip = 0.5 * slip1 + 0.5 * slip2

    # Funding / borrow cost per bar
    funding_rate = 0.0001 if asset_class.lower() == "crypto" else 0.00005
    funding_cost = funding_rate * max(1, bars_held)

    total_friction_pct = fee_base + weighted_slip + funding_cost
    friction_r = total_friction_pct / r_stop

    # R-Multiple calculation
    r1 = (exit1_price - entry_price) / stop_dist
    r2 = (exit2_price - entry_price) / stop_dist
    raw_r = 0.5 * r1 + 0.5 * r2
    net_r = raw_r - friction_r

    return {
        "net_r": round(float(net_r), 4),
        "raw_r": round(float(raw_r), 4),
        "friction_r": round(float(friction_r), 4),
        "r1": round(float(r1), 4),
        "r2": round(float(r2), 4),
        "exit1_price": round(float(exit1_price), 4),
        "exit2_price": round(float(exit2_price), 4),
        "exit1_reason": exit1_reason,
        "exit2_reason": exit2_reason,
        "bars_held": bars_held,
    }


def calendar_block_bootstrap(
    dates: List[str],
    r_multiples: List[float],
    block_days: int = 60,
    n_resamples: int = 2000,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Calendar-Time Block Bootstrap across events (Opus Phase 2 Specification):
    - Blocks events by calendar time (L = 60 days) to account for cross-asset correlation.
    - Resamples calendar blocks with replacement B = 2,000 times.
    - Yields 95% Confidence Interval for mean R and counts effective N blocks.
    """
    if not r_multiples or len(r_multiples) != len(dates):
        return {
            "mean_r": 0.0,
            "median_r": 0.0,
            "ci_lower_r": 0.0,
            "ci_upper_r": 0.0,
            "effective_n": 0,
        }

    # Convert dates to day ordinals relative to min date
    try:
        s_dt = pd.Series(pd.to_datetime(dates))
        min_dt = s_dt.min()
        day_diffs = (s_dt - min_dt).dt.days.to_numpy()
    except Exception:
        day_diffs = np.arange(len(dates))

    block_ids = day_diffs // block_days

    # Group R-multiples by block_id
    block_map: Dict[int, List[float]] = {}
    for bid, r in zip(block_ids, r_multiples):
        block_map.setdefault(int(bid), []).append(float(r))

    effective_n = len(block_map)
    mean_r = float(np.mean(r_multiples))
    median_r = float(np.median(r_multiples))

    if effective_n < 2:
        return {
            "mean_r": round(mean_r, 4),
            "median_r": round(median_r, 4),
            "ci_lower_r": round(mean_r - 0.5, 4),
            "ci_upper_r": round(mean_r + 0.5, 4),
            "effective_n": effective_n,
        }

    # Vectorized block bootstrap
    block_sums = np.array([sum(vals) for vals in block_map.values()], dtype=np.float64)
    block_counts = np.array([len(vals) for vals in block_map.values()], dtype=np.float64)

    rng = np.random.default_rng(seed)
    sampled_indices = rng.choice(effective_n, size=(n_resamples, effective_n), replace=True)

    sampled_sums = np.sum(block_sums[sampled_indices], axis=1)
    sampled_counts = np.sum(block_counts[sampled_indices], axis=1)

    valid_mask = sampled_counts > 0
    resampled_means = np.where(valid_mask, sampled_sums / np.maximum(sampled_counts, 1e-8), mean_r)

    ci_lower = float(np.percentile(resampled_means, 2.5))
    ci_upper = float(np.percentile(resampled_means, 97.5))

    return {
        "mean_r": round(mean_r, 4),
        "median_r": round(median_r, 4),
        "ci_lower_r": round(ci_lower, 4),
        "ci_upper_r": round(ci_upper, 4),
        "effective_n": effective_n,
    }


class EventStudyEngine:
    def __init__(
        self,
        horizons: Optional[List[int]] = None,
        cost_bps: float = 10.0,  # 10 bps total fee + slippage (0.10%)
        min_warmup: int = 60,
    ):
        self.horizons = horizons or [5, 10, 20, 60]
        self.cost = cost_bps / 10000.0
        self.min_warmup = min_warmup
        self.data_manager = BacktestDataManager()

    def detect_events_for_asset(
        self,
        symbol: str,
        df: pd.DataFrame,
        asset_class: str = "crypto",
        timeframe: str = "1D",
        benchmark_df: Optional[pd.DataFrame] = None,
    ) -> List[TransitionEvent]:
        """
        Scans OHLCV series, computes ribbon states, and identifies all state transitions.
        Simulates both fixed-hold forward returns and realistic live-rule execution
        (trailing SMMA-29 stop + time stop) as well as benchmark-excess return (Alpha).
        """
        if len(df) <= self.min_warmup + max(self.horizons):
            return []

        opens = df["open"].to_numpy(dtype=np.float64) if "open" in df.columns else df["close"].to_numpy(dtype=np.float64)
        highs = df["high"].to_numpy(dtype=np.float64)
        lows = df["low"].to_numpy(dtype=np.float64)
        closes = df["close"].to_numpy(dtype=np.float64)
        dates = df["date"].tolist()
        n_bars = len(df)

        v1, m1, m2, v2, states_enum = compute_larsson_series(highs, lows)
        states = [s.value for s in states_enum]

        # Benchmark price lookup map by date
        bench_prices = {}
        if benchmark_df is not None and "date" in benchmark_df.columns and "close" in benchmark_df.columns:
            bench_prices = {str(d): float(c) for d, c in zip(benchmark_df["date"], benchmark_df["close"])}

        events: List[TransitionEvent] = []

        for i in range(self.min_warmup, n_bars - 1):
            prev_s = states[i - 1]
            curr_s = states[i]

            if prev_s == curr_s:
                continue

            # Found a state transition
            transition_type = f"{prev_s}_TO_{curr_s}"
            entry_price = closes[i]

            forward_returns: Dict[int, float] = {}
            forward_mfe: Dict[int, float] = {}
            forward_mae: Dict[int, float] = {}
            live_rule_returns: Dict[int, float] = {}
            excess_returns: Dict[int, float] = {}
            r_multiples: Dict[int, float] = {}
            exit_details: Dict[int, Dict[str, Any]] = {}

            for h in self.horizons:
                if i + h < n_bars:
                    future_close = closes[i + h]
                    future_highs = highs[i + 1 : i + h + 1]
                    future_lows = lows[i + 1 : i + h + 1]

                    # Standard directional forward return
                    if curr_s == "GOLD":
                        raw_ret = (future_close - entry_price) / entry_price
                        mfe = (np.max(future_highs) - entry_price) / entry_price
                        mae = (np.min(future_lows) - entry_price) / entry_price

                        # Live Rule: Trailing stop at v2 line (SMMA-29) + 60-bar time stop
                        live_exit_price = future_close
                        exit_idx = i + h
                        for k_bar in range(i + 1, i + h + 1):
                            stop_val = v2[k_bar]
                            if lows[k_bar] <= stop_val:
                                live_exit_price = min(opens[k_bar], stop_val)
                                exit_idx = k_bar
                                break
                        live_ret = ((live_exit_price - entry_price) / entry_price) - self.cost

                        # Phase 2: Institutional Non-Binary Multi-Exit Simulation in R units
                        initial_sl = v2[i]
                        if (entry_price - initial_sl) < 0.02 * entry_price:
                            initial_sl = entry_price * 0.98
                        tp1 = entry_price + 1.8 * (entry_price - initial_sl)
                        sim_res = simulate_multi_exit_policy(
                            entry_price=entry_price,
                            initial_sl=initial_sl,
                            tp1=tp1,
                            opens=opens,
                            highs=highs,
                            lows=lows,
                            closes=closes,
                            trailing_stops=v2,
                            start_idx=i,
                            horizon=h,
                            asset_class=asset_class,
                            direction="LONG",
                        )
                        r_multiples[h] = sim_res["net_r"]
                        exit_details[h] = sim_res

                    elif curr_s == "BLUE":
                        raw_ret = (entry_price - future_close) / entry_price
                        mfe = (entry_price - np.min(future_lows)) / entry_price
                        mae = (entry_price - np.max(future_highs)) / entry_price

                        # Live Rule for Short: Trailing stop above v2 line + time stop
                        live_exit_price = future_close
                        exit_idx = i + h
                        for k_bar in range(i + 1, i + h + 1):
                            stop_val = v2[k_bar]
                            if highs[k_bar] >= stop_val:
                                live_exit_price = max(opens[k_bar], stop_val)
                                exit_idx = k_bar
                                break
                        live_ret = ((entry_price - live_exit_price) / entry_price) - self.cost

                    else:  # NEUTRAL
                        raw_ret = (future_close - entry_price) / entry_price
                        mfe = (np.max(future_highs) - entry_price) / entry_price
                        mae = (np.min(future_lows) - entry_price) / entry_price
                        live_ret = raw_ret - self.cost
                        exit_idx = i + h

                    net_ret = raw_ret - self.cost
                    forward_returns[h] = float(net_ret)
                    forward_mfe[h] = float(mfe)
                    forward_mae[h] = float(mae)
                    live_rule_returns[h] = float(live_ret)

                    # Benchmark excess return (Alpha over SPY / BTC)
                    if bench_prices:
                        d_entry = str(dates[i])
                        d_exit = str(dates[exit_idx])
                        if d_entry in bench_prices and d_exit in bench_prices:
                            b_start = bench_prices[d_entry]
                            b_end = bench_prices[d_exit]
                            b_ret = (b_end - b_start) / b_start if b_start > 0 else 0.0
                            excess = live_ret - b_ret
                        else:
                            excess = live_ret
                    else:
                        excess = live_ret
                    excess_returns[h] = float(excess)

            events.append(
                TransitionEvent(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe=timeframe,
                    date=str(dates[i]),
                    bar_index=i,
                    prev_state=prev_s,
                    new_state=curr_s,
                    transition_type=transition_type,
                    entry_price=entry_price,
                    forward_returns=forward_returns,
                    forward_mfe=forward_mfe,
                    forward_mae=forward_mae,
                    live_rule_returns=live_rule_returns,
                    excess_returns=excess_returns,
                    r_multiples=r_multiples,
                    exit_details=exit_details,
                )
            )

        return events

    def calculate_base_rates(
        self,
        events: List[TransitionEvent],
        group_by_asset_class: bool = True,
    ) -> List[BaseRateMetrics]:
        """
        Aggregates forward returns across events into rigorous base-rate statistics.
        """
        if not events:
            return []

        # Create groupings
        grouped_events: Dict[Tuple, List[TransitionEvent]] = {}
        for ev in events:
            ac_key = ev.asset_class if group_by_asset_class else "ALL"
            key = (ev.transition_type, ac_key, ev.timeframe)
            if key not in grouped_events:
                grouped_events[key] = []
            grouped_events[key].append(ev)

        summaries: List[BaseRateMetrics] = []

        for (ttype, aclass, tf), ev_list in grouped_events.items():
            for h in self.horizons:
                rets = [e.forward_returns[h] for e in ev_list if h in e.forward_returns]
                mfes = [e.forward_mfe[h] for e in ev_list if h in e.forward_mfe]
                maes = [e.forward_mae[h] for e in ev_list if h in e.forward_mae]

                if not rets:
                    continue

                rets_arr = np.array(rets)
                mfes_arr = np.array(mfes)
                maes_arr = np.array(maes)
                n = len(rets_arr)

                wins = rets_arr[rets_arr > 0]
                losses = rets_arr[rets_arr < 0]

                win_rate = float(len(wins) / n) if n > 0 else 0.0
                mean_ret = float(np.mean(rets_arr))
                median_ret = float(np.median(rets_arr))
                std_dev = float(np.std(rets_arr, ddof=1)) if n > 1 else 0.0

                sum_wins = float(np.sum(wins)) if len(wins) > 0 else 0.0
                sum_losses = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
                profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

                avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
                avg_loss = float(np.abs(np.mean(losses))) if len(losses) > 0 else 0.0
                expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss)

                avg_mfe = float(np.mean(mfes_arr))
                avg_mae = float(np.mean(maes_arr))
                edge_ratio = (avg_mfe / abs(avg_mae)) if abs(avg_mae) > 1e-6 else 1.0

                # Statistical hypothesis test (Is mean return > 0?)
                if n > 2 and std_dev > 1e-8:
                    standard_error = std_dev / math.sqrt(n)
                    t_stat = float(mean_ret / standard_error)
                    p_val = float(math.erfc(abs(t_stat) / math.sqrt(2.0)))
                    stat_sig = bool(p_val < 0.05 and t_stat > 0)
                else:
                    t_stat = 0.0
                    p_val = 1.0
                    stat_sig = False

                # Calculate Live Execution (SMMA-29 Trailing Stop) and Excess Return metrics
                live_rets = [e.live_rule_returns[h] for e in ev_list if e.live_rule_returns and h in e.live_rule_returns]
                excess_rets = [e.excess_returns[h] for e in ev_list if e.excess_returns and h in e.excess_returns]

                if live_rets:
                    live_arr = np.array(live_rets)
                    live_wins = live_arr[live_arr > 0]
                    live_win_rate = float(len(live_wins) / len(live_arr))
                    live_mean = float(np.mean(live_arr))

                    # 5% Trimmed Mean (removes outlier tails)
                    sorted_live = np.sort(live_arr)
                    k_trim = max(1, int(len(sorted_live) * 0.05)) if len(sorted_live) >= 20 else 0
                    trimmed_arr = sorted_live[k_trim : len(sorted_live) - k_trim] if k_trim > 0 else sorted_live
                    trimmed_mean = float(np.mean(trimmed_arr))
                else:
                    live_win_rate = win_rate
                    live_mean = mean_ret
                    trimmed_mean = mean_ret

                excess_mean = float(np.mean(excess_rets)) if excess_rets else mean_ret

                # Phase 2: Calendar-Time Block Bootstrap (L = 60 days) across all events
                r_vals = [e.r_multiples[h] for e in ev_list if e.r_multiples and h in e.r_multiples]
                dates_list = [e.date for e in ev_list if e.r_multiples and h in e.r_multiples]
                if r_vals:
                    boot = calendar_block_bootstrap(dates_list, r_vals, block_days=60, n_resamples=2000)
                    mean_r = boot["mean_r"]
                    median_r = boot["median_r"]
                    ci_lower_r = boot["ci_lower_r"]
                    ci_upper_r = boot["ci_upper_r"]
                    eff_n = boot["effective_n"]
                else:
                    mean_r = None
                    median_r = None
                    ci_lower_r = None
                    ci_upper_r = None
                    eff_n = None

                summaries.append(
                    BaseRateMetrics(
                        transition_type=ttype,
                        asset_class=aclass,
                        timeframe=tf,
                        horizon=h,
                        sample_size=n,
                        win_rate=win_rate,
                        mean_return=mean_ret,
                        median_return=median_ret,
                        std_dev=std_dev,
                        profit_factor=profit_factor,
                        expectancy=expectancy,
                        avg_mfe=avg_mfe,
                        avg_mae=avg_mae,
                        edge_ratio=edge_ratio,
                        t_stat=t_stat,
                        p_value=p_val,
                        statistically_significant=stat_sig,
                        live_win_rate=live_win_rate,
                        live_mean_return=live_mean,
                        trimmed_mean_return=trimmed_mean,
                        excess_mean_return=excess_mean,
                        mean_r=mean_r,
                        median_r=median_r,
                        ci_lower_r=ci_lower_r,
                        ci_upper_r=ci_upper_r,
                        effective_n=eff_n,
                        validation_status="PAPER",
                    )
                )

        # Multiple testing correction using Benjamini-Hochberg (FDR) and Opus Dual Gate
        if summaries:
            raw_p_values = [s.p_value for s in summaries]
            fdr_p_values = benjamini_hochberg_correction(raw_p_values)
            for s, fdr_p in zip(summaries, fdr_p_values):
                s.fdr_p_value = round(float(fdr_p), 4)
                s.fdr_significant = bool(fdr_p < 0.10 and s.t_stat > 0)
                # Opus Dual Gate for Validation:
                # 1. E[R] >= +0.25R
                # 2. CI_lower > 0.0R (95% bootstrap lower bound positive)
                # 3. Effective N >= 30 independent calendar blocks
                # 4. Multiple testing FDR q < 0.10
                if s.mean_r is not None and s.ci_lower_r is not None and s.effective_n is not None:
                    is_validated = bool(
                        s.mean_r >= 0.25
                        and s.ci_lower_r > 0.0
                        and s.effective_n >= 30
                        and s.fdr_significant
                    )
                    s.validation_status = "VALIDATED" if is_validated else "PAPER"
                else:
                    s.validation_status = "PAPER"

        return summaries

    def run_universe_study(
        self,
        universe: Optional[Dict[str, List[str]]] = None,
        timeframe: str = "1D",
        start_date: str = "2021-09-01",
        force_refresh: bool = False,
    ) -> Tuple[List[TransitionEvent], List[BaseRateMetrics]]:
        """
        Loads all assets, processes events, and produces comprehensive base rate tables.
        """
        target_universe = universe or DEFAULT_UNIVERSE
        logger.info(f"Loading data for Event Study [{timeframe}] across {len(target_universe)} sectors...")

        datasets = self.data_manager.load_universe(
            universe=target_universe,
            start_date=start_date,
            timeframe=timeframe,
            force_refresh=force_refresh,
        )

        # Invert universe to get asset_class lookup
        sym_to_class: Dict[str, str] = {}
        for aclass, symbols in target_universe.items():
            for s in symbols:
                sym_to_class[s] = aclass

        # Identify benchmark datasets for excess return (Alpha)
        spy_df = datasets.get("SPY")
        btc_df = datasets.get("BTCUSDT")

        all_events: List[TransitionEvent] = []
        for sym, df in datasets.items():
            aclass = sym_to_class.get(sym, "unknown")
            bench_df = btc_df if aclass == "crypto" else spy_df
            evs = self.detect_events_for_asset(
                symbol=sym,
                df=df,
                asset_class=aclass,
                timeframe=timeframe,
                benchmark_df=bench_df,
            )
            all_events.extend(evs)

        # Calculate metrics segmented by asset class and global
        metrics_by_class = self.calculate_base_rates(all_events, group_by_asset_class=True)
        metrics_global = self.calculate_base_rates(all_events, group_by_asset_class=False)

        total_metrics = metrics_by_class + metrics_global
        return all_events, total_metrics

    def export_base_rates_json(
        self,
        metrics: List[BaseRateMetrics],
        filepath: str = BASE_RATES_FILE,
    ) -> str:
        """
        Saves calculated base rates as a structured JSON lookup table.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = [asdict(m) for m in metrics]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Exported base rates database ({len(data)} rows) to: {filepath}")
        return filepath

    def format_terminal_report(self, metrics: List[BaseRateMetrics]) -> str:
        """
        Renders clear ASCII table of the results including live stop, excess alpha, R expectancy, and Opus validation.
        """
        lines = []
        lines.append("\n" + "=" * 135)
        lines.append("  [QUANT AUDIT] LARSSON SCANNER: REALISTIC MULTI-EXIT BASE RATES, BLOCK-BOOTSTRAP & OPUS GATES")
        lines.append("=" * 135)
        lines.append(
            f"{'Transition':<16} | {'Asset Class':<10} | {'TF':<3} | {'H':<3} | {'N':<4} | {'N_eff':<5} | {'E[R]':<7} | {'95% CI [R]':<16} | {'Status':<10} | {'Live WinRate':<12} | {'Excess Alpha':<12} | {'FDR (q<0.10)':<12}"
        )
        lines.append("-" * 135)

        # Focus on key actionable transitions: NEUTRAL_TO_GOLD, BLUE_TO_GOLD, GOLD_TO_BLUE, NEUTRAL_TO_BLUE
        key_transitions = ["NEUTRAL_TO_GOLD", "BLUE_TO_GOLD", "NEUTRAL_TO_BLUE", "GOLD_TO_BLUE"]
        filtered = [m for m in metrics if m.transition_type in key_transitions]

        # Sort by asset_class, transition_type, horizon
        filtered.sort(key=lambda x: (x.asset_class, x.transition_type, x.horizon))

        for m in filtered:
            fdr_marker = "YES (q<0.10)" if m.fdr_significant else "NO"
            live_win = f"{m.live_win_rate * 100:.1f}%" if m.live_win_rate is not None else f"{m.win_rate * 100:.1f}%"
            excess_str = f"{m.excess_mean_return * 100:+.2f}%" if m.excess_mean_return is not None else "N/A"
            r_str = f"{m.mean_r:+.2f}R" if m.mean_r is not None else "N/A"
            ci_str = f"[{m.ci_lower_r:+.2f}, {m.ci_upper_r:+.2f}]" if m.ci_lower_r is not None and m.ci_upper_r is not None else "N/A"
            eff_n_str = str(m.effective_n) if m.effective_n is not None else "N/A"
            status_str = m.validation_status or "PAPER"
            lines.append(
                f"{m.transition_type:<16} | {m.asset_class:<10} | {m.timeframe:<3} | {m.horizon:<3} | {m.sample_size:<4} | {eff_n_str:<5} | {r_str:<7} | {ci_str:<16} | {status_str:<10} | {live_win:<12} | {excess_str:<12} | {fdr_marker:<12}"
            )

        lines.append("=" * 135)
        return "\n".join(lines)


def run_event_study(timeframe: str = "1D", force_refresh: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    engine = EventStudyEngine()
    events, metrics = engine.run_universe_study(timeframe=timeframe, force_refresh=force_refresh)
    output_table = engine.format_terminal_report(metrics)
    print(output_table)
    engine.export_base_rates_json(metrics)
    return events, metrics


def lookup_base_rate(
    transition_type: str,
    asset_class: str = "ALL",
    timeframe: str = "1D",
    horizon: int = 60,
    filepath: str = BASE_RATES_FILE,
) -> Optional[Dict[str, Any]]:
    """
    Looks up precomputed base rates for a specific transition and asset class.
    Falls back to ALL asset classes if specific class not found.
    """
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            records = json.load(f)

        # 1. Exact match
        for r in records:
            if (
                r.get("transition_type") == transition_type
                and r.get("asset_class") == asset_class
                and r.get("timeframe") == timeframe
                and r.get("horizon") == horizon
            ):
                return r

        # 2. Fallback to asset_class='ALL'
        for r in records:
            if (
                r.get("transition_type") == transition_type
                and r.get("asset_class") == "ALL"
                and r.get("timeframe") == timeframe
                and r.get("horizon") == horizon
            ):
                return r

    except Exception as e:
        logger.error(f"Error reading base rates from {filepath}: {e}")

    return None


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_event_study(timeframe="1D")
