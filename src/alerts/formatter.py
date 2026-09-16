"""
Message formatting for Larsson Line Scanner alerts.
Generates clean HTML messages for Telegram with TradingView deep-links.
"""

from datetime import datetime, timezone
from typing import List, Optional
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
) -> str:
    """
    Formats a single state transition alert in Telegram HTML format,
    enriched with macro Support & Resistance (S/R) levels and context flags.
    """
    new_emoji = STATE_EMOJI.get(new_state, "⚪")
    old_emoji = STATE_EMOJI.get(old_state, "⚪")
    new_text = STATE_TITLE.get(new_state, new_state.value)
    old_text = STATE_TITLE.get(old_state, old_state.value)

    tv_url = get_tradingview_link(tv_symbol, timeframe)
    price_str = _format_price(price)

    lines = [
        f"{new_emoji} <b>{ticker} | {timeframe}</b>",
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

    lines.append(f"📊 <a href=\"{tv_url}\">Отвори в TradingView</a>")
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

        line = f"• <a href=\"{tv_url}\"><b>{ticker}</b></a> ({tf}): {old_emoji} ➡️ <b>{new_emoji} {new_state.value}</b> @ <code>{p_str}</code>{sr_tag}"
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

    # 2. Top Bullish Trends (Highest Spread %)
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

            chg_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): {old_em} ➡️ <b>{new_em} {new_val}</b> @ <code>{p_str}</code>")

        if len(recent_changes) > 8:
            chg_lines.append(f"<i>... и още {len(recent_changes) - 8} промени в дашборда.</i>")
        sections.append("\n".join(chg_lines))
    else:
        sections.append("🔄 <b>Промени за 24ч:</b> <i>Няма нови промени в състоянието.</i>")

    # 5. Footer link to Web Dashboard
    footer = f"🌐 <a href=\"{dashboard_url}\"><b>Отвори Live Web Dashboard</b></a>"
    sections.append(footer)

    return "\n\n".join(sections)

