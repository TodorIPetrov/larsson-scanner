"""
Portfolio Correlation & Diversification Matrix Engine.
Computes pairwise Pearson correlation of daily returns, HHI concentration index,
and suggests universe assets that would reduce portfolio correlation.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Threshold above which average off-diagonal correlation triggers a warning
CONCENTRATION_WARNING_THRESHOLD = 0.75


def _pearson_correlation(a: pd.Series, b: pd.Series) -> Optional[float]:
    """
    Computes Pearson correlation between two return series.
    Aligns on index, requires at least 5 overlapping observations.
    Returns None if insufficient data or zero variance.
    """
    combined = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(combined) < 5:
        return None
    col_a = combined.iloc[:, 0]
    col_b = combined.iloc[:, 1]
    std_a = col_a.std()
    std_b = col_b.std()
    if std_a == 0 or std_b == 0:
        return None
    corr_val = col_a.corr(col_b)
    if math.isnan(corr_val) or math.isinf(corr_val):
        return None
    return round(float(corr_val), 4)


def _daily_returns(prices: pd.Series) -> pd.Series:
    """Converts price series to daily log or pct returns, dropping NaN."""
    return prices.pct_change().dropna()


def compute_correlation_matrix(
    symbols: List[str],
    price_data: Dict[str, pd.Series],
    window: int = 30,
    position_weights: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Compute pairwise Pearson correlation of daily returns over the trailing
    *window* trading days for all symbols whose price data is available.

    Args:
        symbols:          List of portfolio symbol tickers to include.
        price_data:       Mapping of ticker -> pd.Series of close prices
                          (index should be date-like or integer-ordinal).
        window:           Number of trailing periods used for returns.
        position_weights: Optional mapping of ticker -> USD position weight.
                          If omitted, equal weights are assumed for HHI.

    Returns a dict with:
        'matrix':                   {sym_a: {sym_b: float|None}}  – full NxN
        'portfolio_avg_correlation': float   – mean of all off-diagonal elements
        'concentration_warning':     bool    – True if avg_corr > threshold
        'uncorrelated_candidates':   list[str] – tickers not in portfolio with
                                                  lowest avg corr to portfolio
        'hhi':                      float   – Herfindahl-Hirschman Index [0, 1]
    """
    # Filter to symbols with enough price data
    valid_symbols = [
        s for s in symbols
        if s in price_data and price_data[s] is not None and len(price_data[s]) >= window + 2
    ]

    # Build return series (last `window` observations)
    returns: Dict[str, pd.Series] = {}
    for sym in valid_symbols:
        ret = _daily_returns(price_data[sym].iloc[-(window + 5):])
        if len(ret) >= max(5, window // 2):
            returns[sym] = ret

    active = list(returns.keys())

    # Build NxN correlation matrix
    matrix: Dict[str, Dict[str, Optional[float]]] = {}
    for sym_a in active:
        matrix[sym_a] = {}
        for sym_b in active:
            if sym_a == sym_b:
                matrix[sym_a][sym_b] = 1.0
            elif sym_b in matrix and sym_a in matrix[sym_b]:
                # Symmetry shortcut
                matrix[sym_a][sym_b] = matrix[sym_b][sym_a]
            else:
                matrix[sym_a][sym_b] = _pearson_correlation(returns[sym_a], returns[sym_b])

    # Average off-diagonal correlation (portfolio average)
    off_diagonal: List[float] = []
    for i, sym_a in enumerate(active):
        for j, sym_b in enumerate(active):
            if i < j:
                val = matrix[sym_a].get(sym_b)
                if val is not None:
                    off_diagonal.append(val)

    if off_diagonal:
        portfolio_avg_correlation = round(float(np.mean(off_diagonal)), 4)
    else:
        portfolio_avg_correlation = 0.0

    concentration_warning = portfolio_avg_correlation > CONCENTRATION_WARNING_THRESHOLD

    # HHI – Herfindahl-Hirschman Index of position weights [0, 1]
    # HHI = sum(w_i^2) where w_i are fractional weights summing to 1
    if position_weights:
        total_w = sum(abs(v) for v in position_weights.values() if v is not None)
        if total_w > 0:
            hhi = round(
                float(sum((abs(position_weights.get(s, 0.0)) / total_w) ** 2 for s in symbols)),
                4,
            )
        else:
            hhi = 1.0 / max(1, len(symbols)) if symbols else 0.0
    else:
        n = len(valid_symbols) if valid_symbols else 1
        hhi = round(1.0 / n, 4)

    # Uncorrelated candidates: universe symbols NOT in portfolio with lowest
    # average correlation to portfolio assets
    universe_only = [
        s for s in price_data
        if s not in set(symbols) and s in returns
    ]

    candidate_scores: Dict[str, float] = {}
    for cand in universe_only:
        corr_vals = []
        for port_sym in active:
            val = _pearson_correlation(returns[cand], returns[port_sym])
            if val is not None:
                corr_vals.append(abs(val))
        if corr_vals:
            candidate_scores[cand] = round(float(np.mean(corr_vals)), 4)

    uncorrelated_candidates = sorted(candidate_scores, key=lambda x: candidate_scores[x])[:5]

    return {
        "matrix": matrix,
        "portfolio_avg_correlation": portfolio_avg_correlation,
        "concentration_warning": concentration_warning,
        "uncorrelated_candidates": uncorrelated_candidates,
        "hhi": hhi,
    }


def suggest_diversification(
    portfolio_symbols: List[str],
    universe_symbols: List[str],
    price_data: Dict[str, pd.Series],
    window: int = 30,
    top_n: int = 5,
) -> List[dict]:
    """
    Suggest assets from *universe_symbols* that are NOT already in
    *portfolio_symbols* and would most reduce portfolio correlation.

    Returns a list of dicts (up to top_n), each containing:
        'ticker':           str
        'avg_corr_to_portfolio': float  – absolute average correlation
        'would_reduce_hhi': bool        – True if adding reduces concentration
    """
    all_symbols = list(set(portfolio_symbols) | set(universe_symbols))
    result = compute_correlation_matrix(
        symbols=portfolio_symbols,
        price_data={s: price_data[s] for s in all_symbols if s in price_data},
        window=window,
    )

    portfolio_avg = result["portfolio_avg_correlation"]
    matrix = result["matrix"]

    # Build return series for universe candidates
    candidate_info: List[dict] = []
    returns: Dict[str, pd.Series] = {}
    for sym in all_symbols:
        if sym in price_data and price_data[sym] is not None and len(price_data[sym]) >= window + 2:
            ret = _daily_returns(price_data[sym].iloc[-(window + 5):])
            if len(ret) >= 5:
                returns[sym] = ret

    for cand in universe_symbols:
        if cand in portfolio_symbols:
            continue
        if cand not in returns:
            continue

        corr_vals = []
        for port_sym in portfolio_symbols:
            if port_sym not in returns:
                continue
            val = _pearson_correlation(returns[cand], returns[port_sym])
            if val is not None:
                corr_vals.append(abs(val))

        if not corr_vals:
            continue

        avg_corr = round(float(np.mean(corr_vals)), 4)
        candidate_info.append({
            "ticker": cand,
            "avg_corr_to_portfolio": avg_corr,
            "would_reduce_hhi": True,  # Adding any asset reduces single-name concentration
        })

    # Sort by lowest average absolute correlation (best diversifiers first)
    candidate_info.sort(key=lambda x: x["avg_corr_to_portfolio"])
    return candidate_info[:top_n]


def format_correlation_telegram(corr_result: dict, portfolio_symbols: List[str]) -> str:
    """
    Formats a concise Telegram HTML summary of the portfolio correlation matrix.
    """
    avg_corr = corr_result.get("portfolio_avg_correlation", 0.0)
    hhi = corr_result.get("hhi", 0.0)
    warning = corr_result.get("concentration_warning", False)
    candidates = corr_result.get("uncorrelated_candidates", [])
    matrix = corr_result.get("matrix", {})

    warning_icon = "⚠️" if warning else "✅"
    hhi_pct = round(hhi * 100, 1)

    lines = [
        f"📊 <b>Корелационна Матрица на Портфолиото</b>",
        f"",
        f"• Активи в портфолио: <b>{len(portfolio_symbols)}</b>",
        f"• Средна корелация: <b>{avg_corr:.2f}</b> {warning_icon}",
        f"• HHI Концентрация: <b>{hhi_pct:.1f}%</b>",
    ]

    if warning:
        lines.append(f"⚠️ <i>Висока концентрация! Обмислете диверсификация.</i>")
    else:
        lines.append(f"✅ <i>Корелацията е в допустими граници.</i>")

    # Top pairwise correlations (highest risk pairs)
    pairs = []
    active = list(matrix.keys())
    for i, sym_a in enumerate(active):
        for j, sym_b in enumerate(active):
            if i < j:
                val = matrix[sym_a].get(sym_b)
                if val is not None:
                    pairs.append((sym_a, sym_b, val))

    if pairs:
        pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        lines.append(f"\n<b>Топ корелирани двойки:</b>")
        for sym_a, sym_b, corr_val in pairs[:3]:
            icon = "🔴" if abs(corr_val) > 0.7 else ("🟡" if abs(corr_val) > 0.4 else "🟢")
            lines.append(f"  {icon} {sym_a} / {sym_b}: <code>{corr_val:+.2f}</code>")

    if candidates:
        lines.append(f"\n<b>Препоръки за диверсификация:</b>")
        for cand in candidates[:3]:
            lines.append(f"  • <b>{cand}</b> – ниска корелация с портфолиото")

    return "\n".join(lines)
