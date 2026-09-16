"""
Support and Resistance (S/R) Mathematical & Analytical Engine.
Implements Wilder's ATR calculation, rolling swing pivot identification,
adaptive ATR-normalized 1D clustering, touch scoring, and nearest S/R level extraction.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class Pivot:
    index: int
    price: float
    pivot_type: str  # 'HIGH' or 'LOW'


@dataclass
class SRZone:
    zone_type: str  # 'SUPPORT', 'RESISTANCE', or 'BOTH'
    core_price: float
    lower: float
    upper: float
    touches: int
    last_touch_index: int
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SRAnalysis:
    current_price: float
    atr: float
    s1: Optional[float] = None
    s1_touches: int = 0
    s1_dist_pct: Optional[float] = None
    s2: Optional[float] = None
    s2_touches: int = 0
    r1: Optional[float] = None
    r1_touches: int = 0
    r1_dist_pct: Optional[float] = None
    r2: Optional[float] = None
    r2_touches: int = 0
    context_flag: str = "IN_VALUE_RANGE"
    context_desc: str = ""
    zones: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """
    Computes Wilder's Smoothed Average True Range (ATR).
    """
    n = len(high)
    atr = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return np.maximum(high - low, 1e-6)

    # True Range calculation
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    if n < period:
        # Fallback for short series: cumulative mean
        for i in range(n):
            atr[i] = np.mean(tr[: i + 1])
        return atr

    # First ATR value is SMA of first 'period' TRs
    atr[period - 1] = np.mean(tr[:period])

    # Wilder's recurrent smoothing
    factor = period - 1
    for i in range(period, n):
        atr[i] = (atr[i - 1] * factor + tr[i]) / period

    # Backfill warm-up period with first valid ATR
    first_val = atr[period - 1]
    for i in range(period - 1):
        atr[i] = first_val

    return atr


def find_swing_pivots(
    high: np.ndarray,
    low: np.ndarray,
    left_bars: int = 5,
    right_bars: int = 5,
) -> Tuple[List[Pivot], List[Pivot]]:
    """
    Extracts deterministic swing highs and swing lows using a rolling window.
    High pivot at i: high[i] > high[i-k..i-1] and high[i] >= high[i+1..i+k]
    Low pivot at i:  low[i] < low[i-k..i-1]   and low[i] <= low[i+1..i+k]
    """
    n = len(high)
    high_pivots: List[Pivot] = []
    low_pivots: List[Pivot] = []

    if n < left_bars + right_bars + 1:
        return high_pivots, low_pivots

    for i in range(left_bars, n - right_bars):
        h = high[i]
        l = low[i]

        # Swing High
        if np.all(h > high[i - left_bars : i]) and np.all(h >= high[i + 1 : i + right_bars + 1]):
            high_pivots.append(Pivot(index=i, price=float(h), pivot_type="HIGH"))

        # Swing Low
        if np.all(l < low[i - left_bars : i]) and np.all(l <= low[i + 1 : i + right_bars + 1]):
            low_pivots.append(Pivot(index=i, price=float(l), pivot_type="LOW"))

    return high_pivots, low_pivots


def cluster_sr_zones(
    pivots: List[Pivot],
    current_atr: float,
    total_bars: int,
    tolerance_atr: float = 0.35,
    min_touches: int = 2,
    half_life_bars: float = 60.0,
) -> List[SRZone]:
    """
    Clusters adjacent swing pivots into consolidated S/R zones using 1D ATR tolerance.
    Calculates zone boundaries, touch counts, and recency-decayed scores.
    """
    if not pivots:
        return []

    # Sort pivots by price ascending
    sorted_pivots = sorted(pivots, key=lambda p: p.price)
    tolerance = max(current_atr * tolerance_atr, 1e-6)

    clusters: List[List[Pivot]] = []
    current_cluster: List[Pivot] = [sorted_pivots[0]]

    for p in sorted_pivots[1:]:
        # Compare against current cluster's price mean
        cluster_mean = sum(x.price for x in current_cluster) / len(current_cluster)
        if abs(p.price - cluster_mean) <= tolerance:
            current_cluster.append(p)
        else:
            clusters.append(current_cluster)
            current_cluster = [p]
    if current_cluster:
        clusters.append(current_cluster)

    zones: List[SRZone] = []
    for cluster in clusters:
        touches = len(cluster)
        prices = [p.price for p in cluster]
        core = float(np.median(prices))
        lower = float(min(prices))
        upper = float(max(prices))
        last_idx = max(p.index for p in cluster)

        # Recency decay: half-life in bars
        bars_ago = max(0, (total_bars - 1) - last_idx)
        recency_weight = 2.0 ** (-bars_ago / half_life_bars)

        # Determine zone type
        types = set(p.pivot_type for p in cluster)
        if "HIGH" in types and "LOW" in types:
            zone_type = "BOTH"
        elif "HIGH" in types:
            zone_type = "RESISTANCE"
        else:
            zone_type = "SUPPORT"

        # Score balances touch count and recency
        score = touches * (1.0 + recency_weight)

        zones.append(
            SRZone(
                zone_type=zone_type,
                core_price=core,
                lower=lower,
                upper=upper,
                touches=touches,
                last_touch_index=last_idx,
                score=round(score, 3),
            )
        )

    # Sort zones by core price ascending
    return sorted(zones, key=lambda z: z.core_price)


def analyze_sr_levels(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    current_price: float,
    left_bars: int = 5,
    right_bars: int = 5,
    tolerance_atr: float = 0.35,
    near_threshold_pct: float = 1.5,
) -> SRAnalysis:
    """
    Main S/R analytical pipeline:
    1. Computes ATR(14)
    2. Identifies swing pivots
    3. Clusters pivots into cohesive S/R zones
    4. Extracts nearest S1, S2, R1, R2 relative to current_price
    5. Computes % distances and contextual risk guidance
    """
    n = len(high)
    atr_series = compute_atr(high, low, close, period=14)
    current_atr = float(atr_series[-1]) if len(atr_series) > 0 and not np.isnan(atr_series[-1]) else max(float(high[-1] - low[-1]), 1e-4)

    high_pivots, low_pivots = find_swing_pivots(high, low, left_bars, right_bars)
    all_pivots = high_pivots + low_pivots

    if not all_pivots:
        return SRAnalysis(current_price=current_price, atr=current_atr)

    zones = cluster_sr_zones(
        pivots=all_pivots,
        current_atr=current_atr,
        total_bars=n,
        tolerance_atr=tolerance_atr,
    )

    # Filter into confirmed zones (touches >= 2) and single-touch pivots for fallbacks
    confirmed_zones = [z for z in zones if z.touches >= 2]

    # Supports: zones with core_price < current_price
    supports_confirmed = [z for z in confirmed_zones if z.core_price < current_price]
    # Resistances: zones with core_price > current_price
    resistances_confirmed = [z for z in confirmed_zones if z.core_price > current_price]

    # Fallback to single-touch zones if no multi-touch zones exist
    all_supports = [z for z in zones if z.core_price < current_price]
    all_resistances = [z for z in zones if z.core_price > current_price]

    # S1 & S2 selection (closest below current_price)
    s1_val: Optional[float] = None
    s1_touches = 0
    s2_val: Optional[float] = None
    s2_touches = 0

    if supports_confirmed:
        # Highest support below current price
        s1_zone = max(supports_confirmed, key=lambda z: z.core_price)
        s1_val = round(s1_zone.core_price, 4)
        s1_touches = s1_zone.touches
        remaining_supports = [z for z in supports_confirmed if z.core_price < s1_zone.core_price]
        if remaining_supports:
            s2_zone = max(remaining_supports, key=lambda z: z.core_price)
            s2_val = round(s2_zone.core_price, 4)
            s2_touches = s2_zone.touches
    elif all_supports:
        s1_zone = max(all_supports, key=lambda z: z.core_price)
        s1_val = round(s1_zone.core_price, 4)
        s1_touches = s1_zone.touches

    # R1 & R2 selection (closest above current_price)
    r1_val: Optional[float] = None
    r1_touches = 0
    r2_val: Optional[float] = None
    r2_touches = 0

    if resistances_confirmed:
        # Lowest resistance above current price
        r1_zone = min(resistances_confirmed, key=lambda z: z.core_price)
        r1_val = round(r1_zone.core_price, 4)
        r1_touches = r1_zone.touches
        remaining_res = [z for z in resistances_confirmed if z.core_price > r1_zone.core_price]
        if remaining_res:
            r2_zone = min(remaining_res, key=lambda z: z.core_price)
            r2_val = round(r2_zone.core_price, 4)
            r2_touches = r2_zone.touches
    elif all_resistances:
        r1_zone = min(all_resistances, key=lambda z: z.core_price)
        r1_val = round(r1_zone.core_price, 4)
        r1_touches = r1_zone.touches

    # Compute percentage distances
    s1_dist_pct = round(((current_price - s1_val) / current_price) * 100.0, 2) if s1_val is not None else None
    r1_dist_pct = round(((r1_val - current_price) / current_price) * 100.0, 2) if r1_val is not None else None

    # Determine context flag and description
    context_flag = "IN_VALUE_RANGE"
    context_desc = ""

    atr_near_margin = current_atr * 0.75

    if r1_val is not None and ((r1_dist_pct is not None and r1_dist_pct <= near_threshold_pct) or (r1_val - current_price) <= atr_near_margin):
        context_flag = "NEAR_RESISTANCE"
        context_desc = f"Непосредствено под съпротива R1 (+{r1_dist_pct:.1f}%)"
    elif s1_val is not None and ((s1_dist_pct is not None and s1_dist_pct <= near_threshold_pct) or (current_price - s1_val) <= atr_near_margin):
        context_flag = "NEAR_SUPPORT"
        context_desc = f"Непосредствено над подкрепа S1 (-{s1_dist_pct:.1f}%)"
    elif r1_val is None:
        context_flag = "BREAKOUT_ABOVE"
        context_desc = "Пробив над всички установени съпротиви (Price Discovery)"
    elif s1_val is None:
        context_flag = "BREAKDOWN_BELOW"
        context_desc = "Пробив под всички установени подкрепи"
    else:
        context_flag = "IN_VALUE_RANGE"
        s1_txt = f"-{s1_dist_pct:.1f}%" if s1_dist_pct is not None else "N/A"
        r1_txt = f"+{r1_dist_pct:.1f}%" if r1_dist_pct is not None else "N/A"
        context_desc = f"В диапазон: S1 ({s1_txt}) ⟷ R1 ({r1_txt})"

    return SRAnalysis(
        current_price=float(current_price),
        atr=round(current_atr, 4),
        s1=s1_val,
        s1_touches=s1_touches,
        s1_dist_pct=s1_dist_pct,
        s2=s2_val,
        s2_touches=s2_touches,
        r1=r1_val,
        r1_touches=r1_touches,
        r1_dist_pct=r1_dist_pct,
        r2=r2_val,
        r2_touches=r2_touches,
        context_flag=context_flag,
        context_desc=context_desc,
        zones=[z.to_dict() for z in zones],
    )
