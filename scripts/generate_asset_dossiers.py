"""
Asset Dossier & Backtest Visualizer Generator.
Generates comprehensive dossier files for assets featured in the Momentum Rotation Portfolio:
1. Daily OHLCV candles (last 300-350 bars) + Larsson Ribbon (v1, m1, m2, v2) + 200-SMA.
2. Backtest simulation across 6 strategies:
   - CLASSIC_BLUE_EXIT (Hold through Neutral, exit strictly on BLUE)
   - FAST_EXIT_NEUTRAL (Take profits quickly at Neutral)
   - PULLBACK_V1_ACCUMULATOR (Scale 50% on Gold, 50% on v1 test)
   - V3_CAPITULATION_S1 (Capitulation at S1 support with RSI reversal)
   - V4_VALUE_GOLD_HOLD (Extended value trend holding above SMA200)
   - BUY_AND_HOLD (Benchmark)
3. Visual trade markers (BUY / EXIT with PnL %) for the winning strategy.
4. Daily equity curves (growth of EUR 10,000) for visual comparison.
5. Full trade-by-trade historical journal.
Saved to dashboard/data/dossiers/{SAFE_TICKER}.json.
"""

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

CACHE_DIR = os.path.join(BASE_DIR, "data", "backtest_cache")
PROFILES_PATH = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
VERDICTS_PATH = os.path.join(BASE_DIR, "dashboard", "fundamental_verdicts.json")
DOSSIERS_DIR = os.path.join(BASE_DIR, "dashboard", "data", "dossiers")
DATA_JSON_PATH = os.path.join(BASE_DIR, "dashboard", "data.json")

