"""
Tests for src/engine/signal_confidence.py

Covers:
- Feature extraction from proposals
- Rule-based fallback scoring logic
- Tier-based base scores (A vs B vs C)
- Bonus and penalty factors (support, BTC alpha, volatility, volume)
- Confidence labels (HIGH, MEDIUM, LOW)
- Telegram formatting line
- Graceful handling of empty or partial data
"""

import pytest

from src.engine.signal_confidence import (
    extract_features_from_proposal,
    compute_signal_confidence,
    format_confidence_for_telegram,
)


def test_extract_features():
    proposal = {
        "spread_pct": 1.5,
        "tier": "A",
        "btc_alpha_30d": 5.2,
        "btc_ratio_state": "GOLD",
    }
    ctx = {
        "atr_percentile": 0,  # low vol
        "sr_proximity": 0.85, # near support
        "volume_ratio": 2.1,  # volume surge
    }

    features = extract_features_from_proposal(proposal, ctx)

    assert features["ribbon_spread_at_flip"] == 1.5
    assert features["quality_tier"] == 0  # Tier A encoded as 0
    assert features["btc_alpha_direction"] == 1
    assert features["atr_percentile"] == 0
    assert features["sr_proximity"] == 0.85
    assert features["volume_ratio"] == 2.1


def test_rule_based_high_confidence():
    # Tier A + near support + positive BTC alpha + low vol compression
    features = {
        "quality_tier": 0,
        "sr_proximity": 0.9,
        "btc_alpha_direction": 1,
        "atr_percentile": 0,
        "ribbon_spread_at_flip": 1.2,
        "volume_ratio": 1.8,
    }

    conf = compute_signal_confidence(features)

    assert conf["model_type"] == "rule_based"
    assert conf["score"] >= 80
    assert conf["confidence_label"] == "HIGH"
    assert "Near support level" in conf["top_factors"]
    assert "Positive BTC alpha" in conf["top_factors"]


def test_rule_based_low_confidence():
    # Tier C + negative BTC alpha + high vol
    features = {
        "quality_tier": 2,
        "sr_proximity": 0.1,
        "btc_alpha_direction": -1,
        "atr_percentile": 2,
        "ribbon_spread_at_flip": 0.2,
        "volume_ratio": 0.8,
    }

    conf = compute_signal_confidence(features)

    assert conf["score"] < 50
    assert conf["confidence_label"] == "LOW"


def test_raw_proposal_input():
    raw_proposal = {
        "spread_pct": 2.0,
        "tier": "B",
        "btc_alpha_30d": 3.0,
        "btc_ratio_state": "GOLD",
    }
    conf = compute_signal_confidence(raw_proposal)
    assert 0 <= conf["score"] <= 100
    assert conf["confidence_label"] in ("HIGH", "MEDIUM", "LOW")


def test_telegram_formatter():
    conf = {
        "score": 75,
        "confidence_label": "HIGH",
        "similar_setups_win_rate": 0.68,
    }
    line = format_confidence_for_telegram(conf)
    assert "75/100" in line
    assert "HIGH" in line
    assert "68% historical win rate" in line
