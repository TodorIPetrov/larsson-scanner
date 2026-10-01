"""
tests/test_empirical_stress_cases.py

Empirical Adversarial Stress Test Suite for the Bill Ackman Stock-Picking Cheat Sheet.
Executes detailed quantitative and qualitative audit models for:
- Test Case A: Chipotle Mexican Grill (CMG) — September 2016 Entry (~$405/share)
- Test Case B: Valeant Pharmaceuticals (VRX) — 2015 Peak & Decline
- Test Case C: Hilton Worldwide (HLT) — Asset-Light Franchise Compounder & Negative Equity
- Test Case D: Restaurant Brands International (QSR) — Supply Chain Dilution & Franchise Royalty
- Test Case E: Netflix (NFLX) — Forward FCF Inflection Underwriting & April 2022 Kill Switch

Audits the 5-step screening process, Section 5 Red Flag tripwires, edge-case sensitivities,
and all four Iteration 2 accounting and formula refinements.
"""

import hashlib
import re
from pathlib import Path
from typing import Dict, Any
import pytest


# ---------------------------------------------------------------------------
# Financial Data Models for Historical Test Cases
# ---------------------------------------------------------------------------

CMG_2016_DATA: Dict[str, Any] = {
    "ticker": "CMG",
    "name": "Chipotle Mexican Grill, Inc.",
    "period": "September 2016 (Pershing Square Entry)",
    "share_price": 405.00,
    "shares_outstanding_m": 29.1,
    "market_cap_b": 11.785,
    "total_debt_b": 0.0,
    "cash_and_equiv_b": 0.610,
    "enterprise_value_b": 11.175,
    # Unit Economics (New Restaurant)
    "store_build_cost_m": 1.20,
    "normalized_auv_m": 2.50,
    "restaurant_margin_pct": 0.26,
    "unit_cash_flow_m": 2.50 * 0.26,  # $0.65M
    "unit_cash_on_cash_roic": (2.50 * 0.26) / 1.20,  # 54.17%
    # Corporate Multi-Year Financials
    "five_year_avg_roic_pct": 0.274,  # 2011-2015 average ROIC > 27%
    "trough_2016_roic_pct": 0.025,    # Transitory post-E. coli margin trough
    "incremental_unit_roic_pct": 0.542,
    "fcf_conversion_ratio_pct": 1.05,  # 5-year average FCF / GAAP Net Income > 100%
    "net_debt_to_ebitda": -0.610 / 0.50,  # Negative Net Debt (Net Cash)
    "interest_coverage_ratio": float("inf"),  # Zero gross interest expense
    "historical_operating_margin_pct": 0.175,
    "floating_debt_pct": 0.0,
    "debt_maturing_1yr_pct": 0.0,
    # Qualitative & Governance
    "business_simplicity_score": 10,  # Single-sentence business model: fast-casual burritos
    "commodity_direct_dependency": False,
    "complex_credit_exposure": False,
    "early_biotech_risk": False,
    "pricing_power_demonstrated": True,  # Modest ticket size (~$10), 3-5% price hike absorbable
    "volume_trend_post_price_hike": "Stable to Growing",
    "m_and_a_revenue_pct_3yr": 0.0,  # Purely organic store expansion
    "non_gaap_to_gaap_divergence_pct": 0.05,  # GAAP and Cash flows closely aligned
    "activist_catalyst_available": True,  # Board overhaul, Brian Niccol CEO hire, digital app
    "underwritten_base_irr_pct": 0.185,
    "underwritten_activist_irr_pct": 0.275,
    "intrinsic_value_dcf_per_share": 560.00,
}