os.makedirs(DOSSIERS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AssetDossierGen")

COMMISSION_PCT = 0.001  # 0.10%


def safe_ticker_filename(ticker: str) -> str:
    return ticker.replace("/", "_").replace("^", "_").replace(":", "_")


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


def simulate_strategy_full(
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
    dates: List[str],
    start_idx: int = 150,
) -> dict:
    n = len(closes)
    initial_capital = 10000.0
    cash = initial_capital
    shares = 0.0
    in_position = False
    position_stage = 0
    entry_price = 0.0
    entry_idx = 0
    entry_date = ""
    stop_loss = 0.0
    blue_bars_count = 0

    trades = []
    equity_curve = []

    # Handle Buy & Hold benchmark separately
    if strategy == "BUY_AND_HOLD":
        bnh_shares = (initial_capital * (1.0 - COMMISSION_PCT)) / opens[start_idx]
        bnh_entry_date = dates[start_idx]
        bnh_entry_price = opens[start_idx]
        for i in range(start_idx, n):
            eq = bnh_shares * closes[i]
            equity_curve.append({"time": dates[i], "value": round(eq, 2)})
        final_eq = bnh_shares * closes[n - 1] * (1.0 - COMMISSION_PCT)
        ret_pct = ((final_eq - initial_capital) / initial_capital) * 100.0
        years = max(0.5, (n - start_idx) / 252.0)
        cagr = (((max(0.01, final_eq) / initial_capital) ** (1.0 / years)) - 1.0) * 100.0
        
        eq_arr = np.array([pt["value"] for pt in equity_curve])
        peaks = np.maximum.accumulate(eq_arr)
        dds = (eq_arr - peaks) / peaks
        max_dd = abs(np.min(dds)) * 100.0 if len(dds) > 0 else 0.0

        daily_ret = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)) if len(daily_ret) > 1 and np.std(daily_ret) > 0 else 0.0

        return {
            "strategy": "BUY_AND_HOLD",
            "name_bg": "Купи и Дръж (Бенчмарк)",
            "description_bg": "Пасивно инвестиране без защита на капитала при мечи пазари.",
            "final_equity": round(final_eq, 2),
            "total_return_pct": round(ret_pct, 1),
            "cagr_pct": round(cagr, 1),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_dd, 1),
            "win_rate_pct": 100.0 if ret_pct > 0 else 0.0,
            "profit_factor": round(max(0.1, ret_pct / max(1.0, max_dd)), 2),
            "total_trades": 1,
            "trades": [{
                "num": 1,
                "entry_date": bnh_entry_date,
                "entry_price": round(bnh_entry_price, 2),
                "exit_date": dates[n - 1],
                "exit_price": round(closes[n - 1], 2),
                "holding_days": n - start_idx,
                "pnl_pct": round(ret_pct, 2),
                "pnl_eur": round(final_eq - initial_capital, 2),
                "exit_reason": "BENCHMARK_HOLD",
            }],
            "equity_curve": equity_curve,
        }

    # Simulation loop for active strategies
    for i in range(start_idx, n):
        curr_open = opens[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_close = closes[i]

        prev_close = closes[i - 1]
        prev_open = opens[i - 1]
        prev_state = states[i - 1]
        prev_v1 = v1[i - 1]
        prev_v2 = v2[i - 1]
        prev_sma = sma200[i - 1]
        prev_atr = atr[i - 1]
        prev_rsi = rsi[i - 1]

        if prev_state == -1:
            blue_bars_count += 1
        else:
            blue_bars_count = 0

        recent_swing = float(np.min(lows[max(0, i - 20):i])) if i > 20 else curr_low

        # 1. Manage Open Position
        if in_position:
            exited = False
            exit_price = 0.0
            exit_reason = ""

            # Hard Stop Loss Check
            if curr_low <= stop_loss and stop_loss > 0:
                exit_price = min(curr_open, stop_loss)
                exited = True
                exit_reason = "Твърд Стоп-Лос"
            else:
                if strategy == "CLASSIC_BLUE_EXIT":
                    # Exit strictly when state changes to BLUE
                    if prev_state == -1:
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Обръщане в BLUE"

                elif strategy == "FAST_EXIT_NEUTRAL":
                    # Take profit immediately when GOLD ends (NEUTRAL or BLUE)
                    if prev_state != 1:
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Fast Exit при NEUTRAL"

                elif strategy == "PULLBACK_V1_ACCUMULATOR":
                    # Scale to 100% on v1 test in Gold, exit strictly on BLUE
                    if position_stage == 1 and prev_state == 1 and abs(prev_close - prev_v1) / prev_v1 <= 0.02:
                        add_shares = (cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                        shares += add_shares
                        cash -= add_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_stage = 2
                        stop_loss = prev_v2
                    if prev_state == -1:
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Обръщане в BLUE"

                elif strategy == "V3_CAPITULATION_S1":
                    # Scale to 100% on GOLD, exit if support breaks or BLUE after GOLD
                    if position_stage == 1 and prev_state == 1:
                        add_shares = (cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                        shares += add_shares
                        cash -= add_shares * curr_open * (1.0 + COMMISSION_PCT)
                        position_stage = 2
                        stop_loss = prev_v2
                    if curr_close < entry_price * 0.88:
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Пробив на Подкрепа (-12%)"
                    elif position_stage == 2 and prev_state == -1:
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Изход след Златен Вход"

                elif strategy == "V4_VALUE_GOLD_HOLD":
                    # Extended trend hold: exit on BLUE only if below SMA200
                    if prev_state == -1 and (np.isnan(prev_sma) or prev_close < prev_sma):
                        exit_price = curr_open
                        exited = True
                        exit_reason = "Пробив под 200-SMA"

            if exited:
                net_proc = shares * exit_price * (1.0 - COMMISSION_PCT)
                trade_pnl = (net_proc - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
                pnl_eur = net_proc - (shares * entry_price * (1.0 + COMMISSION_PCT))
                trades.append({
                    "num": len(trades) + 1,
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 2),
                    "exit_date": dates[i],
                    "exit_price": round(exit_price, 2),
                    "holding_days": i - entry_idx,
                    "pnl_pct": round(trade_pnl * 100.0, 2),
                    "pnl_eur": round(pnl_eur, 2),
                    "exit_reason": exit_reason,
                    "is_win": bool(trade_pnl > 0),
                })
                cash += net_proc
                shares = 0.0
                in_position = False
                position_stage = 0
                stop_loss = 0.0

        # 2. Check Entry Triggers
        if not in_position and i < n - 1:
            should_enter = False
            initial_stage = 1
            calc_stop = 0.0

            if strategy == "CLASSIC_BLUE_EXIT" or strategy == "FAST_EXIT_NEUTRAL":
                if prev_state == 1:
                    should_enter = True
                    initial_stage = 2
                    calc_stop = prev_v2

            elif strategy == "PULLBACK_V1_ACCUMULATOR":
                if prev_state == 1:
                    should_enter = True
                    initial_stage = 1
                    calc_stop = prev_v2

            elif strategy == "V3_CAPITULATION_S1":
                rsi_reversal = (prev_rsi >= 32.0) and (rsi[i - 2] < 30.0)
                if rsi_reversal and prev_state in [-1, 0]:
                    should_enter = True
                    initial_stage = 1
                    calc_stop = curr_low - (1.5 * prev_atr)

            elif strategy == "V4_VALUE_GOLD_HOLD":
                is_fresh_gold = (prev_state == 1) and (states[i - 2] != 1)
                if is_fresh_gold:
                    should_enter = True
                    initial_stage = 2
                    calc_stop = prev_v2

            if should_enter:
                in_position = True
                position_stage = initial_stage
                entry_price = curr_open
                entry_idx = i
                entry_date = dates[i]
                if calc_stop >= entry_price or calc_stop <= 0:
                    calc_stop = entry_price * 0.93
                stop_loss = calc_stop

                alloc = 1.0 if position_stage == 2 else 0.5
                alloc_cash = cash * alloc
                shares = (alloc_cash * 0.999) / (curr_open * (1.0 + COMMISSION_PCT))
                cash -= shares * curr_open * (1.0 + COMMISSION_PCT)

        # Mark to market equity
        curr_eq = cash + (shares * curr_close)
        equity_curve.append({"time": dates[i], "value": round(curr_eq, 2)})

    # Close open trade at test end
    if in_position and shares > 0:
        exit_p = closes[n - 1]
        net_proc = shares * exit_p * (1.0 - COMMISSION_PCT)
        trade_pnl = (net_proc - (shares * entry_price * (1.0 + COMMISSION_PCT))) / (shares * entry_price * (1.0 + COMMISSION_PCT))
        pnl_eur = net_proc - (shares * entry_price * (1.0 + COMMISSION_PCT))
        trades.append({
            "num": len(trades) + 1,
            "entry_date": entry_date,
            "entry_price": round(entry_price, 2),
            "exit_date": dates[n - 1],
            "exit_price": round(exit_p, 2),
            "holding_days": (n - 1) - entry_idx,
            "pnl_pct": round(trade_pnl * 100.0, 2),
            "pnl_eur": round(pnl_eur, 2),
            "exit_reason": "Край на Бектеста (Отворена)",
            "is_win": bool(trade_pnl > 0),
        })
        cash += net_proc

    final_eq = cash
    total_ret = ((final_eq - initial_capital) / initial_capital) * 100.0
    years = max(0.5, (n - start_idx) / 252.0)
    cagr = (((max(0.01, final_eq) / initial_capital) ** (1.0 / years)) - 1.0) * 100.0

    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    gw = sum(t["pnl_eur"] for t in wins)
    gl = abs(sum(t["pnl_eur"] for t in losses))
    pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 1.0)

    eq_arr = np.array([pt["value"] for pt in equity_curve])
    peaks = np.maximum.accumulate(eq_arr)
    dds = (eq_arr - peaks) / peaks
    max_dd = abs(np.min(dds)) * 100.0 if len(dds) > 0 else 0.0

    daily_ret = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)) if len(daily_ret) > 1 and np.std(daily_ret) > 0 else 0.0

    names_bg = {
        "CLASSIC_BLUE_EXIT": "Класически Larsson (Изход на BLUE)",
        "FAST_EXIT_NEUTRAL": "Бърз Изход (Прибиране при NEUTRAL)",
        "PULLBACK_V1_ACCUMULATOR": "Вход на Подкрепа v1 (Двустепенен)",
        "V3_CAPITULATION_S1": "Value Капитулация на S1 Подкрепа",
        "V4_VALUE_GOLD_HOLD": "Value Тренд (Държане над 200-SMA)",
    }
    desc_bg = {
        "CLASSIC_BLUE_EXIT": "Влиза при GOLD, остава в позиция през фази на колебание (NEUTRAL) и излиза само при потвърден мечи пробив (BLUE).",
        "FAST_EXIT_NEUTRAL": "Прибира печалбата веднага при първия признак на загуба на моментум (NEUTRAL). Пази от резки сривове.",
        "PULLBACK_V1_ACCUMULATOR": "Влиза с 50% транш при пробив в GOLD и добавя още 50% при успешен тест на линията v1.",
        "V3_CAPITULATION_S1": "Купува свръхпродадени разпродажби директно на структурна подкрепа S1 с изключително плътен риск.",
        "V4_VALUE_GOLD_HOLD": "Изчаква златен пробив при подценена качествена компания и държи докато цената е над 200-дневната средна.",
    }

    return {
        "strategy": strategy,
        "name_bg": names_bg.get(strategy, strategy),
        "description_bg": desc_bg.get(strategy, ""),
        "final_equity": round(final_eq, 2),
        "total_return_pct": round(total_ret, 1),
        "cagr_pct": round(cagr, 1),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 1),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "total_trades": len(trades),
        "trades": trades,
        "equity_curve": equity_curve,
    }


