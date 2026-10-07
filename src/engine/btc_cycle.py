"""
Bitcoin On-Chain Cycle Engine (BlockHorizon Integration).

Evaluates macro Bitcoin market cycle metrics from BlockHorizon:
- 0–100 Cycle Signal & sub-metrics (MVRV, MVRV-Z, NUPL, SOPR, Puell Multiple, Reserve Risk, Mayer Multiple)
- Classifies macro regime:
    * DEEP_VALUE (0 - 20): Capitulation / maximum long-term accumulation opportunity
    * EARLY_BULL (20 - 45): Macro breakout & recovery phase, risk-on favorable
    * MID_CYCLE (45 - 70): Trend continuation, follow technical trend
    * LATE_CYCLE (70 - 85): Overheating, trim leverage and tighten stops
    * EUPHORIA (85 - 100): Extreme distribution risk, defensive / hedge
- Generates institutional trading overlays:
    * Confluence score adjustment (+10, +5, 0, -10, -20)
    * Position sizing multiplier (1.25x, 1.0x, 1.0x, 0.6x, 0.3x)
    * Leverage ceiling (3x, 3x, 2x, 2x, 1x)
    * Altcoin long gate (blocks altcoin longs in EUPHORIA when BTC is not GOLD)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.storage.database import Database

logger = logging.getLogger(__name__)


# Standard scale mappings for individual on-chain metrics into 0 - 100 cycle scores
# (Higher = hotter / more overvalued; Lower = cooler / more undervalued)
def normalize_mvrv_z(val: float) -> float:
    """MVRV Z-score: <0 is deep value (~0-15), 0-2 is early bull (15-45), 2-4 mid (45-70), 4-6 late (70-85), >6 euphoria (>85)."""
    if val <= -0.5:
        return 5.0
    if val <= 0.0:
        return 10.0 + (val - (-0.5)) / 0.5 * 10.0  # 10 - 20
    if val <= 2.0:
        return 20.0 + (val / 2.0) * 25.0           # 20 - 45
    if val <= 4.0:
        return 45.0 + ((val - 2.0) / 2.0) * 25.0   # 45 - 70
    if val <= 6.5:
        return 70.0 + ((val - 4.0) / 2.5) * 18.0   # 70 - 88
    return min(100.0, 88.0 + (val - 6.5) * 4.0)


def normalize_mvrv(val: float) -> float:
    """MVRV ratio: <0.8 deep value, 1.0 breakeven, 1.0-2.4 neutral/bull, 2.4-3.5 late, >3.7 euphoria."""
    if val <= 0.8:
        return 10.0
    if val <= 1.2:
        return 10.0 + ((val - 0.8) / 0.4) * 20.0   # 10 - 30
    if val <= 2.2:
        return 30.0 + ((val - 1.2) / 1.0) * 30.0   # 30 - 60
    if val <= 3.2:
        return 60.0 + ((val - 2.2) / 1.0) * 22.0   # 60 - 82
    return min(100.0, 82.0 + (val - 3.2) * 12.0)


def normalize_nupl(val: float) -> float:
    """NUPL: <0 capitulation, 0-0.25 hope, 0.25-0.5 optimism, 0.5-0.7 belief, >0.75 euphoria."""
    if val <= 0.0:
        return max(0.0, 15.0 + val * 30.0)
    if val <= 0.25:
        return 15.0 + (val / 0.25) * 20.0         # 15 - 35
    if val <= 0.50:
        return 35.0 + ((val - 0.25) / 0.25) * 25.0 # 35 - 60
    if val <= 0.70:
        return 60.0 + ((val - 0.50) / 0.20) * 22.0 # 60 - 82
    return min(100.0, 82.0 + ((val - 0.70) / 0.20) * 18.0)


def normalize_puell(val: float) -> float:
    """Puell Multiple: <0.5 miner stress/bottom, 0.5-1.2 neutral, 1.2-2.0 bull expansion, >2.0 top risk."""
    if val <= 0.4:
        return 8.0
    if val <= 0.8:
        return 8.0 + ((val - 0.4) / 0.4) * 22.0    # 8 - 30
    if val <= 1.4:
        return 30.0 + ((val - 0.8) / 0.6) * 30.0   # 30 - 60
    if val <= 2.2:
        return 60.0 + ((val - 1.4) / 0.8) * 25.0   # 60 - 85
    return min(100.0, 85.0 + (val - 2.2) * 12.0)


def normalize_mayer(val: float) -> float:
    """Mayer Multiple: <0.8 deep value, 0.8-1.5 neutral/bull, 1.5-2.4 overheat, >2.4 euphoria."""
    if val <= 0.6:
        return 8.0
    if val <= 1.0:
        return 8.0 + ((val - 0.6) / 0.4) * 25.0    # 8 - 33
    if val <= 1.6:
        return 33.0 + ((val - 1.0) / 0.6) * 30.0   # 33 - 63
    if val <= 2.4:
        return 63.0 + ((val - 1.6) / 0.8) * 22.0   # 63 - 85
    return min(100.0, 85.0 + (val - 2.4) * 15.0)


@dataclass
class BtcCycleProfile:
    """Full quantitative profile of Bitcoin on-chain cycle regime."""
    cycle_score: float                     # 0 - 100
    regime: str                            # DEEP_VALUE, EARLY_BULL, MID_CYCLE, LATE_CYCLE, EUPHORIA
    slope_30d: float = 0.0                 # Trend of cycle score over 30 days
    metrics: Dict[str, float] = field(default_factory=dict)
    sizing_multiplier: float = 1.0         # Position sizing scaling factor
    confluence_adjustment: int = 0         # Score delta for BTC trades
    max_leverage: int = 2                  # Cap on allowed leverage
    allow_alt_longs: bool = True           # Gate for altcoin longs
    verdict_text: str = ""                 # Descriptive summary string
    badge_bg: str = ""                     # Localized display badge
    thesis_bg: str = ""                    # Localized thesis narrative

    def to_dict(self) -> dict:
        return {
            "cycle_score": round(self.cycle_score, 1),
            "regime": self.regime,
            "slope_30d": round(self.slope_30d, 2),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "sizing_multiplier": self.sizing_multiplier,
            "confluence_adjustment": self.confluence_adjustment,
            "max_leverage": self.max_leverage,
            "allow_alt_longs": self.allow_alt_longs,
            "verdict_text": self.verdict_text,
            "badge_bg": self.badge_bg,
            "thesis_bg": self.thesis_bg,
        }


class BtcCycleEngine:
    """Evaluates Bitcoin on-chain data and determines market cycle regime."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db

    def classify_regime(self, cycle_score: float) -> str:
        """Classifies 0-100 composite cycle score into standardized macro regime."""
        score = max(0.0, min(100.0, float(cycle_score)))
        if score < 20.0:
            return "DEEP_VALUE"
        if score < 45.0:
            return "EARLY_BULL"
        if score < 70.0:
            return "MID_CYCLE"
        if score < 85.0:
            return "LATE_CYCLE"
        return "EUPHORIA"

    def compute_cycle_score(self, metrics: Dict[str, float]) -> float:
        """
        Computes composite 0-100 cycle score from available metrics.
        If BlockHorizon 'cycle_signal' is present, it serves as the authoritative anchor.
        """
        if not metrics:
            return 50.0

        # 1. Authoritative BlockHorizon Cycle Signal (0-100)
        direct_signal = metrics.get("cycle_signal")
        if direct_signal is not None:
            direct_val = max(0.0, min(100.0, float(direct_signal)))
            # If other sub-metrics are also present, blend gently (80% BlockHorizon signal, 20% sub-metrics)
            sub_score = self._compute_submetrics_score(metrics, exclude_keys={"cycle_signal"})
            if sub_score is not None:
                return round(0.80 * direct_val + 0.20 * sub_score, 1)
            return round(direct_val, 1)

        # 2. Derive from sub-metrics
        sub_score = self._compute_submetrics_score(metrics)
        if sub_score is not None:
            return round(sub_score, 1)

        return 50.0

    def _compute_submetrics_score(
        self,
        metrics: Dict[str, float],
        exclude_keys: Optional[set] = None,
    ) -> Optional[float]:
        """Calculates normalized weighted average of individual on-chain sub-metrics."""
        ex = exclude_keys or set()
        components: List[Tuple[float, float]] = []  # (value, weight)

        if "mvrv_z" in metrics and "mvrv_z" not in ex:
            components.append((normalize_mvrv_z(metrics["mvrv_z"]), 0.30))
        elif "mvrv" in metrics and "mvrv" not in ex:
            components.append((normalize_mvrv(metrics["mvrv"]), 0.25))

        if "nupl" in metrics and "nupl" not in ex:
            components.append((normalize_nupl(metrics["nupl"]), 0.25))

        if "puell_multiple" in metrics and "puell_multiple" not in ex:
            components.append((normalize_puell(metrics["puell_multiple"]), 0.20))

        if "mayer_multiple" in metrics and "mayer_multiple" not in ex:
            components.append((normalize_mayer(metrics["mayer_multiple"]), 0.15))

        if "fear_and_greed" in metrics and "fear_and_greed" not in ex:
            components.append((float(metrics["fear_and_greed"]), 0.10))

        if "cycle_signal_proxy" in metrics and "cycle_signal_proxy" not in ex:
            components.append((float(metrics["cycle_signal_proxy"]), 0.25))

        if not components:
            return None

        total_weight = sum(w for _, w in components)
        if total_weight <= 0:
            return None

        weighted_sum = sum(val * w for val, w in components)
        return max(0.0, min(100.0, weighted_sum / total_weight))

    def evaluate_cycle(
        self,
        metrics: Optional[Dict[str, float]] = None,
        btc_state: str = "GOLD",
    ) -> BtcCycleProfile:
        """
        Evaluates current Bitcoin cycle metrics and builds full institutional trading profile.
        If metrics is None, attempts to load latest metrics from SQLite Database.
        """
        active_metrics = dict(metrics) if metrics is not None else {}
        slope_30d = 0.0

        if not active_metrics and self.db:
            active_metrics = self.db.get_latest_onchain_metrics()
            # Calculate slope over last 30 days if history exists
            history = self.db.get_onchain_metrics(metric="cycle_signal")
            if not history:
                history = self.db.get_onchain_metrics(metric="mvrv_z")
            if len(history) >= 2:
                oldest_val = float(history[0]["value"])
                latest_val = float(history[-1]["value"])
                slope_30d = latest_val - oldest_val

        cycle_score = self.compute_cycle_score(active_metrics)
        regime = self.classify_regime(cycle_score)

        # Institutional Overlays by Regime
        if regime == "DEEP_VALUE":
            sizing_multiplier = 1.25
            confluence_adjustment = 10
            max_leverage = 3
            allow_alt_longs = True
            badge_bg = "🟢 ДЪЛБОКО ПОДЦЕНЕН (DEEP VALUE)"
            thesis_bg = (
                f"Он-чейн цикълът е на дъно (Score: {cycle_score:.0f}/100). "
                "Мрежовата оценка показва максимална акумулация и капитулация на продавачите. "
                "Препоръчва се пълно оразмеряване (1.25x) и приоритет на дълги позиции."
            )
            verdict_text = "DEEP_VALUE (Heavy Accumulation Zone)"

        elif regime == "EARLY_BULL":
            sizing_multiplier = 1.0
            confluence_adjustment = 5
            max_leverage = 3
            allow_alt_longs = True
            badge_bg = "🟢 РАНЕН БИК (EARLY BULL)"
            thesis_bg = (
                f"Он-чейн метриките показват здравословно разширяване на цикъла (Score: {cycle_score:.0f}/100). "
                "Ниска вероятност за макро връх, нормално оразмеряване (1.0x)."
            )
            verdict_text = "EARLY_BULL (Expansion / Accumulation)"

        elif regime == "MID_CYCLE":
            sizing_multiplier = 1.0
            confluence_adjustment = 0
            max_leverage = 2
            allow_alt_longs = True
            badge_bg = "⚪ СРЕДЕН ЦИКЪЛ (MID CYCLE)"
            thesis_bg = (
                f"Он-чейн оценките са неутрални (Score: {cycle_score:.0f}/100). "
                "Следвайте техническите сигнали на Larsson лентата."
            )
            verdict_text = "MID_CYCLE (Neutral / Trend Continuation)"

        elif regime == "LATE_CYCLE":
            sizing_multiplier = 0.6
            confluence_adjustment = -10
            max_leverage = 2
            allow_alt_longs = True
            badge_bg = "🟠 КЪСЕН ЦИКЪЛ (LATE CYCLE)"
            thesis_bg = (
                f"Прегряване на он-чейн метриките (Score: {cycle_score:.0f}/100). "
                "Нарастващ риск от разпределение. Препоръчва се намаляване на размера (0.6x) "
                "и пристягане на стоповете."
            )
            verdict_text = "LATE_CYCLE (Overheating / Risk Off)"

        else:  # EUPHORIA
            sizing_multiplier = 0.3
            confluence_adjustment = -20
            max_leverage = 1
            # In euphoria, altcoin longs are prohibited unless BTC is confirmed GOLD
            allow_alt_longs = (btc_state == "GOLD")
            badge_bg = "🔴 ЕУФОРИЯ (CYCLE TOP RISK)"
            thesis_bg = (
                f"Екстремно прегряване на он-чейн цикъла (Score: {cycle_score:.0f}/100). "
                "Висок риск от макро обръщане и дистрибуция от дългосрочните притежатели (LTH). "
                "Защитен режим: минимален размер (0.3x), лимит ливъридж 1x, блокада на нови алткойн позиции."
            )
            verdict_text = "EUPHORIA (Distribution Risk / Defensive)"

        return BtcCycleProfile(
            cycle_score=cycle_score,
            regime=regime,
            slope_30d=slope_30d,
            metrics=active_metrics,
            sizing_multiplier=sizing_multiplier,
            confluence_adjustment=confluence_adjustment,
            max_leverage=max_leverage,
            allow_alt_longs=allow_alt_longs,
            verdict_text=verdict_text,
            badge_bg=badge_bg,
            thesis_bg=thesis_bg,
        )
