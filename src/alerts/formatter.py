"""
Message formatting for Larsson Line Scanner alerts.
Generates clean HTML messages for Telegram with TradingView deep-links.
"""

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