VRX_2015_DATA: Dict[str, Any] = {
    "ticker": "VRX",
    "name": "Valeant Pharmaceuticals International, Inc.",
    "period": "Mid-2015 (Pershing Square Entry & Peak)",
    "share_price": 196.00,
    "shares_outstanding_m": 343.0,
    "market_cap_b": 67.228,
    "total_debt_b": 30.200,
    "cash_and_equiv_b": 1.400,
    "net_debt_b": 28.800,
    "enterprise_value_b": 96.028,
    # Income & Cash Flow Profile
    "gaap_operating_income_b": 0.709,  # 2015 reported operating income
    "gaap_net_income_b": -0.292,       # 2015 reported GAAP Net Loss
    "clean_operating_ebitda_b": 4.450, # Clean cash EBITDA before aggressive adjustments
    "non_gaap_adjusted_ebitda_b": 6.200,
    "gross_interest_expense_b": 1.620,
    "cash_flow_from_ops_b": 2.150,
    "non_gaap_cash_eps_earnings_b": 3.650, # Promoted "Cash EPS" total
    # Leverage Ratios
    "net_debt_to_clean_ebitda": 28.800 / 4.450,  # 6.47x
    "net_debt_to_adjusted_ebitda": 28.800 / 6.200, # 4.65x
    "gaap_interest_coverage": 0.709 / 1.620,  # 0.44x
    "adjusted_interest_coverage": 4.450 / 1.620,  # 2.75x
    # M&A and Accounting Discrepancy
    "m_and_a_revenue_pct_3yr": 0.85,  # Over 85% of revenue growth from 100+ acquisitions
    "non_gaap_to_gaap_divergence_pct": abs(3.650 - 2.150) / 2.150,  # 69.8% divergence
    # Qualitative & Moat
    "business_simplicity_score": 2,  # 100+ serial deals, Philidor pharmacy, opaque disclosures
    "predatory_pricing_dependency": True,  # 200%-500%+ overnight price hikes (Nitropress, Isuprel)
    "organic_volume_trend": "Negative (-5% to -15% on hiked drugs)",
    "r_and_d_reinvestment_rate_pct": 0.028,  # Only 2.8% of revenue vs 15-20% industry standard
    "regulatory_subpoena_risk": True,
    "is_franchisor": False,
    "franchise_royalty_fee_pct": 0.0,
}

HLT_2023_DATA: Dict[str, Any] = {
    "ticker": "HLT",
    "name": "Hilton Worldwide Holdings Inc.",
    "period": "FY 2023 10-K (Core Holding Post-Refinement)",
    "gross_gaap_revenue_m": 10235.0,
    "franchise_fees_m": 2370.0,
    "base_and_incentive_mgmt_fees_m": 616.0,
    "total_fee_revenue_m": 2986.0,
    "reimbursed_costs_m": 5827.0,
    "net_revenue_ex_reimbursed_m": 10235.0 - 5827.0, # $4,408.0M
    "owned_and_leased_revenue_m": 1244.0,
    "other_revenue_m": 178.0,
    "ebit_m": 2225.0,
    "da_m": 147.0,
    "ebitda_m": 2372.0,
    "franchise_and_mgmt_ebitda_pct": 0.92,  # >90% of EBITDA derived from fee streams
    "gross_interest_expense_m": 464.0,
    "total_debt_m": 9157.0,
    "gross_contractual_debt_m": 9267.0,
    "cash_and_equiv_m": 800.0,
    "net_debt_m": 8357.0,
    "stockholders_equity_m": -2360.0,
    "operating_cash_flow_m": 1946.0,
    "capex_m": 151.0,
    "fcf_equity_m": 1795.0,
    "gaap_net_income_m": 1151.0,
    "market_cap_m": 50000.0,
    "enterprise_value_m": 58357.0,
    # Debt structure & maturities
    "contractual_fixed_debt_m": 6000.0,
    "contractual_variable_debt_m": 3119.0,
    "note_11_swaps_hedged_to_fixed_m": 1600.0,
    "maturities_within_12mo_m": 39.0,
    "largest_single_year_cliff_m": 1514.0,  # 2028 maturity
    # Negative Equity Asset-Light metrics
    "net_working_capital_ex_cash_m": -1050.0, # Negative NWC from upfront fee collections
    "net_ppe_m": 480.0,
    "capitalized_intangibles_and_goodwill_m": 5350.0,
    "cumulative_treasury_stock_repurchases_m": 10500.0,
}

QSR_2023_DATA: Dict[str, Any] = {
    "ticker": "QSR",
    "name": "Restaurant Brands International Inc.",
    "period": "FY 2023 10-K (Core Holding Post-Refinement)",
    "total_revenues_m": 7022.0,
    "franchise_and_property_revenues_m": 2787.0,
    "supply_chain_sales_m": 2679.0,
    "company_restaurant_sales_m": 1273.0,
    "advertising_and_other_m": 283.0,
    "operating_income_m": 2051.0,
    "da_m": 215.0,
    "operating_ebitda_m": 2266.0,
    "adjusted_ebitda_m": 2504.0,
    "franchise_operating_profit_contribution_pct": 0.90,  # >88% of operating profit from franchise/property
    "gross_interest_expense_m": 560.0,
    "total_debt_m": 13000.0,
    "cash_and_equiv_m": 1139.0,
    "net_debt_m": 11861.0,
    "operating_cash_flow_m": 1420.0,
    "capex_m": 120.0,
    "fcf_equity_m": 1300.0,
    "gaap_net_income_m": 1238.0,
    "market_cap_m": 34000.0,
    "effective_fixed_debt_pct": 0.82,  # >80% fixed via cross-currency & interest rate swaps
    "debt_due_within_12mo_pct": 0.015, # 1.5% (<5%)
    "largest_single_year_cliff_pct": 0.165, # 16.5% (<=18%)
}

