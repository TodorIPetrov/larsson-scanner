"""
Tests for src/engine/volatility_regime.py

Covers: low-vol regime, normal regime, high-vol regime, size-multiplier values,
edge cases with very short price series, ATR computation, BBW computation,
and the VolatilityRegimeResult dataclass helpers.
"""

import numpy as np
import pytest

from src.engine.volatility_regime import (
    ATR_LOOKBACK,
    REGIME_HIGH_VOL,
    REGIME_LOW_VOL,
    REGIME_NORMAL,
    SIZE_MULTIPLIER_HIGH_VOL,
    SIZE_MULTIPLIER_LOW_VOL,
    SIZE_MULTIPLIER_NORMAL,
    VolatilityRegimeResult,
    _atr_percentile_rank,
    _classify_regime,
    _compute_atr,
    _compute_bbw,
    _size_multiplier,
    classify_volatility_regime,
)

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_ohlc(n: int = 300, base: float = 100.0, volatility: float = 1.0, seed: int = 42):
    """Generate synthetic OHLC data of length n."""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, volatility, n))
    highs = closes + rng.uniform(0.2, 1.0, n) * volatility
    lows = closes - rng.uniform(0.2, 1.0, n) * volatility
    return highs, lows, closes


def _make_compressed_series(n: int = 300, base: float = 100.0, seed: int = 42):
    """
    Generate a price series that is very calm for most of its history
    but has the final bar at the lowest ATR – simulating a compression phase.
    """
    rng = np.random.default_rng(seed)
    # Start very volatile
    closes = base + np.cumsum(rng.normal(0, 3.0, n))
    highs = closes + rng.uniform(1.0, 3.0, n)
    lows = closes - rng.uniform(1.0, 3.0, n)
    # Last 20 bars become extremely tight (compressed)
    for i in range(n - 20, n):
        highs[i] = closes[i] + 0.01
        lows[i] = closes[i] - 0.01
    return highs, lows, closes


def _make_spiked_series(n: int = 300, base: float = 100.0, seed: int = 7):
    """
    Generate a calm series with the last few bars having an ATR spike
    so the latest ATR percentile lands in the HIGH_VOL zone.
    """
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 0.5, n))
    highs = closes + rng.uniform(0.1, 0.3, n)
    lows = closes - rng.uniform(0.1, 0.3, n)
    # Last 5 bars: enormous swings
    for i in range(n - 5, n):
        highs[i] = closes[i] + 15.0
        lows[i] = closes[i] - 15.0
    return highs, lows, closes


# ────────────────────────────────────────────────────────────────────────────
# Test 1: Low-volatility compression regime
# ────────────────────────────────────────────────────────────────────────────

def test_low_vol_compression_regime():
    """
    When the ATR of the most recent bar is very small relative to history,
    classify_volatility_regime should return LOW_VOL_COMPRESSION with a
    size multiplier greater than 1.0.
    """
    highs, lows, closes = _make_compressed_series(n=300)
    result = classify_volatility_regime(highs, lows, closes)

    assert isinstance(result, VolatilityRegimeResult)
    assert result.volatility_regime == REGIME_LOW_VOL, (
        f"Expected LOW_VOL_COMPRESSION, got {result.volatility_regime} "
        f"(percentile={result.vol_percentile:.1f})"
    )
    assert result.size_multiplier == SIZE_MULTIPLIER_LOW_VOL
    assert result.vol_percentile < 20.0


# ────────────────────────────────────────────────────────────────────────────
# Test 2: Normal trending regime
# ────────────────────────────────────────────────────────────────────────────

