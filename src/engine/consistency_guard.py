"""
ConsistencyGuard: Institutional Validation and Integrity Layer.
Enforces strict quantitative invariants across fundamental valuation,
asset classification, moat normalization, target bounds, and options flow.
Implements the 5 mandatory patches approved by Claude Opus (Phase 1).
"""

import math
from typing import Dict, Optional, Tuple


def is_pure_crypto(
    asset_class: Optional[str] = None,
    ticker: Optional[str] = None,
    fund_profile: Optional[object] = None,
) -> bool:
    """
    Patch 2: Asset-Class Identification via Data Source / Registry.
    Uses registry lookup and corporate financial markers rather than naive string guessing.
    - COIN, MSTR, MARA, IBIT are crypto-exposed equities/ETFs, NOT pure crypto.
    - Assets with corporate DCF/financial profiles (sector, model_type, roic, shares) are NOT pure crypto.
    """
    # 1. If fundamental profile has corporate equity data, it is an equity
    if fund_profile:
        if (
            getattr(fund_profile, "sector", None)
            or getattr(fund_profile, "model_type", None)
            or getattr(fund_profile, "shares", None)
            or getattr(fund_profile, "roic_pct", None)
            or getattr(fund_profile, "ebit_b", None)
        ):
            return False

    # 2. Check ticker via canonical registry
    eff_ticker = ticker or (getattr(fund_profile, "ticker", None) if fund_profile else None)
    if eff_ticker:
        clean_ticker = str(eff_ticker).split(":")[-1].strip().upper()
        from src.engine.asset_profiles import get_asset_class_for_ticker
        reg_class = get_asset_class_for_ticker(clean_ticker)
        if reg_class:
            return reg_class == "crypto"

    # 3. Check asset_class
    if asset_class:
        ac_str = str(asset_class).strip().lower()
        if ac_str in ("us_stocks", "ai_stocks", "crypto_stocks", "intl_stocks", "commodities", "indices", "stocks", "equities"):
            return False
        if ac_str == "crypto":
            return True

    return False


def validate_fair_value_and_mos(
    fair_value: Optional[float],
    current_price: float,
    asset_class: str = "crypto",
    min_mos_threshold: float = 15.0,
    ticker: Optional[str] = None,
    fund_profile: Optional[object] = None,
) -> Tuple[Optional[float], bool, str]:
    """
    Patch 1: Robust MoS Calculation & FV Guard.
    - If asset is pure crypto, returns (None, False, "Crypto has no corporate DCF").
    - If fair_value is None, non-finite, or <= 0, returns (None, False, "Invalid non-positive Fair Value").
    - Dynamic MoS = (fair_value - current_price) / fair_value * 100.
    - Requires MoS >= min_mos_threshold (15.0%) for fundamental undervaluation bonus.
    Returns: (clean_mos_pct, is_undervalued, reason)
    """
    if is_pure_crypto(asset_class=asset_class, ticker=ticker, fund_profile=fund_profile):
        return None, False, "Pure crypto: corporate DCF / MoS model not applicable"

    if fair_value is None or not isinstance(fair_value, (int, float)):
        return None, False, "Missing or non-numeric Fair Value"

    fv_float = float(fair_value)
    if not math.isfinite(fv_float) or fv_float <= 0.0:
        return None, False, f"Invalid non-positive Fair Value ({fair_value})"

    if current_price <= 0.0 or not math.isfinite(current_price):
        return None, False, f"Invalid current price ({current_price})"

    # Clean Margin of Safety calculation
    mos_pct = round(((fv_float - current_price) / fv_float) * 100.0, 2)

    if mos_pct >= min_mos_threshold:
        return mos_pct, True, f"Undervalued: MoS {mos_pct:+.1f}% >= {min_mos_threshold:.1f}% threshold"
    else:
        return mos_pct, False, f"Insufficient margin of safety: MoS {mos_pct:+.1f}% < {min_mos_threshold:.1f}% gate"


def normalize_moat(moat: Optional[str]) -> Tuple[str, int]:
    """
    Patch 3: Strict Moat Normalization.
    Normalizes string: case-insensitive, strip whitespace.
    Returns: (normalized_moat_str, bonus_points)
    - 'Wide' -> ('Wide', 5)
    - 'Narrow' -> ('Narrow', 2)
    - None, 'None', 'N/A', '', 'Unknown' -> ('None', 0)
    """
    if not moat:
        return "None", 0

    cleaned = str(moat).strip().title()
    if cleaned == "Wide":
        return "Wide", 5
    elif cleaned == "Narrow":
        return "Narrow", 2
    else:
        return "None", 0