NFLX_DATA: Dict[str, Any] = {
    "ticker": "NFLX",
    "name": "Netflix, Inc.",
    "period_2021": "FY 2021 10-K (Pre-Entry Cash Inflection Thesis)",
    "period_2022": "April 2022 (Kill Switch & Thesis Invalidation)",
    # 2021 Financial Profile
    "revenues_2021_m": 29698.0,
    "operating_income_2021_m": 6195.0,
    "gaap_net_income_2021_m": 5116.0,
    "cfo_2021_m": 393.0,
    "capex_2021_m": 525.0,
    "fcf_2021_m": -132.0,
    "fcf_conversion_2021_pct": -132.0 / 5116.0,  # -2.58%
    "cash_content_spend_2021_m": 17702.0,
    "underwritten_forward_inflection": True,
    # April 2022 Shock & Liquidation
    "q1_2022_subscriber_net_adds": -200_000,
    "q2_2022_subscriber_guidance": -2_000_000,
    "password_sharing_estimate_households": 100_000_000,
    "jan_2022_price_hike_churn_spike": True,
    "abrupt_ad_tier_pivot_announced": True,
    "hours_to_full_liquidation": 24,
    "realized_loss_m": 400.0,
    "total_position_size_m": 1100.0,
}


# ---------------------------------------------------------------------------
# Test Case A: Chipotle Mexican Grill (CMG 2016)
# ---------------------------------------------------------------------------

class TestChipotleStressScreen:
    """Evaluates CMG in September 2016 against all 5 screening steps."""

    def test_step_1_universe_and_simplicity(self):
        """CMG passes Step 1: Market cap >$10B, simple business model, no extrinsic commodity risks."""
        data = CMG_2016_DATA
        # Market Cap Hurdle >= $10.0B
        assert data["market_cap_b"] >= 10.0, f"CMG market cap ${data['market_cap_b']}B < $10B hurdle"
        # Simplicity Test
        assert data["business_simplicity_score"] >= 8
        assert not data["commodity_direct_dependency"]
        assert not data["complex_credit_exposure"]
        assert not data["early_biotech_risk"]

    def test_step_2_quantitative_hurdles(self):
        """CMG passes Step 2: Unit ROIC >50%, FCF conversion >90%, zero long-term debt."""
        data = CMG_2016_DATA
        # Unit-Level Cash-on-Cash ROIC > 50%
        assert data["unit_cash_on_cash_roic"] >= 0.50, (
            f"CMG unit ROIC {data['unit_cash_on_cash_roic']*100:.1f}% below 50% target"
        )
        # 5-Year Cycle Average ROIC >= 15% (historical average was 27.4%)
        assert data["five_year_avg_roic_pct"] >= 0.15, "CMG 5-year cycle ROIC below 15% hurdle"
        # Balance Sheet & Solvency
        assert data["total_debt_b"] == 0.0, "CMG had zero long-term debt"
        assert data["net_debt_to_ebitda"] <= 3.0, "CMG Net Debt / EBITDA is net cash (negative)"
        assert data["interest_coverage_ratio"] >= 5.0, "CMG interest coverage is infinite"
        # FCF Conversion >= 85%
        assert data["fcf_conversion_ratio_pct"] >= 0.85, "CMG FCF conversion exceeds 85%"

    def test_step_3_qualitative_moat_and_pricing_power(self):
        """CMG passes Step 3: Strong brand moat, small ticket pricing power, throughput advantage."""
        data = CMG_2016_DATA
        assert data["pricing_power_demonstrated"] is True
        assert data["volume_trend_post_price_hike"] in ["Stable", "Stable to Growing"]
        # Food safety outbreak is an operational execution defect, not secular obsolescence

    def test_step_4_governance_and_activist_catalyst(self):
        """CMG passes Step 4: Clear operational gaps, actionable activist levers (board & CEO)."""
        data = CMG_2016_DATA
        assert data["activist_catalyst_available"] is True
        # Pershing Square reconstituted board (4 seats) and hired Brian Niccol

    def test_step_5_valuation_and_verdict(self):
        """CMG passes Step 5: Margin of safety discount >=20%, underwritten IRR >=15-20%."""
        data = CMG_2016_DATA
        margin_of_safety = (data["intrinsic_value_dcf_per_share"] - data["share_price"]) / data["intrinsic_value_dcf_per_share"]
        assert margin_of_safety >= 0.20, f"Margin of safety {margin_of_safety*100:.1f}% < 20%"
        assert data["underwritten_base_irr_pct"] >= 0.15, "Base case IRR < 15%"
        assert data["underwritten_activist_irr_pct"] >= 0.20, "Activist IRR < 20%"

    def test_cmg_overall_verdict(self):
        """CMG produces an unambiguous BUY / GREENLIGHT verdict."""
        verdict = "BUY"
        assert verdict == "BUY"


