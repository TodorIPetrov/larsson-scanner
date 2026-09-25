"""
Performance Attribution Engine for Larsson Scanner.
Analyses completed trades from the paper/real trade log and explains WHY
trades worked or failed across multiple dimensions:
  - Signal / setup type
  - Asset class
  - Quality tier (A+/A/B/C)
  - Day-of-week entry bias
  - Leverage tier
Produces human-readable insights and best/worst signal identification.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Asset-class helpers
# ──────────────────────────────────────────────────────────────────────────────

_CRYPTO_SUFFIXES = ("USDT", "USDC", "BTC", "ETH")

def _infer_asset_class(ticker: str, stored_class: Optional[str] = None) -> str:
    """Derive asset class from stored value or ticker naming convention."""
    if stored_class and stored_class not in ("", "unknown"):
        return stored_class
    up = ticker.upper()
    if any(up.endswith(sfx) for sfx in _CRYPTO_SUFFIXES):
        return "Crypto"
    return "US Equities"


def _leverage_bucket(leverage: Any) -> str:
    try:
        lev = int(leverage)
    except (TypeError, ValueError):
        lev = 1
    if lev <= 1:
        return "1x"
    elif lev == 2:
        return "2x"
    else:
        return "3x"


def _day_of_week(date_str: Optional[str]) -> Optional[int]:
    """Return Python weekday (Monday=0) from an ISO-format date string."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.weekday()
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Core grouping helper
# ──────────────────────────────────────────────────────────────────────────────

def _empty_bucket() -> dict:
    return {"trades": 0, "wins": 0, "losses": 0, "pnl_usd_list": [], "rr_list": [], "hold_days_list": []}


def _bucket_stats(bucket: dict) -> dict:
    trades = bucket["trades"]
    wins = bucket["wins"]
    pnl_list = bucket["pnl_usd_list"]
    rr_list = [r for r in bucket["rr_list"] if r is not None]
    hold_list = [h for h in bucket["hold_days_list"] if h is not None]

    win_rate = round(wins / trades * 100.0, 1) if trades > 0 else 0.0
    total_pnl = sum(pnl_list)
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    avg_rr = round(sum(rr_list) / len(rr_list), 2) if rr_list else None
    avg_hold = round(sum(hold_list) / len(hold_list), 1) if hold_list else None
    avg_pnl_usd = round(total_pnl / trades, 2) if trades > 0 else 0.0

    return {
        "trades": trades,
        "wins": wins,
        "losses": bucket["losses"],
        "win_rate": win_rate,
        "total_pnl_usd": round(total_pnl, 2),
        "avg_pnl_usd": avg_pnl_usd,
        "profit_factor": round(min(profit_factor, 999.0), 2) if profit_factor != float("inf") else 999.0,
        "avg_rr": avg_rr,
        "avg_hold_days": avg_hold,
    }


def _update_bucket(bucket: dict, pnl_usd: float, rr: Optional[float], hold_days: Optional[int]) -> None:
    bucket["trades"] += 1
    if pnl_usd > 0:
        bucket["wins"] += 1
    else:
        bucket["losses"] += 1
    bucket["pnl_usd_list"].append(pnl_usd)
    bucket["rr_list"].append(rr)
    bucket["hold_days_list"].append(hold_days)


# ──────────────────────────────────────────────────────────────────────────────
# Main attribution function
# ──────────────────────────────────────────────────────────────────────────────

