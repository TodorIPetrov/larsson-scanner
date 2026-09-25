"""
Sector Rotation Heatmap for Larsson Line Scanner.

Aggregates per-symbol Larsson ribbon states into sector-level breadth metrics
and derives a market-regime classification.

Design decisions:
- The asset_class field on each scan result is used as the primary grouping key
  because that is what the scanner actually produces. An optional override map
  can further subdivide (e.g., 'Crypto' → 'DeFi', 'Layer1', etc.).
- Momentum ('IMPROVING' | 'DETERIORATING' | 'STABLE') is computed by comparing
  the current gold_pct to the previous snapshot passed in via `prev_breadth`.
  If no previous data is given, momentum defaults to 'STABLE'.
- The function is pure (no I/O) so it is trivially unit-testable.
"""

from __future__ import annotations

from typing import Dict, List, Optional


# Minimum symbols in a sector before we draw conclusions
_MIN_SECTOR_SIZE = 2

# Thresholds for regime classification
_BULL_THRESHOLD = 60.0   # gold_pct >= this → BULL
_BEAR_THRESHOLD = 40.0   # blue_pct >= this → BEAR
_TRANSITION = 20.0       # gold_pct > 0 but swinging → TRANSITIONING


# Map scanner asset_class strings → human-readable sector labels
ASSET_CLASS_TO_SECTOR: Dict[str, str] = {
    "crypto": "Crypto",
    "crypto_stocks": "Crypto Stocks",
    "us_stocks": "US Stocks",
    "ai_stocks": "AI / Tech",
    "intl_stocks": "International",
    "commodities": "Commodities",
    "indices": "Indices",
}


def _classify_regime(gold_pct: float, blue_pct: float, neutral_pct: float) -> str:
    """Classify a sector's market regime from breadth percentages."""
    if gold_pct >= _BULL_THRESHOLD:
        return "BULL"
    if blue_pct >= _BEAR_THRESHOLD:
        return "BEAR"
    if gold_pct > 30 and blue_pct > 30:
        return "TRANSITIONING"
    return "MIXED"


def _classify_momentum(
    current_gold_pct: float,
    prev_gold_pct: Optional[float],
    delta_threshold: float = 5.0,
) -> str:
    """Compare current vs previous gold_pct to determine momentum direction."""
    if prev_gold_pct is None:
        return "STABLE"
    delta = current_gold_pct - prev_gold_pct
    if delta >= delta_threshold:
        return "IMPROVING"
    if delta <= -delta_threshold:
        return "DETERIORATING"
    return "STABLE"


def compute_sector_breadth(
    scan_results: List[Dict],
    prev_breadth: Optional[Dict] = None,
) -> Dict:
    """Aggregate per-symbol scan results into sector-level breadth statistics.

    Parameters
    ----------
    scan_results:
        List of dicts, each representing one scanned symbol.  Required keys:
            ``asset_class`` (str), ``state`` (str: 'GOLD'|'BLUE'|'NEUTRAL'),
            ``ticker`` (str), ``bars_since_flip`` (int, optional).
    prev_breadth:
        Optional previous output of this function (used to compute momentum).

    Returns
    -------
    dict keyed by sector name, each value is::

        {
            'total': N,
            'gold': N, 'blue': N, 'neutral': N,
            'gold_pct': float, 'blue_pct': float, 'neutral_pct': float,
            'regime': 'BULL'|'BEAR'|'MIXED'|'TRANSITIONING',
            'momentum': 'IMPROVING'|'DETERIORATING'|'STABLE',
            'top_movers': [list of up to 3 symbol dicts by bars_in_state desc],
        }
    """
    # Bucket symbols by sector
    buckets: Dict[str, List[Dict]] = {}
    for sym in scan_results:
        ac = sym.get("asset_class", "unknown")
        sector = ASSET_CLASS_TO_SECTOR.get(ac, ac.replace("_", " ").title())
        buckets.setdefault(sector, []).append(sym)

    result: Dict = {}

    for sector, symbols in buckets.items():
        total = len(symbols)
        if total == 0:
            continue

        gold = sum(1 for s in symbols if s.get("state") == "GOLD")
        blue = sum(1 for s in symbols if s.get("state") == "BLUE")
        neutral = total - gold - blue

        gold_pct = round(gold / total * 100.0, 1)
        blue_pct = round(blue / total * 100.0, 1)
        neutral_pct = round(neutral / total * 100.0, 1)

        regime = _classify_regime(gold_pct, blue_pct, neutral_pct)

        prev_sector = (prev_breadth or {}).get(sector, {})
        prev_gold_pct: Optional[float] = prev_sector.get("gold_pct")
        momentum = _classify_momentum(gold_pct, prev_gold_pct)

        # Top-3 movers: symbols with the most bars in current state,
        # preferring GOLD, then BLUE, then NEUTRAL for tie-breaks.
        state_priority = {"GOLD": 0, "BLUE": 1, "NEUTRAL": 2}
        sorted_syms = sorted(
            symbols,
            key=lambda s: (
                state_priority.get(s.get("state", "NEUTRAL"), 2),
                -(s.get("bars_since_flip") or 0),
            ),
        )
        top_movers = [
            {
                "ticker": s.get("ticker", ""),
                "state": s.get("state", "NEUTRAL"),
                "bars_since_flip": s.get("bars_since_flip"),
            }
            for s in sorted_syms[:3]
        ]

        result[sector] = {
            "total": total,
            "gold": gold,
            "blue": blue,
            "neutral": neutral,
            "gold_pct": gold_pct,
            "blue_pct": blue_pct,
            "neutral_pct": neutral_pct,
            "regime": regime,
            "momentum": momentum,
            "top_movers": top_movers,
        }

    return result


