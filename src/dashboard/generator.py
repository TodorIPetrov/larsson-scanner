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

        items.append({
            "ticker": ticker,
            "name": name,
            "asset_class": r["asset_class"],
            "tv_symbol": r["tv_symbol"],
            "timeframe": r["timeframe"],
            "state": state,
            "price": r["last_price"],
            "v1": round(r["v1"], 4),
            "m1": round(r["m1"], 4),
            "m2": round(r["m2"], 4),
            "v2": round(r["v2"], 4),
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
