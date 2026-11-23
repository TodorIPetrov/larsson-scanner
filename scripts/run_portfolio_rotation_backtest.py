"""
Clean Zero-Look-Ahead Walk-Forward Top-15 Momentum Portfolio Rotation Simulator ($100,000 Capital).

Design invariants:
1. ZERO hindsight bias: Never reads future Sharpe, empirical_tier, or full-sample profiles.
2. Strictly causal signals & ranking: all indicators (SMMA 15/19/25/29, 60d momentum, 126d volatility,
   252d trailing Sharpe) are evaluated at t-1 close and executed at t open with 0.10% fee per fill.
3. Crypto uses FAST_SILVER (exit on non-GOLD); equities/commodities/indices use CLASSIC_BLUE (exit on BLUE).
4. Daily Mark-to-Market equity curve with forward-fill for closed weekend markets.
"""

import json
import logging
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.run_master_universe_optimization import (
    evaluate_larsson_states,
    fast_compute_smma,
    validate_ohlcv_quality,
)
from src.backtest.data_manager import BacktestDataManager
from src.engine.asset_profiles import (
    classify_risk_cluster,
    compute_normalized_invvol_weights,
    load_rotation_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WalkForwardRotation")

COMMISSION_PCT = 0.001


def _load_universe_categories() -> Dict[str, str]:
    ticker_cat: Dict[str, str] = {}
    assets_path = os.path.join(BASE_DIR, "config", "assets.yaml")
    if os.path.exists(assets_path):
        with open(assets_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for cat, items in cfg.items():
            for it in items or []:
                t = it["ticker"] if isinstance(it, dict) else str(it)
                if t not in ticker_cat:
                    ticker_cat[t] = cat

    sp500_path = os.path.join(BASE_DIR, "config", "sp500_tickers.json")
    if os.path.exists(sp500_path):
        with open(sp500_path, "r", encoding="utf-8") as f:
            for t in json.load(f):
                tu = t.strip().upper()
                if tu not in ticker_cat:
                    ticker_cat[tu] = "us_stocks"

    return ticker_cat


def prepare_causal_asset_frame(df: pd.DataFrame, symbol: str, asset_class: str) -> Optional[dict]:
    """Precomputes strictly backward-looking series for a single validated OHLCV dataframe."""
    is_valid, _ = validate_ohlcv_quality(df)
    if not is_valid:
        return None

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"].astype(str).str[:10], errors="coerce")
    for col in ("open", "high", "low", "close"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)

    recent = work[work["date"] >= "2021-06-01"].reset_index(drop=True)
    if len(recent) >= 150:
        work = recent

    if len(work) < 120:
        return None

    ann_days = 365.0 if (asset_class == "crypto" or "USDT" in symbol) else 252.0
    opens = work["open"].to_numpy(dtype=np.float64)
    highs = work["high"].to_numpy(dtype=np.float64)
    lows = work["low"].to_numpy(dtype=np.float64)
    closes = work["close"].to_numpy(dtype=np.float64)

    hl2 = (highs + lows) / 2.0
    v1 = fast_compute_smma(hl2, 15)
    m1 = fast_compute_smma(hl2, 19)
    m2 = fast_compute_smma(hl2, 25)
    v2 = fast_compute_smma(hl2, 29)
    states = evaluate_larsson_states(v1, m1, m2, v2)

    mom60 = np.full(len(closes), np.nan, dtype=np.float64)
    valid_past = closes[:-60] > 0
    mom60_vals = np.full(len(closes) - 60, np.nan, dtype=np.float64)
    mom60_vals[valid_past] = (closes[60:][valid_past] / closes[:-60][valid_past]) - 1.0
    mom60[60:] = mom60_vals

    ret1 = np.zeros(len(closes), dtype=np.float64)
    prev_pos = closes[:-1] > 0
    ret1[1:][prev_pos] = (closes[1:][prev_pos] / closes[:-1][prev_pos]) - 1.0
    ret1_s = pd.Series(ret1)

    vol126 = (ret1_s.rolling(126, min_periods=60).std() * np.sqrt(ann_days) * 100.0).to_numpy(dtype=np.float64)
    roll_std252 = ret1_s.rolling(252, min_periods=126).std()
    roll_mean252 = ret1_s.rolling(252, min_periods=126).mean()
    sharpe252 = np.where(
        roll_std252 > 1e-12,
        (roll_mean252 / roll_std252) * np.sqrt(ann_days),
        np.nan,
    )

    dstrs = work["date"].dt.strftime("%Y-%m-%d").tolist()
    dmap = {d: i for i, d in enumerate(dstrs)}

    return {
        "symbol": symbol,
        "cat": asset_class,
        "opens": opens,
        "closes": closes,
        "states": states,
        "v2": v2,
        "mom60": mom60,
        "vol126": vol126,
        "sharpe252": sharpe252,
        "dates": dstrs,
        "dmap": dmap,
    }


def load_rotation_universe(start_trade_date: str = "2021-12-01") -> Tuple[Dict[str, dict], List[str]]:
    """Loads all validated assets from local cache and constructs unified calendar."""
    dm = BacktestDataManager()
    ticker_cat = _load_universe_categories()

    datasets: Dict[str, dict] = {}
    all_dates: Set[str] = set()

    for sym, cat in ticker_cat.items():
        clean_sym = sym.replace("=", "_").replace("^", "_").replace(":", "_")
        cache_file = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")
        if not os.path.exists(cache_file):
            continue
        try:
            df = pd.read_csv(cache_file)
            prepared = prepare_causal_asset_frame(df, sym, cat)
            if prepared is None:
                continue
            datasets[sym] = prepared
            for d in prepared["dates"]:
                if d >= start_trade_date:
                    all_dates.add(d)
        except Exception:
            continue

    calendar = sorted(all_dates)
    return datasets, calendar


def run_walk_forward_rotation(
    datasets: Dict[str, dict],
    calendar: List[str],
    allowed_cats: Optional[Set[str]] = None,
    allowed_tickers: Optional[Set[str]] = None,
    min_vol: float = 0.0,
    max_positions: int = 15,
    initial_capital: float = 100000.0,
    use_v2_stop: bool = False,
    max_per_class: Optional[int] = None,
    cash_rf_annual: float = 0.0,
    fast_crypto: bool = True,
    inverse_vol_sizing: bool = False,
    min_slot_weight_pct: float = 7.0,
    max_slot_weight_pct: float = 20.0,
    cluster_caps: Optional[Dict[str, int]] = None,
    gold_vol_exempt: Optional[Set[str]] = None,
) -> dict:
    """Runs a strictly causal daily walk-forward portfolio rotation simulation."""
    if not calendar or not datasets:
        return {
            "final_equity": initial_capital,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "open_positions": 0,
        }

    exempt_set = {"GC=F", "PAXGUSDT"} if gold_vol_exempt is None else {str(x).upper() for x in gold_vol_exempt}
    allowed_ticker_set = {str(x).upper() for x in allowed_tickers} if allowed_tickers is not None else None
    cluster_by_sym = {sym: classify_risk_cluster(sym, info["cat"]) for sym, info in datasets.items()}

    cal_days = max(1, (pd.Timestamp(calendar[-1]) - pd.Timestamp(calendar[0])).days)
    years = max(1.0 / 365.25, cal_days / 365.25)
    bars_per_year = max(1.0, len(calendar) / years)
    daily_rf = cash_rf_annual / bars_per_year if cash_rf_annual > 0 else 0.0

    cash = float(initial_capital)
    open_positions: Dict[str, dict] = {}
    last_known_close: Dict[str, float] = {}
    last_known_vol: Dict[str, float] = {}
    equity_curve: List[float] = []
    trades: List[float] = []

    for date in calendar:
        # Update latest known closing prices and causal t-1 volatilities
        for sym, info in datasets.items():
            idx = info["dmap"].get(date)
            if idx is not None:
                last_known_close[sym] = info["closes"][idx]
                if idx >= 1 and not np.isnan(info["vol126"][idx - 1]):
                    last_known_vol[sym] = float(info["vol126"][idx - 1])

        if daily_rf > 0 and cash > 0:
            cash *= (1.0 + daily_rf)

        # 1. Manage exits strictly from t-1 state at t open
        for sym in list(open_positions.keys()):
            info = datasets[sym]
            idx = info["dmap"].get(date)
            if idx is None or idx < 1:
                continue

            prev_state = info["states"][idx - 1]
            curr_open = info["opens"][idx]
            if curr_open <= 0:
                continue

            is_crypto = info["cat"] == "crypto"
            is_gold_proxy = sym.upper() in exempt_set
            should_exit = (prev_state != 1) if (fast_crypto and is_crypto and not is_gold_proxy) else (prev_state == -1)

            if use_v2_stop and not should_exit:
                prev_close = info["closes"][idx - 1]
                prev_v2 = info["v2"][idx - 1]
                if not np.isnan(prev_v2) and prev_v2 > 0 and prev_close <= prev_v2:
                    should_exit = True

            if should_exit:
                proceeds = open_positions[sym]["shares"] * curr_open * (1.0 - COMMISSION_PCT)
                cost = open_positions[sym]["cost"]
                trades.append((proceeds - cost) / cost if cost > 0 else 0.0)
                cash += proceeds
                del open_positions[sym]

        # 2. Rank & enter causal GOLD candidates into open slots
        avail = max_positions - len(open_positions)
        if avail > 0:
            class_counts = Counter(datasets[s]["cat"] for s in open_positions)
            cluster_counts = Counter(cluster_by_sym[s] for s in open_positions)
            candidates = []

            for sym, info in datasets.items():
                if sym in open_positions:
                    continue
                if allowed_ticker_set is not None and sym.upper() not in allowed_ticker_set:
                    continue
                if allowed_cats is not None and info["cat"] not in allowed_cats:
                    continue
                if max_per_class is not None and class_counts[info["cat"]] >= max_per_class:
                    continue
                cl = cluster_by_sym[sym]
                if cluster_caps is not None and cluster_counts[cl] >= int(cluster_caps.get(cl, 2)):
                    continue

                idx = info["dmap"].get(date)
                if idx is None or idx < 61:
                    continue

                prev_state = info["states"][idx - 1]
                prev_close = info["closes"][idx - 1]
                prev_v2 = info["v2"][idx - 1]
                curr_open = info["opens"][idx]
                if prev_state != 1 or curr_open <= 0:
                    continue
                if not np.isnan(prev_v2) and prev_v2 > 0 and prev_close <= prev_v2:
                    continue

                m60 = info["mom60"][idx - 1]
                v126 = info["vol126"][idx - 1]
                sh252 = info["sharpe252"][idx - 1]
                if np.isnan(m60) or np.isnan(v126):
                    continue
                if sym.upper() not in exempt_set and v126 < min_vol:
                    continue

                sh_term = 0.0 if np.isnan(sh252) else float(np.clip(sh252, -1.0, 3.0))
                score = (float(m60) / max(float(v126) / 100.0, 0.15)) + (0.5 * sh_term)
                candidates.append((sym, score, curr_open, float(v126)))

            candidates.sort(key=lambda c: c[1], reverse=True)
            pval = cash + sum(
                pos["shares"] * last_known_close.get(s, pos["entry_price"])
                for s, pos in open_positions.items()
            )

            chosen = []
            sim_cls_counts = Counter(class_counts)
            sim_cl_counts = Counter(cluster_counts)
            for sym, _, open_px, vol_val in candidates:
                if len(open_positions) + len(chosen) >= max_positions:
                    break
                cat = datasets[sym]["cat"]
                cl = cluster_by_sym[sym]
                if max_per_class is not None and sim_cls_counts[cat] >= max_per_class:
                    continue
                if cluster_caps is not None and sim_cl_counts[cl] >= int(cluster_caps.get(cl, 2)):
                    continue
                chosen.append((sym, open_px, vol_val))
                sim_cls_counts[cat] += 1
                sim_cl_counts[cl] += 1

            alloc_by_sym: Dict[str, float] = {}
            if chosen:
                if inverse_vol_sizing:
                    active_vols = {s: last_known_vol.get(s, 40.0) for s in open_positions}
                    for sym, _, vol_val in chosen:
                        active_vols[sym] = vol_val
                    weights = compute_normalized_invvol_weights(
                        active_vols,
                        target_slots=max_positions,
                        min_weight_pct=min_slot_weight_pct,
                        max_weight_pct=max_slot_weight_pct,
                    )
                    for sym, _, _ in chosen:
                        alloc_by_sym[sym] = pval * (weights[sym] / 100.0)
                else:
                    slot_val = pval / float(max_positions)
                    for sym, _, _ in chosen:
                        alloc_by_sym[sym] = slot_val

            for sym, open_px, _ in chosen:
                invest_usd = min(cash, alloc_by_sym.get(sym, 0.0))
                if invest_usd >= 1000.0 and open_px > 0:
                    shares = (invest_usd * (1.0 - COMMISSION_PCT)) / open_px
                    cost = shares * open_px * (1.0 + COMMISSION_PCT)
                    cash -= cost
                    open_positions[sym] = {
                        "shares": shares,
                        "entry_price": open_px,
                        "cost": cost,
                    }

        # 3. Daily Mark-to-Market
        pos_val = sum(
            pos["shares"] * last_known_close.get(sym, pos["entry_price"])
            for sym, pos in open_positions.items()
        )
        equity_curve.append(cash + pos_val)

    eq_arr = np.array(equity_curve, dtype=np.float64)
    final_eq = float(eq_arr[-1])
    total_ret = ((final_eq - initial_capital) / initial_capital) * 100.0
    cagr = (((max(final_eq, 1.0) / initial_capital) ** (1.0 / years)) - 1.0) * 100.0

    peaks = np.maximum.accumulate(eq_arr)
    dds = (peaks - eq_arr) / np.where(peaks > 0, peaks, 1.0)
    max_dd = float(np.max(dds)) * 100.0 if len(dds) > 0 else 0.0

    daily_rets = np.diff(eq_arr) / np.where(eq_arr[:-1] > 0, eq_arr[:-1], 1.0)
    std = float(np.std(daily_rets)) if len(daily_rets) > 1 else 0.0
    sharpe = (float(np.mean(daily_rets)) / std) * np.sqrt(bars_per_year) if std > 1e-12 else 0.0
    neg_rets = daily_rets[daily_rets < 0]
    neg_std = float(np.std(neg_rets)) if len(neg_rets) > 1 else 0.0
    sortino = (float(np.mean(daily_rets)) / neg_std) * np.sqrt(bars_per_year) if neg_std > 1e-12 else 0.0
    calmar = cagr / max_dd if max_dd > 0.1 else 0.0

    win_rate = (sum(1 for t in trades if t > 0) / len(trades) * 100.0) if trades else 0.0

    return {
        "final_equity": round(final_eq, 2),
        "total_return_pct": round(total_ret, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "open_positions": len(open_positions),
    }


def _compute_benchmark_spx(datasets: Dict[str, dict], calendar: List[str]) -> Optional[dict]:
    if "^GSPC" not in datasets or not calendar:
        return None
    spx = datasets["^GSPC"]
    valid_idxs = [spx["dmap"][d] for d in calendar if d in spx["dmap"]]
    if len(valid_idxs) < 20:
        return None
    closes = spx["closes"][valid_idxs]
    opens = spx["opens"][valid_idxs]
    entry = opens[0] * (1.0 + COMMISSION_PCT)
    eq = (100000.0 / entry) * closes
    final_eq = float(eq[-1]) * (1.0 - COMMISSION_PCT)
    cal_days = max(1, (pd.Timestamp(calendar[-1]) - pd.Timestamp(calendar[0])).days)
    years = max(0.25, cal_days / 365.25)
    tot = ((final_eq - 100000.0) / 100000.0) * 100.0
    cagr = (((max(final_eq, 1.0) / 100000.0) ** (1.0 / years)) - 1.0) * 100.0
    peaks = np.maximum.accumulate(eq)
    mdd = float(np.max((peaks - eq) / peaks)) * 100.0
    dr = np.diff(eq) / eq[:-1]
    sh = (float(np.mean(dr)) / float(np.std(dr))) * np.sqrt(252.0) if np.std(dr) > 1e-12 else 0.0
    cal = cagr / mdd if mdd > 0.1 else 0.0
    return {
        "final_equity": round(final_eq, 2),
        "total_return_pct": round(tot, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(mdd, 2),
        "sharpe_ratio": round(sh, 2),
        "calmar_ratio": round(cal, 2),
    }


def run_portfolio_simulation():
    logger.info("Initializing Clean Walk-Forward Rotation Backtest ($100,000 Capital, ZERO Look-Ahead)...")
    datasets, calendar = load_rotation_universe(start_trade_date="2021-12-01")
    logger.info(f"Preloaded {len(datasets)} validated assets | Trading calendar: {calendar[0]} -> {calendar[-1]} ({len(calendar)} days)")

    rot_cfg = load_rotation_settings()
    core_tickers = {str(t).upper() for t in (rot_cfg.get("core_focus_tickers") or [])}

    runs = [
        ("1. All Universe (Top-15 Equal, Vol >= 0%)", dict(allowed_cats=None, min_vol=0.0, max_positions=15)),
        ("2. High-Vol Trend Filter (Top-15, Vol >= 35%)", dict(allowed_cats=None, min_vol=35.0, max_positions=15)),
        ("3. Core Trend Sleeve (AI+Crypto+Comm, Top-15)", dict(allowed_cats={"ai_stocks", "crypto", "commodities"}, min_vol=25.0, max_positions=15)),
        ("4. Broad Low-Vol Baseline (US Stocks + Indices)", dict(allowed_cats={"us_stocks", "indices"}, min_vol=0.0, max_positions=15)),
        (
            "5. Core-20 Focus Top-8 (InvVol+Caps+4% Cash)",
            dict(
                allowed_tickers=core_tickers,
                min_vol=float(rot_cfg.get("min_annualized_vol_pct", 25.0)),
                max_positions=int(rot_cfg.get("target_positions_count", 8)),
                cash_rf_annual=0.04,
                inverse_vol_sizing=bool(rot_cfg.get("inverse_vol_sizing", True)),
                min_slot_weight_pct=float(rot_cfg.get("min_slot_weight_pct", 7.0)),
                max_slot_weight_pct=float(rot_cfg.get("max_slot_weight_pct", 20.0)),
                cluster_caps=dict(rot_cfg.get("cluster_caps") or {}),
                gold_vol_exempt=set(rot_cfg.get("gold_vol_exempt") or ["GC=F", "PAXGUSDT"]),
            ),
        ),
    ]

    print("\n" + "=" * 118)
    print(f"HONEST ZERO-LOOK-AHEAD WALK-FORWARD ROTATION ({calendar[0]} -> {calendar[-1]} | $100,000 | 0.10% Fee)")
    print("=" * 118)
    print(f"{'Universe / Sleeve':49s} | {'Final $':>10s} | {'Tot %':>8s} | {'CAGR':>6s} | {'MaxDD':>6s} | {'Sharpe':>6s} | {'Calmar':>6s} | {'Trades':>6s} | {'WR %':>6s}")
    print("-" * 118)

    for label, kwargs in runs:
        res = run_walk_forward_rotation(datasets, calendar, **kwargs)
        print(
            f"{label:49s} | ${res['final_equity']:>9,.0f} | {res['total_return_pct']:>+7.1f}% | "
            f"{res['cagr_pct']:>5.1f}% | {res['max_drawdown_pct']:>5.1f}% | {res['sharpe_ratio']:>6.2f} | "
            f"{res['calmar_ratio']:>6.2f} | {res['total_trades']:>6d} | {res['win_rate_pct']:>5.1f}%"
        )

    spx = _compute_benchmark_spx(datasets, calendar)
    if spx:
        print("-" * 118)
        print(
            f"{'Benchmark: ^GSPC (S&P 500 Buy & Hold)':49s} | ${spx['final_equity']:>9,.0f} | {spx['total_return_pct']:>+7.1f}% | "
            f"{spx['cagr_pct']:>5.1f}% | {spx['max_drawdown_pct']:>5.1f}% | {spx['sharpe_ratio']:>6.2f} | "
            f"{spx['calmar_ratio']:>6.2f} | {'1':>6s} | {'100.0%':>6s}"
        )

    print("=" * 118)
    print("Note: All signals, trailing volatility, and momentum/Sharpe rankings are 100% causal (zero look-ahead).")
    print("      Curation/survivorship bias in config/assets.yaml still applies to absolute CAGR; relative sleeve spread is structural.")


if __name__ == "__main__":
    run_portfolio_simulation()
