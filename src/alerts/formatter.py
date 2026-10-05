"""
Message formatting for Larsson Line Scanner alerts.
Generates clean HTML messages for Telegram with TradingView deep-links.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
from src.engine.smma import LarssonState

STATE_EMOJI = {
    LarssonState.GOLD: "🟡",
    LarssonState.BLUE: "🔵",
    LarssonState.NEUTRAL: "⚪",
}

STATE_TITLE = {
    LarssonState.GOLD: "Gold (Bullish)",
    LarssonState.BLUE: "Blue (Bearish)",
    LarssonState.NEUTRAL: "Neutral (Consolidation)",
}


import json
import os

NAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "names_mapping.json",
)
_NAMES_MAP_CACHE = None

def get_asset_name(ticker: str) -> str:
    """Returns human-readable name/description for an asset ticker."""
    global _NAMES_MAP_CACHE
    if not isinstance(ticker, str):
        return str(ticker) if ticker is not None else ""

    if _NAMES_MAP_CACHE is None:
        try:
            if os.path.exists(NAMES_PATH):
                with open(NAMES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _NAMES_MAP_CACHE = data if isinstance(data, dict) else {}
            else:
                _NAMES_MAP_CACHE = {}
        except Exception:
            _NAMES_MAP_CACHE = {}

    name = _NAMES_MAP_CACHE.get(ticker)
    if name:
        return name
    if len(ticker) > 4 and ticker.endswith("USDT"):
        return f"{ticker[:-4]} / USDT"
    if len(ticker) > 4 and ticker.endswith("USDC"):
        return f"{ticker[:-4]} / USDC"
    return ticker


def get_tradingview_link(tv_symbol: str, timeframe: str) -> str:
    """
    Generates a deep link to TradingView chart.
    Timeframe mapping:
      '1D' -> '1D'
      '4H' -> '240'
      '1W' -> '1W'
    """
    tf_code = "240" if timeframe == "4H" else timeframe
    return f"https://www.tradingview.com/chart/?symbol={tv_symbol}&interval={tf_code}"


def _format_price(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    if val >= 1000:
        return f"${val:,.2f}"
    elif val >= 1:
        return f"${val:.3f}"
    else:
        return f"${val:.6f}"


def format_single_alert(
    ticker: str,
    timeframe: str,
    old_state: LarssonState,
    new_state: LarssonState,
    price: float,
    tv_symbol: str,
    sr_data: Optional[dict] = None,
    asset_class: str = "crypto",
    trade_suggestion: Optional[Any] = None,
) -> str:
    """
    Formats a single state transition alert in Telegram HTML format,
    enriched with macro Support & Resistance (S/R) levels, context flags,
    and TradingView USD & /BTC ratio chart links.
    """
    new_emoji = STATE_EMOJI.get(new_state, "⚪")
    old_emoji = STATE_EMOJI.get(old_state, "⚪")
    new_text = STATE_TITLE.get(new_state, new_state.value)
    old_text = STATE_TITLE.get(old_state, old_state.value)

    tv_url = get_tradingview_link(tv_symbol, timeframe)
    price_str = _format_price(price)
    asset_name = get_asset_name(ticker)
    name_desc = f" ({asset_name})" if asset_name and asset_name != ticker else ""

    lines = [
        f"{new_emoji} <b>{ticker}{name_desc} | {timeframe}</b>",
        f"🔄 {old_emoji} {old_text} ➡️ <b>{new_emoji} {new_text}</b>",
        f"💵 Цена: <code>{price_str}</code>",
    ]

    # Support & Resistance Section
    if sr_data:
        r1 = sr_data.get("r1")
        r1_dist = sr_data.get("r1_dist_pct")
        r1_touches = sr_data.get("r1_touches", 0)
        s1 = sr_data.get("s1")
        s1_dist = sr_data.get("s1_dist_pct")
        s1_touches = sr_data.get("s1_touches", 0)
        context_flag = sr_data.get("context_flag", "")

        lines.append("\n📍 <b>S/R Нива (1D Macro):</b>")
        if r1 is not None:
            r1_str = _format_price(r1)
            dist_str = f"+{r1_dist:.1f}%" if r1_dist is not None else ""
            touch_str = f" | {r1_touches} теста" if r1_touches > 1 else ""
            lines.append(f"• 🔴 Съпротива (R1): <code>{r1_str}</code> ({dist_str}{touch_str})")
        else:
            lines.append("• 🔴 Съпротива (R1): <i>Няма установена (Price Discovery)</i>")

        if s1 is not None:
            s1_str = _format_price(s1)
            dist_str = f"-{s1_dist:.1f}%" if s1_dist is not None else ""
            touch_str = f" | {s1_touches} теста" if s1_touches > 1 else ""
            lines.append(f"• 🟢 Подкрепа (S1): <code>{s1_str}</code> ({dist_str}{touch_str})")
        else:
            lines.append("• 🟢 Подкрепа (S1): <i>Няма установена</i>")

        # Tactical contextual flags
        if new_state == LarssonState.GOLD:
            if context_flag == "NEAR_RESISTANCE":
                lines.append(f"⚠️ <b>Внимание:</b> Непосредствено под съпротива R1 (+{r1_dist:.1f}%)! Възможен откат.")
            elif context_flag == "NEAR_SUPPORT":
                lines.append(f"🎯 <b>Отлична позиция:</b> Gold обръщане близо до подкрепа S1 (-{s1_dist:.1f}%)!")
            elif context_flag == "BREAKOUT_ABOVE":
                lines.append("🚀 <b>Пробив:</b> Търгува се над всички ключови съпротиви!")
            elif r1_dist is not None and r1_dist >= 5.0:
                lines.append(f"✅ <b>Чист път:</b> +{r1_dist:.1f}% пространство до първа съпротива.")
        elif new_state == LarssonState.BLUE:
            if context_flag == "NEAR_SUPPORT":
                lines.append(f"⚠️ <b>Внимание:</b> Директно върху силна подкрепа S1 (-{s1_dist:.1f}%)!")
            elif context_flag == "BREAKDOWN_BELOW":
                lines.append("🔻 <b>Срив:</b> Пробив под всички ключови нива на подкрепа!")

    # Phase 3: Invalidation Level, Time Stop, and Base Rates
    if trade_suggestion:
        inv_lvl = getattr(trade_suggestion, "invalidation_level", None)
        inv_pct = getattr(trade_suggestion, "invalidation_pct", None)
        time_stop = getattr(trade_suggestion, "time_stop_bars", 60)
        win_rate = getattr(trade_suggestion, "base_rate_win_rate", None)
        mean_ret = getattr(trade_suggestion, "base_rate_mean_ret", None)
        n_samples = getattr(trade_suggestion, "base_rate_sample_size", None)
        htf_ok = getattr(trade_suggestion, "htf_aligned", True)

        lines.append("\n🛑 <b>Ниво на невалидност & Базови вероятности:</b>")
        if inv_lvl is not None:
            inv_str = _format_price(inv_lvl)
            pct_str = f" (-{inv_pct:.1f}%)" if inv_pct is not None else ""
            lines.append(f"• 🛑 <b>Invalidation Level:</b> <code>{inv_str}</code>{pct_str}")
            lines.append(f"• ⏳ <b>Time Stop:</b> {time_stop} бара (~макс. хоризонт)")

        if win_rate is not None and mean_ret is not None:
            n_str = f" (N={n_samples})" if n_samples else ""
            lines.append(
                f"• 📊 <b>Base Rate:</b> <b>{win_rate * 100:.1f}%</b> Win Rate | <b>{mean_ret * 100:+.1f}%</b> Нетна доходност{n_str}"
            )

        if not htf_ok:
            lines.append("• ⚠️ <b>Предупреждение:</b> Конфликт с дневния макро тренд (HTF)!")

    # TradingView links (USD & /BTC ratio)
    links = [f"📊 <a href=\"{tv_url}\">TradingView (USD)</a>"]
    clean_t = ticker.upper()
    if clean_t not in ("BTCUSDT", "BTC-USD", "BTC") and not clean_t.startswith("^"):
        try:
            from src.engine.btc_relative import get_tradingview_ratio_link
            btc_tv_url = get_tradingview_ratio_link(ticker, asset_class=asset_class, timeframe=timeframe, tv_symbol=tv_symbol)
            links.append(f"🪙 <a href=\"{btc_tv_url}\">TradingView (/BTC)</a>")
        except Exception:
            pass

    lines.append(" | ".join(links))
    return "\n".join(lines)



def format_batch_alert(changes: List[dict]) -> str:
    """
    Formats a consolidated batch message when multiple symbols change state simultaneously.
    Prevents alert storming / spam.
    """
    count = len(changes)
    header = f"🚨 <b>Пазарен ъпдейт: {count} промени в състоянието</b>\n\n"

    lines = []
    for item in changes:
        ticker = item["ticker"]
        tf = item["timeframe"]
        new_state = item["new_state"]
        old_state = item["old_state"]
        price = item["price"]
        tv_symbol = item["tv_symbol"]
        tv_url = get_tradingview_link(tv_symbol, tf)
        sr = item.get("sr_data")

        new_emoji = STATE_EMOJI.get(new_state, "⚪")
        old_emoji = STATE_EMOJI.get(old_state, "⚪")
        p_str = _format_price(price)

        sr_tag = ""
        if sr and (sr.get("s1") or sr.get("r1")):
            s_part = f"S1: {_format_price(sr.get('s1'))}" if sr.get("s1") else ""
            r_part = f"R1: {_format_price(sr.get('r1'))}" if sr.get("r1") else ""
            parts = [p for p in [s_part, r_part] if p]
            sr_tag = f" <i>[{' | '.join(parts)}]</i>"

        asset_name = get_asset_name(ticker)
        desc = f" ({asset_name})" if asset_name and asset_name != ticker else ""
        line = f"• <a href=\"{tv_url}\"><b>{ticker}</b></a>{desc} ({tf}): {old_emoji} ➡️ <b>{new_emoji} {new_state.value}</b> @ <code>{p_str}</code>{sr_tag}"
        lines.append(line)

    body = "\n".join(lines)
    return header + body


def format_daily_digest(
    total: int,
    gold_count: int,
    blue_count: int,
    neutral_count: int,
    top_bullish: List[dict],
    top_bearish: List[dict],
    recent_changes: List[dict],
    date_str: Optional[str] = None,
    dashboard_url: str = "https://todoripetrov.github.io/larsson-scanner/",
    priority_summary: Optional[List[dict]] = None,
) -> str:
    """
    Formats the daily market digest into a clean, comprehensive Telegram HTML message.
    """
    bullish_pct = round((gold_count / total * 100), 1) if total > 0 else 0.0
    bearish_pct = round((blue_count / total * 100), 1) if total > 0 else 0.0
    neutral_pct = round((neutral_count / total * 100), 1) if total > 0 else 0.0

    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    sections = []

    # 1. Header & Market Balance
    header = (
        f"🌅 <b>Larsson Line Сутрешен Бюлетин</b>\n"
        f"📅 <i>{date_str}</i>\n\n"
        f"📊 <b>Пазарен Баланс ({total} актива):</b>\n"
        f"• 🟡 <b>Gold (Бичи):</b> {gold_count} ({bullish_pct}%)\n"
        f"• 🔵 <b>Blue (Мечи):</b> {blue_count} ({bearish_pct}%)\n"
        f"• ⚪ <b>Neutral:</b> {neutral_count} ({neutral_pct}%)"
    )
    sections.append(header)

    # 2. Priority Focus Assets (BTC, MSTR, Metaplanet, NAKA)
    if priority_summary:
        focus_lines = ["⭐ <b>Ключови активи (Focus Watch):</b>"]
        for p in priority_summary:
            ticker = p["ticker"]
            name = p.get("name", ticker)
            tf = p.get("timeframe", "1D")
            st = str(p.get("state", "NEUTRAL")).upper()
            st_emoji = "🟡" if "GOLD" in st else ("🔵" if "BLUE" in st else "⚪")
            spread = p.get("spread_pct", 0.0)
            sign = "+" if spread > 0 else ""
            price = p.get("price", 0.0)
            p_str = _format_price(price)
            tv_sym = p.get("tv_symbol", ticker)
            url = get_tradingview_link(tv_sym, tf)
            focus_lines.append(f"• <a href=\"{url}\"><b>{name}</b></a>: {st_emoji} <b>{st}</b> @ <code>{p_str}</code> ({sign}{spread:.1f}%)")
        sections.append("\n".join(focus_lines))

    # 3. Top Bullish Trends (Highest Spread %)
    if top_bullish:
        bull_lines = ["🚀 <b>Топ Бичи Трендове (Ribbon Spread):</b>"]
        for item in top_bullish:
            ticker = item["ticker"]
            name = item.get("name", ticker)
            tf = item["timeframe"]
            spread = item["spread_pct"]
            price = item["price"]
            tv_sym = item["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            sign = "+" if spread > 0 else ""
            desc = f" ({name})" if name and name != ticker else ""
            bull_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a>{desc} ({tf}): <code>{sign}{spread:.1f}%</code> @ <code>{p_str}</code>")
        sections.append("\n".join(bull_lines))

    # 3. Top Bearish Trends (Lowest Spread %)
    if top_bearish:
        bear_lines = ["🔻 <b>Топ Мечи Трендове:</b>"]
        for item in top_bearish:
            ticker = item["ticker"]
            name = item.get("name", ticker)
            tf = item["timeframe"]
            spread = item["spread_pct"]
            price = item["price"]
            tv_sym = item["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            desc = f" ({name})" if name and name != ticker else ""
            bear_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a>{desc} ({tf}): <code>{spread:.1f}%</code> @ <code>{p_str}</code>")
        sections.append("\n".join(bear_lines))

    # 4. Recent State Transitions (Last 24h)
    if recent_changes:
        chg_lines = [f"🔄 <b>Промени в състоянието (последни 24ч: {len(recent_changes)}):</b>"]
        for item in recent_changes[:8]:
            ticker = item["ticker"]
            tf = item["timeframe"]
            new_st = item["new_state"]
            old_st = item.get("old_state", "")
            price = item["price"]
            tv_sym = item["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")

            new_em = STATE_EMOJI.get(new_st, "⚪") if isinstance(new_st, LarssonState) else ("🟡" if new_st == "GOLD" else ("🔵" if new_st == "BLUE" else "⚪"))
            old_em = STATE_EMOJI.get(old_st, "⚪") if isinstance(old_st, LarssonState) else ("🟡" if old_st == "GOLD" else ("🔵" if old_st == "BLUE" else "⚪"))
            new_val = new_st.value if isinstance(new_st, LarssonState) else str(new_st)
            asset_name = get_asset_name(ticker)
            desc = f" ({asset_name})" if asset_name and asset_name != ticker else ""

            chg_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a>{desc} ({tf}): {old_em} ➡️ <b>{new_em} {new_val}</b> @ <code>{p_str}</code>")

        if len(recent_changes) > 8:
            chg_lines.append(f"<i>... и още {len(recent_changes) - 8} промени в дашборда.</i>")
        sections.append("\n".join(chg_lines))
    else:
        sections.append("🔄 <b>Промени за 24ч:</b> <i>Няма нови промени в състоянието.</i>")

    # 5. Footer link to Web Dashboard
    footer = f"🌐 <a href=\"{dashboard_url}\"><b>Отвори Live Web Dashboard</b></a>"
    sections.append(footer)

    return "\n\n".join(sections)

