"""
Dashboard Data Generator.
Exports SQLite states into a clean JSON structure suitable for the web dashboard.
"""

from datetime import datetime, timezone
import json
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


def _load_names_map() -> Dict[str, str]:
    try:
        if os.path.exists(NAMES_PATH):
            with open(NAMES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


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

        v1_val = round(float(r["v1"]), 4)
        m1_val = round(float(r["m1"]), 4)
        m2_val = round(float(r["m2"]), 4)
        v2_val = round(float(r["v2"]), 4)
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
                "fair_value": fund.fair_value,
                "mos_pct": fund.mos_pct,
                "moat": fund.moat,
                "roic_pct": fund.roic_pct,
                "z_score": fund.z_score,
                "upside_pct": fund.upside_pct,
                "thesis": fund.thesis,
            }
        elif "ts_fund_verdict" in r.keys() and r["ts_fund_verdict"]:
            fund_data = {
                "verdict": r["ts_fund_verdict"],
                "fair_value": r["ts_fair_value"],
                "mos_pct": r["ts_mos_pct"],
                "moat": r["ts_moat"] or "None",
                "roic_pct": None,
                "z_score": r["ts_z_score"],
                "upside_pct": None,
                "thesis": "",
            }

        items.append({
            "ticker": ticker,
            "name": name,
            "asset_class": r["asset_class"],
            "tv_symbol": r["tv_symbol"],
            "timeframe": r["timeframe"],
            "state": state,
            "price": r["last_price"],
            "v1": v1_val,
            "m1": m1_val,
            "m2": m2_val,
            "v2": v2_val,
            "spread_pct": spread_pct,
            "s1": r["s1"] if "s1" in r.keys() and r["s1"] is not None else None,
            "s1_touches": r["s1_touches"] if "s1_touches" in r.keys() and r["s1_touches"] is not None else 0,
            "s1_dist_pct": r["s1_dist_pct"] if "s1_dist_pct" in r.keys() and r["s1_dist_pct"] is not None else None,
            "r1": r["r1"] if "r1" in r.keys() and r["r1"] is not None else None,
            "r1_touches": r["r1_touches"] if "r1_touches" in r.keys() and r["r1_touches"] is not None else 0,
            "r1_dist_pct": r["r1_dist_pct"] if "r1_dist_pct" in r.keys() and r["r1_dist_pct"] is not None else None,
            "context_flag": r["context_flag"] if "context_flag" in r.keys() and r["context_flag"] is not None else "IN_VALUE_RANGE",
            "context_desc": r["context_desc"] if "context_desc" in r.keys() and r["context_desc"] is not None else "",
            "fundamental": fund_data,
            "trade_suggestion": {
                "action": r["ts_action"] if "ts_action" in r.keys() and r["ts_action"] is not None else "WAIT",
                "direction": r["ts_direction"] if "ts_direction" in r.keys() and r["ts_direction"] is not None else "NEUTRAL",
                "setup_type": r["ts_setup_type"] if "ts_setup_type" in r.keys() and r["ts_setup_type"] is not None else "WAIT_FOR_SETUP",
                "entry": r["ts_entry"] if "ts_entry" in r.keys() and r["ts_entry"] is not None else None,
                "sl": r["ts_sl"] if "ts_sl" in r.keys() and r["ts_sl"] is not None else None,
                "tp1": r["ts_tp1"] if "ts_tp1" in r.keys() and r["ts_tp1"] is not None else None,
                "tp2": r["ts_tp2"] if "ts_tp2" in r.keys() and r["ts_tp2"] is not None else None,
                "rr": r["ts_rr"] if "ts_rr" in r.keys() and r["ts_rr"] is not None else None,
                "score": r["ts_score"] if "ts_score" in r.keys() and r["ts_score"] is not None else 0,
                "tier": r["ts_tier"] if "ts_tier" in r.keys() and r["ts_tier"] is not None else "NONE",
                "reason_bg": r["ts_reason_bg"] if "ts_reason_bg" in r.keys() and r["ts_reason_bg"] is not None else "",
                "reason_en": r["ts_reason_en"] if "ts_reason_en" in r.keys() and r["ts_reason_en"] is not None else "",
                "fund_verdict": r["ts_fund_verdict"] if "ts_fund_verdict" in r.keys() and r["ts_fund_verdict"] else (fund.verdict if fund else None),
                "fair_value": r["ts_fair_value"] if "ts_fair_value" in r.keys() and r["ts_fair_value"] else (fund.fair_value if fund else None),
                "moat": r["ts_moat"] if "ts_moat" in r.keys() and r["ts_moat"] else (fund.moat if fund else "None"),
                "quantamental_tag": r["ts_quantamental_tag"] if "ts_quantamental_tag" in r.keys() and r["ts_quantamental_tag"] else None,
            } if ("ts_action" in r.keys() and r["ts_action"] is not None) else None,
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
        json.dump(payload, f, indent=2)

    return payload
