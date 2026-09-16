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


def format_single_alert(
    ticker: str,
    timeframe: str,
    old_state: LarssonState,
    new_state: LarssonState,
    price: float,
    tv_symbol: str,
) -> str:
    """
    Formats a single state transition alert in Telegram HTML format.
    """
    new_emoji = STATE_EMOJI.get(new_state, "⚪")
    old_emoji = STATE_EMOJI.get(old_state, "⚪")
    new_text = STATE_TITLE.get(new_state, new_state.value)
    old_text = STATE_TITLE.get(old_state, old_state.value)

    tv_url = get_tradingview_link(tv_symbol, timeframe)

    # Format price cleanly
    if price >= 1000:
        price_str = f"${price:,.2f}"
    elif price >= 1:
        price_str = f"${price:.3f}"
    else:
        price_str = f"${price:.6f}"

    msg = (
        f"{new_emoji} <b>{ticker} | {timeframe}</b>\n"
        f"🔄 {old_emoji} {old_text} ➡️ <b>{new_emoji} {new_text}</b>\n"
        f"💵 Цена: <code>{price_str}</code>\n"
        f"📊 <a href=\"{tv_url}\">Отвори в TradingView</a>"
    )
    return msg


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

        new_emoji = STATE_EMOJI.get(new_state, "⚪")
        old_emoji = STATE_EMOJI.get(old_state, "⚪")

        if price >= 1000:
            p_str = f"${price:,.2f}"
        else:
            p_str = f"${price:.2f}"

        line = f"• <a href=\"{tv_url}\"><b>{ticker}</b></a> ({tf}): {old_emoji} ➡️ <b>{new_emoji} {new_state.value}</b> @ <code>{p_str}</code>"
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

