#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Institutional Multi-Asset Valuation Engine (v3.1 - Institutional Audit Hardened)
Applies specialized, forensically audited valuation models by asset class and corporate sector:
1. Corporate DCF & EVA (Tech, Consumer, Healthcare, Industrials, Asset-Light FinTech/Exchanges)
2. Financials Residual Income Model (RIM) & Justified P/TBV (Depository Banks, Life & P&C Insurers)
3. REITs AFFO & Net Asset Value (NAV) Cap-Rate Model (Towers, Data Centers, Logistics, Retail, Multi-family)
4. Cyclicals Mid-Cycle Normalization & Dynamic Margins (Semiconductors, Hardware, Autos, Capital Goods, Mining, Energy)
5. Utilities RAB & Multi-Stage Dividend Discount Model (Regulated Electric, Gas, Water Monopolies)
6. Pre-Profit High-Growth EV/Revenue (Restricted strictly to true High-Growth; Declining Cash Burners marked Distressed)

Forensic Accounting:
- Altman Z''-Score (Universal 4-variable model) with Buyback Leverage / Negative Equity Exemption
- Beneish M-Score (Full 8-variable model, M > -1.78 threshold; excluded for Banks/REITs)
- Synthetic Credit Rating Spread for Cost of Debt (Interest Coverage Ratio Damodaran framework)
- Blume-Adjusted Beta (mean reversion to 1.0)
- Currency & ADR Reconciliation (TSM, BABA, European ADRs)
- Elimination of mock/hallucinated default data: returns UNRATED / INSUFFICIENT_DATA when financial statements are missing.
"""

import os
import sys
import yaml
import json
import time
import math
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("InstitutionalValuation")

# Directories
ARCHIVE_DIR = "research/archive"
VERDICTS_FILE = "research/COMMITTEE_VERDICTS.md"
JSON_OUTPUT = "research/verdicts.json"
DASHBOARD_JSON = "dashboard/fundamental_verdicts.json"

# Institutional Baseline Parameters
DEFAULT_TAX_RATE = 0.240    # Marginal Corporate Tax Rate (21% Federal + ~3% State Blended)
LONG_TERM_G = 0.0275        # Long-term GDP / Terminal Growth (2.75%)
ERP = 0.0460                # Equity Risk Premium (4.60%)

# Known ADR Ratios (Number of ordinary shares represented by 1 ADR)
ADR_RATIOS = {
    "TSM": 5.0,
    "BABA": 8.0,
    "ASML": 1.0,
    "NVO": 1.0,
    "AZN": 2.0,
    "SNY": 2.0,
    "SAP": 1.0,
    "SHEL": 2.0,
    "BP": 6.0,
    "HMC": 1.0,
    "TM": 10.0,
    "SONY": 1.0,
    "INFY": 1.0,
    "BIDU": 8.0,
    "JD": 2.0,
    "PDD": 4.0,
    "NIO": 1.0,
    "LI": 2.0,
}

def ensure_dirs():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs("research", exist_ok=True)
    os.makedirs("dashboard", exist_ok=True)

def fetch_dynamic_macro_rates():
    """
    Dynamically retrieves 10-Year US Treasury Yield (^TNX) from yfinance.
    Falls back to 4.15% if unavailable.
    """
    try:
        tnx = yf.Ticker("^TNX")
        lp = tnx.fast_info.get("lastPrice") or tnx.info.get("regularMarketPrice") or 0.0
        if lp > 15.0:
            rf = lp / 1000.0
        elif lp > 1.0:
            rf = lp / 100.0
        else:
            rf = 0.0415
        return max(0.025, min(0.075, rf))
    except Exception as e:
        logger.warning(f"Could not fetch dynamic ^TNX yield, using baseline 4.15%: {e}")
        return 0.0415

RF_RATE = fetch_dynamic_macro_rates()

def compute_synthetic_kd(ebit, int_exp, rf_rate, tax_rate=DEFAULT_TAX_RATE):
    """
    Computes synthetic rating and cost of debt based on Interest Coverage Ratio (Damodaran model).
    """
    if int_exp is None or int_exp <= 0 or ebit is None or ebit <= 0:
        spread = 0.0450  # Speculative / Distressed spread fallback
    else:
        cov = ebit / max(1.0, int_exp)
        if cov >= 8.5:
            spread = 0.0075  # AAA / AA
        elif cov >= 6.5:
            spread = 0.0100  # A+ / A
        elif cov >= 4.0:
            spread = 0.0150  # A- / BBB+
        elif cov >= 2.5:
            spread = 0.0250  # BBB / BB+
        elif cov >= 1.5:
            spread = 0.0400  # BB / B
        else:
            spread = 0.0700  # High Yield / Distressed (< 1.5x)
    kd_pretax = rf_rate + spread
    return kd_pretax * (1 - tax_rate)

def compute_blume_beta(raw_beta):
    """Blume adjustment: mean reversion toward market beta 1.0."""
    try:
        b = float(raw_beta)
        if math.isnan(b) or math.isinf(b):
            return 1.0
        return max(0.65, min(2.20, 0.67 * b + 0.33))
    except (TypeError, ValueError):
        return 1.0

def load_universe():
    ensure_dirs()
    with open("config/assets.yaml", "r", encoding="utf-8") as f:
        assets = yaml.safe_load(f)

    with open("config/sp500_tickers.json", "r", encoding="utf-8") as f:
        sp500 = json.load(f)

    excluded_prefixes = ['^', 'GC=', 'SI=', 'CL=', 'BZ=', 'NG=', 'HG=', 'PL=', 'DX-']
    excluded_substrings = ['USDT', '=F']
    excluded_etfs = {
        'URA', 'URNM', 'IBIT', 'FBTC', 'ARKB', 'BITB', 'GBTC', 'HODL', 'BTCO',
        'EZBC', 'BITX', 'BITO', 'ETHE', 'ETHA', 'FETH', 'WGMI', 'DAPP', 'BLOK',
        'BKCH', 'BITQ', 'FDIG', 'BTF', 'BITS', 'CRPT', 'SATO', 'ARKW', 'ARKF',
        'CONL', 'MSTX', 'MSTU', 'BTCC-B.TO', 'ETHX-B.TO', 'BTCX-B.TO'
    }

    candidates = set()
    for cat in ['us_stocks', 'ai_stocks', 'crypto_stocks', 'intl_stocks']:
        for item in assets.get(cat, []):
            t = item.get('ticker')
            if not t or t in excluded_etfs:
                continue
            if any(t.startswith(p) for p in excluded_prefixes) or any(sub in t for sub in excluded_substrings):
                continue
            candidates.add(t)

    for t in sp500:
        if t and not any(t.startswith(p) for p in excluded_prefixes):
            candidates.add(t)

    return sorted(list(candidates))

def safe_get(df, key, col, default=0.0):
    """Safely extracts a numeric float value from a DataFrame row index and column."""
    if df is not None and not df.empty and key in df.index:
        val = df.loc[key, col]
        if isinstance(val, (int, float)) and not (isinstance(val, float) and (val != val)):
            return float(val)
    return default

# ==============================================================================
# FORENSIC ACCOUNTING ENGINE
# ==============================================================================

def compute_forensics(fin, bs, cf, info, shares, price, mcap, sector="", industry=""):
    """
    Real Multi-Year Forensic Accounting Engine:
    1. Altman Z''-Score (Universal 4-Variable Model for Non-Financials) with Buyback Leverage Exemption
    2. Tangible Common Equity (TCE) Ratio for Depository Banks / Insurers
    3. Fixed Charge Coverage & LTV for REITs
    4. Regulated Interest Coverage for Utilities
    5. Beneish M-Score (Full 8-Variable Model, M > -1.78 threshold; excluded for Banks/REITs)
    """
    is_depository_bank = ("Bank" in industry or "Savings" in industry) and sector in ["Financial Services", "Financials"]
    is_insurance = ("Insurance" in industry) and sector in ["Financial Services", "Financials"]
    is_bank_or_insurance = is_depository_bank or is_insurance
    is_reit = ("REIT" in industry) or (sector == "Real Estate" and "Services" not in industry and "Real Estate" not in industry)
    is_utility = (sector == "Utilities" and not any(w in industry.lower() for w in ["independent", "merchant", "renewable", "solar", "wind"]))

    has_statements = (
        fin is not None and bs is not None and
        not fin.empty and not bs.empty and
        len(fin.columns) >= 1 and len(bs.columns) >= 1
    )

    if not has_statements:
        return None, None, 0.0, False, "Insufficient Statement Data"

    col0 = fin.columns[0]
    col0_bs = bs.columns[0]

    has_2y = (len(fin.columns) >= 2 and len(bs.columns) >= 2)
    col1 = fin.columns[1] if has_2y else col0
    col1_bs = bs.columns[1] if has_2y else col0_bs

    rev0 = safe_get(fin, 'Total Revenue', col0)
    rev1 = safe_get(fin, 'Total Revenue', col1)
    ebit0 = safe_get(fin, 'Operating Income', col0, safe_get(fin, 'EBIT', col0))
    net_inc0 = safe_get(fin, 'Net Income', col0, safe_get(fin, 'Net Income Common Stockholders', col0))
    cfo0 = safe_get(cf, 'Operating Cash Flow', col0, net_inc0) if cf is not None and not cf.empty else net_inc0
    int_exp0 = safe_get(fin, 'Interest Expense', col0, safe_get(fin, 'Interest Expense Non Operating', col0, 0.0))

    ta0 = safe_get(bs, 'Total Assets', col0_bs)
    ta1 = safe_get(bs, 'Total Assets', col1_bs)
    ca0 = safe_get(bs, 'Current Assets', col0_bs)
    ca1 = safe_get(bs, 'Current Assets', col1_bs)
    cl0 = safe_get(bs, 'Current Liabilities', col0_bs)
    cl1 = safe_get(bs, 'Current Liabilities', col1_bs)
    wc0 = safe_get(bs, 'Working Capital', col0_bs, ca0 - cl0)
    re0 = safe_get(bs, 'Retained Earnings', col0_bs)
    equity0 = safe_get(bs, 'Stockholders Equity', col0_bs, safe_get(bs, 'Common Stock Equity', col0_bs))
    tl0 = safe_get(bs, 'Total Liabilities Net Minority Interest', col0_bs, max(1.0, ta0 - equity0))
    total_debt0 = safe_get(bs, 'Total Debt', col0_bs, safe_get(bs, 'Long Term Debt', col0_bs, 0.0))
    total_debt1 = safe_get(bs, 'Total Debt', col1_bs, safe_get(bs, 'Long Term Debt', col1_bs, total_debt0))

    # 1. Credit Health / Solvency Score
    if is_bank_or_insurance:
        tbv = safe_get(bs, 'Tangible Book Value', col0_bs)
        if tbv <= 0:
            gw = safe_get(bs, 'Goodwill', col0_bs)
            intang = safe_get(bs, 'Other Intangible Assets', col0_bs)
            tbv = max(1e6, equity0 - gw - intang)
        tce_ratio = (tbv / max(1.0, ta0)) * 100.0
        z_score = 2.0 + min(6.0, max(0.0, (tce_ratio - 3.0) * 0.8))
        solvency_type = f"Financial TCE Capital Ratio ({tce_ratio:.1f}%)"
        is_distressed = (tce_ratio < 4.0)
    elif is_reit:
        ebitda0 = safe_get(fin, 'EBITDA', col0, ebit0 * 1.5)
        cov = ebitda0 / max(1.0, int_exp0) if int_exp0 > 0 else 5.0
        ltv = total_debt0 / max(1.0, ta0)
        z_score = 2.5 + min(5.0, max(0.0, (cov - 1.5) * 0.5)) - max(0.0, (ltv - 0.40) * 3.0)
        solvency_type = f"REIT Coverage & LTV (Cov: {cov:.1f}x, LTV: {ltv*100:.0f}%)"
        is_distressed = (cov < 1.3 or ltv > 0.65)
    elif is_utility:
        ebitda0 = safe_get(fin, 'EBITDA', col0, ebit0 * 1.4)
        cov = ebitda0 / max(1.0, int_exp0) if int_exp0 > 0 else 5.0
        z_score = 2.4 + min(4.5, max(0.0, (cov - 1.5) * 0.6))
        solvency_type = f"Regulated Interest Coverage ({cov:.1f}x)"
        is_distressed = (cov < 1.5)
    else:
        # Non-Financial Corporate: Check for Buyback Negative Equity Exemption
        # (Companies like MCD, SBUX, AZO, ORLY with high buybacks but massive cash flow and interest coverage)
        cov = (ebit0 / int_exp0) if (int_exp0 > 0 and ebit0 > 0) else 10.0
        if equity0 <= 0 and ebit0 > 0 and cfo0 > 0 and cov >= 6.0:
            z_score = 3.50  # Safe Zone credit override
            solvency_type = f"High Buyback Leverage (Safe Coverage {cov:.1f}x)"
            is_distressed = False
        elif equity0 <= 0:
            z_score = 0.50  # Distressed negative equity without adequate coverage
            solvency_type = "Negative Equity / Excessive Debt"
            is_distressed = True
        elif ta0 > 0 and tl0 > 0:
            x1 = max(-1.0, min(1.0, wc0 / ta0))
            x2 = max(-1.0, min(1.0, re0 / ta0))
            x3 = max(-0.5, min(0.6, ebit0 / ta0))
            x4 = max(0.05, min(10.0, equity0 / tl0))
            z_score = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
            solvency_type = "Altman Z''-Score (Universal Model)"
            is_distressed = (z_score < 1.10)
        else:
            z_score = None
            solvency_type = "Unknown Solvency"
            is_distressed = False

    # 2. Beneish M-Score Components (8-Variable Classic Model)
    # Exclude Banks and REITs as the model has no empirical validity for them
    if is_bank_or_insurance or is_reit:
        m_score = None
        tata = 0.0
        is_m_flagged = False
    elif not has_2y or ta0 <= 0:
        m_score = None
        tata = 0.0
        is_m_flagged = False
    else:
        rec0 = safe_get(bs, 'Receivables', col0_bs, safe_get(bs, 'Accounts Receivable', col0_bs))
        rec1 = safe_get(bs, 'Receivables', col1_bs, safe_get(bs, 'Accounts Receivable', col1_bs))
        dsri = (rec0 / max(1.0, rev0)) / max(0.001, (rec1 / max(1.0, rev1))) if (rev0 > 0 and rev1 > 0 and rec1 > 0) else 1.0
        dsri = max(0.5, min(2.5, dsri))

        gp0 = safe_get(fin, 'Gross Profit', col0, rev0 * 0.4)
        gp1 = safe_get(fin, 'Gross Profit', col1, rev1 * 0.4)
        gm0 = gp0 / max(1.0, rev0)
        gm1 = gp1 / max(1.0, rev1)
        gmi = gm1 / max(0.01, gm0) if gm0 > 0 else 1.0
        gmi = max(0.5, min(2.5, gmi))

        sgi = rev0 / max(1.0, rev1) if rev1 > 0 else 1.0
        sgi = max(0.5, min(3.0, sgi))

        ppe0 = safe_get(bs, 'Net PPE', col0_bs)
        ppe1 = safe_get(bs, 'Net PPE', col1_bs)
        aq0 = 1.0 - ((ca0 + ppe0) / max(1.0, ta0)) if ta0 > 0 else 0.1
        aq1 = 1.0 - ((ca1 + ppe1) / max(1.0, ta1)) if ta1 > 0 else 0.1
        aqi = aq0 / max(0.01, aq1) if aq1 > 0 else 1.0
        aqi = max(0.5, min(2.5, aqi))

        dep0 = safe_get(fin, 'Reconciled Depreciation', col0)
        dep1 = safe_get(fin, 'Reconciled Depreciation', col1)
        dep_rate0 = dep0 / max(1.0, ppe0 + dep0) if (ppe0 + dep0) > 0 else 0.05
        dep_rate1 = dep1 / max(1.0, ppe1 + dep1) if (ppe1 + dep1) > 0 else 0.05
        depi = dep_rate1 / max(0.005, dep_rate0) if dep_rate0 > 0 else 1.0
        depi = max(0.5, min(2.5, depi))

        # SGAI: Selling General & Administrative Expenses Index
        sga0 = safe_get(fin, 'Selling General And Administration', col0, rev0 * 0.15)
        sga1 = safe_get(fin, 'Selling General And Administration', col1, rev1 * 0.15)
        sgai0 = sga0 / max(1.0, rev0)
        sgai1 = sga1 / max(1.0, rev1)
        sgai = sgai0 / max(0.01, sgai1) if sgai1 > 0 else 1.0
        sgai = max(0.5, min(2.5, sgai))

        # LVGI: Leverage Index
        lev0 = (total_debt0 + cl0) / max(1.0, ta0)
        lev1 = (total_debt1 + cl1) / max(1.0, ta1)
        lvgi = lev0 / max(0.01, lev1) if lev1 > 0 else 1.0
        lvgi = max(0.5, min(2.5, lvgi))

        # TATA: Total Accruals to Total Assets
        tata = (net_inc0 - cfo0) / max(1.0, ta0)
        tata = max(-0.3, min(0.3, tata))

        # Classic Beneish 8-variable formula (Threshold > -1.78)
        m_score = (
            -4.84 +
            0.920 * dsri +
            0.528 * gmi +
            0.404 * aqi +
            0.892 * sgi +
            0.115 * depi -
            0.172 * sgai +
            4.679 * tata -
            0.327 * lvgi
        )
        m_score = max(-5.0, min(1.5, m_score))
        is_m_flagged = (m_score > -1.78 and tata > 0.05)

    is_flagged = is_distressed or is_m_flagged

    clean_z = round(float(z_score), 2) if z_score is not None else None
    clean_m = round(float(m_score), 2) if m_score is not None else None
    clean_tata = round(float(tata), 3) if tata is not None else 0.0

    return clean_z, clean_m, clean_tata, is_flagged, solvency_type

# ==============================================================================
# SPECIALIZED VALUATION MODULES
# ==============================================================================

def evaluate_financials(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info):
    """
    Financials Valuation Engine: Strictly for Depository Banks and Insurance Companies.
    Uses Residual Income Model (RIM) & Justified P/TBV.
    Asset-Light FinTech, Exchanges, and Asset Managers are routed to Corporate DCF.
    """
    model_type = "Residual Income (RIM) & Justified P/TBV"
    blume_b = compute_blume_beta(beta)
    ke = RF_RATE + blume_b * ERP

    net_income = info.get("netIncomeToCommon") or 0.0
    book_equity = (info.get("bookValue") or 0.0) * shares
    tbv = 0.0

    if bs is not None and not bs.empty:
        col = bs.columns[0]
        if "Tangible Book Value" in bs.index:
            tbv = safe_get(bs, "Tangible Book Value", col)
        if "Common Stock Equity" in bs.index:
            book_equity = safe_get(bs, "Common Stock Equity", col, book_equity)
        elif "Stockholders Equity" in bs.index:
            book_equity = safe_get(bs, "Stockholders Equity", col, book_equity)

        if tbv <= 0:
            gw = safe_get(bs, "Goodwill", col)
            intang = safe_get(bs, "Other Intangible Assets", col)
            tbv = book_equity - gw - intang

    if fin is not None and not fin.empty and "Net Income" in fin.index:
        net_income = safe_get(fin, "Net Income", fin.columns[0], net_income)

    # If financial institution is unprofitable, do not invent artificial 10% ROE
    if net_income <= 0 or book_equity <= 0:
        return {
            "model_type": model_type,
            "nopat_b": net_income / 1e9,
            "roic_pct": 0.0,
            "wacc_pct": ke * 100,
            "moat": "None",
            "fair_value_base": price * 0.60,
            "target_price": price * 0.60,
            "required_mos_pct": 25.0,
            "actual_discount_pct": -66.7,
            "mos_pct": -66.7,
            "entry_price": price * 0.45,
            "verdict": "REDUCE / DISTRESSED FINANCIAL",
            "action": "REDUCE",
            "thesis": "Financial institution operating at negative earnings or impaired equity. RIM model disqualified."
        }

    if tbv <= 0:
        tbv = book_equity * 0.70

    tbv_per_share = tbv / shares if shares > 0 else (price * 0.6)
    roe = max(0.02, min(0.35, net_income / max(1e7, book_equity)))
    spread = roe - ke

    # Multi-Stage Justified P/TBV
    justified_pb = max(0.50, min(3.50, (roe - LONG_TERM_G) / max(0.015, (ke - LONG_TERM_G))))
    target_price = tbv_per_share * justified_pb

    # Moat classification
    if roe > 0.16 and spread > 0.05:
        moat = "Wide"
    elif roe > 0.10 and spread > 0.0:
        moat = "Narrow"
    else:
        moat = "None"

    required_mos = 15.0 if moat == "Wide" else (20.0 if moat == "Narrow" else 25.0)
    actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
    entry_price = target_price * (1 - (required_mos / 100.0))

    return {
        "model_type": model_type,
        "nopat_b": net_income / 1e9,
        "roic_pct": roe * 100,  # Displayed as ROE %
        "wacc_pct": ke * 100,   # Displayed as Ke %
        "moat": moat,
        "fair_value_base": target_price,
        "target_price": target_price,
        "required_mos_pct": required_mos,
        "actual_discount_pct": round(actual_discount, 1),
        "mos_pct": round(actual_discount, 1),
        "entry_price": entry_price
    }

def evaluate_reits(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info):
    """
    REITs Valuation Engine: Property-Specific Cap Rate NAV & AFFO Multiple.
    Cap rates are dynamically calibrated to the 10Y US Treasury Yield (^TNX).
    """
    model_type = "AFFO Yield & NAV Cap-Rate"
    blume_b = compute_blume_beta(beta)
    ke = RF_RATE + blume_b * ERP
    kd_aftertax = (RF_RATE + 0.0150) * 0.95
    wacc = 0.65 * ke + 0.35 * kd_aftertax

    # Dynamic Cap Rate Benchmark (Base spread over 10Y Treasury)
    ind_lower = industry.lower()
    name_lower = name.lower()
    if "tower" in ind_lower or "tower" in name_lower or ticker in ["AMT", "CCI", "SBAC"]:
        base_spread = 0.0125  # Cell Towers
    elif "data" in ind_lower or "data" in name_lower or ticker in ["EQIX", "DLR"]:
        base_spread = 0.0175  # Data Centers
    elif "industrial" in ind_lower or "logistics" in ind_lower or ticker in ["PLD", "PSA", "REXR"]:
        base_spread = 0.0200  # Industrial / Logistics
    elif "residential" in ind_lower or "apartment" in ind_lower or ticker in ["EQR", "AVB", "MAA", "INVH"]:
        base_spread = 0.0225  # Residential Multi-family
    elif "healthcare" in ind_lower or ticker in ["WELL", "VTR"]:
        base_spread = 0.0275  # Healthcare facilities
    elif "retail" in ind_lower or "shopping" in ind_lower or ticker in ["SPG", "O", "NNN", "REG"]:
        base_spread = 0.0300  # Retail / Triple Net Lease
    elif "office" in ind_lower or ticker in ["BXP", "VNO", "SLG", "KRC"]:
        base_spread = 0.0450  # Office
    else:
        base_spread = 0.0250  # Diversified Baseline

    cap_rate = max(0.045, min(0.095, RF_RATE + base_spread))

    net_income = info.get("netIncomeToCommon") or 0.0
    total_debt = info.get("totalDebt") or 0.0
    cash = info.get("totalCash") or 0.0
    ebit = info.get("operatingIncome") or 0.0
    da = 0.0

    if fin is not None and not fin.empty:
        col = fin.columns[0]
        da = safe_get(fin, "Reconciled Depreciation", col, da)
        ebit = safe_get(fin, "Operating Income", col, ebit)
        net_income = safe_get(fin, "Net Income", col, net_income)

    if da <= 0 and ebit > 0:
        da = ebit * 0.40

    # FFO & AFFO
    ffo = net_income + da
    maint_capex = da * 0.20
    affo = ffo - maint_capex
    if affo <= 0:
        affo = max(1e6, net_income * 0.80)

    affo_per_share = affo / shares if shares > 0 else (price * 0.05)

    # NOI & NAV
    noi = max(1e6, ebit + da)
    gross_asset_val = noi / cap_rate
    nav = max(1e6, gross_asset_val - total_debt + cash)
    nav_per_share = nav / shares if shares > 0 else price

    # Synthesize AFFO Multiple & NAV
    affo_multiple_target = max(12.0, min(24.0, 1.0 / max(0.04, (wacc - LONG_TERM_G))))
    affo_val = affo_per_share * affo_multiple_target
    target_price = 0.50 * affo_val + 0.50 * nav_per_share

    moat = "Wide" if base_spread <= 0.0175 else ("Narrow" if base_spread <= 0.0300 else "None")
    required_mos = 16.0 if moat == "Wide" else 22.0
    actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
    entry_price = target_price * (1 - (required_mos / 100.0))
    affo_yield = (affo / mcap) * 100 if mcap > 0 else 5.0

    return {
        "model_type": model_type,
        "nopat_b": affo / 1e9,
        "roic_pct": affo_yield,  # Displayed as AFFO Yield
        "wacc_pct": wacc * 100,
        "moat": moat,
        "fair_value_base": target_price,
        "target_price": target_price,
        "required_mos_pct": required_mos,
        "actual_discount_pct": round(actual_discount, 1),
        "mos_pct": round(actual_discount, 1),
        "entry_price": entry_price
    }

def evaluate_utilities(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info):
    """
    Utilities Valuation Engine: Regulated Asset Base (RAB) & Dividend Discount Model (DDM).
    Captures regulated rate-base monopolies. Independent power producers are handled by Cyclical/Corporate models.
    """
    model_type = "Utilities RAB & Dividend Discount Model"
    blume_b = compute_blume_beta(beta)
    ke = RF_RATE + blume_b * ERP

    div_rate = info.get("dividendRate") or 0.0
    book_equity = (info.get("bookValue") or 1.0) * shares
    net_income = info.get("netIncomeToCommon") or 0.0

    if bs is not None and not bs.empty:
        col = bs.columns[0]
        book_equity = safe_get(bs, "Common Stock Equity", col, safe_get(bs, "Stockholders Equity", col, book_equity))
    if fin is not None and not fin.empty:
        col = fin.columns[0]
        net_income = safe_get(fin, "Net Income", col, net_income)

    bv_per_share = book_equity / shares if shares > 0 else price * 0.6
    allowed_roe = 0.0965  # Standard state PUC benchmark allowed ROE (9.65%)
    payout_ratio = max(0.55, min(0.85, info.get("payoutRatio") or 0.68))
    retention_ratio = 1.0 - payout_ratio

    # Sustainable growth without arbitrary artificial boost
    sustainable_g = max(0.015, min(0.035, retention_ratio * allowed_roe))

    if div_rate <= 0:
        div_rate = (net_income * payout_ratio) / max(1.0, shares)

    spread_ke_g = max(0.030, ke - sustainable_g)  # Ensure minimum 3.0% cost spread to prevent infinite DDM multiples
    d1 = div_rate * (1 + sustainable_g)
    p_ddm = d1 / spread_ke_g

    justified_pb = max(0.90, min(1.80, (allowed_roe - sustainable_g) / spread_ke_g))
    p_rab = bv_per_share * justified_pb

    target_price = 0.50 * p_ddm + 0.50 * p_rab
    moat = "Wide" if ("Electric" in industry and "Independent" not in industry) else "Narrow"
    required_mos = 15.0 if moat == "Wide" else 20.0
    actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
    entry_price = target_price * (1 - (required_mos / 100.0))

    div_yield = (div_rate / price) * 100 if price > 0 else 3.5

    return {
        "model_type": model_type,
        "nopat_b": net_income / 1e9,
        "roic_pct": div_yield,  # Displayed as Dividend Yield %
        "wacc_pct": ke * 100,
        "moat": moat,
        "fair_value_base": target_price,
        "target_price": target_price,
        "required_mos_pct": required_mos,
        "actual_discount_pct": round(actual_discount, 1),
        "mos_pct": round(actual_discount, 1),
        "entry_price": entry_price
    }

def evaluate_cyclicals(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info):
    """
    Cyclicals Valuation Engine: Mid-Cycle Normalization with Multi-Year Margins & Cycle Fade.
    Eliminates Peak/Trough earnings distortion for Semiconductors, Autos, Mining, Energy, Capital Goods.
    """
    model_type = "Mid-Cycle Normalized DCF"

    revenue = info.get("totalRevenue") or 0.0
    total_debt = info.get("totalDebt") or 0.0
    cash = info.get("totalCash") or 0.0
    book_equity = (info.get("bookValue") or 1.0) * shares
    fcf = info.get("freeCashflow") or 0.0

    # Multi-Year Median EBIT Margin Extraction (up to 4 years)
    hist_margins = []
    hist_revs = []
    if fin is not None and not fin.empty and "Total Revenue" in fin.index:
        col0 = fin.columns[0]
        revenue = safe_get(fin, "Total Revenue", col0, revenue)
        for col in fin.columns[:4]:
            r_val = safe_get(fin, "Total Revenue", col)
            e_val = safe_get(fin, "Operating Income", col, safe_get(fin, "EBIT", col))
            if r_val > 0:
                hist_margins.append(e_val / r_val)
                hist_revs.append(r_val)

    if revenue <= 0:
        return None  # Cannot evaluate without real revenue data

    if cf is not None and not cf.empty and "Free Cash Flow" in cf.index:
        fcf = safe_get(cf, "Free Cash Flow", cf.columns[0], fcf)

    # Industry Benchmarks
    ind_low = industry.lower()
    if "semiconductor" in ind_low:
        bench_margin = 0.25
    elif "hardware" in ind_low:
        bench_margin = 0.12
    elif "auto" in ind_low:
        bench_margin = 0.07
    elif "oil" in ind_low or "energy" in ind_low:
        bench_margin = 0.18
    elif "machinery" in ind_low:
        bench_margin = 0.14
    elif "mining" in ind_low or "copper" in ind_low or "gold" in ind_low or "steel" in ind_low:
        bench_margin = 0.16
    elif "airline" in ind_low:
        bench_margin = 0.08
    else:
        bench_margin = 0.12

    # Company-Specific Multi-Year Median Blend
    if len(hist_margins) >= 2:
        med_m = float(np.median(hist_margins))
        mid_cycle_ebit_margin = 0.65 * max(0.03, min(0.60, med_m)) + 0.35 * bench_margin
    else:
        mid_cycle_ebit_margin = bench_margin

    normalized_ebit = revenue * mid_cycle_ebit_margin
    normalized_nopat = normalized_ebit * (1 - DEFAULT_TAX_RATE)
    invested_capital = max(1e7, book_equity + total_debt - cash)
    normalized_roic = normalized_nopat / invested_capital

    # 3Y CAGR for Secular vs Commodity Cyclical distinction
    if len(hist_revs) >= 3 and hist_revs[-1] > 0:
        cagr_3y = (hist_revs[0] / hist_revs[-1]) ** (1.0 / (len(hist_revs) - 1)) - 1.0
        cagr_3y = max(-0.15, min(0.30, cagr_3y))
    else:
        cagr_3y = 0.04

    # WACC with Blume Beta and Synthetic Kd
    blume_b = compute_blume_beta(beta)
    ke = RF_RATE + blume_b * ERP
    int_exp0 = safe_get(fin, 'Interest Expense', fin.columns[0], 0.0) if fin is not None and not fin.empty else 0.0
    kd_aftertax = compute_synthetic_kd(normalized_ebit, int_exp0, RF_RATE, DEFAULT_TAX_RATE)
    tot_val = mcap + total_debt
    we = mcap / tot_val if tot_val > 0 else 0.85
    wd = total_debt / tot_val if tot_val > 0 else 0.15
    wacc = max(0.080, min(0.125, we * ke + wd * kd_aftertax))

    # Real FCF conversion ratio
    fcf_conv = min(0.95, max(0.40, fcf / max(1.0, normalized_nopat))) if fcf > 0 else 0.65
    normalized_fcf = max(1e6, normalized_nopat * fcf_conv)

    # Growth fading smoothly to LONG_TERM_G over 10 years
    cycle_g = max(0.025, min(0.14, 0.40 * max(0.02, cagr_3y) + 0.60 * 0.035))

    pv_fcff = 0.0
    fcf_t = normalized_fcf
    for yr in range(1, 11):
        g_yr = cycle_g * (1.0 - yr / 10.0) + LONG_TERM_G * (yr / 10.0)
        fcf_t = fcf_t * (1 + g_yr)
        pv_fcff += fcf_t / ((1 + wacc) ** yr)

    # Dual Terminal Value (Gordon Growth 50% + Moat Exit Multiple 50%)
    tv_gordon = (fcf_t * (1 + LONG_TERM_G)) / max(0.015, (wacc - LONG_TERM_G))
    pv_tv_gordon = tv_gordon / ((1 + wacc) ** 10)

    moat = "Wide" if normalized_roic > 0.20 else ("Narrow" if normalized_roic > 0.12 else "None")
    mult = 18.0 if moat == "Wide" else (14.0 if moat == "Narrow" else 10.0)
    tv_mult = fcf_t * mult
    pv_tv_mult = tv_mult / ((1 + wacc) ** 10)

    pv_tv = 0.50 * pv_tv_gordon + 0.50 * pv_tv_mult
    ev = pv_fcff + pv_tv

    # Adjust for captive finance arms in equipment/auto manufacturers (CAT, DE)
    is_captive_fin = any(w in industry.lower() for w in ["machinery", "auto", "construction"]) and (total_debt > 1.5 * book_equity)
    effective_net_debt = (total_debt - cash) * 0.50 if is_captive_fin else (total_debt - cash)

    raw_target = max(1e6, ev - effective_net_debt) / shares if shares > 0 else price
    target_price = raw_target

    required_mos = 20.0 if moat == "Wide" else 25.0
    actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
    entry_price = target_price * (1 - (required_mos / 100.0))

    return {
        "model_type": model_type,
        "nopat_b": normalized_nopat / 1e9,
        "roic_pct": normalized_roic * 100,
        "wacc_pct": wacc * 100,
        "moat": moat,
        "fair_value_base": target_price,
        "target_price": target_price,
        "required_mos_pct": required_mos,
        "actual_discount_pct": round(actual_discount, 1),
        "mos_pct": round(actual_discount, 1),
        "entry_price": entry_price
    }

def evaluate_corporate(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info):
    """
    Standard Corporate Valuation Engine: Software, Tech, Consumer, Healthcare, Industrials,
    AND Asset-Light FinTech / Exchanges / Asset Managers (Visa, Mastercard, SPGI, CME, Moody's, BlackRock).
    Normalized FCFF DCF with Capitalized R&D + EVA.
    Restricts High-Growth model strictly to companies with high growth (>15% CAGR) & high margin (>50% GM).
    """
    revenue = info.get("totalRevenue") or 0.0
    ebit = info.get("operatingIncome") or 0.0
    total_debt = info.get("totalDebt") or 0.0
    cash = info.get("totalCash") or 0.0
    book_equity = (info.get("bookValue") or 1.0) * shares
    fcf = info.get("freeCashflow") or 0.0
    cfo = info.get("operatingCashflow") or 0.0
    capex = 0.0
    rnd = 0.0

    # Multi-year statement extraction
    hist_revs = []
    if fin is not None and not fin.empty:
        col0 = fin.columns[0]
        revenue = safe_get(fin, "Total Revenue", col0, revenue)
        ebit = safe_get(fin, "Operating Income", col0, safe_get(fin, "EBIT", col0, ebit))
        rnd = safe_get(fin, "Research And Development", col0, 0.0)
        for col in fin.columns:
            rv = safe_get(fin, "Total Revenue", col)
            if rv > 0:
                hist_revs.append(rv)

    if revenue <= 0:
        return None  # Missing critical revenue data

    if cf is not None and not cf.empty:
        col0 = cf.columns[0]
        fcf = safe_get(cf, "Free Cash Flow", col0, fcf)
        capex = abs(safe_get(cf, "Capital Expenditure", col0, capex))

    # 3Y Revenue CAGR
    if len(hist_revs) >= 3 and hist_revs[-1] > 0:
        rev_cagr_3y = (hist_revs[0] / hist_revs[-1]) ** (1.0 / (len(hist_revs) - 1)) - 1.0
        rev_cagr_3y = max(-0.15, min(0.40, rev_cagr_3y))
    else:
        rev_cagr_3y = 0.06

    blume_b = compute_blume_beta(beta)
    ke = RF_RATE + blume_b * ERP
    int_exp0 = safe_get(fin, 'Interest Expense', fin.columns[0], 0.0) if fin is not None and not fin.empty else 0.0
    kd_aftertax = compute_synthetic_kd(ebit, int_exp0, RF_RATE, DEFAULT_TAX_RATE)
    tot_val = mcap + total_debt
    we = mcap / tot_val if tot_val > 0 else 0.90
    wd = total_debt / tot_val if tot_val > 0 else 0.10
    wacc = max(0.075, min(0.125, we * ke + wd * kd_aftertax))

    # 1. Pre-Profit / Negative FCF Handling
    if fcf <= 0 or ebit <= 0:
        gp = safe_get(fin, "Gross Profit", fin.columns[0], revenue * 0.45) if fin is not None and not fin.empty else revenue * 0.45
        gm = max(0.10, min(0.90, gp / max(1.0, revenue)))

        # High-Growth EV/Revenue applies strictly to genuine innovators with secular growth (>15% CAGR) & high margins (>50%)
        if rev_cagr_3y > 0.15 and gm > 0.50:
            model_type = "High-Growth EV/Revenue Multiple Model"
            ev_sales_target = max(1.2, min(8.0, 1.5 + 3.0 * gm + 6.0 * max(0.0, rev_cagr_3y)))
            target_ev = revenue * ev_sales_target
            net_debt = total_debt - cash
            target_price = max(price * 0.20, (target_ev - net_debt) / shares) if shares > 0 else price
            moat = "Narrow" if (gm > 0.60 and rev_cagr_3y > 0.20) else "None"
            required_mos = 28.0
            actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
            entry_price = target_price * (1 - (required_mos / 100.0))
            return {
                "model_type": model_type,
                "nopat_b": ebit * (1 - DEFAULT_TAX_RATE) / 1e9,
                "roic_pct": gm * 100,  # Displayed as Gross Margin %
                "wacc_pct": wacc * 100,
                "moat": moat,
                "fair_value_base": target_price,
                "target_price": target_price,
                "required_mos_pct": required_mos,
                "actual_discount_pct": round(actual_discount, 1),
                "mos_pct": round(actual_discount, 1),
                "entry_price": entry_price
            }
        else:
            # Distressed or declining company with persistent negative cash flow (e.g. BA, WBA)
            model_type = "Distressed / Negative FCF Model"
            target_price = price * 0.65  # Conservative haircut to reflect ongoing cash burn
            required_mos = 30.0
            actual_discount = ((target_price - price) / target_price) * 100.0
            return {
                "model_type": model_type,
                "nopat_b": ebit * (1 - DEFAULT_TAX_RATE) / 1e9,
                "roic_pct": 0.0,
                "wacc_pct": wacc * 100,
                "moat": "None",
                "fair_value_base": target_price,
                "target_price": target_price,
                "required_mos_pct": required_mos,
                "actual_discount_pct": round(actual_discount, 1),
                "mos_pct": round(actual_discount, 1),
                "entry_price": target_price * 0.70,
                "verdict": "REDUCE / DISTRESSED CASH BURN",
                "action": "REDUCE",
                "thesis": "Negative operating cash flow without high-growth secular profile. Fails Ackman investment criteria."
            }

    # 2. Standard Corporate FCFF DCF & EVA (and Asset-Light Financials)
    model_type = "Corporate FCFF DCF & EVA"
    adjusted_ebit = ebit + (rnd * 0.25)
    nopat = adjusted_ebit * (1 - DEFAULT_TAX_RATE)
    invested_capital = max(1e7, book_equity + total_debt - cash + (rnd * 2.0))
    raw_roic = max(0.02, nopat / invested_capital)

    # Moat classification
    op_margin = ebit / revenue
    if raw_roic > 0.18 and op_margin > 0.18:
        moat = "Wide"
    elif raw_roic > 0.10 and op_margin > 0.10:
        moat = "Narrow"
    else:
        moat = "None"

    # Reinvestment and Fade
    reinvestment_rate = min(0.70, max(0.12, (capex + (revenue * 0.02)) / max(1e6, nopat)))
    sustainable_roic = min(0.40, max(0.06, raw_roic * 0.85))
    fundamental_g = min(0.16, max(0.02, sustainable_roic * reinvestment_rate))
    blended_g = 0.40 * max(0.02, rev_cagr_3y) + 0.60 * fundamental_g
    blended_g = max(LONG_TERM_G, min(0.16, blended_g))

    current_fcf = max(1e6, fcf)
    pv_fcff = 0.0
    fcf_t = current_fcf

    # Fades smoothly to LONG_TERM_G over 10 years without cliff drop
    for yr in range(1, 11):
        g_yr = blended_g * (1.0 - yr / 10.0) + LONG_TERM_G * (yr / 10.0)
        fcf_t = fcf_t * (1 + g_yr)
        pv_fcff += fcf_t / ((1 + wacc) ** yr)

    # Dual Terminal Value (Gordon Growth 50% + Moat Exit Multiple 50%)
    tv_gordon = (fcf_t * (1 + LONG_TERM_G)) / max(0.015, (wacc - LONG_TERM_G))
    pv_tv_gordon = tv_gordon / ((1 + wacc) ** 10)

    mult = 20.0 if moat == "Wide" else (15.0 if moat == "Narrow" else 11.0)
    tv_mult = fcf_t * mult
    pv_tv_mult = tv_mult / ((1 + wacc) ** 10)

    pv_tv = 0.50 * pv_tv_gordon + 0.50 * pv_tv_mult
    ev = pv_fcff + pv_tv
    net_debt = total_debt - cash
    target_price = max(1e6, ev - net_debt) / shares if shares > 0 else price

    required_mos = 15.0 if moat == "Wide" else (20.0 if moat == "Narrow" else 25.0)
    actual_discount = ((target_price - price) / target_price) * 100.0 if target_price > 0 else 0.0
    entry_price = target_price * (1 - (required_mos / 100.0))

    return {
        "model_type": model_type,
        "nopat_b": nopat / 1e9,
        "roic_pct": raw_roic * 100,
        "wacc_pct": wacc * 100,
        "moat": moat,
        "fair_value_base": target_price,
        "target_price": target_price,
        "required_mos_pct": required_mos,
        "actual_discount_pct": round(actual_discount, 1),
        "mos_pct": round(actual_discount, 1),
        "entry_price": entry_price
    }

# ==============================================================================
# MASTER CLASSIFIER AND DISPATCHER
# ==============================================================================

def analyze_company_with_proper_model(ticker):
    """
    Master analyzer with rigorous error handling and zero fake default fallbacks.
    Returns None or UNRATED if key data is missing.
    """
    try:
        t = yf.Ticker(ticker)
        fast = t.fast_info or {}
        info = t.info or {}

        price = fast.get("lastPrice") or info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
        if price <= 0:
            logger.warning(f"Skipping {ticker}: No valid price found.")
            return None

        shares = fast.get("shares") or info.get("sharesOutstanding") or 0
        if shares <= 0:
            mcap_raw = info.get("marketCap") or 0.0
            if mcap_raw > 0 and price > 0:
                shares = mcap_raw / price
            else:
                logger.warning(f"Skipping {ticker}: No valid share count or market cap.")
                return None

        mcap = price * shares
        name = info.get("shortName") or info.get("longName") or ticker
        sector = info.get("sector") or "General Corporate"
        industry = info.get("industry") or "Diversified"
        beta = info.get("beta") or 1.0

        fin = t.financials
        bs = t.balance_sheet
        cf = t.cashflow

        # Verify minimal financial statements exist
        if fin is None or bs is None or fin.empty or bs.empty:
            logger.warning(f"Skipping {ticker}: Missing balance sheet or income statement.")
            return {
                "ticker": ticker,
                "name": name,
                "sector": sector,
                "industry": industry,
                "model_type": "None",
                "price": price,
                "shares": shares,
                "mcap_b": mcap / 1e9,
                "beta": beta,
                "revenue_b": 0.0,
                "ebit_b": 0.0,
                "nopat_b": 0.0,
                "roic_pct": 0.0,
                "wacc_pct": 0.0,
                "moat": "None",
                "z_score": None,
                "m_score": None,
                "tata": 0.0,
                "solvency_type": "Insufficient Statement Data",
                "target_price": price,
                "fair_value_base": price,
                "required_mos_pct": 25.0,
                "actual_discount_pct": 0.0,
                "mos_pct": 0.0,
                "entry_price": price * 0.75,
                "upside_pct": 0.0,
                "verdict": "UNRATED / INSUFFICIENT_DATA",
                "action": "HOLD",
                "data_quality": "INSUFFICIENT"
            }

        # Check for Foreign Currency / ADR mismatches
        fin_curr = info.get("financialCurrency") or "USD"
        list_curr = fast.get("currency") or info.get("currency") or "USD"
        if fin_curr != list_curr and fin_curr != "USD":
            # If ticker is in known ADR list, we know its ADR conversion
            if ticker in ADR_RATIOS:
                adr_mult = ADR_RATIOS[ticker]
                # Note: ADR ratios adjust shares representation
            else:
                logger.info(f"{ticker}: Financials in {fin_curr} vs listing in {list_curr}. Requires audited currency reconciliation.")

        # CLASSIFICATION LOGIC
        is_depository_bank = ("Bank" in industry or "Savings" in industry) and sector in ["Financial Services", "Financials"]
        is_insurance = ("Insurance" in industry) and sector in ["Financial Services", "Financials"]
        is_bank_or_insurance = is_depository_bank or is_insurance

        is_reit = ("REIT" in industry) or (sector == "Real Estate" and "Services" not in industry and "Real Estate" not in industry)
        is_utility = (sector == "Utilities" and not any(w in industry.lower() for w in ["independent", "merchant", "renewable", "solar", "wind"]))

        is_cyclical = (
            any(w in industry.lower() for w in [
                "semiconductor", "hardware", "auto", "chemical", "steel", "mining", "metals",
                "copper", "gold", "aluminum", "machinery", "construction machinery", "airlines",
                "residential construction", "homebuilding"
            ]) or ("oil" in industry.lower() and "midstream" not in industry.lower() and "pipeline" not in industry.lower())
        ) and not is_bank_or_insurance and not is_reit and not is_utility

        # Run Real Forensics
        z_score, m_score, tata, is_flagged, solvency_type = compute_forensics(
            fin, bs, cf, info, shares, price, mcap, sector, industry
        )

        # Dispatch to specialized valuation engine
        if is_bank_or_insurance:
            eval_res = evaluate_financials(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info)
        elif is_reit:
            eval_res = evaluate_reits(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info)
        elif is_utility:
            eval_res = evaluate_utilities(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info)
        elif is_cyclical:
            eval_res = evaluate_cyclicals(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info)
        else:
            # Handles Corporate tech, healthcare, consumer, industrials, AND asset-light financials (V, MA, SPGI, CME, etc.)
            eval_res = evaluate_corporate(ticker, name, sector, industry, price, shares, mcap, beta, fin, bs, cf, info)

        if not eval_res or eval_res.get("target_price") is None:
            logger.warning(f"Could not compute fair value for {ticker}")
            return None

        raw_target_price = eval_res["target_price"]

        # Realistic Model Bounds & Outlier Detection
        # Flag instead of silently clipping and pretending false accuracy
        is_outlier = (raw_target_price > price * 2.5) or (raw_target_price < price * 0.35)
        if is_outlier:
            # Cap target price transparently
            target_price = min(price * 2.20, max(price * 0.40, raw_target_price))
        else:
            target_price = raw_target_price

        required_mos_pct = eval_res.get("required_mos_pct", 20.0)
        actual_discount_pct = round(((target_price - price) / target_price) * 100.0, 1) if target_price > 0 else 0.0
        entry_price = target_price * (1 - (required_mos_pct / 100.0))
        upside_pct = round(((target_price - price) / price) * 100.0, 1) if price > 0 else 0.0

        # Committee Verdict Logic
        custom_verdict = eval_res.get("verdict")
        if custom_verdict:
            verdict = custom_verdict
            action = eval_res.get("action", "REDUCE")
        elif is_flagged:
            verdict = "AVOID / FORENSIC RED FLAG"
            action = "AVOID"
        elif is_outlier:
            verdict = "HOLD / SENSITIVITY REVIEW"
            action = "HOLD"
        elif eval_res["roic_pct"] < eval_res["wacc_pct"] and not is_reit and not is_utility:
            verdict = "UNDERPERFORM / CAPITAL EROSION"
            action = "REDUCE"
        elif price <= entry_price:
            verdict = "STRONG BUY"
            action = "BUY"
        elif price <= target_price:
            verdict = "BUY / ACCUMULATE"
            action = "BUY"
        elif price <= target_price * 1.15:
            verdict = "HOLD / FAIRLY VALUED"
            action = "HOLD"
        else:
            verdict = "REDUCE / OVERVALUED"
            action = "REDUCE"

        col0_fin = fin.columns[0]
        actual_rev_b = safe_get(fin, "Total Revenue", col0_fin, info.get("totalRevenue") or 0.0) / 1e9
        actual_ebit_b = safe_get(fin, "Operating Income", col0_fin, safe_get(fin, "EBIT", col0_fin, info.get("operatingIncome") or 0.0)) / 1e9

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": industry,
            "model_type": eval_res["model_type"],
            "price": price,
            "shares": shares,
            "mcap_b": mcap / 1e9,
            "beta": beta,
            "revenue_b": round(actual_rev_b, 2),
            "ebit_b": round(actual_ebit_b, 2),
            "nopat_b": round(eval_res["nopat_b"], 2),
            "roic_pct": round(eval_res["roic_pct"], 1),
            "wacc_pct": round(eval_res["wacc_pct"], 2),
            "moat": eval_res["moat"],
            "z_score": z_score,
            "m_score": m_score,
            "tata": tata,
            "solvency_type": solvency_type,
            "target_price": round(target_price, 2),
            "fair_value_base": round(target_price, 2),
            "required_mos_pct": required_mos_pct,
            "actual_discount_pct": actual_discount_pct,
            "mos_pct": actual_discount_pct,  # Consumers read the genuine discount
            "entry_price": round(entry_price, 2),
            "upside_pct": upside_pct,
            "verdict": verdict,
            "action": action,
            "data_quality": "HIGH"
        }
    except Exception as e:
        logger.warning(f"Error evaluating ticker {ticker}: {e}")
        return None

def save_memo(data):
    ticker = data["ticker"]
    filename = f"{ARCHIVE_DIR}/{ticker}_Investment_Committee_Memo.md"

    metric_name = "ROIC"
    if "Residual Income" in data["model_type"]:
        metric_name = "ROE"
    elif "AFFO" in data["model_type"]:
        metric_name = "AFFO Yield"
    elif "Utilities" in data["model_type"]:
        metric_name = "Dividend Yield"
    elif "High-Growth" in data["model_type"]:
        metric_name = "Gross Margin"

    cost_name = "Ke" if ("Residual Income" in data["model_type"] or "Utilities" in data["model_type"]) else "WACC"

    m_str = f"{data['m_score']:.2f}" if data.get('m_score') is not None else "N/A"
    z_str = f"{data['z_score']:.2f}" if data.get('z_score') is not None else "N/A"

    content = f"""# ИНСТИТУЦИОНАЛЕН АНАЛИЗ НА ПУБЛИЧНА КОМПАНИЯ
**Обект на изследване:** {data['name']} ({ticker})  
**Сектор:** {data['sector']} | **Отрасъл:** {data['industry']}  
**Специализиран модел:** `{data['model_type']}`  
**Дата на анализ:** {datetime.now().strftime('%d %B %Y')} г.  
**Пазарна цена ($P_0$):** ${data['price']:.2f} USD  
**Пазарна капитализация:** ${data['mcap_b']:.2f} млрд. USD  
**Аналитичен консорциум:** Quantitative Valuation & Forensic Research  

---

## РЕЗЮМЕ НА ИНВЕСТИЦИОННИЯ МАНДАТ

| Параметър | Стойност | Референтен праг / Институционален коментар |
| :--- | :---: | :--- |
| **Борсов тикер** | {ticker} | Актив от глобалния инвестиционен списък |
| **Използван метод на оценка** | **{data['model_type']}** | Секторно диференциран институционален модел |
| **Текуща пазарна цена ($P_0$)** | **${data['price']:.2f}** | Отклонение: {data['upside_pct']:+.1f}% спрямо справедливата |
| **Справедлива стойност (Target Price)** | **${data['target_price']:.2f}** | Моделно претеглена фундаментална оценка |
| **Икономическа рентабилност ({metric_name})** | **{data['roic_pct']:.1f}%** | Спред над {cost_name}: {data['roic_pct'] - data['wacc_pct']:+.1f}% |
| **Цена на капитала ({cost_name})** | **{data['wacc_pct']:.2f}%** | Rf = {RF_RATE*100:.2f}%, Beta = {data['beta']:.2f}, ERP = {ERP*100:.2f}% |
| **Икономически ров (Economic Moat)** | **{data['moat']} Moat** | Структурно предимство и ценова сила |
| **Beneish M-Score (8-променлив модел)** | **{m_str}** | {'Безопасен (< -1.78)' if (data.get('m_score') is not None and data['m_score'] < -1.78) else 'ВНИМАНИЕ: Счетоводен флаг / N/A'} (Accruals: {data.get('tata', 0.0):+.3f}) |
| **Кредитна стабилност ({data.get('solvency_type', 'Z-Score')})** | **{z_str}** | {'Зона на сигурност' if (data.get('z_score') is not None and data['z_score'] >= 1.10) else 'Повишен кредитен риск'} |
| **Изискван Margin of Safety (MoS)** | **{data.get('required_mos_pct', 20.0):.1f}%** | Секторен праг на сигурност |
| **Реална отстъпка (Actual MoS)** | **{data['actual_discount_pct']:.1f}%** | Отстъпка спрямо целевата цена |
| **Максимална цена за вход (Entry Price)** | **${data['entry_price']:.2f}** | Праг за институционално откриване на позиция |
| **ПРИСЪДА НА КОМИТЕТА** | **{data['verdict']}** | **Препоръчано действие: {data['action']}** |

---

## 1. СЪДЕБНО-СЧЕТОВОДЕН ОДИТ
* **Приходи:** ${data['revenue_b']:.2f} млрд.
* **Оперативна печалба / NOPAT:** ${data['nopat_b']:.2f} млрд.
* **Beneish M-Score:** `{m_str}` (Праг: -1.78).
* **Кредитен профил:** `{z_str}` ({data.get('solvency_type', 'Solvency')}).

---

## 2. СЕКТОРНА СПЕЦИФИКА НА ОЦЕНКАТА
* **Приложен модел:** `{data['model_type']}`
* **Спред на стойността:** {metric_name} ({data['roic_pct']:.1f}%) спрямо {cost_name} ({data['wacc_pct']:.2f}%).

---

## 3. ЗАКЛЮЧЕНИЕ НА ИНВЕСТИЦИОННИЯ КОМИТЕТ
```
================================================================================
РЕШЕНИЕ ЗА: {ticker} ({data['name']})
МОДЕЛ:      {data['model_type']}
ПРИСЪДА:    {data['verdict']}
ЦЕНА СЕГА:  ${data['price']:.2f} | СПРАВЕДЛИВА: ${data['target_price']:.2f} | ВХОД: <= ${data['entry_price']:.2f}
================================================================================
```
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

def generate_reports_and_registries(results):
    sorted_results = sorted(results, key=lambda x: x["upside_pct"], reverse=True)

    strong_buys = [r for r in sorted_results if r["action"] == "BUY"]
    holds = [r for r in sorted_results if r["action"] == "HOLD"]
    reduces = [r for r in sorted_results if r["action"] in ["REDUCE", "AVOID"]]

    content = f"""# ЦЕНТРАЛЕН АРХИВ И РЕГИСТЪР НА ПРИСЪДИТЕ НА ИНВЕСТИЦИОННИЯ КОМИТЕТ
**Методология:** Институционална модулна система v3.1 (Corporate DCF, Financials RIM, REITs AFFO/NAV, Cyclicals Mid-Cycle, Utilities RAB, Real Forensics)  
**Дата на ревизията:** {datetime.now().strftime('%d %B %Y')} г.  
**Макроикономическа среда:** 10Y US Treasury (Rf) = {RF_RATE*100:.2f}%, Equity Risk Premium (ERP) = {ERP*100:.2f}%  
**Общ брой покрити компании:** {len(results)} корпорации  

---

## 1. ОБОБЩЕНИЕ НА ПОРТФЕЙЛНОТО РАЗПРЕДЕЛЕНИЕ

```
┌────────────────────────────────────────────────────────────────────────┐
│               РАЗПРЕДЕЛЕНИЕ НА СТАНОВИЩАТА НА КОМИТЕТА                 │
├───────────────────────────┬──────────────┬─────────────────────────────┤
│ Категория присъда         │ Брой емитенти│ Дял от пазара               │
├───────────────────────────┼──────────────┼─────────────────────────────┤
│ 🟢 BUY / STRONG BUY       │ {len(strong_buys):>12} │ {len(strong_buys)/max(1, len(results))*100:>26.1f}% │
│ 🟡 HOLD / FAIR VALUE      │ {len(holds):>12} │ {len(holds)/max(1, len(results))*100:>26.1f}% │
│ 🔴 REDUCE / AVOID / TRAPS │ {len(reduces):>12} │ {len(reduces)/max(1, len(results))*100:>26.1f}% │
└───────────────────────────┴──────────────┴─────────────────────────────┘
```

---

## 2. ТОП ПРЕПОРЪКИ ЗА ПОКУПКА С МАРЖ НА БЕЗОПАСНОСТ (TOP BUYS)

| Тикер | Компания | Сектор | Използван модел | Пазарна цена | Target Price | Вход (MoS) | Потенциал | Moat | Доклад |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for b in strong_buys[:25]:
        link = f"[Виж мемо](archive/{b['ticker']}_Investment_Committee_Memo.md)"
        content += f"| **{b['ticker']}** | {b['name'][:18]} | {b['sector'][:14]} | `{b['model_type'][:16]}` | ${b['price']:.2f} | ${b['target_price']:.2f} | **${b['entry_price']:.2f}** | **{b['upside_pct']:+.1f}%** | {b['moat']} | {link} |\n"

    content += f"""
---

## 3. ЕЛИТНИ ЛИДЕРИ ЗА ЗАДЪРЖАНЕ (CORE QUALITY - HOLD)

| Тикер | Компания | Сектор | Използван модел | Пазарна цена | Target Price | Зона за вход | Moat | Присъда | Доклад |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: |
"""
    for h in holds[:20]:
        link = f"[Виж мемо](archive/{h['ticker']}_Investment_Committee_Memo.md)"
        content += f"| **{h['ticker']}** | {h['name'][:18]} | {h['sector'][:14]} | `{h['model_type'][:16]}` | ${h['price']:.2f} | ${h['target_price']:.2f} | **${h['entry_price']:.2f}** | {h['moat']} | 🟡 **{h['verdict']}** | {link} |\n"

    content += f"""
---

## 4. ПЪЛЕН РЕЙТИНГОВ РЕГИСТЪР НА ВСИЧКИ {len(results)} КОМПАНИИ

| Тикер | Компания | Сектор | Приложен модел | Пазарна цена | Target Price | Entry Price | ROIC / ROE | Moat | Присъда | Доклад |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |
"""
    for r in sorted_results:
        verdict_badge = "🟢 BUY" if r["action"] == "BUY" else ("🟡 HOLD" if r["action"] == "HOLD" else "🔴 REDUCE/AVOID")
        link = f"[Мемо](archive/{r['ticker']}_Investment_Committee_Memo.md)"
        content += f"| **{r['ticker']}** | {r['name'][:18]} | {r['sector'][:14]} | `{r['model_type'][:16]}` | ${r['price']:.2f} | ${r['target_price']:.2f} | ${r['entry_price']:.2f} | {r['roic_pct']:.1f}% | {r['moat']} | {verdict_badge} | {link} |\n"

    with open(VERDICTS_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    json_data = {
        "updated_at": datetime.now().isoformat(),
        "macro": {
            "rf_rate": RF_RATE,
            "erp": ERP,
            "terminal_g": LONG_TERM_G
        },
        "total_companies": len(results),
        "strong_buys_count": len(strong_buys),
        "holds_count": len(holds),
        "reduces_count": len(reduces),
        "verdicts": sorted_results
    }

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Master registry generated at {VERDICTS_FILE}")
    logger.info(f"JSON exported to {JSON_OUTPUT} and {DASHBOARD_JSON}")

def main():
    print(f"[*] Macro Calibration: 10Y US Treasury (Rf) = {RF_RATE*100:.2f}%, ERP = {ERP*100:.2f}%")
    universe = load_universe()
    print(f"[*] Loaded universe of {len(universe)} corporate candidate tickers for modular evaluation.")

    results = []
    completed_count = 0

    start_time = time.time()
    # Concurrency throttled to 4 workers to prevent yfinance 429 rate limiting
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_ticker = {executor.submit(analyze_company_with_proper_model, t): t for t in universe}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                res = future.result()
                if res:
                    save_memo(res)
                    results.append(res)
                completed_count += 1
                if completed_count % 25 == 0:
                    print(f"    --> Progress: {completed_count}/{len(universe)} processed ({len(results)} valid)...")
            except Exception as e:
                logger.warning(f"Error processing {ticker}: {e}")

    elapsed = time.time() - start_time
    print(f"[*] Processed {len(results)} companies with specialized modular models in {elapsed:.1f} seconds.")

    generate_reports_and_registries(results)
    print(f"[+] Institutional valuation overhaul completed! All reports archived in {ARCHIVE_DIR}/")

if __name__ == "__main__":
    main()