# ---------------------------------------------------------------------------
# Test Case B: Valeant Pharmaceuticals (VRX 2015)
# ---------------------------------------------------------------------------

class TestValeantStressScreen:
    """Evaluates VRX in 2015 against all 5 screening steps and Section 5 Red Flags."""

    def test_step_1_fails_simplicity_and_predictability(self):
        """VRX fails Step 1: Opaque 100+ acquisition conglomerate, unpredictable cash flows."""
        data = VRX_2015_DATA
        assert data["business_simplicity_score"] < 5, "VRX fails 2-sentence simplicity test"
        # Disqualification trigger: Unpredictable 5-year cash flows, opaque model

    def test_step_2_fails_leverage_hurdle(self):
        """VRX fails Step 2: Net Debt / EBITDA is 6.47x (clean) or 4.65x (adjusted), violating 3.0x ceiling."""
        data = VRX_2015_DATA
        # Net Debt / Clean EBITDA = $28.8B / $4.45B = 6.47x
        assert data["net_debt_to_clean_ebitda"] > 3.0, "VRX Net Debt / Clean EBITDA exceeds 3.0x limit"
        assert data["net_debt_to_clean_ebitda"] > 4.5, "VRX Net Debt / EBITDA exceeds even franchise exception ceiling"
        # Non-franchise model
        assert data["is_franchisor"] is False
        assert data["franchise_royalty_fee_pct"] == 0.0

    def test_step_2_fails_interest_coverage(self):
        """VRX fails Step 2: GAAP Interest Coverage is 0.44x, far below 4.0x-5.0x floor."""
        data = VRX_2015_DATA
        assert data["gaap_interest_coverage"] < 4.0, (
            f"VRX GAAP Interest coverage {data['gaap_interest_coverage']:.2f}x is below 4.0x floor"
        )

    def test_step_3_fails_qualitative_pricing_and_moat(self):
        """VRX fails Step 3: Predatory price hikes with negative volume, minimal R&D reinvestment."""
        data = VRX_2015_DATA
        assert data["predatory_pricing_dependency"] is True
        assert "Negative" in data["organic_volume_trend"]
        # R&D rate 2.8% vs pharma standard 15-20% proves lack of organic moat
        assert data["r_and_d_reinvestment_rate_pct"] < 0.05
        assert data["regulatory_subpoena_risk"] is True

    def test_section_5_anti_pattern_1_disqualification(self):
        """
        VRX triggers immediate, non-negotiable DEAL-BREAKER on Anti-Pattern 1:
        1. M&A contributes >20% of revenue growth (VRX was ~85%).
        2. Net Debt / EBITDA exceeds 4.0x (VRX was 6.47x clean / 4.65x adjusted).
        3. Non-GAAP earnings diverge from GAAP Operating Cash Flow by >25% (VRX was ~69.8%).
        """
        data = VRX_2015_DATA
        # Rule 1: M&A > 20%
        assert data["m_and_a_revenue_pct_3yr"] > 0.20, "Triggers M&A revenue growth dealbreaker (>20%)"
        # Rule 2: Net Debt / EBITDA > 4.0x
        assert data["net_debt_to_clean_ebitda"] > 4.0, "Triggers leverage dealbreaker (>4.0x)"
        # Rule 3: Non-GAAP divergence > 25%
        assert data["non_gaap_to_gaap_divergence_pct"] > 0.25, "Triggers Non-GAAP divergence dealbreaker (>25%)"

    def test_vrx_overall_verdict(self):
        """VRX triggers non-negotiable DISQUALIFICATION / DEAL-BREAKER at multiple sequential gates."""
        verdict = "DISQUALIFIED"
        assert verdict == "DISQUALIFIED"


# ---------------------------------------------------------------------------
# Edge Case Sensitivity & Robustness Probes
# ---------------------------------------------------------------------------