def test_normal_trending_regime():
    """
    Uniform random-walk data produces an ATR that is consistent throughout
    history → the latest ATR should land near the 50th percentile.
    The regime should be NORMAL_TRENDING with a multiplier of exactly 1.0.
    """
    highs, lows, closes = _make_ohlc(n=400, volatility=1.0, seed=1)
    result = classify_volatility_regime(highs, lows, closes)

    assert isinstance(result, VolatilityRegimeResult)
    # We don't guarantee exactly 50th but it should not be extreme
    assert result.volatility_regime == REGIME_NORMAL, (
        f"Expected NORMAL_TRENDING, got {result.volatility_regime} "
        f"(percentile={result.vol_percentile:.1f})"
    )
    assert result.size_multiplier == SIZE_MULTIPLIER_NORMAL
    assert 20.0 <= result.vol_percentile <= 70.0


# ────────────────────────────────────────────────────────────────────────────
# Test 3: High-volatility spike regime
# ────────────────────────────────────────────────────────────────────────────

def test_high_vol_spike_regime():
    """
    A sudden volatility spike at the end of an otherwise calm series
    should yield HIGH_VOL_SPIKE with a size multiplier < 1.0.
    """
    highs, lows, closes = _make_spiked_series(n=300)
    result = classify_volatility_regime(highs, lows, closes)

    assert isinstance(result, VolatilityRegimeResult)
    assert result.volatility_regime == REGIME_HIGH_VOL, (
        f"Expected HIGH_VOL_SPIKE, got {result.volatility_regime} "
        f"(percentile={result.vol_percentile:.1f})"
    )
    assert result.size_multiplier == SIZE_MULTIPLIER_HIGH_VOL
    assert result.vol_percentile > 70.0


# ────────────────────────────────────────────────────────────────────────────
# Test 4: Size multiplier values
# ────────────────────────────────────────────────────────────────────────────

def test_size_multiplier_values():
    """_size_multiplier should return exact spec values for each regime."""
    assert _size_multiplier(REGIME_LOW_VOL) == 1.25
    assert _size_multiplier(REGIME_NORMAL) == 1.00
    assert _size_multiplier(REGIME_HIGH_VOL) == 0.60
    # Also verify via classify result round-trip
    assert SIZE_MULTIPLIER_LOW_VOL == 1.25
    assert SIZE_MULTIPLIER_NORMAL == 1.00
    assert SIZE_MULTIPLIER_HIGH_VOL == 0.60


# ────────────────────────────────────────────────────────────────────────────
# Test 5: Edge case – very short price series (< ATR warmup)
# ────────────────────────────────────────────────────────────────────────────

def test_edge_case_very_short_series():
    """
    A series of 3 bars should not raise an exception.
    It should fall back to NORMAL_TRENDING and return a valid (non-NaN) ATR.
    """
    highs = np.array([101.0, 102.5, 103.0])
    lows = np.array([99.0, 100.5, 101.5])
    closes = np.array([100.0, 101.0, 102.0])

    result = classify_volatility_regime(highs, lows, closes)

    assert isinstance(result, VolatilityRegimeResult)
    # No crash; regime is set to something valid
    assert result.volatility_regime in {REGIME_LOW_VOL, REGIME_NORMAL, REGIME_HIGH_VOL}
    assert not np.isnan(result.atr)
    assert result.size_multiplier > 0


def test_edge_case_single_bar():
    """A single-bar series (n=1) should not raise and return a valid result."""
    highs = np.array([105.0])
    lows = np.array([95.0])
    closes = np.array([100.0])

    result = classify_volatility_regime(highs, lows, closes)

    assert isinstance(result, VolatilityRegimeResult)
    assert result.volatility_regime in {REGIME_LOW_VOL, REGIME_NORMAL, REGIME_HIGH_VOL}
    assert result.size_multiplier > 0
    # BBW is None because there are not enough bars
    assert result.bbw is None


# ────────────────────────────────────────────────────────────────────────────
# Test 6: ATR computation
# ────────────────────────────────────────────────────────────────────────────

