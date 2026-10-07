"""
Unit tests for Bitcoin On-Chain Cycle Engine and Trading Overlays.
"""

import pytest

from src.engine.btc_cycle import (
    BtcCycleEngine,
    normalize_mvrv_z,
    normalize_nupl,
    normalize_puell,
)
from src.engine.trade_suggestions import (
    calculate_confluence_score,
    calculate_leverage_matrix,
    generate_trade_suggestion,
)
from src.storage.database import Database


@pytest.fixture
def memory_db():
    return Database(":memory:")


def test_normalization_functions():
    # MVRV-Z
    assert normalize_mvrv_z(-0.6) == 5.0
    assert 10.0 <= normalize_mvrv_z(0.0) <= 20.0
    assert 20.0 <= normalize_mvrv_z(1.5) <= 45.0
    assert 70.0 <= normalize_mvrv_z(5.0) <= 85.0
    assert normalize_mvrv_z(7.0) >= 88.0

    # NUPL
    assert normalize_nupl(-0.1) <= 15.0
    assert 15.0 <= normalize_nupl(0.20) <= 35.0
    assert 35.0 <= normalize_nupl(0.40) <= 60.0
    assert normalize_nupl(0.80) >= 85.0

    # Puell
    assert normalize_puell(0.3) == 8.0
    assert 30.0 <= normalize_puell(1.0) <= 60.0
    assert normalize_puell(2.5) >= 85.0


def test_regime_classification():
    engine = BtcCycleEngine()
    assert engine.classify_regime(15.0) == "DEEP_VALUE"
    assert engine.classify_regime(35.0) == "EARLY_BULL"
    assert engine.classify_regime(55.0) == "MID_CYCLE"
    assert engine.classify_regime(78.0) == "LATE_CYCLE"
    assert engine.classify_regime(92.0) == "EUPHORIA"


def test_cycle_engine_deep_value_overlays():
    engine = BtcCycleEngine()
    profile = engine.evaluate_cycle({"cycle_signal": 12.0})

    assert profile.regime == "DEEP_VALUE"
    assert profile.sizing_multiplier == 1.25
    assert profile.confluence_adjustment == 10
    assert profile.max_leverage == 3
    assert profile.allow_alt_longs is True


def test_cycle_engine_euphoria_overlays():
    engine = BtcCycleEngine()
    profile_bullish_btc = engine.evaluate_cycle({"cycle_signal": 88.0}, btc_state="GOLD")
    assert profile_bullish_btc.regime == "EUPHORIA"
    assert profile_bullish_btc.sizing_multiplier == 0.3
    assert profile_bullish_btc.confluence_adjustment == -20
    assert profile_bullish_btc.max_leverage == 1
    assert profile_bullish_btc.allow_alt_longs is True  # Allowed only if BTC is confirmed GOLD

    profile_bearish_btc = engine.evaluate_cycle({"cycle_signal": 90.0}, btc_state="BLUE")
    assert profile_bearish_btc.allow_alt_longs is False  # Blocked in Euphoria when BTC is not GOLD


def test_confluence_score_btc_adjustments():
    engine = BtcCycleEngine()
    cycle_deep_val = engine.evaluate_cycle({"cycle_signal": 15.0})
    cycle_euphoria = engine.evaluate_cycle({"cycle_signal": 89.0})

    # Baseline score with standard technical alignment
    base_score, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.2,
        asset_class="crypto",
        ticker="BTCUSDT",
    )

    # With Deep Value cycle tailwind
    val_score, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.2,
        asset_class="crypto",
        ticker="BTCUSDT",
        btc_cycle=cycle_deep_val,
    )
    assert val_score == min(100, base_score + 10)

    # With Euphoria cycle headwind
    euph_score, _ = calculate_confluence_score(
        is_mtf_aligned=True,
        near_support=True,
        s1_touches=2,
        spread_expanding=True,
        rr_ratio=2.2,
        asset_class="crypto",
        ticker="BTCUSDT",
        btc_cycle=cycle_euphoria,
    )
    assert euph_score == max(0, base_score - 20)


def test_leverage_matrix_cycle_cap():
    engine = BtcCycleEngine()
    cycle_euphoria = engine.evaluate_cycle({"cycle_signal": 90.0})

    matrix = calculate_leverage_matrix(
        entry_price=60000.0,
        stop_loss=58000.0,
        position_size_usd=300.0,
        max_leverage=3,
        btc_cycle=cycle_euphoria,
    )
    # In euphoria, max leverage is strictly capped at 1x
    assert len(matrix) == 1
    assert matrix[0]["leverage"] == 1


def test_generate_trade_suggestion_with_cycle():
    engine = BtcCycleEngine()
    cycle_profile = engine.evaluate_cycle({"cycle_signal": 15.0})

    suggestion = generate_trade_suggestion(
        current_price=62000.0,
        state="GOLD",
        v1=61500.0,
        m1=61200.0,
        m2=60800.0,
        v2=60500.0,
        spread_pct=1.65,
        atr=1200.0,
        s1=61500.0,
        s1_touches=2,
        r1=68000.0,
        ticker="BTCUSDT",
        asset_class="crypto",
        btc_cycle=cycle_profile,
    )

    assert suggestion.btc_cycle_score == 15.0
    assert suggestion.btc_cycle_regime == "DEEP_VALUE"
    assert suggestion.btc_cycle_sizing_mult == 1.25
    assert "Deep Value" in suggestion.reason_bg