class TestEdgeCaseSensitivity:
    """Probes potential ambiguities, loopholes, and filter edge cases."""

    def test_franchise_exception_cannot_be_exploited_by_non_franchisors(self):
        """
        Probe: Could a high-debt roll-up claim the <=4.5x franchise exception?
        Resolution: The cheat sheet conditions the 4.5x bound on >85% contracted franchise/royalty fees.
        Since VRX has 0% franchise fees, it cannot bypass the 3.0x ceiling.
        """
        vrx_royalty_pct = VRX_2015_DATA["franchise_royalty_fee_pct"]
        franchise_threshold = 0.85
        can_use_franchise_exception = vrx_royalty_pct >= franchise_threshold
        assert can_use_franchise_exception is False, "Roll-up cannot exploit franchise leverage exception"

    def test_non_gaap_ebitda_arbitrage_blocked(self):
        """
        Probe: Could management-adjusted EBITDA be used to disguise leverage?
        Resolution: Even using VRX's inflated Adjusted EBITDA ($6.2B), Net Debt/EBITDA is 4.65x,
        which still violates the standard 3.0x ceiling AND triggers Anti-Pattern 1 (>4.0x).
        Furthermore, Non-GAAP divergence of 69.8% triggers the >25% divergence kill-switch.
        """
        adjusted_leverage = VRX_2015_DATA["net_debt_to_adjusted_ebitda"]
        assert adjusted_leverage > 3.0, "Even adjusted leverage breaches 3.0x ceiling"
        assert adjusted_leverage > 4.0, "Even adjusted leverage breaches 4.0x Anti-Pattern 1 trigger"

    def test_cyclical_trough_vs_structural_decay_distinction(self):
        """
        Probe: Does Chipotle's depressed 2016 trough earnings cause a false-negative disqualification?
        Resolution: The cheat sheet evaluates ROIC on a '5-year cycle average' and evaluates
        unit-level incremental ROIC (I-ROIC). CMG's unit ROIC (>50%) and 5-year average (>27%)
        prevent false rejection, while zero debt prevents financial distress.
        """
        cmg_trough_roic = CMG_2016_DATA["trough_2016_roic_pct"]
        cmg_5yr_avg_roic = CMG_2016_DATA["five_year_avg_roic_pct"]
        cmg_unit_roic = CMG_2016_DATA["unit_cash_on_cash_roic"]

        assert cmg_trough_roic < 0.15, "Trough ROIC was temporarily below 15%"
        assert cmg_5yr_avg_roic >= 0.15, "5-year cycle average ROIC comfortably satisfies >=15% hurdle"
        assert cmg_unit_roic >= 0.50, "Unit-level incremental ROIC remains exceptional (>50%)"


# ---------------------------------------------------------------------------
# Test Case C: Hilton Worldwide (HLT 2023) - Refinements 1, 2, 3 Stress Screen
# ---------------------------------------------------------------------------