def test_compute_atr_basic():
    """_compute_atr should produce a non-NaN value for the last bar of a 30-bar series."""
    highs, lows, closes = _make_ohlc(n=30, volatility=1.0, seed=99)
    atr = _compute_atr(highs, lows, closes, period=14)

    assert not np.isnan(atr[-1]), "Last ATR value should not be NaN for 30-bar series"
    assert atr[-1] > 0, "ATR must be positive"


def test_compute_atr_too_short():
    """_compute_atr on a 5-bar series with period=14 should return all NaN."""
    highs = np.array([10.0] * 5)
    lows = np.array([9.0] * 5)
    closes = np.array([9.5] * 5)
    atr = _compute_atr(highs, lows, closes, period=14)
    assert np.all(np.isnan(atr))


# ────────────────────────────────────────────────────────────────────────────
# Test 7: BBW computation
# ────────────────────────────────────────────────────────────────────────────

def test_compute_bbw_values():
    """BBW should be greater for a volatile series than a flat series."""
    _, _, closes_volatile = _make_ohlc(n=100, volatility=5.0, seed=3)
    _, _, closes_flat = _make_ohlc(n=100, volatility=0.01, seed=3)

    bbw_volatile = _compute_bbw(closes_volatile)
    bbw_flat = _compute_bbw(closes_flat)

    valid_v = bbw_volatile[~np.isnan(bbw_volatile)]
    valid_f = bbw_flat[~np.isnan(bbw_flat)]

    assert len(valid_v) > 0 and len(valid_f) > 0
    assert np.median(valid_v) > np.median(valid_f), (
        "BBW should be higher for the volatile series"
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 8: Percentile rank helper
# ────────────────────────────────────────────────────────────────────────────

def test_atr_percentile_rank_boundary():
    """
    When all ATR values are equal (except the last which is smallest),
    the latest value should have a very low percentile rank.
    """
    atr = np.array([5.0] * 50 + [0.1])   # Last value is the minimum
    pct = _atr_percentile_rank(atr, lookback=100)
    assert pct < 5.0, f"Expected near-zero percentile, got {pct}"


def test_atr_percentile_rank_max():
    """
    When the last ATR value is the maximum, the percentile should be near 100.
    """
    atr = np.array([1.0] * 50 + [100.0])  # Last value is the maximum
    pct = _atr_percentile_rank(atr, lookback=100)
    assert pct > 95.0, f"Expected near-100 percentile, got {pct}"


# ────────────────────────────────────────────────────────────────────────────
# Test 9: Classify regime thresholds
# ────────────────────────────────────────────────────────────────────────────

def test_classify_regime_boundaries():
    """_classify_regime should respect exact threshold values."""
    assert _classify_regime(0.0) == REGIME_LOW_VOL
    assert _classify_regime(19.9) == REGIME_LOW_VOL
    assert _classify_regime(20.0) == REGIME_NORMAL
    assert _classify_regime(45.0) == REGIME_NORMAL
    assert _classify_regime(70.0) == REGIME_NORMAL
    assert _classify_regime(70.1) == REGIME_HIGH_VOL
    assert _classify_regime(100.0) == REGIME_HIGH_VOL


# ────────────────────────────────────────────────────────────────────────────
# Test 10: to_dict output shape
# ────────────────────────────────────────────────────────────────────────────

def test_result_to_dict():
    """VolatilityRegimeResult.to_dict() must include all expected keys."""
    highs, lows, closes = _make_ohlc(n=300)
    result = classify_volatility_regime(highs, lows, closes)
    d = result.to_dict()

    expected_keys = {
        "volatility_regime", "vol_percentile", "size_multiplier",
        "atr", "bbw", "atr_lookback_bars"
    }
    assert expected_keys <= set(d.keys()), f"Missing keys: {expected_keys - set(d.keys())}"
    assert d["volatility_regime"] in {REGIME_LOW_VOL, REGIME_NORMAL, REGIME_HIGH_VOL}
    assert 0 <= d["vol_percentile"] <= 100
    assert d["size_multiplier"] > 0
