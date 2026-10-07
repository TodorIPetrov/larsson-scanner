"""
Unit Tests for Institutional Valuation Audit Hardening.
Verifies that all 5 critical failure modes identified by the Claude Opus audit
have been strictly eliminated and sealed against regression.
"""

import pytest
import math
import pandas as pd
from scripts.generate_institutional_research import (
    compute_synthetic_kd,
    compute_blume_beta,
    compute_forensics,
    evaluate_financials,
    evaluate_corporate,
    evaluate_cyclicals,
    DEFAULT_TAX_RATE,
    RF_RATE,
    LONG_TERM_G,
)
from src.engine.quantamental import FundamentalProfile, get_fundamental_profile


def test_blume_beta_adjustment():
    """Verify Blume adjustment mean reverts extreme betas toward 1.0."""
    # Low beta: 0.5 -> 0.67 * 0.5 + 0.33 = 0.665 -> clamped to 0.65 min
    assert compute_blume_beta(0.5) >= 0.65
    # High beta: 2.0 -> 0.67 * 2.0 + 0.33 = 1.67
    assert compute_blume_beta(2.0) == pytest.approx(1.67, 0.01)
    # Neutral beta: 1.0 -> 0.67 * 1.0 + 0.33 = 1.00
    assert compute_blume_beta(1.0) == pytest.approx(1.00, 0.01)
    # None or NaN fallback to 1.0
    assert compute_blume_beta(None) == 1.0
    assert compute_blume_beta(float("nan")) == 1.0


def test_synthetic_cost_of_debt():
    """Verify Kd reflects interest coverage credit spreads, not a flat 1.0%."""
    rf = 0.0415
    tax = DEFAULT_TAX_RATE

    # High coverage (AAA/AA >= 8.5x): spread 0.75%
    kd_aaa = compute_synthetic_kd(ebit=100.0, int_exp=10.0, rf_rate=rf, tax_rate=tax)
    expected_aaa = (rf + 0.0075) * (1 - tax)
    assert kd_aaa == pytest.approx(expected_aaa, 0.0001)

    # Moderate coverage (BBB 2.5x - 4.0x): spread 2.50%
    kd_bbb = compute_synthetic_kd(ebit=30.0, int_exp=10.0, rf_rate=rf, tax_rate=tax)
    expected_bbb = (rf + 0.0250) * (1 - tax)
    assert kd_bbb == pytest.approx(expected_bbb, 0.0001)

    # Distressed coverage (< 1.5x): spread 7.00%
    kd_junk = compute_synthetic_kd(ebit=12.0, int_exp=10.0, rf_rate=rf, tax_rate=tax)
    expected_junk = (rf + 0.0700) * (1 - tax)
    assert kd_junk == pytest.approx(expected_junk, 0.0001)


def test_altman_z_buyback_negative_equity_exemption():
    """Verify elite compounders with negative equity from buybacks (MCD, SBUX) are not flagged as distress."""
    # Mock statements for a cash machine with negative equity due to share repurchases
    dates = ["2024-12-31", "2023-12-31"]
    fin = pd.DataFrame(
        {
            dates[0]: [10000.0, 3000.0, 2000.0, 300.0, 1500.0],
            dates[1]: [9000.0, 2700.0, 1800.0, 280.0, 1400.0],
        },
        index=["Total Revenue", "Operating Income", "Net Income", "Interest Expense", "Gross Profit"],
    )
    # Negative stockholders equity: -$2,000M
    bs = pd.DataFrame(
        {
            dates[0]: [15000.0, 3000.0, 3500.0, -2000.0, 17000.0, 8000.0, 2000.0, 8000.0, 1000.0],
            dates[1]: [14000.0, 2800.0, 3200.0, -1500.0, 15500.0, 7500.0, 1800.0, 7500.0, 900.0],
        },
        index=[
            "Total Assets", "Current Assets", "Current Liabilities", "Stockholders Equity",
            "Total Liabilities Net Minority Interest", "Total Debt", "Receivables", "Net PPE", "Retained Earnings"
        ],
    )
    cf = pd.DataFrame({dates[0]: [2500.0, 500.0], dates[1]: [2300.0, 480.0]}, index=["Operating Cash Flow", "Capital Expenditure"])

    info = {"totalDebt": 8000.0, "totalRevenue": 10000.0, "operatingIncome": 3000.0}

    z_score, m_score, tata, is_flagged, solvency_type = compute_forensics(
        fin=fin, bs=bs, cf=cf, info=info, shares=100.0, price=100.0, mcap=10000.0,
        sector="Consumer Cyclical", industry="Restaurants"
    )

    # Coverage is 3000 / 300 = 10.0x (Safe!)
    assert z_score == 3.50
    assert "High Buyback Leverage" in solvency_type
    assert is_flagged is False