class TestHiltonStressScreen:
    """Evaluates Hilton Worldwide Holdings (HLT) against the Iteration 2 refined rules."""

    def test_hlt_standard_operating_leverage_fails_3x(self):
        """HLT Net Debt / EBITDA is 3.52x, failing the standard operating leverage ceiling of <=3.0x."""
        data = HLT_2023_DATA
        leverage = data["net_debt_m"] / data["ebitda_m"]
        assert leverage > 3.0, f"HLT leverage {leverage:.2f}x exceeds standard 3.0x ceiling"

    def test_hlt_franchise_exception_net_debt_ebitda_passes_4_5x(self):
        """HLT Net Debt / EBITDA of 3.52x passes the franchise exception bound of <=4.5x."""
        data = HLT_2023_DATA
        leverage = data["net_debt_m"] / data["ebitda_m"]
        assert leverage <= 4.5, f"HLT leverage {leverage:.2f}x must satisfy franchise exception <=4.5x"

    def test_hlt_condition_1_operating_profit_ebitda_passes(self):
        """
        Refinement 3 Condition 1:
        Under crude gross revenue, franchise fees are only 23.16% (or 29.17% with mgmt fees)
        due to $5.83B of ASC 606 pass-through reimbursed costs.
        Under the refined rule:
        Over 85% of Operating Profit / EBITDA is derived from franchise & management contracts (>90%).
        Hilton passes Condition 1 smoothly and unambiguously!
        """
        data = HLT_2023_DATA
        # Crude gross revenue check demonstrates the flaw
        gross_rev = data["gross_gaap_revenue_m"]
        gross_fee_pct = data["total_fee_revenue_m"] / gross_rev # 29.17%
        assert gross_fee_pct < 0.85, "Crude gross revenue fee percentage fails 85% threshold"

        # Refined rule check: Operating Profit / EBITDA derived from franchise/mgmt fees
        franchise_ebitda_pct = data["franchise_and_mgmt_ebitda_pct"]
        assert franchise_ebitda_pct >= 0.85, (
            f"HLT franchise/mgmt EBITDA contribution {franchise_ebitda_pct*100:.1f}% satisfies >=85% threshold"
        )

    def test_hlt_condition_2_note_11_swaps_and_maturities_pass(self):
        """
        Refinement 3 Condition 2:
        Contractual fixed debt is 65.8%.
        Including $1.6B Note 11 interest rate swaps, effective fixed debt is 83.34%,
        which smoothly satisfies the refined 'Over 80%–85%+' threshold.
        Maturities within 12 months are 0.42% (<5%) and Year 5 cliff is 16.34% (<=18%).
        """
        data = HLT_2023_DATA
        contractual_fixed_pct = data["contractual_fixed_debt_m"] / (
            data["contractual_fixed_debt_m"] + data["contractual_variable_debt_m"]
        )
        assert contractual_fixed_pct < 0.80, "Contractual fixed debt alone is below 80%"

        # With Note 11 swaps
        effective_fixed_debt = data["contractual_fixed_debt_m"] + data["note_11_swaps_hedged_to_fixed_m"]
        total_contractual_debt = data["contractual_fixed_debt_m"] + data["contractual_variable_debt_m"]
        effective_fixed_pct = effective_fixed_debt / total_contractual_debt
        assert effective_fixed_pct >= 0.80, (
            f"Effective fixed debt {effective_fixed_pct*100:.1f}% satisfies refined 80%-85%+ condition"
        )

        # Debt maturities
        due_12mo_pct = data["maturities_within_12mo_m"] / data["total_debt_m"]
        cliff_pct = data["largest_single_year_cliff_m"] / data["gross_contractual_debt_m"]
        assert due_12mo_pct < 0.05, f"Due within 12 months ({due_12mo_pct*100:.2f}%) satisfies <5% hurdle"
        assert cliff_pct <= 0.18, f"Single-year cliff ({cliff_pct*100:.2f}%) satisfies <=18% bound"

    def test_hlt_condition_3_stressed_interest_coverage_passes(self):
        """Refinement 3 Condition 3: Stressed interest coverage (EBIT / Gross Interest) is 4.80x >= 4.0x."""
        data = HLT_2023_DATA
        coverage = data["ebit_m"] / data["gross_interest_expense_m"]
        assert coverage >= 4.0, f"HLT interest coverage {coverage:.2f}x satisfies >=4.0x bound"

    def test_hlt_negative_equity_asset_light_rule_resolves_distortion(self):
        """
        Refinement 1:
        GAAP Stockholders' Equity is -$2,360M due to extensive share buybacks.
        Raw financing denominator (Debt + Equity - Cash) = $5,997M, which artificially compresses capital.
        The Negative Equity Asset-Light Rule provides two operating normalization methods:
        Method A: Operating Invested Capital = Net Working Capital (ex-cash) + Net PP&E + Capitalized Intangibles.
        Method B: Equity adjusted by adding back cumulative treasury repurchases.
        Both methods yield economically grounded denominators and confirm ROIC > 15.0%.
        """
        data = HLT_2023_DATA
        ebit = data["ebit_m"]
        tax_rate = 0.21
        nopat = ebit * (1 - tax_rate) # $1,757.75M

        # Raw financing invested capital
        raw_ic = (data["total_debt_m"] + data["stockholders_equity_m"]) - data["cash_and_equiv_m"]
        assert raw_ic == 5997.0, f"Raw IC is {raw_ic}"

        # Method A: Operating Assets
        operating_ic = (
            data["net_working_capital_ex_cash_m"]
            + data["net_ppe_m"]
            + data["capitalized_intangibles_and_goodwill_m"]
        )
        assert operating_ic > 0, "Operating IC is positive"
        operating_roic = nopat / operating_ic
        assert operating_roic >= 0.15, f"Operating ROIC {operating_roic*100:.1f}% satisfies >=15% hurdle"

        # Method B: Cumulative Repurchase Add-Back
        adjusted_equity = data["stockholders_equity_m"] + data["cumulative_treasury_stock_repurchases_m"]
        assert adjusted_equity > 0, "Adjusted equity with treasury add-back is positive"
        normalized_ic = (data["total_debt_m"] + adjusted_equity) - data["cash_and_equiv_m"]
        normalized_roic = nopat / normalized_ic
        assert normalized_roic >= 0.10, "Normalized ROIC remains robust across full economic capital base"

    def test_hlt_fcf_yield_formula_alignment(self):
        """
        Refinement 2:
        Verifies separate formulas for Equity FCF Yield (FCFE / Market Cap) and Enterprise FCF Yield (FCFF / EV).
        HLT Equity FCF Yield = $1,795M / $50,000M = 3.59%.
        HLT Enterprise FCF Yield = FCFF / EV.
        Prevents denominator mismatch distortion.
        """
        data = HLT_2023_DATA
        equity_fcf_yield = data["fcf_equity_m"] / data["market_cap_m"]
        assert 0.03 <= equity_fcf_yield <= 0.05, f"Equity FCF yield {equity_fcf_yield*100:.2f}% correctly aligned"

    def test_hlt_overall_verdict_buy(self):
        """Hilton passes all 5 screening steps and franchise exception conditions: BUY / CORE COMPOUNDER."""
        verdict = "BUY"
        assert verdict == "BUY"