def get_market_regime(sector_breadth: Dict) -> Dict:
    """Derive an overall market regime from cross-sector breadth statistics.

    Parameters
    ----------
    sector_breadth:
        Output of :func:`compute_sector_breadth`.

    Returns
    -------
    dict::

        {
            'regime': 'RISK_ON'|'RISK_OFF'|'MIXED'|'NEUTRAL',
            'breadth_score': float,  # weighted average gold_pct across all sectors
            'rotation_signal': str,  # e.g. 'CRYPTO_LEADING' or 'DEFENSIVES_LEADING'
            'sector_count': int,
        }
    """
    if not sector_breadth:
        return {
            "regime": "NEUTRAL",
            "breadth_score": 0.0,
            "rotation_signal": "NO_DATA",
            "sector_count": 0,
        }

    # Weighted breadth score (each sector weighted equally for simplicity)
    gold_pcts = [v["gold_pct"] for v in sector_breadth.values()]
    breadth_score = round(sum(gold_pcts) / len(gold_pcts) / 100.0, 4) if gold_pcts else 0.0

    bull_sectors = [s for s, v in sector_breadth.items() if v["regime"] == "BULL"]
    bear_sectors = [s for s, v in sector_breadth.items() if v["regime"] == "BEAR"]

    total = len(sector_breadth)
    bull_ratio = len(bull_sectors) / total if total else 0.0
    bear_ratio = len(bear_sectors) / total if total else 0.0

    if bull_ratio >= 0.6:
        regime = "RISK_ON"
    elif bear_ratio >= 0.6:
        regime = "RISK_OFF"
    elif bull_ratio > bear_ratio:
        regime = "MIXED_BULLISH"
    elif bear_ratio > bull_ratio:
        regime = "MIXED_BEARISH"
    else:
        regime = "MIXED"

    # Rotation signal: which sector has the highest gold_pct?
    if sector_breadth:
        leading_sector = max(sector_breadth, key=lambda s: sector_breadth[s]["gold_pct"])
        sector_map = {
            "Crypto": "CRYPTO_LEADING",
            "AI / Tech": "TECH_LEADING",
            "US Stocks": "EQUITIES_LEADING",
            "Commodities": "COMMODITIES_LEADING",
            "Indices": "INDICES_LEADING",
            "International": "INTERNATIONAL_LEADING",
            "Crypto Stocks": "CRYPTO_STOCKS_LEADING",
        }
        rotation_signal = sector_map.get(leading_sector, f"{leading_sector.upper().replace(' ', '_')}_LEADING")
    else:
        rotation_signal = "NO_SIGNAL"

    return {
        "regime": regime,
        "breadth_score": breadth_score,
        "rotation_signal": rotation_signal,
        "sector_count": total,
        "bull_sectors": bull_sectors,
        "bear_sectors": bear_sectors,
    }
