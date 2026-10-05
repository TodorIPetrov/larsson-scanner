"""
Tests for ConsistencyGuard (Phase 1 Institutional Quant Hardening).
Directly verifies Claude Opus's 5 required institutional patches:
1. Robust MoS Calculation & FV Guard (no negative FV, no divide-by-zero, >= 15% threshold gate).
2. Asset-Class Identification via Registry (COIN/MSTR/IBIT are equities; pure crypto has 0 DCF points but can reach A+).
3. Strict Moat Normalization ('Wide', 'Narrow', None/null).
4. Target Ceiling vs Valuation & Rescoring on Relabeling (TP1 <= FV gate, pure momentum rescoring).
5. Split- and Staleness-Aware Options Flow Checks (rejection of split artifacts like NVDA Max Pain $55 vs $155).
"""

import math
import pytest

from src.engine.consistency_guard import (
    is_pure_crypto,
    normalize_moat,
    validate_fair_value_and_mos,
    validate_options_flow,
    validate_target_and_valuation,
)
from src.engine.trade_suggestions import (
    calculate_confluence_score,
    generate_trade_suggestion,
)
from src.engine.quantamental import FundamentalProfile


# =============================================================================
# PATCH 1: Robust MoS Calculation & FV Guard
# =============================================================================

def test_patch1_negative_fair_value_guard():
    """Negative fair value must never produce positive MoS (e.g. (-10 - 100)/(-10) = +1100%)."""
    mos, is_undervalued, reason = validate_fair_value_and_mos(
        fair_value=-10.0,
        current_price=100.0,
        asset_class="us_stocks",
    )
    assert mos is None
    assert is_undervalued is False
    assert "Invalid non-positive Fair Value" in reason


def test_patch1_zero_and_nan_fair_value_guard():
    """Zero, NaN, and Infinite fair values must be rejected."""
    for invalid_fv in [0.0, -0.0, float("nan"), float("inf"), None, "invalid"]:
        mos, is_undervalued, reason = validate_fair_value_and_mos(
            fair_value=invalid_fv,
            current_price=100.0,
            asset_class="us_stocks",
        )
        assert mos is None
        assert is_undervalued is False


def test_patch1_mos_15_percent_gate():
    """
    MoS must meet or exceed the 15.0% threshold.
    Case 1: SOL audit case: FV 135.0 vs Price 118.38 -> MoS = 12.31% (< 15.0% gate) -> Fails gate.
    Case 2: Deep value: FV 100.0 vs Price 70.0 -> MoS = 30.0% (>= 15.0% gate) -> Passes gate.
    """
    # Case 1: 12.31% MoS fails gate
    mos_fail, is_under_fail, reason_fail = validate_fair_value_and_mos(
        fair_value=135.0,
        current_price=118.38,
        asset_class="us_stocks",
    )
    assert mos_fail == pytest.approx(12.31, 0.05)
    assert is_under_fail is False
    assert "Insufficient margin of safety" in reason_fail

    # Case 2: 30.0% MoS passes gate
    mos_pass, is_under_pass, reason_pass = validate_fair_value_and_mos(
        fair_value=100.0,
        current_price=70.0,
        asset_class="us_stocks",
    )
    assert mos_pass == pytest.approx(30.0, 0.05)
    assert is_under_pass is True
    assert "Undervalued" in reason_pass


# =============================================================================
# PATCH 2: Asset-Class Identification via Registry (Not Naive String Matching)
# =============================================================================

def test_patch2_crypto_exposed_equities_not_pure_crypto():
    """COIN, MSTR, MARA, IBIT must NOT be classified as pure crypto."""
    for ticker in ["COIN", "MSTR", "MARA", "IBIT", "RIOT", "HOOD"]:
        assert is_pure_crypto(asset_class="crypto_stocks", ticker=ticker) is False
        assert is_pure_crypto(asset_class="ai_stocks", ticker=ticker) is False
        assert is_pure_crypto(ticker=ticker) is False


