"""
Daily Top 15 Momentum Portfolio Generator.
Scans all 797 assets and outputs:
1. Current Top 15 Holdings (actively in GOLD with highest Point-in-Time Momentum & Sharpe).
2. New rotation signals for today.
3. Top 5 Quantamental Value Accumulator setups (undervalued in BLUE/NEUTRAL with Close > v1).
4. Exports actionable research report to research/LIVE_TOP15_ROTATION_PORTFOLIO.md.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.backtest.data_manager import BacktestDataManager
from src.engine.quantamental import get_fundamental_profile
from scripts.run_master_universe_optimization import fast_compute_smma, evaluate_larsson_states

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LivePortfolioGenerator")


def generate_live_portfolio_report():
    logger.info("Generating Live Top 15 Momentum Portfolio & Actionable Trade Sheet...")
    dm = BacktestDataManager()

    profiles_file = os.path.join(BASE_DIR, "data", "asset_optimal_profiles.json")
    with open(profiles_file, "r", encoding="utf-8") as f:
        optimal_profiles = json.load(f)

    # Pass 1: Compute 60-day momentum across all available cache files for Universe RS Rating (1-99)
    all_mom_60 = {}
    cached_dfs = {}
    for sym in optimal_profiles.keys():
        clean_sym = sym.replace("=", "_").replace("^", "_").replace(":", "_")
        cache_file = os.path.join(dm.cache_dir, f"{clean_sym}_1D.csv")
        if not os.path.exists(cache_file):
            continue
        try:
            df = pd.read_csv(cache_file)
            if len(df) >= 60:
                cached_dfs[sym] = df
                closes = df["close"].to_numpy(dtype=np.float64)
                m60 = ((closes[-1] - closes[-60]) / closes[-60]) * 100.0 if closes[-60] > 0 else 0.0
                all_mom_60[sym] = m60
        except Exception:
            pass

    mom_series = pd.Series(all_mom_60)
    rs_ratings = (mom_series.rank(pct=True) * 98 + 1).fillna(50).astype(int).to_dict()
    logger.info(f"Calculated Universe RS Ratings (1-99) across {len(rs_ratings)} assets.")

    # Pass 2: Scan assets for GOLD trend and Quantamental opportunities
    candidates_gold = []
    quant_candidates = []
    chop_avoid_count = 0

    state_names = {1: "GOLD", 0: "NEUTRAL", -1: "BLUE"}

    for sym, prof in optimal_profiles.items():
        if sym not in cached_dfs:
            continue

        try:
            df = cached_dfs[sym]
            if len(df) < 120:
                continue

            highs = df["high"].to_numpy(dtype=np.float64)
            lows = df["low"].to_numpy(dtype=np.float64)
            closes = df["close"].to_numpy(dtype=np.float64)
            dates = df["date"].astype(str).tolist()

            hl2 = (highs + lows) / 2.0
            v1 = fast_compute_smma(hl2, 15)
            m1 = fast_compute_smma(hl2, 19)
            m2 = fast_compute_smma(hl2, 25)
            v2 = fast_compute_smma(hl2, 29)
            states = evaluate_larsson_states(v1, m1, m2, v2)

            curr_state = states[-1]
            prev_state = states[-2]
            curr_price = float(closes[-1])
            curr_v1 = float(v1[-1])
            curr_v2 = float(v2[-1])
            last_date = dates[-1]

            tier = prof.get("empirical_tier", "B")
            suitability = prof.get("larsson_suitability", "MODERATE_TREND")
            strategy = prof.get("recommended_strategy", "CLASSIC_BLUE_EXIT")
            sharpe = prof.get("sharpe_ratio", 0.0)
            cagr = prof.get("cagr_pct", 0.0)
            max_dd = prof.get("max_drawdown_pct", 0.0)
            asset_class = prof.get("asset_class", "us_stocks")
            rs_score = rs_ratings.get(sym, 50)

            if suitability == "AVOID_CHOP":
                chop_avoid_count += 1

            # 1. Check for GOLD Trend Candidates (S-Tier / A-Tier only)
            if curr_state == 1 and tier in ["S", "A"] and prof.get("walk_forward_stable", True):
                # 60-day momentum
                mom_60 = all_mom_60.get(sym, 0.0)
                rank_score = (sharpe * 50.0) + (rs_score * 0.5) + (mom_60 * 0.5)

                spread_pct = ((curr_v1 - curr_v2) / curr_v2) * 100.0 if curr_v2 > 0 else 0.0
                fresh_flip = (prev_state != 1)

                candidates_gold.append({
                    "symbol": sym,
                    "asset_class": asset_class,
                    "tier": tier,
                    "rs_rating": rs_score,
                    "strategy": strategy,
                    "exit_on_neutral": prof.get("exit_on_neutral", False),
                    "current_price": curr_price,
                    "v2_support": curr_v2,
                    "spread_pct": round(spread_pct, 1),
                    "momentum_60d": round(mom_60, 1),
                    "historical_sharpe": round(sharpe, 2),
                    "historical_cagr": round(cagr, 1),
                    "historical_dd": round(max_dd, 1),
                    "rank_score": round(rank_score, 1),
                    "fresh_flip": fresh_flip,
                    "last_date": last_date,
                })

            # 2. Check for Quantamental Accumulator Setups (Undervalued + Early Base in BLUE/NEUTRAL)
            fund_p = get_fundamental_profile(sym)
            if fund_p and fund_p.is_bullish:
                if curr_state in [-1, 0] and curr_price > curr_v1:
                    fv = getattr(fund_p, "fair_value", None)
                    mos = getattr(fund_p, "mos_pct", None)
                    quant_candidates.append({
                        "symbol": sym,
                        "asset_class": asset_class,
                        "current_price": curr_price,
                        "state": state_names[curr_state],
                        "fair_value": fv,
                        "mos_pct": mos,
                        "rs_rating": rs_score,
                        "verdict": getattr(fund_p, "verdict", "BUY"),
                        "last_date": last_date,
                    })
        except Exception:
            pass

    # Sort GOLD by highest combined Momentum & Sharpe rank
    candidates_gold.sort(key=lambda x: x["rank_score"], reverse=True)
    top15 = candidates_gold[:15]
    bench_reserve = candidates_gold[15:25]

    # Generate Markdown Report
    report_lines = [
        "# 🚀 Дневен Активен Портфейл: Топ 15 Моментум Ротация & Quantamental Сигнали",
        f"*Генериран на: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Базиран на {len(cached_dfs)} кеширани актива и 27,914 емпирични прехода*",
        "",
        "> [!IMPORTANT]",
        "> **Институционален принцип на портфейла:**",
        "> Капиталът се разпределя по равно (по ~6.67% на позиция) в **15-те най-силни S-Tier / A-Tier актива в състояние GOLD** с висок **RS Rating (1–99)**.",
        "> Всяка позиция се управлява стриктно по нейното **индивидуално доказано ДНК за изход** (Fast Exit при Neutral или Classic Hold до Blue).",
        "",
        "---",
        "",
        "## 1. 🏆 Топ 15 Активни Позиции за Портфейла към Днешна Дата",
        "",
        "| № | Тикер | Сектор | Tier | RS (1–99) | Препоръчана стратегия | Цена | Ниво за изход | 60д Momentum | Backtest CAGR | Backtest Sharpe | Статус |",
        "| :-: | :--- | :--- | :-: | :-: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]

    for idx, c in enumerate(top15, 1):
        exit_rule = "💰 Прибери при NEUTRAL" if c["exit_on_neutral"] else "🛡️ Дръж до BLUE"
        status = "✨ ПРЕСЕН ПРОБИВ" if c["fresh_flip"] else "🟢 В ТРЕНД (Hold)"
        report_lines.append(
            f"| {idx} | **{c['symbol']}** | {c['asset_class']} | `{c['tier']}` | **{c['rs_rating']}** | {c['strategy']} | **${c['current_price']:,.2f}** | {exit_rule} | +{c['momentum_60d']}% | +{c['historical_cagr']}% | {c['historical_sharpe']} | {status} |"
        )

    report_lines.extend([
        "",
        "---",
        "",
        "## 2. 🪑 Скамейка: Топ 10 Резервни S-Tier Кандидати (Готови за ротация)",
        "*Тези активи са в силен GOLD трент с висок RS Rating и са първи на опашката, когато текуща позиция от Топ 15 светне за изход:*",
        "",
        "| № | Тикер | Сектор | Tier | RS (1–99) | Стратегия | 60д Momentum | Sharpe | CAGR |",
        "| :-: | :--- | :--- | :-: | :-: | :--- | :---: | :---: | :---: |",
    ])

    for idx, c in enumerate(bench_reserve, 1):
        report_lines.append(
            f"| {idx} | **{c['symbol']}** | {c['asset_class']} | `{c['tier']}` | **{c['rs_rating']}** | {c['strategy']} | +{c['momentum_60d']}% | {c['historical_sharpe']} | +{c['historical_cagr']}% |"
        )

    report_lines.extend([
        "",
        "---",
        "",
        "## 3. 💎 Топ Quantamental Value Входове (Ранна фаза: 50% Транш на спад)",
        "*Фундаментално подценени активи в синя/сребърна лента, които вече са пробили v1 нагоре (начало на стабилизация):*",
        "",
        "| Тикер | Сектор | RS (1–99) | Текуща цена | Fair Value (DCF) | Margin of Safety | Фундаментална оценка | Лента | Действие |",
        "| :--- | :--- | :-: | :---: | :---: | :---: | :--- | :---: | :--- |",
    ])

    if quant_candidates:
        for q in quant_candidates[:8]:
            fv_str = f"${q['fair_value']:,.2f}" if q['fair_value'] else "N/A"
            mos_str = f"+{q['mos_pct']:.0f}%" if q['mos_pct'] else "N/A"
            report_lines.append(
                f"| **{q['symbol']}** | {q['asset_class']} | {q['rs_rating']} | ${q['current_price']:,.2f} | {fv_str} | **{mos_str}** | {q['verdict']} | `{q['state']}` | 📥 **Купи 50% Транш 1** |"
            )
    else:
        report_lines.append("| - | - | Всички основни подценени лидери вече са в състояние GOLD | - | - | - | - | - | - |")

    report_lines.extend([
        "",
        "---",
        "",
        f"## 4. 🛡️ Chop Blocker: {chop_avoid_count} Рейнджови актива са блокирани за тренд търговия",
        "Скенерът автоматично игнорира фалшиви пробиви при тези C-Tier активи, спестявайки излишен риск и такси.",
    ])

    out_md = os.path.join(BASE_DIR, "research", "LIVE_TOP15_ROTATION_PORTFOLIO.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    logger.info(f"Generated Live Portfolio Report at {out_md}")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        print("\n" + "\n".join(report_lines[:35]))
        print("\n... (Пълният списък е запазен в research/LIVE_TOP15_ROTATION_PORTFOLIO.md)\n")
    except Exception:
        pass


if __name__ == "__main__":
    generate_live_portfolio_report()