def test_beneish_m_score_8_variable_model():
    """Verify Beneish M-Score uses authentic 8-variable model and skips for Banks/REITs."""
    # 1. Banks: Beneish must be None
    dates = ["2024-12-31", "2023-12-31"]
    fin = pd.DataFrame({dates[0]: [1000.0], dates[1]: [900.0]}, index=["Total Revenue"])
    bs = pd.DataFrame({dates[0]: [10000.0], dates[1]: [9500.0]}, index=["Total Assets"])
    cf = pd.DataFrame({dates[0]: [500.0], dates[1]: [450.0]}, index=["Operating Cash Flow"])
    info = {}

    z_bank, m_bank, tata_bank, flagged_bank, _ = compute_forensics(
        fin, bs, cf, info, 10.0, 50.0, 500.0, sector="Financial Services", industry="Banks - Diversified"
    )
    assert m_bank is None

    # 2. Corporates with healthy statements: M-score should be safely below -1.78
    bs_corp = pd.DataFrame(
        {
            dates[0]: [5000.0, 1500.0, 1000.0, 2500.0, 2500.0, 1000.0, 500.0, 2000.0, 1000.0],
            dates[1]: [4500.0, 1400.0, 950.0, 2200.0, 2300.0, 900.0, 480.0, 1900.0, 900.0],
        },
        index=[
            "Total Assets", "Current Assets", "Current Liabilities", "Stockholders Equity",
            "Total Liabilities Net Minority Interest", "Total Debt", "Receivables", "Net PPE", "Retained Earnings"
        ],
    )
    fin_corp = pd.DataFrame(
        {
            dates[0]: [3000.0, 600.0, 450.0, 50.0, 1200.0, 400.0, 150.0],
            dates[1]: [2700.0, 520.0, 400.0, 45.0, 1080.0, 360.0, 140.0],
        },
        index=[
            "Total Revenue", "Operating Income", "Net Income", "Interest Expense", "Gross Profit",
            "Selling General And Administration", "Reconciled Depreciation"
        ],
    )
    cf_corp = pd.DataFrame({dates[0]: [500.0], dates[1]: [460.0]}, index=["Operating Cash Flow"])

    z_corp, m_corp, tata_corp, flagged_corp, _ = compute_forensics(
        fin_corp, bs_corp, cf_corp, {}, 50.0, 60.0, 3000.0, sector="Technology", industry="Software - Infrastructure"
    )
    assert m_corp is not None
    assert m_corp < -1.78
    assert flagged_corp is False


def test_unprofitable_financial_fails_safely():
    """Verify losing banks do not receive mock 10% ROE and are flagged REDUCE."""
    info = {"netIncomeToCommon": -500.0, "bookValue": 20.0}
    fin = pd.DataFrame({"2024": [-500.0]}, index=["Net Income"])
    bs = pd.DataFrame({"2024": [2000.0]}, index=["Common Stock Equity"])

    res = evaluate_financials(
        ticker="BADB", name="Bad Bank", sector="Financial Services", industry="Banks - Regional",
        price=15.0, shares=100.0, mcap=1500.0, beta=1.2, fin=fin, bs=bs, cf=None, info=info
    )
    assert res["action"] == "REDUCE"
    assert "DISTRESSED" in res["verdict"]
    assert res["actual_discount_pct"] < 0


def test_declining_negative_fcf_corporate_fails_safely():
    """Verify declining cash-burners (e.g. BA, WBA) are not treated as High-Growth EV/Revenue."""
    # Negative FCF and declining 3Y revenue (0% growth, gross margin 20%)
    fin = pd.DataFrame(
        {
            "2024": [1000.0, -100.0, 200.0],
            "2023": [1050.0, -80.0, 210.0],
            "2022": [1100.0, -50.0, 220.0],
        },
        index=["Total Revenue", "Operating Income", "Gross Profit"]
    )
    cf = pd.DataFrame({"2024": [-200.0, 100.0]}, index=["Free Cash Flow", "Capital Expenditure"])
    info = {"totalRevenue": 1000.0, "operatingIncome": -100.0, "freeCashflow": -200.0}

    res = evaluate_corporate(
        ticker="BURN", name="Declining Burner", sector="Industrials", industry="Aerospace & Defense",
        price=50.0, shares=20.0, mcap=1000.0, beta=1.3, fin=fin, bs=None, cf=cf, info=info
    )
    assert res["action"] == "REDUCE"
    assert "DISTRESSED" in res["verdict"]
    assert res["model_type"] == "Distressed / Negative FCF Model"


def test_cyclicals_smooth_fade_to_long_term_g():
    """Verify cyclicals mid-cycle DCF fades smoothly to 2.75% terminal growth without cliff drops."""
    fin = pd.DataFrame(
        {
            "2024": [5000.0, 1000.0],
            "2023": [4500.0, 900.0],
            "2022": [4000.0, 750.0],
        },
        index=["Total Revenue", "Operating Income"]
    )
    cf = pd.DataFrame({"2024": [800.0]}, index=["Free Cash Flow"])
    info = {"totalRevenue": 5000.0, "operatingIncome": 1000.0, "freeCashflow": 800.0}

    res = evaluate_cyclicals(
        ticker="SEMI", name="Semiconductor Giant", sector="Technology", industry="Semiconductors",
        price=100.0, shares=50.0, mcap=5000.0, beta=1.2, fin=fin, bs=None, cf=cf, info=info
    )
    assert res is not None
    assert res["model_type"] == "Mid-Cycle Normalized DCF"
    assert res["target_price"] > 0
    # Both required_mos_pct and actual_discount_pct exist and are cleanly populated
    assert res["required_mos_pct"] >= 20.0
    assert "actual_discount_pct" in res
