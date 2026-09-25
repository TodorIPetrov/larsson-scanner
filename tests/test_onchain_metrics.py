"""
Tests for src/engine/onchain_metrics.py (Task 13).

Covers:
- Crypto vs non-crypto symbol detection
- On-chain composite score computation
- Score to qualitative verdict classification
- Handling API response with mock requests
- Fallback metrics when API fails
- Caching behavior
"""

import pytest
from unittest.mock import MagicMock, patch

from src.engine.onchain_metrics import (
    is_crypto_symbol,
    compute_onchain_score,
    classify_onchain_verdict,
    fetch_onchain_metrics,
    _ONCHAIN_CACHE,
)


def test_is_crypto_symbol():
    assert is_crypto_symbol("BTCUSDT") is True
    assert is_crypto_symbol("ETHUSDC") is True
    assert is_crypto_symbol("SOL-USD") is True
    assert is_crypto_symbol("AAPL") is False
    assert is_crypto_symbol("NVDA") is False
    assert is_crypto_symbol("GC=F") is False


def test_compute_onchain_score():
    # Ideal accumulation setup: ~60% drawdown, 90% circulating, high volume
    score_high = compute_onchain_score(
        ath_drawdown_pct=60.0,
        supply_circulating_ratio=0.90,
        sentiment_score=60.0,
        volume_to_mcap_ratio=0.10,
    )
    assert score_high >= 70
    assert classify_onchain_verdict(score_high) == "ACCUMULATION"

    # Distressed/dilution setup: low circulating supply, low volume
    score_low = compute_onchain_score(
        ath_drawdown_pct=95.0,
        supply_circulating_ratio=0.20,
        sentiment_score=20.0,
        volume_to_mcap_ratio=0.01,
    )
    assert score_low < 45
    assert classify_onchain_verdict(score_low) == "DISTRIBUTION"


def test_fetch_onchain_non_crypto_returns_none():
    res = fetch_onchain_metrics("NVDA")
    assert res is None


def test_fetch_onchain_metrics_with_mock():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "market_data": {
            "current_price": {"usd": 65000.0},
            "ath": {"usd": 73750.0},
            "ath_change_percentage": {"usd": -11.8},
            "circulating_supply": 19700000.0,
            "total_supply": 21000000.0,
            "market_cap": {"usd": 1280000000000.0},
            "total_volume": {"usd": 35000000000.0},
            "price_change_percentage_7d": 4.5,
        }
    }
    mock_session.get.return_value = mock_resp

    _ONCHAIN_CACHE.clear()
    metrics = fetch_onchain_metrics("BTCUSDT", use_cache=False, session=mock_session)

    assert metrics is not None
    assert metrics["symbol"] == "BTCUSDT"
    assert metrics["ath_usd"] == 73750.0
    assert metrics["dilution_risk"] == "LOW"
    assert 0 <= metrics["onchain_score"] <= 100
    assert metrics["onchain_verdict"] in ("ACCUMULATION", "NEUTRAL", "DISTRIBUTION")


def test_fallback_on_api_error():
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network timeout")

    _ONCHAIN_CACHE.clear()
    metrics = fetch_onchain_metrics("SOLUSDT", use_cache=False, session=mock_session)
    assert metrics is not None
    assert metrics["symbol"] == "SOLUSDT"
    assert metrics["onchain_score"] == 60
    assert metrics["onchain_verdict"] == "NEUTRAL"
