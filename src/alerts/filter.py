"""
Alert Filtering Engine for Larsson Line Scanner.
Enforces strict dispatch rules for Telegram notifications:
1. ANY asset transitioning to GOLD (LarssonState.GOLD).
2. Priority focus assets (BTC, MSTR, Metaplanet [3350.T], NAKA) on ANY transition (GOLD, BLUE, NEUTRAL).
All other transitions are suppressed from Telegram to prevent spam, while remaining fully recorded in SQLite.
"""

from typing import Any, Dict, List, Optional, Set
from src.engine.smma import LarssonState

# Canonical symbols and recognized aliases for priority focus assets
PRIORITY_ASSET_TICKERS: Set[str] = {
    # Bitcoin
    "BTC",
    "BTCUSDT",
    "BTCUSDC",
    "BTC-USD",
    "BINANCE:BTCUSDT",
    # MicroStrategy
    "MSTR",
    "NASDAQ:MSTR",
    # Metaplanet
    "3350.T",
    "3350",
    "METAPLANET",
    "TSE:3350",
    # Nakamoto Inc.
    "NAKA",
    "NASDAQ:NAKA",
}


def normalize_ticker(ticker: str) -> str:
    """Normalizes ticker symbol for reliable comparison."""
    if not ticker:
        return ""
    t = ticker.upper().strip()
    if ":" in t:
        t = t.split(":")[-1].strip()
    return t


def is_priority_asset(ticker: str, custom_priority_list: Optional[List[str]] = None) -> bool:
    """
    Checks if a ticker matches one of the priority assets:
    BTC, MSTR, Metaplanet (3350.T), NAKA.
    """
    clean_t = normalize_ticker(ticker)
    if clean_t in PRIORITY_ASSET_TICKERS:
        return True

    # Also handle variants like 3350 without .T or with exchange prefixes
    if clean_t.startswith("3350"):
        return True

    if clean_t.startswith("BTC") and (clean_t.endswith("USDT") or clean_t.endswith("USDC") or clean_t == "BTC"):
        return True

    if custom_priority_list:
        for p in custom_priority_list:
            if clean_t == normalize_ticker(p):
                return True

    return False


def is_alert_eligible_for_telegram(
    ticker: str,
    old_state: Any,
    new_state: Any,
    config: Optional[dict] = None,
    timeframe: Optional[str] = None,
    macro_1d_state: Optional[str] = None,
) -> bool:
    """
    Determines if a state change event should be dispatched to Telegram.

    Rules:
    - 4H signals are gated by 1D Higher-Timeframe (HTF) agreement (blocks counter-trend funding wicks).
    - If new_state is GOLD: Eligible for ANY asset (provided HTF agreement on 4H).
    - If ticker is a priority asset (BTC, MSTR, Metaplanet, NAKA): Eligible for ALL state changes.
    - Otherwise: Suppressed.
    """
    custom_priority = None
    if config:
        tg_cfg = config.get("telegram", {})
        alert_filters = tg_cfg.get("alert_filters", {})
        custom_priority = alert_filters.get("priority_assets")

    is_priority = is_priority_asset(ticker, custom_priority_list=custom_priority)

    # Normalize state representations
    new_state_str = str(new_state.value if hasattr(new_state, "value") else new_state).upper()

    # Quant Hardening: Mute standalone 4H trade alerts (negative expectancy on 5-20 bars).
    # 4H is permitted strictly as an entry-timing confluence for the 1D trend (macro_1d_state == "GOLD").
    allow_4h_standalone = False
    if config:
        allow_4h_standalone = config.get("telegram", {}).get("alert_filters", {}).get("allow_standalone_4h_alerts", False)

    if timeframe == "4H" and not is_priority:
        if not allow_4h_standalone:
            # Standalone 4H blocked: requires explicit 1D GOLD confluence
            if not macro_1d_state or macro_1d_state.upper() != "GOLD":
                return False
        elif macro_1d_state and macro_1d_state.upper() != "GOLD":
            return False

    if "GOLD" in new_state_str:
        return True

    if is_priority:
        return True

    return False


def filter_state_changes_for_telegram(
    state_changes: List[Dict[str, Any]],
    config: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """
    Filters a list of state change events, keeping only those permitted to send Telegram notifications.
    """
    if not state_changes:
        return []

    eligible: List[Dict[str, Any]] = []
    for ev in state_changes:
        ticker = ev.get("ticker", "")
        old_st = ev.get("old_state")
        new_st = ev.get("new_state")
        tf = ev.get("timeframe")
        m_st = ev.get("macro_1d_state")
        if is_alert_eligible_for_telegram(
            ticker, old_st, new_st, config=config, timeframe=tf, macro_1d_state=m_st
        ):
            eligible.append(ev)

    return eligible
