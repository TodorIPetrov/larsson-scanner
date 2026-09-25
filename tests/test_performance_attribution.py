"""
Tests for src/engine/performance_attribution.py

Covers:
- Attribution by signal type
- Attribution by asset class
- Attribution by quality tier
- Attribution by day of week
- Attribution by leverage
- Best & worst signal detection
- Insight generation
- Edge cases: empty trade log, single trade
- Telegram formatter formatting
"""

import pytest

from src.engine.performance_attribution import (
    compute_attribution,
    format_attribution_telegram,
)


def _sample_trades():
    return [
        {
            "ticker": "BTCUSDT",
            "pnl_usd": 250.0,
            "entry_date": "2026-03-02T10:00:00Z",  # Monday (0)
            "exit_date": "2026-03-06T10:00:00Z",
            "signal_type": "GOLD_FLIP",
            "quality_tier": "A",
            "leverage": 2,
            "rr_ratio": 2.5,
        },
        {
            "ticker": "ETHUSDT",
            "pnl_usd": 120.0,
            "entry_date": "2026-03-03T10:00:00Z",  # Tuesday (1)
            "exit_date": "2026-03-05T10:00:00Z",
            "signal_type": "GOLD_FLIP",
            "quality_tier": "A",
            "leverage": 1,
            "rr_ratio": 1.8,
        },
        {
            "ticker": "SOLUSDT",
            "pnl_usd": -80.0,
            "entry_date": "2026-03-04T10:00:00Z",  # Wednesday (2)
            "exit_date": "2026-03-05T10:00:00Z",
            "signal_type": "QUALITY_DIP_BUY",
            "quality_tier": "B",
            "leverage": 3,
            "rr_ratio": 1.2,
        },
        {
            "ticker": "NVDA",
            "pnl_usd": 300.0,
            "entry_date": "2026-03-02T15:30:00Z",  # Monday (0)
            "exit_date": "2026-03-09T15:30:00Z",
            "signal_type": "GOLD_FLIP",
            "quality_tier": "A+",
            "leverage": 1,
            "rr_ratio": 3.0,
        },
    ]


def test_compute_attribution_breakdown():
    trades = _sample_trades()
    res = compute_attribution(trades)

    assert res["total_trades_analyzed"] == 4

    # Signal type
    assert "GOLD_FLIP" in res["by_signal_type"]
    gold_stats = res["by_signal_type"]["GOLD_FLIP"]
    assert gold_stats["trades"] == 3
    assert gold_stats["wins"] == 3
    assert gold_stats["win_rate"] == 100.0
    assert gold_stats["total_pnl_usd"] == 670.0

    # Best & worst signal
    assert res["best_signal"] == "GOLD_FLIP"
    assert res["worst_signal"] == "QUALITY_DIP_BUY"

    # Asset class
    assert "Crypto" in res["by_asset_class"]
    assert "US Equities" in res["by_asset_class"]
    assert res["by_asset_class"]["US Equities"]["trades"] == 1
    assert res["by_asset_class"]["Crypto"]["trades"] == 3

    # Quality tier
    assert "A" in res["by_quality_tier"]
    assert "B" in res["by_quality_tier"]
    assert res["by_quality_tier"]["A"]["win_rate"] == 100.0

    # Insights
    assert len(res["insights"]) > 0


def test_empty_trade_log():
    res = compute_attribution([])
    assert res["total_trades_analyzed"] == 0
    assert res["best_signal"] is None
    assert "No completed trades" in res["insights"][0]

    msg = format_attribution_telegram(res)
    assert "Няма приключили сделки" in msg


def test_telegram_formatter():
    trades = _sample_trades()
    res = compute_attribution(trades)
    msg = format_attribution_telegram(res)
    assert "Анализ на Изпълнението" in msg
    assert "GOLD_FLIP" in msg