def test_patch2_pure_crypto_has_zero_dcf_points():
    """Pure crypto (BTCUSDT, SOLUSDT) must receive zero DCF bonus points."""
    crypto_profile = FundamentalProfile(
        ticker="SOLUSDT",
        name="Solana",
        verdict="STRONG BUY",
        target_price=150.0,
        fair_value=135.0,
        mos_pct=28.0,
        moat="Narrow",
    )
    score, tier = calculate_confluence_score(
        is_mtf_aligned=False,
        near_support=False,
        s1_touches=0,
        spread_expanding=False,
        rr_ratio=2.0,
        fund_profile=crypto_profile,
        asset_class="crypto",
        current_price=118.38,
    )
    # Base: 40, rr_ratio 2.0: +5 -> 45. Zero DCF bonus (+0), tier NONE.
    assert score == 45
    assert tier == "NONE"


def test_patch2_pure_crypto_can_reach_tier_a_plus_via_technical_and_alpha():
    """Crypto must not be permanently trapped in Tier B. Strong technicals + BTC alpha reach A+."""
    class MockBtcRelative:
        ratio_state = "GOLD"
        alpha_30d_pct = 8.5

    score, tier = calculate_confluence_score(
        is_mtf_aligned=True,       # +20
        near_support=True,         # +20
        s1_touches=3,              # +10
        spread_expanding=True,     # +10
        rr_ratio=2.6,              # +10
        fund_profile=None,         # +0
        btc_relative=MockBtcRelative(),  # +15 (GOLD and alpha >= 5%)
        asset_class="crypto",
        current_price=100.0,
    )
    # 40 (base) + 20 + 20 + 10 + 10 + 10 + 15 = 125 -> capped at 100, Tier A+
    assert score == 100
    assert tier == "A+"


# =============================================================================
# PATCH 3: Strict Moat Normalization
# =============================================================================

def test_patch3_moat_normalization():
    """Moat strings must be strictly normalized and only 'Wide' gets full bonus (+5)."""
    assert normalize_moat("Wide") == ("Wide", 5)
    assert normalize_moat("wide") == ("Wide", 5)
    assert normalize_moat("  WIDE  ") == ("Wide", 5)

    assert normalize_moat("Narrow") == ("Narrow", 2)
    assert normalize_moat("narrow") == ("Narrow", 2)

    assert normalize_moat(None) == ("None", 0)
    assert normalize_moat("None") == ("None", 0)
    assert normalize_moat("N/A") == ("None", 0)
    assert normalize_moat("") == ("None", 0)
    assert normalize_moat("Unknown") == ("None", 0)


# =============================================================================
# PATCH 4: Target Ceiling vs Valuation & Rescoring on Relabeling
# =============================================================================

def test_patch4_target_ceiling_relabels_and_rescores():
    """
    If TP1 > Fair Value, setup cannot be QUANTAMENTAL_ALPHA_BUY.
    Must relabel to TECHNICAL_MOMENTUM_BREAKOUT and rescore with zero fundamental bonus.
    """
    clean_setup, requires_rescore, audit_msg = validate_target_and_valuation(
        setup_type="QUANTAMENTAL_ALPHA_BUY",
        tp1=160.93,
        fair_value=135.0,
        current_price=118.38,
        asset_class="us_stocks",
    )
    assert clean_setup == "TECHNICAL_MOMENTUM_BREAKOUT"
    assert requires_rescore is True
    assert "exceeds Fair Value" in audit_msg


def test_patch4_full_flow_sol_target_above_fv_relabeled():
    """
    Simulates SOL-style setup where target (160) exceeds fair value (135).
    Verifies that the suggestion is relabeled and fundamental points are stripped.
    """
    fund_profile = FundamentalProfile(
        ticker="TECH_CORP",
        name="Tech Corp",
        verdict="STRONG BUY",
        target_price=140.0,
        fair_value=135.0,
        mos_pct=25.0,
        moat="Wide",
    )
    # Pullback to S1 at 110, R1 at 155 (exceeds fair value of 135!)
    s = generate_trade_suggestion(
        current_price=118.0,
        state="GOLD",
        v1=120.0,
        m1=116.0,
        m2=112.0,
        v2=108.0,
        spread_pct=3.0,
        atr=4.0,
        s1=110.0,
        r1=155.0,  # TP1 = 155.0 > fair_value = 135.0!
        context_flag="NEAR_SUPPORT",
        fund_profile=fund_profile,
        ticker="TECH_CORP",
        asset_class="us_stocks",
    )

    # Must be relabeled to TECHNICAL_MOMENTUM_BREAKOUT, NOT QUANTAMENTAL_ALPHA_BUY!
    assert s.setup_type == "TECHNICAL_MOMENTUM_BREAKOUT"
    assert "MOMENTUM BREAKOUT" in s.synthesis_badge_bg
    assert "ТЕХНИЧЕСКИ МОМЕНТУМ" in s.reason_bg