def compute_attribution(trade_log: List[dict]) -> dict:
    """
    Analyse completed trades and compute multi-dimensional attribution metrics.

    Each entry in *trade_log* is expected to have at minimum:
        ticker, pnl_usd, entry_date (ISO str), exit_date (ISO str)
    Optional enrichment fields (used when present):
        signal_type / setup_type, asset_class, quality_tier / tier,
        leverage, rr_ratio / rr

    Returns a dict matching the specification in the task docstring.
    """
    # Only consider closed/completed trades with a PnL value
    closed = [
        t for t in trade_log
        if t.get("pnl_usd") is not None and t.get("exit_date")
    ]

    if not closed:
        return _empty_attribution()

    # ── Dimension buckets ────────────────────────────────────────────────────
    by_signal: Dict[str, dict] = defaultdict(_empty_bucket)
    by_asset: Dict[str, dict] = defaultdict(_empty_bucket)
    by_tier: Dict[str, dict] = defaultdict(_empty_bucket)
    by_dow: Dict[int, dict] = defaultdict(_empty_bucket)
    by_leverage: Dict[str, dict] = defaultdict(_empty_bucket)

    for trade in closed:
        pnl_usd = float(trade.get("pnl_usd", 0.0))
        ticker = str(trade.get("ticker", "UNKNOWN"))
        entry_date = trade.get("entry_date") or trade.get("opened_at")
        exit_date = trade.get("exit_date") or trade.get("closed_at")
        rr = trade.get("rr_ratio") or trade.get("rr")
        if rr is not None:
            try:
                rr = float(rr)
            except (TypeError, ValueError):
                rr = None

        # Hold duration in calendar days
        hold_days: Optional[int] = None
        if entry_date and exit_date:
            try:
                dt_in = datetime.fromisoformat(str(entry_date).replace("Z", "+00:00"))
                dt_out = datetime.fromisoformat(str(exit_date).replace("Z", "+00:00"))
                hold_days = max(0, (dt_out - dt_in).days)
            except Exception:
                pass

        # Signal / setup type
        signal = (
            trade.get("signal_type")
            or trade.get("setup_type")
            or trade.get("exit_reason")
            or "UNKNOWN"
        )
        signal = str(signal).upper()

        # Asset class
        stored_class = trade.get("asset_class") or trade.get("portfolio_type")
        asset_class = _infer_asset_class(ticker, stored_class if stored_class not in ("PAPER", "REAL") else None)

        # Quality tier
        tier = str(trade.get("quality_tier") or trade.get("tier") or "UNKNOWN").upper()

        # Leverage
        lev_bucket = _leverage_bucket(trade.get("leverage") or trade.get("leverage_selected") or 1)

        # Day-of-week of entry
        dow = _day_of_week(entry_date)

        _update_bucket(by_signal[signal], pnl_usd, rr, hold_days)
        _update_bucket(by_asset[asset_class], pnl_usd, rr, hold_days)
        _update_bucket(by_tier[tier], pnl_usd, rr, hold_days)
        _update_bucket(by_leverage[lev_bucket], pnl_usd, rr, hold_days)
        if dow is not None:
            _update_bucket(by_dow[dow], pnl_usd, rr, hold_days)

    # ── Flatten to stats ─────────────────────────────────────────────────────
    signal_stats = {k: _bucket_stats(v) for k, v in by_signal.items()}
    asset_stats = {k: _bucket_stats(v) for k, v in by_asset.items()}
    tier_stats = {k: _bucket_stats(v) for k, v in by_tier.items()}
    dow_stats = {k: _bucket_stats(v) for k, v in by_dow.items()}
    lev_stats = {k: _bucket_stats(v) for k, v in by_leverage.items()}

    # ── Best / Worst signal (by risk-adjusted return = win_rate * profit_factor) ─
    def _risk_adj(stats: dict) -> float:
        if stats["trades"] < 2:
            return 0.0
        return stats["win_rate"] * min(stats["profit_factor"], 10.0)

    best_signal: Optional[str] = None
    worst_signal: Optional[str] = None
    if signal_stats:
        best_signal = max(signal_stats, key=lambda s: _risk_adj(signal_stats[s]))
        worst_signal = min(signal_stats, key=lambda s: _risk_adj(signal_stats[s]))

    # ── Human-readable insights ───────────────────────────────────────────────
    insights: List[str] = []
    total_trades = len(closed)
    total_wins = sum(1 for t in closed if float(t.get("pnl_usd", 0)) > 0)
    overall_wr = round(total_wins / total_trades * 100.0, 1) if total_trades > 0 else 0.0

    insights.append(f"Overall win rate across {total_trades} completed trades: {overall_wr}%.")

    if best_signal and best_signal != "UNKNOWN":
        bs = signal_stats[best_signal]
        insights.append(
            f"Best performing signal: {best_signal} "
            f"({bs['trades']} trades, {bs['win_rate']}% win rate, PF {bs['profit_factor']})."
        )

    if worst_signal and worst_signal != best_signal and worst_signal != "UNKNOWN":
        ws = signal_stats[worst_signal]
        insights.append(
            f"Worst performing signal: {worst_signal} "
            f"({ws['trades']} trades, {ws['win_rate']}% win rate, PF {ws['profit_factor']})."
        )

    # Asset class with highest profit factor
    if asset_stats:
        best_class = max(asset_stats, key=lambda k: asset_stats[k]["profit_factor"])
        bc = asset_stats[best_class]
        insights.append(
            f"{best_class} trades show highest profit factor: {bc['profit_factor']} "
            f"({bc['trades']} trades, {bc['win_rate']}% win rate)."
        )

    # Leverage insight
    lev_3x = lev_stats.get("3x")
    if lev_3x and lev_3x["trades"] >= 2:
        if lev_3x["win_rate"] < 40.0:
            insights.append(
                f"3x leverage trades are underperforming: {lev_3x['win_rate']}% win rate "
                f"over {lev_3x['trades']} trades – consider reducing leverage."
            )
        else:
            insights.append(
                f"3x leverage trades performing well: {lev_3x['win_rate']}% win rate "
                f"over {lev_3x['trades']} trades."
            )

    # Day-of-week best entry day
    if dow_stats and len(dow_stats) >= 3:
        _day_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
        best_dow = max(dow_stats, key=lambda d: dow_stats[d]["win_rate"])
        bd = dow_stats[best_dow]
        if bd["trades"] >= 2:
            insights.append(
                f"Best entry day by win rate: {_day_names.get(best_dow, str(best_dow))} "
                f"({bd['win_rate']}% over {bd['trades']} trades)."
            )

    # Tier insight
    a_plus = tier_stats.get("A+")
    if a_plus and a_plus["trades"] >= 2:
        insights.append(
            f"Tier A+ trades: {a_plus['win_rate']}% win rate over {a_plus['trades']} trades "
            f"(avg R:R {a_plus['avg_rr']})."
        )

    return {
        "by_signal_type": signal_stats,
        "by_asset_class": asset_stats,
        "by_quality_tier": tier_stats,
        "by_day_of_week": {str(k): v for k, v in dow_stats.items()},
        "by_leverage": lev_stats,
        "best_signal": best_signal,
        "worst_signal": worst_signal,
        "insights": insights,
        "total_trades_analyzed": total_trades,
    }


