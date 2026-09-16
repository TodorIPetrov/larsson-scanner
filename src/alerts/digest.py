"""
Daily Market Digest Generator & Dispatcher for Larsson Line Scanner.
Produces a synthesized daily report featuring market balance %, top bullish/bearish
trends ranked by Ribbon Spread %, and recent 24h state transitions.
Includes duplicate prevention between local scheduler and GitHub Actions.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
import os
from typing import Dict, List, Optional

from src.alerts.formatter import format_daily_digest
from src.alerts.telegram import TelegramNotifier
from src.storage.database import Database

logger = logging.getLogger(__name__)

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


def generate_digest_data(db: Database) -> Dict:
    """
    Extracts and computes statistics, top momentum trends, and recent changes
    from the database for the daily digest.
    """
    names_map = _load_names_map()
    rows = db.get_all_states()

    if not rows:
        return {
            "total": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "top_bullish": [],
            "top_bearish": [],
            "recent_changes": [],
            "message": "📊 Няма записани активи в базата данни.",
        }

    total = len(rows)
    gold_count = 0
    blue_count = 0
    neutral_count = 0

    all_items = []
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    state_change_candidates = []

    for r in rows:
        st = r["current_state"]
        if st == "GOLD":
            gold_count += 1
        elif st == "BLUE":
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
        v2_val = round(float(r["v2"]), 4)
        spread_pct = round(((v1_val - v2_val) / v2_val) * 100, 2) if v2_val > 0 else 0.0

        item = {
            "ticker": ticker,
            "name": name,
            "asset_class": r["asset_class"],
            "tv_symbol": r["tv_symbol"],
            "timeframe": r["timeframe"],
            "state": st,
            "price": r["last_price"],
            "spread_pct": spread_pct,
            "last_state_change": r["last_state_change"],
        }
        all_items.append(item)

        if r["last_state_change"] and r["last_state_change"] >= cutoff_24h:
            state_change_candidates.append(item)

    # Filter top bullish: Prefer 1D timeframe first, then highest spread_pct
    gold_items = [i for i in all_items if i["state"] == "GOLD"]
    gold_1d = [i for i in gold_items if i["timeframe"] == "1D"]
    if len(gold_1d) >= 4:
        top_bullish = sorted(gold_1d, key=lambda x: x["spread_pct"], reverse=True)[:4]
    else:
        top_bullish = sorted(gold_items, key=lambda x: x["spread_pct"], reverse=True)[:4]

    # Filter top bearish: lowest spread_pct (most negative)
    blue_items = [i for i in all_items if i["state"] == "BLUE"]
    blue_1d = [i for i in blue_items if i["timeframe"] == "1D"]
    if len(blue_1d) >= 4:
        top_bearish = sorted(blue_1d, key=lambda x: x["spread_pct"])[:4]
    else:
        top_bearish = sorted(blue_items, key=lambda x: x["spread_pct"])[:4]

    # Recent changes: from alert_logs first, fallback to symbol_states cutoff
    recent_alerts = db.get_recent_alerts(hours=24)
    recent_changes = []
    if recent_alerts:
        for a in recent_alerts:
            recent_changes.append({
                "ticker": a["ticker"],
                "timeframe": a["timeframe"],
                "old_state": a["old_state"],
                "new_state": a["new_state"],
                "price": a["price"],
                "tv_symbol": a["tv_symbol"],
            })
    else:
        # Fallback to symbol_states that changed in last 24h
        for c in state_change_candidates[:8]:
            recent_changes.append({
                "ticker": c["ticker"],
                "timeframe": c["timeframe"],
                "old_state": "⚪ NEUTRAL",
                "new_state": c["state"],
                "price": c["price"],
                "tv_symbol": c["tv_symbol"],
            })

    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    formatted_msg = format_daily_digest(
        total=total,
        gold_count=gold_count,
        blue_count=blue_count,
        neutral_count=neutral_count,
        top_bullish=top_bullish,
        top_bearish=top_bearish,
        recent_changes=recent_changes,
        date_str=date_str,
    )

    return {
        "total": total,
        "gold_count": gold_count,
        "blue_count": blue_count,
        "neutral_count": neutral_count,
        "top_bullish": top_bullish,
        "top_bearish": top_bearish,
        "recent_changes": recent_changes,
        "message": formatted_msg,
    }


def send_daily_digest(
    notifier: TelegramNotifier,
    db: Database,
    force: bool = False,
) -> bool:
    """
    Sends the daily digest to Telegram.
    Checks and persists 'last_daily_digest_date' in system_metadata to avoid
    duplicate messages when both local daemon and GitHub Actions run.
    """
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not force:
        last_sent = db.get_metadata("last_daily_digest_date")
        if last_sent == today_key:
            logger.info(f"Daily digest already sent for {today_key}. Skipping duplicate.")
            return False

    digest_info = generate_digest_data(db)
    msg = digest_info["message"]

    logger.info("Sending Daily Market Digest to Telegram...")
    ok = notifier.send_raw_message(msg)
    if ok:
        db.set_metadata("last_daily_digest_date", today_key)
        logger.info(f"Daily digest successfully dispatched and logged for {today_key}.")
        return True
    else:
        logger.error(f"Failed to dispatch daily digest for {today_key}.")
        return False