def test_patch4_deterministic_target_precedence_no_clipping():
    """
    If R1 exists and is reachable, TP1 is strictly anchored to R1.
    If R:R < 1.8, the engine does NOT arbitrarily switch to ATR projection to pass; it returns WAIT.
    """
    s = generate_trade_suggestion(
        current_price=100.0,
        state="GOLD",
        v1=98.0,
        m1=96.0,
        m2=94.0,
        v2=92.0,
        spread_pct=2.0,
        atr=3.0,
        s1=90.0,    # Stop below S1 = ~88.5 -> Risk = 11.5
        r1=105.0,   # Reward = 5.0 -> R:R = 5.0 / 11.5 = 0.43 (< 1.8)
        context_flag="NEAR_SUPPORT",
        asset_class="us_stocks",
    )
    assert s.action == "WAIT"
    assert s.setup_type == "WAIT_FOR_SETUP"


# =============================================================================
# PATCH 5: Split- and Staleness-Aware Options Flow Checks
# =============================================================================

def test_patch5_max_pain_split_artifact_rejection():
    """
    NVDA audit case: Price $155, Max Pain $55 (pre-split artifact).
    Ratio: 55 / 155 = 0.35 (< 0.50 sanity band). Must be rejected!
    """
    stale_flow = {
        "max_pain": 55.0,
        "put_call_ratio": 0.65,
        "net_sentiment": "BULLISH",
        "confluence_boost": True,
        "call_oi": 10000,
        "put_oi": 6500,
    }
    is_valid, msg, clean_flow = validate_options_flow(stale_flow, current_price=155.0)
    assert is_valid is False
    assert clean_flow["is_valid"] is False
    assert clean_flow["confluence_boost"] is False
    assert "outside sanity band" in msg


def test_patch5_valid_options_flow_passes_and_boosts():
    """Valid options flow within [0.5x, 1.5x] sanity band passes and allows boost."""
    valid_flow = {
        "max_pain": 150.0,
        "put_call_ratio": 0.60,
        "net_sentiment": "BULLISH",
        "confluence_boost": True,
        "call_oi": 10000,
        "put_oi": 6000,
    }
    is_valid, msg, clean_flow = validate_options_flow(valid_flow, current_price=155.0)
    assert is_valid is True
    assert clean_flow["is_valid"] is True
    assert clean_flow["confluence_boost"] is True


def test_patch5_stale_options_data_rejected():
    """Options data older than 3 days or marked stale must be rejected."""
    stale_flow = {
        "max_pain": 150.0,
        "days_old": 5,
        "confluence_boost": True,
        "call_oi": 10000,
        "put_oi": 6000,
    }
    is_valid, msg, clean_flow = validate_options_flow(stale_flow, current_price=155.0)
    assert is_valid is False
    assert clean_flow["confluence_boost"] is False
    assert "older" in msg or "days old" in msg


def test_patch5_zero_oi_and_volume_rejected():
    """Zero open interest and zero volume must be rejected (inactive market)."""
    dead_flow = {
        "max_pain": 100.0,
        "call_oi": 0,
        "put_oi": 0,
        "call_volume": 0,
        "put_volume": 0,
        "confluence_boost": True,
    }
    is_valid, msg, clean_flow = validate_options_flow(dead_flow, current_price=100.0)
    assert is_valid is False
    assert clean_flow["confluence_boost"] is False
    assert "Zero options open interest" in msg
