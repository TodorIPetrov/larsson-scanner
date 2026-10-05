"""
Unit tests for Alert Filter Engine (src/alerts/filter.py).
Verifies:
1. Only GOLD state changes are dispatched for general assets.
2. ALL state changes (GOLD, BLUE, NEUTRAL) are dispatched for BTC, MSTR, Metaplanet (3350.T), and NAKA.
3. BLUE and NEUTRAL transitions for non-priority assets are suppressed.
"""

import pytest
from src.alerts.filter import (
    is_priority_asset,
    is_alert_eligible_for_telegram,
    filter_state_changes_for_telegram,
)
from src.engine.smma import LarssonState


def test_is_priority_asset():
    # BTC variants
    assert is_priority_asset("BTCUSDT") is True
    assert is_priority_asset("BTC") is True
    assert is_priority_asset("btcusdt") is True
    assert is_priority_asset("BINANCE:BTCUSDT") is True
    assert is_priority_asset("BTC-USD") is True

    # MSTR
    assert is_priority_asset("MSTR") is True
    assert is_priority_asset("mstr") is True
    assert is_priority_asset("NASDAQ:MSTR") is True

    # Metaplanet
    assert is_priority_asset("3350.T") is True
    assert is_priority_asset("3350") is True
    assert is_priority_asset("METAPLANET") is True
    assert is_priority_asset("TSE:3350") is True

    # NAKA
    assert is_priority_asset("NAKA") is True
    assert is_priority_asset("naka") is True
    assert is_priority_asset("NASDAQ:NAKA") is True

    # Non-priority assets
    assert is_priority_asset("ETHUSDT") is False
    assert is_priority_asset("SOLUSDT") is False
    assert is_priority_asset("NVDA") is False
    assert is_priority_asset("AAPL") is False
    assert is_priority_asset("TSLA") is False


def test_is_alert_eligible_for_telegram_gold_for_any_asset():
    # Any asset going to GOLD must be eligible
    assert is_alert_eligible_for_telegram("ETHUSDT", LarssonState.NEUTRAL, LarssonState.GOLD) is True
    assert is_alert_eligible_for_telegram("NVDA", LarssonState.BLUE, LarssonState.GOLD) is True
    assert is_alert_eligible_for_telegram("SOLUSDT", "BLUE", "GOLD") is True
    assert is_alert_eligible_for_telegram("AMZN", LarssonState.NEUTRAL, LarssonState.GOLD) is True


def test_is_alert_eligible_for_telegram_priority_assets_all_transitions():
    # Priority assets going to BLUE must be eligible
    assert is_alert_eligible_for_telegram("BTCUSDT", LarssonState.GOLD, LarssonState.BLUE) is True
    assert is_alert_eligible_for_telegram("MSTR", LarssonState.GOLD, LarssonState.BLUE) is True
    assert is_alert_eligible_for_telegram("3350.T", LarssonState.GOLD, LarssonState.BLUE) is True
    assert is_alert_eligible_for_telegram("NAKA", LarssonState.GOLD, LarssonState.BLUE) is True

    # Priority assets going to NEUTRAL must be eligible
    assert is_alert_eligible_for_telegram("BTCUSDT", LarssonState.BLUE, LarssonState.NEUTRAL) is True
    assert is_alert_eligible_for_telegram("MSTR", LarssonState.GOLD, LarssonState.NEUTRAL) is True
    assert is_alert_eligible_for_telegram("3350.T", LarssonState.BLUE, LarssonState.NEUTRAL) is True
    assert is_alert_eligible_for_telegram("NAKA", LarssonState.GOLD, LarssonState.NEUTRAL) is True


def test_is_alert_eligible_for_telegram_non_priority_suppressed():
    # Non-priority assets going to BLUE or NEUTRAL must be SUPPRESSED
    assert is_alert_eligible_for_telegram("ETHUSDT", LarssonState.GOLD, LarssonState.BLUE) is False
    assert is_alert_eligible_for_telegram("ETHUSDT", LarssonState.GOLD, LarssonState.NEUTRAL) is False
    assert is_alert_eligible_for_telegram("NVDA", LarssonState.GOLD, LarssonState.BLUE) is False
    assert is_alert_eligible_for_telegram("AAPL", LarssonState.BLUE, LarssonState.NEUTRAL) is False
    assert is_alert_eligible_for_telegram("SOLUSDT", LarssonState.NEUTRAL, LarssonState.BLUE) is False


def test_filter_state_changes_for_telegram():
    events = [
        # Should pass: ETH goes to GOLD
        {"ticker": "ETHUSDT", "old_state": LarssonState.NEUTRAL, "new_state": LarssonState.GOLD, "price": 2500.0},
        # Should be filtered out: SOL goes to BLUE
        {"ticker": "SOLUSDT", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 140.0},
        # Should pass: BTC goes to BLUE (priority asset)
        {"ticker": "BTCUSDT", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 63000.0},
        # Should pass: MSTR goes to NEUTRAL (priority asset)
        {"ticker": "MSTR", "old_state": LarssonState.GOLD, "new_state": LarssonState.NEUTRAL, "price": 175.0},
        # Should be filtered out: NVDA goes to BLUE
        {"ticker": "NVDA", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 115.0},
        # Should pass: 3350.T goes to BLUE (priority asset)
        {"ticker": "3350.T", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 1050.0},
        # Should pass: NAKA goes to NEUTRAL (priority asset)
        {"ticker": "NAKA", "old_state": LarssonState.GOLD, "new_state": LarssonState.NEUTRAL, "price": 1.20},
    ]

    filtered = filter_state_changes_for_telegram(events)
    tickers_passed = [x["ticker"] for x in filtered]

    assert tickers_passed == ["ETHUSDT", "BTCUSDT", "MSTR", "3350.T", "NAKA"]
    assert "SOLUSDT" not in tickers_passed
    assert "NVDA" not in tickers_passed


def test_htf_gating_for_4h_alerts():
    # 4H GOLD with 1D BLUE macro trend -> suppressed for non-priority
    assert is_alert_eligible_for_telegram(
        "ETHUSDT", LarssonState.NEUTRAL, LarssonState.GOLD,
        timeframe="4H", macro_1d_state="BLUE"
    ) is False

    # 4H GOLD with 1D GOLD macro trend -> approved
    assert is_alert_eligible_for_telegram(
        "ETHUSDT", LarssonState.NEUTRAL, LarssonState.GOLD,
        timeframe="4H", macro_1d_state="GOLD"
    ) is True

    # 4H BLUE with 1D GOLD macro trend -> suppressed
    assert is_alert_eligible_for_telegram(
        "ETHUSDT", LarssonState.GOLD, LarssonState.BLUE,
        timeframe="4H", macro_1d_state="GOLD"
    ) is False

    # Priority asset (BTC) bypasses HTF gating
    assert is_alert_eligible_for_telegram(
        "BTCUSDT", LarssonState.NEUTRAL, LarssonState.GOLD,
        timeframe="4H", macro_1d_state="BLUE"
    ) is True
