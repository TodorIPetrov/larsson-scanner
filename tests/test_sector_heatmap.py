"""
Tests for src/engine/sector_heatmap.py

Covers:
- Sector breadth calculation from scan results
- Market regime classification (BULL, BEAR, MIXED, TRANSITIONING)
- Momentum classification (IMPROVING, DETERIORATING, STABLE)
- Market-wide regime (RISK_ON, RISK_OFF, rotation signals)
- Top movers selection
- Empty data edge cases
"""

import pytest

from src.engine.sector_heatmap import compute_sector_breadth, get_market_regime


def test_sector_breadth_basic():
    scan_results = [
        {"ticker": "BTCUSDT", "asset_class": "crypto", "state": "GOLD", "bars_since_flip": 15},
        {"ticker": "ETHUSDT", "asset_class": "crypto", "state": "GOLD", "bars_since_flip": 10},
        {"ticker": "SOLUSDT", "asset_class": "crypto", "state": "BLUE", "bars_since_flip": 2},
        {"ticker": "DOGEUSDT", "asset_class": "crypto", "state": "NEUTRAL", "bars_since_flip": 0},
        {"ticker": "NVDA", "asset_class": "us_stocks", "state": "GOLD", "bars_since_flip": 25},
        {"ticker": "AAPL", "asset_class": "us_stocks", "state": "BLUE", "bars_since_flip": 5},
    ]

    breadth = compute_sector_breadth(scan_results)

    assert "Crypto" in breadth
    crypto = breadth["Crypto"]
    assert crypto["total"] == 4
    assert crypto["gold"] == 2
    assert crypto["blue"] == 1
    assert crypto["neutral"] == 1
    assert crypto["gold_pct"] == 50.0
    assert crypto["blue_pct"] == 25.0
    assert crypto["neutral_pct"] == 25.0
    assert len(crypto["top_movers"]) <= 3

    assert "US Stocks" in breadth
    stocks = breadth["US Stocks"]
    assert stocks["total"] == 2
    assert stocks["gold_pct"] == 50.0


def test_sector_regime_bull():
    scan_results = [
        {"ticker": f"COIN_{i}", "asset_class": "crypto", "state": "GOLD", "bars_since_flip": i}
        for i in range(10)
    ]
    breadth = compute_sector_breadth(scan_results)
    assert breadth["Crypto"]["regime"] == "BULL"
    assert breadth["Crypto"]["gold_pct"] == 100.0


def test_sector_regime_bear():
    scan_results = [
        {"ticker": f"COIN_{i}", "asset_class": "crypto", "state": "BLUE", "bars_since_flip": i}
        for i in range(10)
    ]
    breadth = compute_sector_breadth(scan_results)
    assert breadth["Crypto"]["regime"] == "BEAR"
    assert breadth["Crypto"]["blue_pct"] == 100.0


def test_momentum_tracking():
    scan_results = [
        {"ticker": f"COIN_{i}", "asset_class": "crypto", "state": "GOLD", "bars_since_flip": i}
        for i in range(8)
    ] + [
        {"ticker": "COIN_8", "asset_class": "crypto", "state": "BLUE", "bars_since_flip": 1},
        {"ticker": "COIN_9", "asset_class": "crypto", "state": "BLUE", "bars_since_flip": 1},
    ]
    # Current gold_pct = 80.0%

    # Scenario A: prev was 60.0% -> IMPROVING
    prev_breadth = {"Crypto": {"gold_pct": 60.0}}
    breadth = compute_sector_breadth(scan_results, prev_breadth=prev_breadth)
    assert breadth["Crypto"]["momentum"] == "IMPROVING"

    # Scenario B: prev was 90.0% -> DETERIORATING
    prev_breadth_high = {"Crypto": {"gold_pct": 90.0}}
    breadth_det = compute_sector_breadth(scan_results, prev_breadth=prev_breadth_high)
    assert breadth_det["Crypto"]["momentum"] == "DETERIORATING"

    # Scenario C: prev was 82.0% (within 5%) -> STABLE
    prev_breadth_close = {"Crypto": {"gold_pct": 82.0}}
    breadth_stable = compute_sector_breadth(scan_results, prev_breadth=prev_breadth_close)
    assert breadth_stable["Crypto"]["momentum"] == "STABLE"


def test_get_market_regime():
    sector_breadth = {
        "Crypto": {"regime": "BULL", "gold_pct": 80.0},
        "US Stocks": {"regime": "BULL", "gold_pct": 75.0},
        "AI / Tech": {"regime": "BULL", "gold_pct": 70.0},
        "Commodities": {"regime": "MIXED", "gold_pct": 45.0},
    }

    market = get_market_regime(sector_breadth)
    assert market["regime"] == "RISK_ON"
    assert market["rotation_signal"] == "CRYPTO_LEADING"
    assert market["breadth_score"] > 0.6


def test_empty_scan_results():
    breadth = compute_sector_breadth([])
    assert breadth == {}

    market = get_market_regime({})
    assert market["regime"] == "NEUTRAL"
    assert market["rotation_signal"] == "NO_DATA"
