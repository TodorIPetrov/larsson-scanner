"""
Dashboard Data Generator.
Exports SQLite states into a clean JSON structure suitable for the web dashboard.
"""

from datetime import datetime, timezone
import json
import math
import os
from typing import Dict, List, Optional

from src.storage.database import Database

DEFAULT_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "dashboard",
    "data.json",
)


NAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "names_mapping.json",
)


def _clean_float(val: Optional[float]) -> Optional[float]:
    """Ensures floats are JSON compliant (converts NaN/Inf to None)."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _load_names_map() -> Dict[str, str]:
    try:
        if os.path.exists(NAMES_PATH):
            with open(NAMES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _row_val(row, key, default=None):
    if key in row.keys() and row[key] is not None:
        return row[key]
    return default


def export_dashboard_data(
    db: Optional[Database] = None,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> Dict:
    """
    Reads all states from the database and writes a JSON file for the static dashboard.
    """
    if db is None:
        db = Database()

    names_map = _load_names_map()
    rows = db.get_all_states()

    items = []
    gold_count = 0
    blue_count = 0
    neutral_count = 0

    for r in rows:
        state = r["current_state"]
        if state == "GOLD":
            gold_count += 1
        elif state == "BLUE":
            blue_count += 1
        else:
            neutral_count += 1

        ticker = r["ticker"]
        name = names_map.get(ticker)
        if not name:
            if ticker.endswith("USDT"):
                name = f"{ticker[:-4]} / USDT"
            else:
                name = ticker

        v1_clean = _clean_float(r["v1"])
        m1_clean = _clean_float(r["m1"])
        m2_clean = _clean_float(r["m2"])
        v2_clean = _clean_float(r["v2"])

        v1_val = round(v1_clean, 4) if v1_clean is not None else 0.0
        m1_val = round(m1_clean, 4) if m1_clean is not None else 0.0
        m2_val = round(m2_clean, 4) if m2_clean is not None else 0.0
        v2_val = round(v2_clean, 4) if v2_clean is not None else 0.0
        spread_pct = round(((v1_val - v2_val) / v2_val) * 100, 2) if v2_val > 0 else 0.0

        # Fundamental Profile lookup
        try:
            from src.engine.quantamental import get_fundamental_profile
            fund = get_fundamental_profile(ticker)
        except Exception:
            fund = None

        fund_data = None
        if fund:
            fund_data = {
                "verdict": fund.verdict,
                "fair_value": _clean_float(fund.fair_value),
                "mos_pct": _clean_float(fund.mos_pct),
                "moat": fund.moat,
                "roic_pct": _clean_float(fund.roic_pct),
                "z_score": _clean_float(fund.z_score),
                "upside_pct": _clean_float(fund.upside_pct),
                "thesis": fund.thesis,
            }
        elif _row_val(r, "ts_fund_verdict"):
            fund_data = {
                "verdict": _row_val(r, "ts_fund_verdict"),
                "fair_value": _clean_float(_row_val(r, "ts_fair_value")),
                "mos_pct": _clean_float(_row_val(r, "ts_mos_pct")),
                "moat": _row_val(r, "ts_moat") or "None",
                "roic_pct": None,
                "z_score": _clean_float(_row_val(r, "ts_z_score")),
                "upside_pct": None,
                "thesis": "",
            }

        # ---------------------------------------------------------------------
        # 1. TECHNICAL ANALYSIS BLOCK (Larsson Ribbon & S/R Structure)
        # ---------------------------------------------------------------------
        ts_action = _row_val(r, "ts_action", "WAIT")
        ts_setup = _row_val(r, "ts_setup_type", "WAIT_FOR_SETUP")
        tech_act = _row_val(r, "ts_tech_action")
        tech_lbl = _row_val(r, "ts_tech_label_bg")
        tech_the = _row_val(r, "ts_tech_thesis_bg")

        if not tech_act:
            if state == "GOLD":
                if ts_action == "SPOT_BUY":
                    tech_act = "BUY"
                    if "PULLBACK" in ts_setup:
                        tech_lbl = "🟢 BUY (Pullback S1)"
                        tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с тест на S1 подкрепа."
                    elif "BREAKOUT" in ts_setup:
                        tech_lbl = "🟢 BUY (Пробив / Momentum)"
                        tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с пробив в Price Discovery."
                    else:
                        tech_lbl = "🟢 BUY (Бича панделка)"
                        tech_the = f"Бичи тренд с възходяща подредба на лентата (spread {spread_pct:+.1f}%)."
                elif ts_action == "TAKE_PROFIT":
                    tech_act = "TAKE_PROFIT"
                    tech_lbl = "💰 TAKE PROFIT (Тест на R1)"
                    tech_the = "Бичи тренд, но цената тества макро съпротива R1. Прибери печалба."
                else:
                    tech_act = "HOLD"
                    tech_lbl = "🟡 HOLD (Възходящ тренд)"
                    tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%). Задръж текуща позиция."
            elif state == "BLUE":
                if ts_action == "SHORT_2X_OPTIONAL":
                    tech_act = "SHORT"
                    tech_lbl = "🔴 SHORT (Меча панделка)"
                    tech_the = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%)."
                else:
                    tech_act = "EXIT"
                    tech_lbl = "🔴 EXIT / STOP (Мечи тренд)"
                    tech_the = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%) или загуба на S1."
            else:
                tech_act = "WAIT"
                tech_lbl = "⏳ WAIT (Консолидация)"
                tech_the = "Панделката е преплетена без ясна посока. Изчакайте формиране на тренд."

        s1_val = _clean_float(_row_val(r, "s1"))
        s1_dist = _clean_float(_row_val(r, "s1_dist_pct"))
        r1_val = _clean_float(_row_val(r, "r1"))
        r1_dist = _clean_float(_row_val(r, "r1_dist_pct"))

        technical_block = {
            "state": state,
            "spread_pct": spread_pct,
            "action": tech_act,
            "label_bg": tech_lbl,
            "thesis": tech_the,
            "s1": s1_val,
            "s1_dist_pct": s1_dist,
            "s1_touches": _row_val(r, "s1_touches", 0),
            "r1": r1_val,
            "r1_dist_pct": r1_dist,
            "r1_touches": _row_val(r, "r1_touches", 0),
        }

        # ---------------------------------------------------------------------
        # 2. FUNDAMENTAL ANALYSIS BLOCK (DCF Valuation & Moat)
        # ---------------------------------------------------------------------
        fund_act = _row_val(r, "ts_fund_action")
        fund_lbl = _row_val(r, "ts_fund_label_bg")
        fund_the = _row_val(r, "ts_fund_thesis_bg")

        if not fund_act:
            if fund_data and fund_data.get("verdict"):
                v = fund_data["verdict"].upper()
                mos = fund_data.get("mos_pct")
                mos_txt = f"{mos:+.0f}%" if mos is not None else ""
                fv = fund_data.get("fair_value")
                fv_txt = f"${fv:,.2f}" if fv else "N/A"
                moat_txt = f", {fund_data['moat']} Moat" if fund_data.get("moat") and fund_data["moat"] != "None" else ""

                if "STRONG BUY" in v:
                    fund_act = "STRONG_BUY"
                    fund_lbl = f"🟢 СИЛНО ПОДЦЕНЕН ({mos_txt} MoS)"
                    fund_the = f"DCF Стойност: {fv_txt} (MoS: {mos_txt}{moat_txt}). {fund_data.get('thesis', '')}".strip()
                elif "BUY" in v or "OVERWEIGHT" in v:
                    fund_act = "BUY"
                    fund_lbl = f"🟢 ПОДЦЕНЕН ({mos_txt} MoS)"
                    fund_the = f"DCF Стойност: {fv_txt} (MoS: {mos_txt}{moat_txt}). {fund_data.get('thesis', '')}".strip()
                elif "HOLD" in v or "NEUTRAL" in v:
                    fund_act = "HOLD"
                    fund_lbl = "🟡 СПРАВЕДЛИВА ЦЕНА (Hold)"
                    fund_the = f"Търгува се около DCF цена {fv_txt}{moat_txt}.".strip()
                elif "REDUCE" in v or "AVOID" in v or "UNDERPERFORM" in v:
                    fund_act = "REDUCE"
                    fund_lbl = "🔴 НАДЦЕНЕН (Reduce)"
                    fund_the = f"Надценен спрямо DCF парични потоци ({fv_txt}).".strip()
                else:
                    fund_act = "HOLD"
                    fund_lbl = f"⚪ {fund_data['verdict']}"
                    fund_the = f"DCF: {fv_txt}{moat_txt}."
            else:
                fund_act = "SPECULATIVE_NA"
                fund_lbl = "⚪ МАКРО / СПЕКУЛАТИВЕН"
                fund_the = "Крипто/суровинен актив без корпоративен DCF модел. Движи се от ликвидност и моментум."

        if not fund_data:
            fund_data = {
                "verdict": "SPECULATIVE_NA",
                "fair_value": None,
                "mos_pct": None,
                "moat": "None",
                "roic_pct": None,
                "z_score": None,
                "upside_pct": None,
                "thesis": "",
            }

        fund_data["action"] = fund_act
        fund_data["label_bg"] = fund_lbl
        fund_data["thesis_bg"] = fund_the

        # ---------------------------------------------------------------------
        # 3. SYNTHESIS BLOCK (Quantamental Confluence)
        # ---------------------------------------------------------------------
        synth_badge = _row_val(r, "ts_synthesis_badge_bg")
        synth_label = _row_val(r, "ts_synthesis_label_bg")

        if not synth_badge:
            if ts_setup == "QUANTAMENTAL_ALPHA_BUY":
                synth_badge = "⭐ ALPHA BUY"
                synth_label = "Пълен консенсус (Бича техника + Подценен фундамент)"
            elif ts_setup == "VALUE_TRAP_WARNING":
                synth_badge = "⏳ VALUE TRAP RISK"
                synth_label = "Конфликт: Евтин фундамент, но меча техника (Не купувай преди обръщане!)"
            elif ts_setup in ["SPECULATIVE_MOMENTUM_BUY", "SPECULATIVE_PULLBACK_BUY"]:
                synth_badge = "⚠️ СПЕКУЛАТИВЕН ВХОД"
                synth_label = "Конфликт: Бича техника, но слаб/надценен фундамент (Търгувай само с къс SL)"
            elif ts_setup == "QUALITY_HOLD_ACCUMULATION":
                synth_badge = "🧱 QUALITY ACCUMULATE"
                synth_label = "Качествена компания за дългосрочно натрупване (DCA) на ключови нива"
            elif ts_action == "SPOT_BUY":
                synth_badge = "🟢 SPOT BUY"
                synth_label = "Чист технически вход в бичи тренд"
            elif ts_action == "TAKE_PROFIT":
                synth_badge = "💰 TAKE PROFIT"
                synth_label = "Прибиране на печалби при тест на съпротива"
            elif ts_action == "EXIT_PROTECT":
                synth_badge = "🛑 CAPITAL PROTECT"
                synth_label = "Защита на капитала при пробив на структурата"
            elif ts_action == "SHORT_2X_OPTIONAL":
                synth_badge = "🔴 SHORT 2X"
                synth_label = "Мечи трендов шорт с ограничен левъридж"
            else:
                synth_badge = "⏳ WAIT"
                synth_label = "Изчакване на качествена структура за вход"

        entry_val = _clean_float(_row_val(r, "ts_entry"))
        sl_val = _clean_float(_row_val(r, "ts_sl"))
        tp1_val = _clean_float(_row_val(r, "ts_tp1"))
        tp2_val = _clean_float(_row_val(r, "ts_tp2"))
        rr_val = _clean_float(_row_val(r, "ts_rr"))
        score_val = _row_val(r, "ts_score", 0)
        tier_val = _row_val(r, "ts_tier", "NONE")

        synthesis_block = {
            "setup_type": ts_setup,
            "action": ts_action,
            "badge_bg": synth_badge,
            "label_bg": synth_label,
            "entry": entry_val,
            "sl": sl_val,
            "tp1": tp1_val,
            "tp2": tp2_val,
            "rr": rr_val,
            "score": score_val,
            "tier": tier_val,
        }

        trade_suggestion_dict = {
            "action": ts_action,
            "direction": _row_val(r, "ts_direction", "NEUTRAL"),
            "setup_type": ts_setup,
            "entry": entry_val,
            "sl": sl_val,
            "tp1": tp1_val,
            "tp2": tp2_val,
            "rr": rr_val,
            "score": score_val,
            "tier": tier_val,
            "reason_bg": _row_val(r, "ts_reason_bg", ""),
            "reason_en": _row_val(r, "ts_reason_en", ""),
            "fund_verdict": fund_data.get("verdict"),
            "fair_value": fund_data.get("fair_value"),
            "moat": fund_data.get("moat"),
            "quantamental_tag": _row_val(r, "ts_quantamental_tag"),
            "tech_action": tech_act,
            "tech_label_bg": tech_lbl,
            "tech_thesis_bg": tech_the,
            "fund_action": fund_act,
            "fund_label_bg": fund_lbl,
            "fund_thesis_bg": fund_the,
            "synthesis_badge_bg": synth_badge,
            "synthesis_label_bg": synth_label,
        }

        items.append({
            "ticker": ticker,
            "name": name,
            "asset_class": r["asset_class"],
            "tv_symbol": r["tv_symbol"],
            "timeframe": r["timeframe"],
            "state": state,
            "price": _clean_float(r["last_price"]),
            "v1": v1_val,
            "m1": m1_val,
            "m2": m2_val,
            "v2": v2_val,
            "spread_pct": spread_pct,
            "s1": s1_val,
            "s1_touches": _row_val(r, "s1_touches", 0),
            "s1_dist_pct": s1_dist,
            "r1": r1_val,
            "r1_touches": _row_val(r, "r1_touches", 0),
            "r1_dist_pct": r1_dist,
            "context_flag": _row_val(r, "context_flag", "IN_VALUE_RANGE"),
            "context_desc": _row_val(r, "context_desc", ""),
            "technical": technical_block,
            "fundamental": fund_data,
            "synthesis": synthesis_block,
            "trade_suggestion": trade_suggestion_dict,
            "last_change": r["last_state_change"],
            "updated_at": r["updated_at"],
        })

    total = len(items)
    bullish_pct = round((gold_count / total * 100), 1) if total > 0 else 0.0
    bearish_pct = round((blue_count / total * 100), 1) if total > 0 else 0.0
    neutral_pct = round((neutral_count / total * 100), 1) if total > 0 else 0.0

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "gold": gold_count,
            "blue": blue_count,
            "neutral": neutral_count,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "neutral_pct": neutral_pct,
        },
        "symbols": items,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, allow_nan=False)

    return payload