def validate_target_and_valuation(
    setup_type: str,
    tp1: Optional[float],
    fair_value: Optional[float],
    current_price: float,
    asset_class: str = "crypto",
    ticker: Optional[str] = None,
    fund_profile: Optional[object] = None,
) -> Tuple[str, bool, str]:
    """
    Patch 4: Target Ceiling vs Valuation & Rescoring on Relabeling.
    - For QUANTAMENTAL_ALPHA_BUY:
      - Validates TP1 <= fair_value.
      - If TP1 > fair_value:
        - The trade cannot remain a value trade (the technical target contradicts the valuation thesis).
        - Relabels to 'TECHNICAL_MOMENTUM_BREAKOUT'.
        - Flags requires_rescoring = True so all fundamental points are stripped and rescored from scratch.
    Returns: (new_setup_type, requires_rescoring, audit_reason)
    """
    if setup_type != "QUANTAMENTAL_ALPHA_BUY":
        return setup_type, False, "Not a quantamental alpha buy setup"

    if is_pure_crypto(asset_class=asset_class, ticker=ticker, fund_profile=fund_profile):
        return (
            "PULLBACK_VALUE_BUY",
            True,
            "Pure crypto setup relabeled from QUANTAMENTAL_ALPHA_BUY to PULLBACK_VALUE_BUY (no DCF model)",
        )

    if fair_value is None or fair_value <= 0.0 or not math.isfinite(fair_value):
        return (
            "TECHNICAL_MOMENTUM_BREAKOUT",
            True,
            "Invalid or missing Fair Value; relabeled to TECHNICAL_MOMENTUM_BREAKOUT with zero fundamental points",
        )

    if tp1 is not None and tp1 > fair_value:
        return (
            "TECHNICAL_MOMENTUM_BREAKOUT",
            True,
            f"Target TP1 (${tp1:,.2f}) exceeds Fair Value (${fair_value:,.2f}). Relabeled to TECHNICAL_MOMENTUM_BREAKOUT and rescored without fundamental bonus",
        )

    return setup_type, False, f"Target TP1 (${tp1:,.2f}) within Fair Value (${fair_value:,.2f})"


def validate_options_flow(
    options_flow: Optional[dict],
    current_price: float,
) -> Tuple[bool, str, Optional[dict]]:
    """
    Patch 5: Split- and Staleness-Aware Options Flow Checks.
    - Eliminates fragile PCR == 1.0 float check.
    - Checks for missing or error data.
    - Rejects if total OI <= 0 and total volume <= 0.
    - Rejects Max Pain outside [0.50 * price, 1.50 * price] band (splits/reverse splits).
    - Rejects if staleness flag or days_old > 3.
    Returns: (is_valid, validation_message, sanitized_options_flow)
    """
    if not options_flow or not isinstance(options_flow, dict):
        return False, "No options flow data available", None

    flow = dict(options_flow)

    # 1. Missing data or error flags
    if flow.get("error") or flow.get("missing_data") or flow.get("is_stale"):
        flow["is_valid"] = False
        flow["confluence_boost"] = False
        flow["validation_error"] = "Options data marked as missing, stale, or errored"
        return False, flow["validation_error"], flow

    # 2. Staleness check
    days_old = flow.get("days_old")
    if days_old is not None and isinstance(days_old, (int, float)) and days_old > 3:
        flow["is_valid"] = False
        flow["confluence_boost"] = False
        flow["validation_error"] = f"Options data is {days_old} trading days old (> 3 days limit)"
        return False, flow["validation_error"], flow

    # 3. Open Interest & Volume check (replaces PCR == 1.0 float check)
    call_oi = float(flow.get("call_oi") or 0.0)
    put_oi = float(flow.get("put_oi") or 0.0)
    call_vol = float(flow.get("call_volume") or 0.0)
    put_vol = float(flow.get("put_volume") or 0.0)
    total_oi = call_oi + put_oi
    total_vol = call_vol + put_vol

    if total_oi <= 0 and total_vol <= 0:
        flow["is_valid"] = False
        flow["confluence_boost"] = False
        flow["validation_error"] = "Zero options open interest and zero volume (inactive market)"
        return False, flow["validation_error"], flow

    # 4. Max Pain Sanity Band: [0.50 * price, 1.50 * price]
    max_pain = flow.get("max_pain")
    if max_pain is not None and current_price > 0:
        try:
            mp_float = float(max_pain)
            lower_bound = 0.50 * current_price
            upper_bound = 1.50 * current_price
            if mp_float < lower_bound or mp_float > upper_bound:
                flow["is_valid"] = False
                flow["confluence_boost"] = False
                err = (
                    f"Max Pain (${mp_float:,.2f}) outside sanity band [0.5x, 1.5x] "
                    f"of price (${current_price:,.2f}) - likely corporate action / split artifact"
                )
                flow["validation_error"] = err
                return False, err, flow
        except (ValueError, TypeError):
            flow["is_valid"] = False
            flow["confluence_boost"] = False
            flow["validation_error"] = f"Invalid Max Pain value ({max_pain})"
            return False, flow["validation_error"], flow

    # Flow is valid and passed all quality gates
    flow["is_valid"] = True
    return True, "Options flow passed all data-integrity checks", flow