def _empty_attribution() -> dict:
    """Returns an empty attribution structure for when no trades exist."""
    return {
        "by_signal_type": {},
        "by_asset_class": {},
        "by_quality_tier": {},
        "by_day_of_week": {},
        "by_leverage": {},
        "best_signal": None,
        "worst_signal": None,
        "insights": ["No completed trades available for attribution analysis."],
        "total_trades_analyzed": 0,
    }


def format_attribution_telegram(attribution: dict, top_n_insights: int = 3) -> str:
    """
    Formats a compact Telegram HTML message showing top attribution insights.
    """
    total = attribution.get("total_trades_analyzed", 0)
    best = attribution.get("best_signal")
    worst = attribution.get("worst_signal")
    insights = attribution.get("insights", [])
    by_signal = attribution.get("by_signal_type", {})
    by_class = attribution.get("by_asset_class", {})

    if total == 0:
        return "📊 <b>Анализ на Изпълнението</b>\n\n<i>Няма приключили сделки за анализ.</i>"

    lines = [
        f"📊 <b>Анализ на Изпълнението ({total} сделки)</b>",
        "",
    ]

    if best and best in by_signal:
        bs = by_signal[best]
        lines.append(
            f"🏆 <b>Най-добър сигнал:</b> <code>{best}</code> "
            f"({bs['trades']} сд. | {bs['win_rate']}% WR | PF {bs['profit_factor']})"
        )

    if worst and worst != best and worst in by_signal:
        ws = by_signal[worst]
        lines.append(
            f"⚠️ <b>Най-слаб сигнал:</b> <code>{worst}</code> "
            f"({ws['trades']} сд. | {ws['win_rate']}% WR | PF {ws['profit_factor']})"
        )

    if by_class:
        lines.append("\n<b>По клас актив:</b>")
        for cls, stats in sorted(by_class.items(), key=lambda x: -x[1]["win_rate"]):
            lines.append(
                f"  • {cls}: {stats['trades']} сд. | {stats['win_rate']}% WR | PF {stats['profit_factor']}"
            )

    if insights:
        lines.append("\n<b>Топ Изводи:</b>")
        for insight in insights[:top_n_insights]:
            lines.append(f"  💡 <i>{insight}</i>")

    return "\n".join(lines)
