"""
BTC Relative Strength & Ratio Engine.
Evaluates crypto assets and crypto-equities relative to Bitcoin (BTC).
Determines whether an asset is generating Alpha (outperforming BTC) or bleeding satoshis (underperforming).
Acts as an institutional gatekeeper for risk and leverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from src.engine.smma import compute_larsson_series, evaluate_larsson_state, LarssonState

logger = logging.getLogger(__name__)


@dataclass
class BTCRelativeAnalysis:
    """Comprehensive relative strength analysis of an asset against Bitcoin."""
    ticker: str
    asset_class: str
    current_ratio: float                       # Asset price / BTC price
    ratio_state: str                           # 'GOLD', 'BLUE', 'NEUTRAL'
    ratio_spread_pct: float                    # Larsson ribbon spread on ratio
    ratio_v1: float
    ratio_v2: float
    alpha_30d_pct: float                       # Asset 30d return - BTC 30d return
    alpha_7d_pct: float                        # Asset 7d return - BTC 7d return
    asset_perf_30d_pct: float                  # Asset raw 30d return
    btc_perf_30d_pct: float                    # BTC raw 30d return
    verdict: str                               # STRONG_ALPHA, ALPHA_OUTPERFORMER, NEUTRAL_CONSOLIDATION, UNDERPERFORMER, LAGGING_UNDERPERFORMER
    leverage_allowed: bool                     # False if underperforming (BLUE), True if GOLD/NEUTRAL
    badge_bg: str                              # e.g. "⚡ +18.4% vs BTC"
    label_bg: str                              # e.g. "🟢 НАДМИНАВА BTC (Alpha лидер)"
    thesis_bg: str                             # Detailed Bulgarian reasoning
    ratio_candles: List[Dict[str, Union[float, int]]] = field(default_factory=list) # [{time, open, high, low, close}] for UI chart


class BTCRelativeStrengthAnalyzer:
    """
    Computes synthetic Asset / BTC pairs, calculates Larsson SMMA ribbons on the ratio,
    and assigns relative strength / Alpha metrics.
    """

    def __init__(self, btc_cache_ttl_s: int = 300):
        self._cached_btc_crypto: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]] = None
        self._cached_btc_stocks: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]] = None
        self._last_fetch_crypto: float = 0.0
        self._last_fetch_stocks: float = 0.0
        self._ttl_s = btc_cache_ttl_s

    def compute_relative_strength(
        self,
        ticker: str,
        asset_class: str,
        asset_highs: np.ndarray,
        asset_lows: np.ndarray,
        asset_closes: np.ndarray,
        btc_highs: np.ndarray,
        btc_lows: np.ndarray,
        btc_closes: np.ndarray,
    ) -> Optional[BTCRelativeAnalysis]:
        """
        Calculates Asset/BTC ratio and Larsson line indicators on the ratio.
        """
        if len(asset_closes) < 30 or len(btc_closes) < 30:
            return None

        # Align series lengths by right-aligning (latest candle matches latest candle)
        min_len = min(len(asset_closes), len(btc_closes))
        a_h = np.asarray(asset_highs[-min_len:], dtype=np.float64)
        a_l = np.asarray(asset_lows[-min_len:], dtype=np.float64)
        a_c = np.asarray(asset_closes[-min_len:], dtype=np.float64)

        b_h = np.asarray(btc_highs[-min_len:], dtype=np.float64)
        b_l = np.asarray(btc_lows[-min_len:], dtype=np.float64)
        b_c = np.asarray(btc_closes[-min_len:], dtype=np.float64)

        # Avoid zero or negative division
        valid_mask = (b_c > 0) & (b_l > 0) & (b_h > 0) & (a_c > 0)
        if np.sum(valid_mask) < 25:
            return None

        # Compute synthetic ratio series:
        # Ratio Close = Asset Close / BTC Close
        # Ratio High = Asset High / BTC Low (max theoretical intraday ratio)
        # Ratio Low = Asset Low / BTC High (min theoretical intraday ratio)
        ratio_c = a_c / b_c
        ratio_h = np.maximum(a_h / np.maximum(b_l, 1e-8), ratio_c)
        ratio_l = np.minimum(a_l / np.maximum(b_h, 1e-8), ratio_c)

        # Calculate Larsson SMMA series on the ratio
        try:
            v1, m1, m2, v2, states = compute_larsson_series(ratio_h, ratio_l)
            current_state = states[-1].value if hasattr(states[-1], "value") else str(states[-1])
            curr_v1 = float(v1[-1])
            curr_v2 = float(v2[-1])
            ratio_spread = ((curr_v1 - curr_v2) / curr_v2) * 100.0 if curr_v2 > 0 else 0.0
        except Exception as e:
            logger.debug(f"SMMA calculation on ratio failed for {ticker}: {e}")
            current_state = "NEUTRAL"
            curr_v1 = float(ratio_c[-1])
            curr_v2 = float(ratio_c[-1])
            ratio_spread = 0.0

        current_ratio = float(ratio_c[-1])

        # Calculate Performance & Alpha metrics (30d and 7d)
        lookback_30 = min(30, min_len - 1)
        lookback_7 = min(7, min_len - 1)

        asset_30d_ret = ((a_c[-1] - a_c[-lookback_30 - 1]) / a_c[-lookback_30 - 1]) * 100.0 if a_c[-lookback_30 - 1] > 0 else 0.0
        btc_30d_ret = ((b_c[-1] - b_c[-lookback_30 - 1]) / b_c[-lookback_30 - 1]) * 100.0 if b_c[-lookback_30 - 1] > 0 else 0.0
        alpha_30d = round(asset_30d_ret - btc_30d_ret, 2)

        asset_7d_ret = ((a_c[-1] - a_c[-lookback_7 - 1]) / a_c[-lookback_7 - 1]) * 100.0 if a_c[-lookback_7 - 1] > 0 else 0.0
        btc_7d_ret = ((b_c[-1] - b_c[-lookback_7 - 1]) / b_c[-lookback_7 - 1]) * 100.0 if b_c[-lookback_7 - 1] > 0 else 0.0
        alpha_7d = round(asset_7d_ret - btc_7d_ret, 2)

        # Determine Verdict, Leverage gating & Bulgarian annotations
        sign_30 = "+" if alpha_30d >= 0 else ""
        badge_bg = f"₿ {sign_30}{alpha_30d:.1f}% vs BTC"

        if current_state == "GOLD":
            leverage_allowed = True
            if alpha_30d >= 5.0:
                verdict = "STRONG_ALPHA"
                label_bg = f"🟢 НАДМИНАВА BTC (+{alpha_30d:.1f}% Alpha)"
                thesis_bg = (
                    f"🏆 ЛИДЕР СПРЯМО БИТКОЙН: Двойката {ticker}/BTC е в бичи тренд (Gold Ribbon, spread {ratio_spread:+.1f}%). "
                    f"Активът носи +{alpha_30d:.1f}% превъзхождаща доходност (Alpha) над BTC за 30 дни. "
                    f"Поемането на допълнителен пазарен риск и 2x/3x левъридж е напълно оправдано."
                )
            else:
                verdict = "ALPHA_OUTPERFORMER"
                label_bg = f"🟢 БИЧИ ТРЕНД VS BTC ({sign_30}{alpha_30d:.1f}%)"
                thesis_bg = (
                    f"Възходящ тренд спрямо BTC (Gold Ribbon на {ticker}/BTC). "
                    f"Активът набира сила срещу базовия крипто бенчмарк."
                )
        elif current_state == "BLUE":
            leverage_allowed = False  # Hard gate: Block 2x/3x leverage on lagging assets!
            if alpha_30d <= -5.0:
                verdict = "LAGGING_UNDERPERFORMER"
                label_bg = f"🔴 ИЗОСТАВА ОТ BTC ({alpha_30d:.1f}% Alpha)"
                thesis_bg = (
                    f"⚠️ ИЗОСТАВА СПРЯМО БИТКОЙН: Съотношението {ticker}/BTC е в активен мечи тренд (Blue Ribbon). "
                    f"Активът губи стойност в сатошита ({alpha_30d:.1f}% изоставане спрямо BTC за 30д). "
                    f"Поемането на риск с левъридж НЕ Е ОПРАВДАНО — задържането на чист BTC предлага по-добро съотношение риск/доходност."
                )
            else:
                verdict = "UNDERPERFORMER"
                label_bg = f"🔴 СЛАБОСТ VS BTC ({alpha_30d:.1f}%)"
                thesis_bg = (
                    f"Мечи низходящ тренд на съотношението {ticker}/BTC. "
                    f"Активът отстъпва позиции спрямо Bitcoin. Левъриджът е блокиран на 1x Spot."
                )
        else:  # NEUTRAL
            leverage_allowed = True
            verdict = "NEUTRAL_CONSOLIDATION"
            label_bg = f"🟡 БАЛАНС VS BTC ({sign_30}{alpha_30d:.1f}%)"
            thesis_bg = (
                f"Консолидация на съотношението {ticker}/BTC. "
                f"Ценовото представяне е сравнимо с това на Bitcoin ({sign_30}{alpha_30d:.1f}% за 30д). "
                f"Изчакайте пробив на съотношението за агресивна позиция."
            )

        # Generate lightweight candle history for ratio chart (last 90 bars)
        ratio_candles = []
        recent_bars = min(90, min_len)
        for i in range(min_len - recent_bars, min_len):
            ratio_candles.append({
                "index": i,
                "open": round(float(ratio_c[i - 1] if i > 0 else ratio_c[i]), 8),
                "high": round(float(ratio_h[i]), 8),
                "low": round(float(ratio_l[i]), 8),
                "close": round(float(ratio_c[i]), 8),
            })

        return BTCRelativeAnalysis(
            ticker=ticker,
            asset_class=asset_class,
            current_ratio=round(current_ratio, 8),
            ratio_state=current_state,
            ratio_spread_pct=round(ratio_spread, 2),
            ratio_v1=round(curr_v1, 8),
            ratio_v2=round(curr_v2, 8),
            alpha_30d_pct=alpha_30d,
            alpha_7d_pct=alpha_7d,
            asset_perf_30d_pct=round(asset_30d_ret, 2),
            btc_perf_30d_pct=round(btc_30d_ret, 2),
            verdict=verdict,
            leverage_allowed=leverage_allowed,
            badge_bg=badge_bg,
            label_bg=label_bg,
            thesis_bg=thesis_bg,
            ratio_candles=ratio_candles,
        )