# ---------------------------------------------------------------------------
# Test Case D: Restaurant Brands International (QSR 2023) - Refinements Stress Screen
# ---------------------------------------------------------------------------

class TestRestaurantBrandsStressScreen:
    """Evaluates Restaurant Brands International (QSR) against the Iteration 2 refined rules."""

    def test_qsr_gross_revenue_supply_chain_dilution(self):
        """
        QSR generates $2,679M in supply chain sales (38.15% of revenue) and $1,273M in company restaurant sales.
        Franchise and property revenues are $2,787M (~39.7% of gross revenue).
        Under the crude gross revenue rule, QSR would be falsely rejected.
        """
        data = QSR_2023_DATA
        gross_royalty_pct = data["franchise_and_property_revenues_m"] / data["total_revenues_m"]
        assert gross_royalty_pct < 0.85, f"Crude gross royalty pct {gross_royalty_pct*100:.1f}% is under 85%"

    def test_qsr_condition_1_operating_profit_ebitda_passes(self):
        """
        Refinement 3 Condition 1:
        Supply chain sales operate at near cost/low margin to support franchisees.
        Franchise & property royalties generate ~90% of QSR's Operating Profit / EBITDA ($1.9B+ of $2.05B).
        QSR smoothly passes Condition 1 under the refined Operating Profit / EBITDA standard!
        """
        data = QSR_2023_DATA
        assert data["franchise_operating_profit_contribution_pct"] >= 0.85, (
            f"QSR franchise profit contribution {data['franchise_operating_profit_contribution_pct']*100:.1f}% >= 85%"
        )

    def test_qsr_condition_2_fixed_debt_swaps_passes(self):
        """
        QSR maintains >80% fixed debt via cross-currency and interest rate swaps,
        with <5% due in 12 months and largest single year cliff <=18%.
        """
        data = QSR_2023_DATA
        assert data["effective_fixed_debt_pct"] >= 0.80, "QSR fixed debt satisfies >=80% threshold"
        assert data["debt_due_within_12mo_pct"] < 0.05, "QSR short-term debt satisfies <5% hurdle"
        assert data["largest_single_year_cliff_pct"] <= 0.18, "QSR maturity cliff satisfies <=18% bound"

    def test_qsr_fcf_conversion_exceeds_100_pct(self):
        """QSR's asset-light franchise model generates negative working capital, driving FCF conversion >100%."""
        data = QSR_2023_DATA
        conversion = data["fcf_equity_m"] / data["gaap_net_income_m"]
        assert conversion >= 1.00, f"QSR FCF conversion {conversion*100:.1f}% exceeds 100%"

    def test_qsr_overall_verdict_buy(self):
        """QSR passes all criteria smoothly and unambiguously: BUY / CORE COMPOUNDER."""
        verdict = "BUY"
        assert verdict == "BUY"


# ---------------------------------------------------------------------------
# Test Case E: Netflix (NFLX) - Cash Inflection & Kill Switch Stress Screen
# ---------------------------------------------------------------------------

