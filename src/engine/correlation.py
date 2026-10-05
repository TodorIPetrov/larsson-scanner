"""
Portfolio Correlation & Diversification Matrix Engine.
Computes pairwise Pearson correlation of daily returns, HHI concentration index,
and suggests universe assets that would reduce portfolio correlation.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple

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


@dataclass
class SignalCluster:
    cluster_id: str
    asset_class: str
    transition_type: str
    leader_symbol: str
    member_symbols: List[str]
    avg_correlation: float
    benchmark_beta: Optional[float] = None
    is_solo: bool = False
    details: Optional[Dict[str, Any]] = None


def cluster_transition_signals(
    transitions: List[Dict[str, Any]],
    price_data: Dict[str, pd.Series],
    correlation_threshold: float = 0.70,
    benchmark_symbol: Optional[str] = None,
    window: int = 30,
) -> List[SignalCluster]:
    """
    Groups simultaneous state transitions into correlation clusters.
    Prevents alert fatigue and fake diversification by identifying when
    multiple signals represent a single correlated macro factor bet.
    """
    if not transitions:
        return []

    # Bucket transitions by (asset_class, transition_type)
    buckets: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for t in transitions:
        ac = t.get("asset_class", "unknown")
        ttype = t.get("transition_type") or f"{t.get('old_state', 'UNKNOWN')}_TO_{t.get('new_state', 'UNKNOWN')}"
        key = (ac, ttype)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(t)

    clusters: List[SignalCluster] = []
    cluster_counter = 1

    for (ac, ttype), trans_list in buckets.items():
        symbols = [t["ticker"] for t in trans_list if "ticker" in t]
        if not symbols:
            continue

        if len(symbols) == 1:
            sym = symbols[0]
            clusters.append(
                SignalCluster(
                    cluster_id=f"cluster_{cluster_counter}",
                    asset_class=ac,
                    transition_type=ttype,
                    leader_symbol=sym,
                    member_symbols=[sym],
                    avg_correlation=1.0,
                    is_solo=True,
                )
            )
            cluster_counter += 1
            continue

        # Compute return series for available symbols
        returns: Dict[str, pd.Series] = {}
        for s in symbols:
            if s in price_data and price_data[s] is not None and len(price_data[s]) >= 10:
                ret = _daily_returns(price_data[s].iloc[-(window + 5):])
                if len(ret) >= 5:
                    returns[s] = ret

        # Compute pairwise correlations
        adj: Dict[str, Set[str]] = {s: set() for s in symbols}
        pairwise_corrs: Dict[Tuple[str, str], float] = {}

        for i, s1 in enumerate(symbols):
            for j, s2 in enumerate(symbols):
                if i < j:
                    if s1 in returns and s2 in returns:
                        c = _pearson_correlation(returns[s1], returns[s2])
                        if c is not None:
                            pairwise_corrs[(s1, s2)] = c
                            pairwise_corrs[(s2, s1)] = c
                            if c >= correlation_threshold:
                                adj[s1].add(s2)
                                adj[s2].add(s1)

        # Graph connected components for clusters
        visited = set()
        components: List[List[str]] = []

        for s in symbols:
            if s not in visited:
                comp = []
                queue = [s]
                visited.add(s)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(comp)

        # Benchmark returns for beta
        bench_ret = None
        bench_sym = benchmark_symbol or ("BTCUSDT" if ac == "crypto" else "SPY")
        if bench_sym in price_data and price_data[bench_sym] is not None:
            bench_ret = _daily_returns(price_data[bench_sym].iloc[-(window + 5):])

        # Form clusters
        for comp in components:
            # Pick leader: highest recent 5-day return or highest volume/score
            leader = comp[0]
            best_recent_ret = -999.0
            for s in comp:
                if s in price_data and len(price_data[s]) >= 5:
                    r5 = float(price_data[s].iloc[-1] / price_data[s].iloc[-5] - 1.0)
                    if r5 > best_recent_ret:
                        best_recent_ret = r5
                        leader = s

            # Calculate intra-cluster avg correlation
            if len(comp) > 1:
                comp_corrs = []
                for s1 in comp:
                    for s2 in comp:
                        if s1 != s2 and (s1, s2) in pairwise_corrs:
                            comp_corrs.append(pairwise_corrs[(s1, s2)])
                avg_c = round(float(np.mean(comp_corrs)), 2) if comp_corrs else correlation_threshold
                is_solo = False
            else:
                avg_c = 1.0
                is_solo = True

            # Calculate benchmark beta for leader
            beta = None
            if bench_ret is not None and leader in returns:
                c_df = pd.concat([returns[leader], bench_ret], axis=1, join="inner").dropna()
                if len(c_df) >= 10:
                    cov = np.cov(c_df.iloc[:, 0], c_df.iloc[:, 1])[0][1]
                    var_b = np.var(c_df.iloc[:, 1])
                    if var_b > 1e-8:
                        beta = round(float(cov / var_b), 2)

            clusters.append(
                SignalCluster(
                    cluster_id=f"cluster_{cluster_counter}",
                    asset_class=ac,
                    transition_type=ttype,
                    leader_symbol=leader,
                    member_symbols=comp,
                    avg_correlation=avg_c,
                    benchmark_beta=beta,
                    is_solo=is_solo,
                )
            )
            cluster_counter += 1

    return clusters


def format_cluster_alerts_telegram(clusters: List[SignalCluster]) -> str:
    """
    Formats a noise-filtered Telegram HTML alert summary of clustered transitions.
    """
    if not clusters:
        return "Няма клъстерни сигнали."

    lines = ["🌐 <b>Клъстеризирани пазарни преходи (Noise-Filtered)</b>\n"]
    for c in clusters:
        arrow = "🟢" if "GOLD" in c.transition_type else ("🔴" if "BLUE" in c.transition_type else "⚪")
        if c.is_solo:
            lines.append(
                f"{arrow} <b>{c.leader_symbol}</b> [<code>{c.asset_class}</code>]: <code>{c.transition_type}</code> (Изолиран индивидуален сигнал)\n"
            )
        else:
            members_str = ", ".join(c.member_symbols)
            beta_str = f" | Beta: <b>{c.benchmark_beta:+.2f}</b>" if c.benchmark_beta is not None else ""
            lines.append(
                f"{arrow} <b>Клъстер {c.asset_class.upper()} [{len(c.member_symbols)} актива]</b>: <code>{c.transition_type}</code>\n"
                f"   • Водещ актив: <b>{c.leader_symbol}</b>\n"
                f"   • Активи: <i>{members_str}</i>\n"
                f"   • Вътрешна корелация: <b>{c.avg_correlation:.2f}</b>{beta_str}\n"
                f"   ⚠️ <i>Внимание: Това представлява един макро залог, а не {len(c.member_symbols)} независими сделки!</i>\n"
            )
    return "\n".join(lines)
