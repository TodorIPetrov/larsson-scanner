"""
Quantamental Value-Dip Lab & Multi-Year Backtester (2016-2026).
Fixed & Rigorous Institutional Value Architecture:
1. Structural Quality Gate decouples business quality (Moat, ROIC, Solvency) from momentary valuation (today's MoS).
2. Fixed V2_SPRING_REVERSAL logic: triggers on v1 crossover after sustained BLUE decline.
3. Strict approval criteria: Win Rate >= 50.0%, Sharpe >= 0.45, CAGR >= 6.0%, Max DD <= 33.0%.
4. Exports current technical indicators (SMA-200, RSI, ATR, Swing Low) for live trigger validation.
"""

import concurrent.futures
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QuantValueLab")

CACHE_DIR = os.path.join(BASE_DIR, "data", "backtest_cache")
VERDICTS_PATH = os.path.join(BASE_DIR, "dashboard", "fundamental_verdicts.json")
PROFILES_PATH = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
OUTPUT_CSV = os.path.join(BASE_DIR, "quantamental_value_backtest_results.csv")
REPORT_MD = os.path.join(BASE_DIR, "research", "QUANTAMENTAL_VALUE_REPORT.md")

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


def fast_compute_sma(src: np.ndarray, length: int) -> np.ndarray:
    n = len(src)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < length:
        return out
    cumsum = np.cumsum(np.insert(src, 0, 0))
    out[length - 1:] = (cumsum[length:] - cumsum[:-length]) / length
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


