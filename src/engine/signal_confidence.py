"""
ML-Enhanced Signal Confidence Scoring.

Scores trade proposals using a Gradient Boosting classifier trained on historical
completed trades from the trade_log table.  Falls back to a deterministic rule-based
scorer when fewer than 30 labelled training samples are available.

Public API
----------
compute_signal_confidence(proposal_features: dict) -> dict
    Returns a scored confidence report for a single trade proposal.

extract_features_from_proposal(proposal: dict, context: dict) -> dict
    Builds a feature vector from a live proposal + market context dict.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum labelled samples required before the ML model is trusted over rule-based scoring.
_MIN_ML_SAMPLES = 30

# ---------------------------------------------------------------------------
# Feature names (must stay stable – pickled model depends on ordering)
# ---------------------------------------------------------------------------
FEATURE_NAMES = [
    "ribbon_spread_at_flip",  # % spread between v1 and v2 at Gold flip
    "atr_percentile",         # volatility regime: 0=low, 1=normal, 2=high
    "sr_proximity",           # 0.0-1.0 proximity to nearest S/R (1 = right on level)
    "btc_alpha_direction",    # 1=positive BTC alpha, 0=neutral, -1=negative
    "volume_ratio",           # current volume / 20-day average volume
    "quality_tier",           # A→0, B→1, C/NONE→2
    "days_in_prior_state",    # bars in Blue/Neutral before turning Gold
    "market_breadth_pct",     # % of sector that was Gold at time of signal
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tier_to_int(tier: Any) -> int:
    """Encode quality tier to integer for ML feature."""
    if isinstance(tier, (int, float)):
        return int(min(2, max(0, tier)))
    t = str(tier or "").upper()
    if t in ("0", "A+", "A"):
        return 0
    if t in ("1", "B"):
        return 1
    return 2  # C / NONE


def _confidence_label(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Rule-based fallback scorer
# ---------------------------------------------------------------------------

def _rule_based_score(features: dict) -> dict:
    """
    Deterministic rule-based confidence scorer used when training data is sparse.

    Tier base: A=70, B=55, C/NONE=40
    Bonuses:
      +10  near support (sr_proximity >= 0.7)
      +8   positive BTC alpha
      +7   low volatility regime (atr_percentile == 0)
      +5   strong ribbon expansion (ribbon_spread_at_flip > 1.0%)
      +5   volume surge (volume_ratio > 1.5)
      -10  negative BTC alpha
      -5   high volatility regime (atr_percentile == 2)
    """
    tier = _tier_to_int(str(features.get("quality_tier", 2)))
    base = [70, 55, 40][min(tier, 2)]

    score = base

    sr = float(features.get("sr_proximity", 0.0))
    if sr >= 0.7:
        score += 10

    btc_dir = int(features.get("btc_alpha_direction", 0))
    if btc_dir > 0:
        score += 8
    elif btc_dir < 0:
        score -= 10

    atr_p = int(features.get("atr_percentile", 1))
    if atr_p == 0:
        score += 7
    elif atr_p == 2:
        score -= 5

    if float(features.get("ribbon_spread_at_flip", 0.0)) > 1.0:
        score += 5

    if float(features.get("volume_ratio", 1.0)) > 1.5:
        score += 5

    score = max(0, min(100, score))

    factors: List[str] = []
    if sr >= 0.7:
        factors.append("Near support level")
    if btc_dir > 0:
        factors.append("Positive BTC alpha")
    if atr_p == 0:
        factors.append("Low volatility (breakout zone)")
    if float(features.get("ribbon_spread_at_flip", 0.0)) > 1.0:
        factors.append("Strong ribbon expansion")
    if float(features.get("volume_ratio", 1.0)) > 1.5:
        factors.append("Volume surge")
    if btc_dir < 0:
        factors.append("BTC underperformance (drag)")
    if atr_p == 2:
        factors.append("High volatility (elevated risk)")

    return {
        "score": score,
        "confidence_label": _confidence_label(score),
        "top_factors": factors[:3],
        "model_type": "rule_based",
        "similar_setups_win_rate": None,
    }


# ---------------------------------------------------------------------------
# Training data extraction
# ---------------------------------------------------------------------------

def _load_training_data(db) -> tuple:
    """
    Loads completed trades from the trade_log / paper_positions tables
    and builds (X, y) arrays for the ML classifier.

    Returns (feature_rows: list[dict], labels: list[int]) where label=1 means
    the trade reached TP1 (win), label=0 means it did not.
    """
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            # We look for CLOSED positions that have both entry_price and tp1 recorded
            cur.execute("""
                SELECT p.ticker, p.entry_price, p.tp1, p.exit_price,
                       p.opened_at, p.closed_at,
                       p.direction,
                       st.v1, st.v2, st.current_state
                FROM paper_positions p
                LEFT JOIN symbol_states st ON p.ticker = st.ticker AND st.timeframe = '1D'
                WHERE p.status = 'CLOSED'
                  AND p.tp1 IS NOT NULL
                  AND p.exit_price IS NOT NULL
                  AND p.entry_price IS NOT NULL
                ORDER BY p.closed_at DESC
                LIMIT 500
            """)
            rows = cur.fetchall()
    except Exception as e:
        logger.debug(f"Could not load training data: {e}")
        return [], []

    feature_rows: List[dict] = []
    labels: List[int] = []

    for r in rows:
        try:
            entry = float(r["entry_price"])
            tp1 = float(r["tp1"])
            exit_p = float(r["exit_price"])
            direction = (r["direction"] or "LONG").upper()

            # Label: did price reach TP1?
            if direction == "LONG":
                hit_tp1 = int(exit_p >= tp1 * 0.99)
            else:
                hit_tp1 = int(exit_p <= tp1 * 1.01)

            v1 = float(r["v1"] or 0)
            v2 = float(r["v2"] or 0)
            ribbon_spread = ((v1 - v2) / v2 * 100) if v2 > 0 else 0.0

            feat: dict = {
                "ribbon_spread_at_flip": ribbon_spread,
                "atr_percentile": 1,      # default normal – we don't store ATR regime historically
                "sr_proximity": 0.5,       # default mid
                "btc_alpha_direction": 0,  # default neutral
                "volume_ratio": 1.0,       # default
                "quality_tier": 2,         # default C
                "days_in_prior_state": 3,  # default
                "market_breadth_pct": 50.0,# default
            }
            feature_rows.append(feat)
            labels.append(hit_tp1)
        except Exception:
            continue

    return feature_rows, labels


# ---------------------------------------------------------------------------
# Model training + prediction
# ---------------------------------------------------------------------------

_cached_model = None
_cached_model_n = 0  # number of samples model was trained on


def _get_or_train_model(db, force_retrain: bool = False):
    """
    Returns (model, win_rate) or (None, None) if insufficient data.
    Caches the model globally so it is only retrained once per process lifetime
    (or when `force_retrain=True`).
    """
    global _cached_model, _cached_model_n

    feature_rows, labels = _load_training_data(db)
    n = len(labels)

    if n < _MIN_ML_SAMPLES:
        return None, None

    if _cached_model is not None and not force_retrain and n == _cached_model_n:
        return _cached_model, sum(labels) / n

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        import numpy as np

        X = np.array([[r[f] for f in FEATURE_NAMES] for r in feature_rows], dtype=float)
        y = np.array(labels, dtype=int)

        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            random_state=42,
        )
        model.fit(X, y)
        _cached_model = model
        _cached_model_n = n
        win_rate = float(sum(labels)) / n
        logger.info(f"ML confidence model trained on {n} samples | win_rate={win_rate:.2%}")
        return model, win_rate
    except ImportError:
        logger.warning("scikit-learn not installed. Signal confidence will use rule-based fallback.")
        return None, None
    except Exception as e:
        logger.warning(f"ML model training failed: {e}")
        return None, None


def _ml_score(features: dict, model, win_rate: float) -> dict:
    """Use a trained sklearn model to produce a confidence score."""
    try:
        import numpy as np
        x = np.array([[features.get(f, 0.0) for f in FEATURE_NAMES]], dtype=float)
        proba = model.predict_proba(x)[0]
        # proba[1] = probability of reaching TP1
        raw_prob = float(proba[1]) if len(proba) > 1 else 0.5
        score = int(round(raw_prob * 100))
        score = max(0, min(100, score))

        # Feature importances mapped to human descriptions
        importances = model.feature_importances_
        feature_desc = {
            "ribbon_spread_at_flip": "Strong ribbon expansion",
            "atr_percentile": "Low volatility (breakout zone)",
            "sr_proximity": "Near support level",
            "btc_alpha_direction": "Positive BTC alpha",
            "volume_ratio": "Volume surge",
            "quality_tier": "High quality tier",
            "days_in_prior_state": "Extended prior trend",
            "market_breadth_pct": "Strong market breadth",
        }
        # Sort by importance and pick top 3
        ranked = sorted(zip(FEATURE_NAMES, importances), key=lambda x: x[1], reverse=True)
        top_factors = [feature_desc.get(fname, fname) for fname, _ in ranked[:3]]

        return {
            "score": score,
            "confidence_label": _confidence_label(score),
            "top_factors": top_factors,
            "model_type": "ml",
            "similar_setups_win_rate": round(win_rate, 4),
        }
    except Exception as e:
        logger.warning(f"ML scoring failed: {e}")
        return _rule_based_score(features)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features_from_proposal(proposal: dict, context: Optional[dict] = None) -> dict:
    """
    Build a feature dict from a live trade proposal dict and optional market context.

    Parameters
    ----------
    proposal : dict
        A TradeSuggestion.to_dict() output or similar, with keys like
        'spread_pct', 'score', 'tier', 'btc_alpha_30d', 'btc_ratio_state', etc.
    context : dict, optional
        Additional market context: {
            'atr_percentile': 0|1|2,          # volatility regime
            'sr_proximity': float,             # 0.0-1.0
            'volume_ratio': float,             # vol/20d_avg
            'days_in_prior_state': int,
            'market_breadth_pct': float,
        }
    """
    ctx = context or {}

    # ribbon_spread_at_flip
    ribbon_spread = float(proposal.get("spread_pct") or proposal.get("ribbon_spread_at_flip") or 0.0)

    # atr_percentile
    atr_p = int(ctx.get("atr_percentile", 1))

    # sr_proximity
    sr_prox = float(ctx.get("sr_proximity", 0.5))

    # btc_alpha_direction
    btc_state = (proposal.get("btc_ratio_state") or "NA").upper()
    btc_alpha = float(proposal.get("btc_alpha_30d") or 0.0)
    if btc_state == "GOLD" or btc_alpha > 2.0:
        btc_dir = 1
    elif btc_state == "BLUE" or btc_alpha < -2.0:
        btc_dir = -1
    else:
        btc_dir = 0

    # volume_ratio
    vol_ratio = float(ctx.get("volume_ratio", 1.0))

    # quality_tier
    tier = str(proposal.get("tier") or proposal.get("quality_tier") or "NONE")
    tier_int = _tier_to_int(tier)

    # days_in_prior_state
    days_prior = int(ctx.get("days_in_prior_state", 3))

    # market_breadth_pct
    breadth = float(ctx.get("market_breadth_pct", 50.0))

    return {
        "ribbon_spread_at_flip": ribbon_spread,
        "atr_percentile": atr_p,
        "sr_proximity": sr_prox,
        "btc_alpha_direction": btc_dir,
        "volume_ratio": vol_ratio,
        "quality_tier": tier_int,
        "days_in_prior_state": days_prior,
        "market_breadth_pct": breadth,
    }


def compute_signal_confidence(
    proposal_features: dict,
    db=None,
) -> dict:
    """
    Compute an ML (or rule-based fallback) confidence score for a trade proposal.

    Parameters
    ----------
    proposal_features : dict
        Output of :func:`extract_features_from_proposal`.  Can also be a raw
        proposal dict – the function will attempt to extract features if the
        standard keys are absent.
    db : Database, optional
        If provided, the ML model will be trained (or retrieved from cache)
        using historical trades.

    Returns
    -------
    dict with keys:
        score                  : int 0-100
        confidence_label       : 'HIGH' | 'MEDIUM' | 'LOW'
        top_factors            : list[str]
        model_type             : 'ml' | 'rule_based'
        similar_setups_win_rate: float | None
    """
    # Ensure we have the expected feature keys; if not, treat as raw proposal
    if not any(k in proposal_features for k in FEATURE_NAMES):
        proposal_features = extract_features_from_proposal(proposal_features)

    if db is not None:
        model, win_rate = _get_or_train_model(db)
        if model is not None:
            return _ml_score(proposal_features, model, win_rate)

    return _rule_based_score(proposal_features)


def format_confidence_for_telegram(confidence: dict) -> str:
    """
    Formats the confidence report as a single Telegram-ready line.

    Example output:
        📊 Confidence: 72/100 (HIGH) | 68% historical win rate
    """
    score = confidence.get("score", 0)
    label = confidence.get("confidence_label", "LOW")
    win_rate = confidence.get("similar_setups_win_rate")

    label_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(label, "⚪")
    wr_str = f" | {win_rate * 100:.0f}% historical win rate" if win_rate is not None else ""
    return f"📊 Confidence: {score}/100 ({label_emoji} {label}){wr_str}"