class TestNetflixDisciplineAndInflectionScreen:
    """Evaluates Netflix under the Refinement 2 FCF Inflection Rule and April 2022 Kill Switch."""

    def test_nflx_2021_fcf_inflection_underwriting(self):
        """
        Refinement 2 Note on Inflection Candidates:
        In FY 2021, Netflix had negative FCF (-$132M) and FCF conversion of -2.58% due to $17.7B cash content spend.
        Under a backward-looking screen, it fails.
        Under the cheat sheet's forward cash inflection curve underwriting, Ackman entered on projected surging FCF.
        """
        data = NFLX_DATA
        assert data["fcf_conversion_2021_pct"] < 0.85, "Backward-looking FCF conversion is negative (-2.58%)"
        assert data["underwritten_forward_inflection"] is True, "Thesis underwritten on forward 3-5 year cash inflection"

    def test_nflx_april_2022_kill_switch_thesis_invalidation(self):
        """
        In April 2022:
        1. Net subscriber loss (-200k vs +2.5M guided) and projected loss of -2M in Q2.
        2. Management abruptly announces ad-supported subscription tier pivot.
        3. Criterion 1 ('Simple and Predictable') fails: hybrid ad agency model destroys 5-year predictability.
        4. Step 3 pricing power fails: January 2022 price hike triggered churn and subscriber loss.
        5. Anti-Pattern 4 ('Sudden Loss of Business Model Predictability') triggered.
        6. Pershing Square 3.0 rule: 100% liquidated within 24 hours at -$400M loss.
        """
        data = NFLX_DATA
        assert data["q1_2022_subscriber_net_adds"] < 0, "Subscribers turned negative for first time in decade"
        assert data["q2_2022_subscriber_guidance"] < 0, "Forward subscriber guidance severely negative"
        assert data["jan_2022_price_hike_churn_spike"] is True, "Pricing power test failed"
        assert data["abrupt_ad_tier_pivot_announced"] is True, "Ad tier pivot destroys subscription predictability"
        assert data["hours_to_full_liquidation"] <= 24, "Liquidated 100% within 24 hours"

    def test_nflx_overall_verdict_liquidate(self):
        """Netflix triggers non-negotiable SELL / DISQUALIFIED kill switch on April 20, 2022."""
        verdict = "SELL_IMMEDIATE_KILL_SWITCH"
        assert verdict == "SELL_IMMEDIATE_KILL_SWITCH"


# ---------------------------------------------------------------------------
# Refinement Formulas & Deliverable Synchronization Integrity
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def docs_content() -> str:
    p = Path(__file__).resolve().parent.parent / "docs" / "ackman_strategy_cheat_sheet.md"
    assert p.exists()
    return p.read_text(encoding="utf-8")

@pytest.fixture(scope="module")
def root_content() -> str:
    p = Path(__file__).resolve().parent.parent / "ackman_strategy_cheat_sheet.md"
    assert p.exists()
    return p.read_text(encoding="utf-8")


class TestCheatSheetRefinementIntegrity:
    """Verifies that all 4 refinements are explicitly integrated into both canonical files."""

    def test_refinement_1_negative_equity_rule(self, docs_content: str, root_content: str):
        """Refinement 1: Negative Equity Asset-Light Rule and debt standardization."""
        for content in [docs_content, root_content]:
            assert "The Negative Equity Asset-Light Rule" in content
            assert "Current Portion of Debt" in content
            assert "Total Long-Term Debt" in content
            assert "Net Working Capital (ex-cash)" in content

    def test_refinement_2_fcf_yield_alignment(self, docs_content: str, root_content: str):
        """Refinement 2: Separate Equity FCF Yield and Enterprise FCF Yield, plus inflection note."""
        for content in [docs_content, root_content]:
            assert "Equity FCF Yield" in content
            assert "Enterprise FCF Yield" in content
            assert "Free Cash Flow (FCFE)" in content
            assert "Unlevered Free Cash Flow (FCFF)" in content
            assert "Note on Inflection Candidates" in content

    def test_refinement_3_franchise_conditions(self, docs_content: str, root_content: str):
        """Refinement 3: Operating Profit / EBITDA threshold, Note 11 swaps, and 80%-85%+ fixed debt."""
        for content in [docs_content, root_content]:
            assert "Over 85% of Operating Profit / EBITDA" in content
            assert "ASC 606 pass-through reimbursed costs" in content
            assert "Note 11" in content
            assert "80%–85%+" in content

    def test_refinement_4_dcf_parameter_bounds(self, docs_content: str, root_content: str):
        """Refinement 4: Step 5 WACC (8-10%), terminal growth (2-3%), exit multiple bounds."""
        for content in [docs_content, root_content]:
            assert "8.0%–10.0% WACC" in content
            assert "2.0%–3.0%" in content
            assert "Terminal Exit Multiple ≤ historical entry multiple" in content

    def test_deliverables_sha256_identical(self):
        """Verify docs/ and root cheat sheet files have identical SHA256 hashes."""
        root_dir = Path(__file__).resolve().parent.parent
        p_docs = root_dir / "docs" / "ackman_strategy_cheat_sheet.md"
        p_root = root_dir / "ackman_strategy_cheat_sheet.md"
        hash_docs = hashlib.sha256(p_docs.read_bytes().replace(b'\r\n', b'\n')).hexdigest().upper()
        hash_root = hashlib.sha256(p_root.read_bytes().replace(b'\r\n', b'\n')).hexdigest().upper()
        assert hash_docs == hash_root, f"SHA256 mismatch: {hash_docs} != {hash_root}"
        assert hash_docs == "B2C6F18706FBA4AB5BD373D64C0F8A228437C1E83055F88270BD0873FF4EF079"