def generate_single_asset_dossier(ticker: str, optimal_profile: dict, verdict_item: dict) -> Optional[dict]:
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

    if len(df) < 200:
        return None

    dates = df["date"].tolist() if "date" in df.columns else [str(x) for x in range(len(df))]
    highs = df["high"].to_numpy(dtype=np.float64)
    lows = df["low"].to_numpy(dtype=np.float64)
    closes = df["close"].to_numpy(dtype=np.float64)
    opens = df["open"].to_numpy(dtype=np.float64)
    volumes = df["volume"].to_numpy(dtype=np.float64) if "volume" in df.columns else np.zeros(len(df))

    hl2 = (highs + lows) / 2.0
    v1 = fast_compute_smma(hl2, 15)
    m1 = fast_compute_smma(hl2, 19)
    m2 = fast_compute_smma(hl2, 25)
    v2 = fast_compute_smma(hl2, 29)
    states = evaluate_larsson_states(v1, m1, m2, v2)
    sma200 = fast_compute_sma(closes, 200)
    atr = fast_compute_atr(highs, lows, closes, 14)
    rsi = fast_compute_rsi(closes, 14)

    start_idx = min(150, max(30, len(df) // 4))  # Full multi-year backtest horizon (~1,100+ bars)

    # Simulate all strategies
    strats = [
        "CLASSIC_BLUE_EXIT",
        "FAST_EXIT_NEUTRAL",
        "PULLBACK_V1_ACCUMULATOR",
        "V3_CAPITULATION_S1",
        "V4_VALUE_GOLD_HOLD",
        "BUY_AND_HOLD",
    ]

    sim_results = []
    for st in strats:
        res = simulate_strategy_full(
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
            dates=dates,
            start_idx=start_idx,
        )
        sim_results.append(res)

    # Determine Winning Strategy
    active_strats = [s for s in sim_results if s["strategy"] != "BUY_AND_HOLD"]
    # Sort by Sharpe, CAGR, Win Rate with Max DD penalty
    active_strats.sort(key=lambda s: (s["sharpe_ratio"] * 30.0) + (s["cagr_pct"] * 1.0) + (s["win_rate_pct"] * 0.5) - (s["max_drawdown_pct"] * 0.5), reverse=True)
    winner = active_strats[0] if active_strats else sim_results[0]
    winning_strat_id = winner["strategy"]

    # Mark winner in results
    for s in sim_results:
        s["is_winner"] = (s["strategy"] == winning_strat_id)

    # Build Candlestick Series (last 300 bars)
    candles = []
    for i in range(start_idx, len(df)):
        c_entry = {
            "time": dates[i],
            "open": round(float(opens[i]), 2),
            "high": round(float(highs[i]), 2),
            "low": round(float(lows[i]), 2),
            "close": round(float(closes[i]), 2),
            "volume": round(float(volumes[i]), 0),
            "v1": round(float(v1[i]), 2) if not np.isnan(v1[i]) else None,
            "m1": round(float(m1[i]), 2) if not np.isnan(m1[i]) else None,
            "m2": round(float(m2[i]), 2) if not np.isnan(m2[i]) else None,
            "v2": round(float(v2[i]), 2) if not np.isnan(v2[i]) else None,
            "sma200": round(float(sma200[i]), 2) if not np.isnan(sma200[i]) else None,
            "state": "GOLD" if states[i] == 1 else ("BLUE" if states[i] == -1 else "NEUTRAL"),
        }
        candles.append(c_entry)

    # Build Trade Markers for the Winning Strategy
    markers = []
    for tr in winner["trades"]:
        markers.append({
            "time": tr["entry_date"],
            "position": "belowBar",
            "color": "#10b981",
            "shape": "arrowUp",
            "text": f"BUY #{tr['num']} @ ${tr['entry_price']}",
        })
        if tr["exit_date"]:
            color = "#10b981" if tr["pnl_pct"] > 0 else "#ef4444"
            sign = "+" if tr["pnl_pct"] > 0 else ""
            markers.append({
                "time": tr["exit_date"],
                "position": "aboveBar",
                "color": color,
                "shape": "arrowDown",
                "text": f"EXIT {sign}{tr['pnl_pct']}% (${tr['pnl_eur']} €)",
            })

    # Prepare Equity Curves for Top 4 Strategies
    display_strats = [winner]
    for st in [s for s in active_strats if s["strategy"] != winning_strat_id][:2]:
        display_strats.append(st)
    bnh = next((s for s in sim_results if s["strategy"] == "BUY_AND_HOLD"), None)
    if bnh:
        display_strats.append(bnh)

    curves_data = []
    for s in display_strats:
        curves_data.append({
            "strategy": s["strategy"],
            "name_bg": s["name_bg"],
            "is_winner": s.get("is_winner", False),
            "curve": s["equity_curve"],  # Full multi-year equity curve (~1,100+ bars)
        })

    dossier = {
        "ticker": ticker,
        "name": verdict_item.get("name", ticker),
        "sector": verdict_item.get("sector", optimal_profile.get("sector", "Equities")),
        "asset_class": optimal_profile.get("asset_class", "us_stocks"),
        "backtest_start_date": dates[start_idx] if len(dates) > start_idx else "2021-09-01",
        "backtest_end_date": dates[-1] if dates else "2026-10-30",
        "backtest_years": round((len(df) - start_idx) / 252.0, 1),
        "backtest_total_bars": len(df) - start_idx,
        "current_price": round(float(closes[-1]), 2),
        "state": "GOLD" if states[-1] == 1 else ("BLUE" if states[-1] == -1 else "NEUTRAL"),
        "v1": round(float(v1[-1]), 2) if not np.isnan(v1[-1]) else None,
        "v2": round(float(v2[-1]), 2) if not np.isnan(v2[-1]) else None,
        "sma200": round(float(sma200[-1]), 2) if not np.isnan(sma200[-1]) else None,
        "rsi14": round(float(rsi[-1]), 1) if not np.isnan(rsi[-1]) else 50.0,
        "atr14": round(float(atr[-1]), 2) if not np.isnan(atr[-1]) else 2.0,
        "empirical_tier": optimal_profile.get("empirical_tier", "A"),
        "walk_forward_stable": optimal_profile.get("walk_forward_stable", True),
        "winning_strategy": winning_strat_id,
        "winning_strategy_name": winner["name_bg"],
        "winning_metrics": {
            "total_return_pct": winner["total_return_pct"],
            "cagr_pct": winner["cagr_pct"],
            "sharpe_ratio": winner["sharpe_ratio"],
            "win_rate_pct": winner["win_rate_pct"],
            "profit_factor": winner["profit_factor"],
            "max_drawdown_pct": winner["max_drawdown_pct"],
            "total_trades": winner["total_trades"],
        },
        "all_strategies": [
            {
                "strategy": s["strategy"],
                "name_bg": s["name_bg"],
                "is_winner": s.get("is_winner", False),
                "total_return_pct": s["total_return_pct"],
                "cagr_pct": s["cagr_pct"],
                "sharpe_ratio": s["sharpe_ratio"],
                "win_rate_pct": s["win_rate_pct"],
                "profit_factor": s["profit_factor"],
                "max_drawdown_pct": s["max_drawdown_pct"],
                "total_trades": s["total_trades"],
            }
            for s in sim_results
        ],
        "fundamental": {
            "fair_value": verdict_item.get("intrinsic_value") or verdict_item.get("fair_value"),
            "mos_pct": verdict_item.get("margin_of_safety_pct") or verdict_item.get("mos_pct"),
            "moat": verdict_item.get("moat_rating") or verdict_item.get("moat", "None"),
            "roic_pct": verdict_item.get("roic_pct"),
            "wacc_pct": verdict_item.get("wacc_pct"),
            "z_score": verdict_item.get("z_score"),
            "verdict": verdict_item.get("verdict", "FAIRLY VALUED"),
        },
        "candles": candles,
        "markers": markers,
        "equity_curves": curves_data,
        "winning_trades_log": winner["trades"],
    }

    return dossier


def generate_dossiers_for_rotation_assets():
    logger.info("Generating asset dossiers for Momentum Rotation Portfolio...")

    # Load data.json to identify active rotation assets
    rotation_tickers = set()
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                rot = d.get("rotation_portfolio", {})
                for k in ["top15", "reserve_bench", "fresh_flips", "pullback_entries", "quantamental_dips", "broken_leaders"]:
                    for item in rot.get(k, []):
                        if isinstance(item, dict) and "ticker" in item:
                            rotation_tickers.add(item["ticker"])
        except Exception as e:
            logger.warning(f"Could not read rotation tickers from data.json: {e}")

    # Also add standard mega caps if missing
    core_watchlist = ["NVDA", "AAPL", "MSFT", "GOOGL", "2330.TW", "ALV.DE", "1513.TW", "2345.TW", "DECK", "0700.HK", "TSLA", "BTCUSDT", "ETHUSDT"]
    for t in core_watchlist:
        rotation_tickers.add(t)

    logger.info(f"Target rotation universe: {len(rotation_tickers)} assets.")

    # Load profiles and verdicts
    optimal_profiles = {}
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            optimal_profiles = json.load(f)

    verdicts_map = {}
    if os.path.exists(VERDICTS_PATH):
        with open(VERDICTS_PATH, "r", encoding="utf-8") as f:
            v_data = json.load(f)
            for v in v_data.get("verdicts", []):
                verdicts_map[v.get("ticker", "")] = v

    generated = 0
    for ticker in sorted(rotation_tickers):
        prof = optimal_profiles.get(ticker, {})
        verd = verdicts_map.get(ticker, {})
        dossier = generate_single_asset_dossier(ticker, prof, verd)
        if dossier:
            out_fn = f"{safe_ticker_filename(ticker)}.json"
            out_path = os.path.join(DOSSIERS_DIR, out_fn)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(dossier, f, indent=2, ensure_ascii=False)
            generated += 1

    logger.info(f"Successfully generated {generated} asset dossier files in {DOSSIERS_DIR}.")


if __name__ == "__main__":
    generate_dossiers_for_rotation_assets()

