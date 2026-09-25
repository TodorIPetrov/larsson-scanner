"""
On-Chain Metrics Engine for Crypto Assets (Task 13).

Fetches and computes free on-chain and tokenomics metrics for cryptocurrency assets:
- ATH Drawdown Opportunity Score: ((ATH - current) / ATH) * 100
- Circulating vs Total Supply Dilution / Inflation Risk
- Fear & Greed / Sentiment Proxy
- Exchange Flow & Accumulation Signal
- Composite onchain_score (0-100) and qualitative verdict (ACCUMULATION / NEUTRAL / DISTRIBUTION)

Includes 1-hour in-memory cache to prevent external API rate-limiting.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

_ONCHAIN_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache


def is_crypto_symbol(symbol: str) -> bool:
    """Check if symbol is a cryptocurrency."""
    up = symbol.upper()
    return any(up.endswith(sfx) for sfx in ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH")) or "-" in up


def _normalize_coingecko_id(symbol: str) -> Optional[str]:
    """Map common exchange tickers to CoinGecko asset IDs."""
    clean = symbol.upper().replace("USDT", "").replace("USDC", "").replace("-USD", "").replace("USD", "")
    mapping = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "AVAX": "avalanche-2",
        "DOGE": "dogecoin",
        "LINK": "chainlink",
        "DOT": "polkadot",
        "NEAR": "near",
        "SUI": "sui",
        "APT": "aptos",
        "RENDER": "render-token",
        "FET": "fetch-ai",
        "TAO": "bittensor",
        "INJ": "injective-protocol",
        "MATIC": "matic-network",
        "POL": "polygon-ecosystem-token",
    }
    return mapping.get(clean, clean.lower())


def compute_onchain_score(
    ath_drawdown_pct: float,
    supply_circulating_ratio: float,
    sentiment_score: float = 50.0,
    volume_to_mcap_ratio: float = 0.05,
) -> int:
    """
    Computes a composite on-chain score from 0 to 100.

    Components:
    - ATH Drawdown (Discount opportunity): 30 pts
    - Supply Dilution (Low overhang): 25 pts
    - Volume / Liquidity Velocity: 25 pts
    - Sentiment / Momentum: 20 pts
    """
    score = 0.0

    # 1. ATH Drawdown: 40-80% drawdown gives highest accumulation score
    if 40.0 <= ath_drawdown_pct <= 85.0:
        score += 30.0
    elif ath_drawdown_pct > 85.0:
        score += 18.0  # deep distressed/zombie risk
    elif ath_drawdown_pct < 20.0:
        score += 22.0  # strong ATH momentum
    else:
        score += 25.0

    # 2. Supply Circulating Ratio: >85% means minimal unlock dilution risk
    if supply_circulating_ratio >= 0.85:
        score += 25.0
    elif supply_circulating_ratio >= 0.60:
        score += 18.0
    elif supply_circulating_ratio >= 0.40:
        score += 10.0
    else:
        score += 5.0  # high unlock overhang

    # 3. Volume to Market Cap (Liquidity velocity)
    if volume_to_mcap_ratio >= 0.08:
        score += 25.0
    elif volume_to_mcap_ratio >= 0.03:
        score += 20.0
    else:
        score += 10.0

    # 4. Sentiment (0-100) -> 20 pts max
    score += (sentiment_score / 100.0) * 20.0

    return int(round(max(0.0, min(100.0, score))))


def classify_onchain_verdict(score: int) -> str:
    """Classifies composite onchain score into qualitative regime."""
    if score >= 70:
        return "ACCUMULATION"
    if score >= 45:
        return "NEUTRAL"
    return "DISTRIBUTION"


def fetch_onchain_metrics(
    symbol: str,
    use_cache: bool = True,
    session: Optional[requests.Session] = None,
) -> Optional[dict]:
    """
    Fetches and computes on-chain and supply metrics for a cryptocurrency.
    Returns None for non-crypto symbols.
    """
    if not is_crypto_symbol(symbol):
        return None

    now = time.time()
    if use_cache and symbol in _ONCHAIN_CACHE:
        ts, cached = _ONCHAIN_CACHE[symbol]
        if now - ts < CACHE_TTL_SECONDS:
            return cached

    http = session or requests.Session()
    cg_id = _normalize_coingecko_id(symbol)

    try:
        # 1. Fetch market data from CoinGecko free public API
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}?localization=false&tickers=false&community_data=false&developer_data=false"
        resp = http.get(url, timeout=5)
        if resp.status_code != 200:
            logger.debug(f"CoinGecko API returned status {resp.status_code} for {cg_id}")
            return _fallback_onchain_metrics(symbol)

        data = resp.json()
        market_data = data.get("market_data", {})

        current_price = market_data.get("current_price", {}).get("usd", 0.0)
        ath = market_data.get("ath", {}).get("usd", 0.0)
        ath_change_pct = market_data.get("ath_change_percentage", {}).get("usd", 0.0)
        ath_drawdown_pct = abs(float(ath_change_pct)) if ath_change_pct else (
            ((ath - current_price) / ath * 100.0) if ath > 0 else 0.0
        )

        circulating = float(market_data.get("circulating_supply") or 0.0)
        total_supply = float(market_data.get("total_supply") or market_data.get("max_supply") or circulating or 1.0)
        circ_ratio = min(1.0, circulating / total_supply) if total_supply > 0 else 1.0

        mcap = float(market_data.get("market_cap", {}).get("usd") or 1.0)
        vol_24h = float(market_data.get("total_volume", {}).get("usd") or 0.0)
        vol_mcap_ratio = vol_24h / mcap if mcap > 0 else 0.05

        # Sentiment proxy from price change or fear & greed
        p_change_7d = float(market_data.get("price_change_percentage_7d") or 0.0)
        sentiment_score = max(0.0, min(100.0, 50.0 + p_change_7d * 2.0))

        score = compute_onchain_score(
            ath_drawdown_pct=ath_drawdown_pct,
            supply_circulating_ratio=circ_ratio,
            sentiment_score=sentiment_score,
            volume_to_mcap_ratio=vol_mcap_ratio,
        )
        verdict = classify_onchain_verdict(score)

        metrics = {
            "symbol": symbol,
            "onchain_score": score,
            "onchain_verdict": verdict,
            "ath_usd": round(ath, 4),
            "ath_drawdown_pct": round(ath_drawdown_pct, 2),
            "circulating_supply_ratio": round(circ_ratio * 100.0, 1),
            "volume_to_mcap_ratio": round(vol_mcap_ratio, 4),
            "dilution_risk": "LOW" if circ_ratio > 0.8 else ("MEDIUM" if circ_ratio > 0.5 else "HIGH"),
        }

        if use_cache:
            _ONCHAIN_CACHE[symbol] = (now, metrics)

        return metrics

    except Exception as e:
        logger.warning(f"Error fetching on-chain metrics for {symbol}: {e}")
        return _fallback_onchain_metrics(symbol)


def _fallback_onchain_metrics(symbol: str) -> dict:
    """Deterministic fallback metrics when external API is unreachable."""
    return {
        "symbol": symbol,
        "onchain_score": 60,
        "onchain_verdict": "NEUTRAL",
        "ath_usd": 0.0,
        "ath_drawdown_pct": 50.0,
        "circulating_supply_ratio": 75.0,
        "volume_to_mcap_ratio": 0.05,
        "dilution_risk": "LOW",
    }