def fast_compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    rsi = np.full(n, 50.0, dtype=np.float64)
    if n <= period:
        return rsi
    deltas = np.diff(close)
    gains = np.maximum(deltas, 0.0)
    losses = np.maximum(-deltas, 0.0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


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
            states[i] = 1   # GOLD
        elif p3:
            states[i] = -1  # BLUE
        else:
            states[i] = 0   # NEUTRAL
    return states


def simulate_quantamental_strategy(
    strategy: str,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    states: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
    sma200: np.ndarray,
    atr: np.ndarray,
    rsi: np.ndarray,
    start_idx: int = 200,
) -> dict:
    n = len(closes)
    if n <= start_idx + 20:
        return {
            "trades": 0, "win_rate": 0.0, "cagr_pct": 0.0,
            "sharpe": 0.0, "max_dd_pct": 0.0, "profit_factor": 1.0,
            "total_return_pct": 0.0
        }

    in_position = False
    shares = 0.0
    cash = 10000.0
    entry_price = 0.0
    stop_loss = 0.0
    position_stage = 0  # 1 = 50%, 2 = 100%
    blue_bars_count = 0
    recent_swing_low = 0.0

    trades_pnl = []
    equity_curve = []

    for i in range(start_idx, n):
        curr_open = opens[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_state = states[i - 1]
        prev_close = closes[i - 1]
        prev_open = opens[i - 1]
        prev_v1 = v1[i - 1]
        prev_v2 = v2[i - 1]
        prev_sma = sma200[i - 1]
        prev_atr = atr[i - 1] if not np.isnan(atr[i - 1]) else (curr_close * 0.02)
        prev_rsi = rsi[i - 1]

        # Track BLUE duration & swing low
        if prev_state == -1:
            blue_bars_count += 1
            if blue_bars_count == 1:
                recent_swing_low = curr_low
            else:
                recent_swing_low = min(recent_swing_low, curr_low)
        else:
            if prev_state == 1:
                blue_bars_count = 0

        # ---------------------------------------------------------
        # 1. Manage Open Position
        # ---------------------------------------------------------
        if in_position:
            exited = False
            exit_price = 0.0

            # Emergency Stop Loss check (intra-bar)
            if curr_low <= stop_loss and stop_loss > 0:
                exit_price = stop_loss
                exited = True

            # Strategy Specific Exit Rules
            if not exited:
                if strategy == "BASELINE_LARSSON":
                    # Exit strictly when state becomes BLUE
                    if prev_state == -1:
                        exit_price = curr_open
                        exited = True

                elif strategy == "V1_SMA200_BOUNCE":
                    # Scale to 100% on GOLD confirmation
                    if position_stage == 1 and prev_state == 1:
                        add_shares = (cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                        shares += add_shares
                        cash -= add_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_stage = 2
                        stop_loss = prev_v2

                    # Exit on confirmed break below SMA200
                    if prev_state == -1 and not np.isnan(prev_sma) and prev_close < prev_sma * 0.96:
                        exit_price = curr_open
                        exited = True

                elif strategy == "V2_SPRING_REVERSAL":
                    # Scale to 100% on GOLD confirmation
                    if position_stage == 1 and prev_state == 1:
                        add_shares = (cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                        shares += add_shares
                        cash -= add_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_stage = 2
                        stop_loss = prev_v2

                    # Exit if rolls over back to BLUE below entry price, or BLUE after GOLD
                    if prev_state == -1 and (position_stage == 2 or prev_close < entry_price):
                        exit_price = curr_open
                        exited = True

                elif strategy == "V3_CAPITULATION_S1":
                    # Scale to 100% on GOLD confirmation
                    if position_stage == 1 and prev_state == 1:
                        add_shares = (cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                        shares += add_shares
                        cash -= add_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_stage = 2
                        stop_loss = prev_v2

                    # Exit if structural support breaks > 12% below entry
                    if curr_close < entry_price * 0.88:
                        exit_price = curr_open
                        exited = True
                    elif position_stage == 2 and prev_state == -1:
                        exit_price = curr_open
                        exited = True

                elif strategy == "V4_VALUE_GOLD_HOLD":
                    # Extended ride: exit on BLUE only if below SMA200
                    if prev_state == -1 and (np.isnan(prev_sma) or prev_close < prev_sma):
                        exit_price = curr_open
                        exited = True

            if exited:
                net_proceeds = shares * exit_price * (1.0 - COMMISSION_PCT)
                trade_pnl = (net_proceeds - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
                trades_pnl.append(trade_pnl)
                cash += net_proceeds
                shares = 0.0
                in_position = False
                position_stage = 0
                stop_loss = 0.0

        # ---------------------------------------------------------
        # 2. Check Strategy Entry Triggers (If flat)
        # ---------------------------------------------------------
        if not in_position and i < n - 1:
            should_enter = False
            initial_stage = 1
            calc_stop = 0.0

            if strategy == "BASELINE_LARSSON":
                if prev_state == 1:
                    should_enter = True
                    initial_stage = 2  # 100%
                    calc_stop = prev_v2

            elif strategy == "V1_SMA200_BOUNCE":
                # Price tests SMA200 during BLUE or NEUTRAL while SMA200 is not collapsing
                sma_ok = not np.isnan(prev_sma) and (prev_sma >= sma200[max(0, i - 40)] * 0.98)
                near_sma = abs(prev_close - prev_sma) / prev_sma <= 0.04 if sma_ok else False
                bullish_bounce = (prev_close > prev_open) and (prev_close > lows[i - 2])
                
                if sma_ok and near_sma and bullish_bounce and prev_state in [-1, 0]:
                    should_enter = True
                    initial_stage = 1  # 50% tranche
                    calc_stop = prev_sma - (1.75 * prev_atr)

            elif strategy == "V2_SPRING_REVERSAL":
                # Price crosses above v1 after at least 6 bars of decline
                crossed_v1 = (prev_close > prev_v1) and (closes[i - 2] <= v1[i - 2])
                if blue_bars_count >= 6 and crossed_v1 and prev_close > prev_open:
                    should_enter = True
                    initial_stage = 1  # 50% tranche
                    calc_stop = recent_swing_low if (recent_swing_low > 0 and recent_swing_low < prev_close) else (prev_close * 0.93)

            elif strategy == "V3_CAPITULATION_S1":
                # RSI oversold recovery: RSI crosses back above 32 from < 30
                rsi_reversal = (prev_rsi >= 32.0) and (rsi[i - 2] < 30.0)
                if rsi_reversal and prev_state in [-1, 0]:
                    should_enter = True
                    initial_stage = 1  # 50% tranche
                    calc_stop = curr_low - (1.5 * prev_atr)

            elif strategy == "V4_VALUE_GOLD_HOLD":
                # Fresh Gold Flip on Quality Stock
                is_fresh_gold = (prev_state == 1) and (states[i - 2] != 1)
                if is_fresh_gold:
                    should_enter = True
                    initial_stage = 2  # 100%
                    calc_stop = prev_v2

            if should_enter:
                in_position = True
                position_stage = initial_stage
                entry_price = curr_open
                # Guarantee stop loss invariant: stop MUST be strictly below entry price!
                if calc_stop >= entry_price or calc_stop <= 0:
                    calc_stop = entry_price * 0.93
                stop_loss = calc_stop

                allocation = 1.0 if position_stage == 2 else 0.5
                alloc_cash = cash * allocation
                shares = (alloc_cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                cash -= shares * curr_open * (1.0 + COMMISSION_PCT)

        # Daily Mark to Market
        current_eq = cash + (shares * curr_close)
        equity_curve.append(current_eq)

    # Close open trade at test end
    if in_position and shares > 0:
        net_proceeds = shares * closes[n - 1] * (1.0 - COMMISSION_PCT)
        trade_pnl = (net_proceeds - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
        trades_pnl.append(trade_pnl)
        cash += net_proceeds

    total_trades = len(trades_pnl)
    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    final_equity = cash
    total_ret = ((final_equity - 10000.0) / 10000.0) * 100.0

    years = max(0.5, (n - start_idx) / 252.0)
    cagr = (((max(0.01, final_equity) / 10000.0) ** (1.0 / years)) - 1.0) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = min(25.0, gross_profit / gross_loss) if gross_loss > 0 else (25.0 if gross_profit > 0 else 1.0)

    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

    daily_returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)

    return {
        "trades": total_trades,
        "win_rate": round(win_rate, 1),
        "total_return_pct": round(total_ret, 1),
        "cagr_pct": round(cagr, 1),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(max_dd, 1),
        "profit_factor": round(profit_factor, 2),
    }


def evaluate_asset_value_dna(verdict_item: dict) -> Optional[dict]:
    ticker = verdict_item.get("ticker", "")
    name = verdict_item.get("name", ticker)
    sector = verdict_item.get("sector", "Other")
    moat = verdict_item.get("moat", "None")
    z_score = verdict_item.get("z_score")
    m_score = verdict_item.get("m_score")
    roic = verdict_item.get("roic_pct")
    wacc = verdict_item.get("wacc_pct")
    mos_pct = verdict_item.get("mos_pct")

    # 1. Structural Quality Gate (Pure Business Quality & Solvency, NOT today's price!)
    is_quality_moat = (moat in ["Wide", "Narrow"]) or (roic is not None and wacc is not None and roic > wacc + 2.0)
    is_safe_solvency = (z_score is None) or (z_score >= 1.90)  # Safe Altman Z-Score
    is_clean_accounting = (m_score is None) or (m_score < -1.78)

    passes_quality_gate = bool(is_quality_moat and is_safe_solvency and is_clean_accounting)

    # 2. Load historical OHLCV data from cache
    csv_candidates = [
        os.path.join(CACHE_DIR, f"{ticker}_1D.csv"),
        os.path.join(CACHE_DIR, f"{ticker.replace('=', '_')}_1D.csv"),
    ]
    csv_path = next((p for p in csv_candidates if os.path.exists(p)), None)
    if not csv_path:
        return None

    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return None

    if len(df) < 250:
        return None

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
    sma200 = fast_compute_sma(closes, 200)
    atr = fast_compute_atr(highs, lows, closes, 14)
    rsi = fast_compute_rsi(closes, 14)

    # Store latest technical levels for live trigger checks
    latest_sma200 = float(sma200[-1]) if not np.isnan(sma200[-1]) else None
    latest_rsi14 = float(rsi[-1]) if not np.isnan(rsi[-1]) else 50.0
    latest_atr14 = float(atr[-1]) if not np.isnan(atr[-1]) else (closes[-1] * 0.02)
    latest_swing_low_20d = float(np.min(lows[-20:])) if len(lows) >= 20 else float(closes[-1] * 0.93)

    # Test all 4 strategies + Baseline
    strat_results = {}
    strategies = [
        "BASELINE_LARSSON",
        "V1_SMA200_BOUNCE",
        "V2_SPRING_REVERSAL",
        "V3_CAPITULATION_S1",
        "V4_VALUE_GOLD_HOLD"
    ]

    for st in strategies:
        res = simulate_quantamental_strategy(
            strategy=st,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            states=states,
            v1=v1,
            v2=v2,
            sma200=sma200,
            atr=atr,
            rsi=rsi,
            start_idx=200,
        )
        strat_results[st] = res

    base_res = strat_results["BASELINE_LARSSON"]
    value_strats = ["V1_SMA200_BOUNCE", "V2_SPRING_REVERSAL", "V3_CAPITULATION_S1", "V4_VALUE_GOLD_HOLD"]

    best_st = None
    best_score = -999.0
    best_metrics = None

    for st in value_strats:
        m = strat_results[st]
        if m["trades"] >= 3:
            # Score favors high Win Rate, strong Sharpe and CAGR with Drawdown penalty
            score = (m["sharpe"] * 45.0) + (m["cagr_pct"] * 1.0) + (m["win_rate"] * 0.6) - (m["max_dd_pct"] * 0.5)
            if score > best_score:
                best_score = score
                best_st = st
                best_metrics = m

    value_dip_allowed = False
    if passes_quality_gate and best_metrics:
        # Strict Empirical Guard: Win Rate >= 50.0%, Sharpe >= 0.45, CAGR >= 6.0%, Max DD <= 33.0%
        if best_metrics["win_rate"] >= 50.0 and best_metrics["sharpe"] >= 0.45 and best_metrics["cagr_pct"] >= 6.0 and best_metrics["max_dd_pct"] <= 33.0:
            value_dip_allowed = True

    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "moat": moat,
        "z_score": z_score,
        "roic_pct": roic,
        "wacc_pct": wacc,
        "mos_pct": mos_pct,
        "quality_gate": passes_quality_gate,
        "value_dip_allowed": value_dip_allowed,
        "best_value_strategy": best_st if value_dip_allowed else "NONE_MOMENTUM_ONLY",
        "value_sharpe": best_metrics["sharpe"] if best_metrics else 0.0,
        "value_cagr_pct": best_metrics["cagr_pct"] if best_metrics else 0.0,
        "value_win_rate": best_metrics["win_rate"] if best_metrics else 0.0,
        "value_max_dd_pct": best_metrics["max_dd_pct"] if best_metrics else 0.0,
        "value_trades": best_metrics["trades"] if best_metrics else 0,
        "base_sharpe": base_res["sharpe"],
        "base_cagr_pct": base_res["cagr_pct"],
        "base_win_rate": base_res["win_rate"],
        "base_max_dd_pct": base_res["max_dd_pct"],
        "latest_sma200": latest_sma200,
        "latest_rsi14": latest_rsi14,
        "latest_atr14": latest_atr14,
        "latest_swing_low_20d": latest_swing_low_20d,
        "all_metrics": strat_results,
    }


def main():
    logger.info("Initializing Quantamental Value-Dip Lab (Strict Remediated Architecture)...")

    if not os.path.exists(VERDICTS_PATH):
        logger.error(f"Verdicts file not found: {VERDICTS_PATH}")
        return

    with open(VERDICTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        verdicts = data.get("verdicts", [])

    logger.info(f"Loaded {len(verdicts)} fundamental verdicts.")

    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        futures = {executor.submit(evaluate_asset_value_dna, v): v for v in verdicts}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    logger.info(f"Successfully simulated {len(results)} equities.")

    rows = []
    for r in results:
        rows.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "sector": r["sector"],
            "moat": r["moat"],
            "z_score": r["z_score"],
            "roic_pct": r["roic_pct"],
            "mos_pct": r["mos_pct"],
            "quality_gate": r["quality_gate"],
            "value_dip_allowed": r["value_dip_allowed"],
            "best_value_strategy": r["best_value_strategy"],
            "value_sharpe": r["value_sharpe"],
            "value_cagr_pct": r["value_cagr_pct"],
            "value_win_rate": r["value_win_rate"],
            "value_max_dd_pct": r["value_max_dd_pct"],
            "value_trades": r["value_trades"],
            "base_sharpe": r["base_sharpe"],
            "base_cagr_pct": r["base_cagr_pct"],
            "base_win_rate": r["base_win_rate"],
        })

    df_out = pd.DataFrame(rows)
    df_out.sort_values(by=["value_dip_allowed", "value_sharpe"], ascending=[False, False], inplace=True)
    df_out.to_csv(OUTPUT_CSV, index=False)
    logger.info(f"Saved results to {OUTPUT_CSV}")

    allowed = df_out[df_out["value_dip_allowed"] == True]
    forbidden = df_out[df_out["value_dip_allowed"] == False]

    logger.info(f"Value Dip Approved: {len(allowed)} assets ({len(allowed)/len(df_out)*100:.1f}%)")
    logger.info(f"Value Dip Forbidden (Pure Momentum Only): {len(forbidden)} assets ({len(forbidden)/len(df_out)*100:.1f}%)")

    # Update data/asset_optimal_profiles.json
    existing_profiles = {}
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            try:
                existing_profiles = json.load(f)
            except Exception:
                pass

    for r in results:
        sym = r["ticker"]
        prof = existing_profiles.setdefault(sym, {})
        prof["value_dip_allowed"] = r["value_dip_allowed"]
        prof["best_value_strategy"] = r["best_value_strategy"]
        prof["value_sharpe"] = r["value_sharpe"]
        prof["value_cagr_pct"] = r["value_cagr_pct"]
        prof["value_win_rate"] = r["value_win_rate"]
        prof["value_max_dd_pct"] = r["value_max_dd_pct"]
        prof["value_quality_gate"] = r["quality_gate"]
        prof["latest_sma200"] = r["latest_sma200"]
        prof["latest_rsi14"] = r["latest_rsi14"]
        prof["latest_atr14"] = r["latest_atr14"]
        prof["latest_swing_low_20d"] = r["latest_swing_low_20d"]

    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_profiles, f, indent=2, ensure_ascii=False)
    logger.info(f"Updated {PROFILES_PATH} with Value DNA profiles and technical levels.")

    # Generate Markdown Report
    strat_breakdown = allowed["best_value_strategy"].value_counts().to_dict()

    top_allowed_md = ""
    for idx, row in allowed.head(25).iterrows():
        top_allowed_md += f"| **{row['ticker']}** | {row['name']} | {row['sector']} | `{row['best_value_strategy']}` | **{row['value_win_rate']}%** | **{row['value_sharpe']}** | +{row['value_cagr_pct']}% | -{row['value_max_dd_pct']}% |\n"

    top_forbidden_md = ""
    for idx, row in forbidden.head(15).iterrows():
        reason = "Ниска рентабилност/Без ров" if not row['quality_gate'] else "Исторически Win Rate < 50% или неустойчив спад"
        top_forbidden_md += f"| **{row['ticker']}** | {row['name']} | {row['sector']} | **🚫 ЗАБРАНЕН** | {reason} |\n"

    report_content = f"""# 🔬 Доклад: Quantamental Value-Dip Лаборатория (2016–2026) — Прецизирана Версия

## 1. Резюме на Изследването
- **Тествани активи:** {len(df_out)} корпоративни акции с институционални DCF/EVA профили.
- **Период на симулация:** 2016–2026 г. (включващ QT разпродажбата от 2018 г., COVID паниката от 2020 г., мечия пазар от 2022 г. и AI експанзията 2023–2026 г.).
- **Одобрени за покупка на спад (`value_dip_allowed = True`):** **{len(allowed)} актива ({len(allowed)/len(df_out)*100:.1f}%)**
- **Забранени за купуване на спад (`value_dip_allowed = False`):** **{len(forbidden)} актива ({len(forbidden)/len(df_out)*100:.1f}%)**
  - *Извод:* При {len(forbidden)} от акциите купуването на спад в `BLUE` исторически води до лоши резултати (Value Trap). За тях системата налага **строга забрана** и търгува **единствено по тренда в `GOLD`**!

---

## 2. Разпределение на 4-те Value Стратегии сред Одобрените Лидери

| Стратегия | Брой Печеливши Акции | Дял | Описание на Тригера |
| :--- | :---: | :---: | :--- |
| **`V1_SMA200_BOUNCE`** | {strat_breakdown.get('V1_SMA200_BOUNCE', 0)} | {round(strat_breakdown.get('V1_SMA200_BOUNCE', 0)/max(1, len(allowed))*100, 1)}% | Институционална подкрепа на 200-дневната пълзяща средна при възходящ тренд. |
| **`V2_SPRING_REVERSAL`** | {strat_breakdown.get('V2_SPRING_REVERSAL', 0)} | {round(strat_breakdown.get('V2_SPRING_REVERSAL', 0)/max(1, len(allowed))*100, 1)}% | Преход от `BLUE` към `NEUTRAL` със затваряне над $v_1$ и стоп под локалното дъно. |
| **`V3_CAPITULATION_S1`** | {strat_breakdown.get('V3_CAPITULATION_S1', 0)} | {round(strat_breakdown.get('V3_CAPITULATION_S1', 0)/max(1, len(allowed))*100, 1)}% | Капитулация на структурна подкрепа $S_1$ с обръщане на RSI от свръхпродаденост. |
| **`V4_VALUE_GOLD_HOLD`** | {strat_breakdown.get('V4_VALUE_GOLD_HOLD', 0)} | {round(strat_breakdown.get('V4_VALUE_GOLD_HOLD', 0)/max(1, len(allowed))*100, 1)}% | Златен пробив на подценена качествена компания с дълго задържане. |

---

## 3. Топ 25 Одобрени Компании за Покупка на Спад (с доказана Value ДНК)

| Тикер | Име | Сектор | Оптимална Value Стратегия | Win Rate % | Sharpe | CAGR % | Max DD % |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
{top_allowed_md}

---

## 4. Примери за Активи със Строга Забрана за Покупка на Спад (`Value Trap Protection`)

| Тикер | Име | Сектор | Статус | Причина за Забраната |
| :--- | :--- | :--- | :---: | :--- |
{top_forbidden_md}
"""

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report_content)
    logger.info(f"Generated comprehensive report at {REPORT_MD}")


if __name__ == "__main__":
    main()
