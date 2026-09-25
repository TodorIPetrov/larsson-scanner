"""
Options Flow Integration for Larsson Market Scanner (US Equities).
Overlay unusual options activity, put/call ratios, max pain, and gamma exposure
onto equity trend signals using Yahoo Finance option chains.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Cache: symbol -> (timestamp, options_flow_dict)
_OPTIONS_CACHE: Dict[str, Tuple[float, Optional[dict]]] = {}
CACHE_TTL = 3600  # 1 hour in seconds

# Black-Scholes normal PDF
def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_d1(spot: float, strike: float, iv: float, t: float) -> float:
    if spot <= 0 or strike <= 0 or iv <= 0 or t <= 0:
        return 0.0
    return (math.log(spot / strike) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))


def _calculate_gamma(spot: float, strike: float, iv: float, t: float) -> float:
    """Calculates Black-Scholes gamma for an option."""
    if spot <= 0 or strike <= 0 or iv <= 0 or t <= 0:
        return 0.0
    d1 = _norm_d1(spot, strike, iv, t)
    denom = spot * iv * math.sqrt(t)
    if denom <= 0:
        return 0.0
    return _norm_pdf(d1) / denom


def clear_options_cache() -> None:
    """Clears the in-memory options flow cache."""
    _OPTIONS_CACHE.clear()


def is_crypto_or_non_equity(symbol: str) -> bool:
    """Checks if a symbol is crypto, index, or non-equity asset without US options."""
    if not symbol or not isinstance(symbol, str):
        return True
    s = symbol.upper().strip()
    # Crypto indicators
    if s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD"):
        return True
    if "-USD" in s:
        return True
    # Futures / Forex / Special Yahoo symbols
    if "=" in s or "^" in s or "/" in s:
        return True
    # Known top crypto tickers
    if s in {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "DOT", "LINK"}:
        return True
    return False


def get_options_flow(
    symbol: str,
    ribbon_state: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[dict]:
    """
    Fetches and analyzes options chain data for US equities.
    Overlay unusual options activity, put/call ratio, net sentiment, max pain,
    and gamma wall on US equity signals.

    Returns:
    {
        'put_call_ratio': 0.72,
        'unusual_call_sweep': True,  # call vol/OI > 2.0
        'net_sentiment': 'BULLISH',  # 'BULLISH' | 'BEARISH' | 'NEUTRAL'
        'max_pain': 185.0,
        'gamma_wall': 190.0,
        'confluence_boost': True,  # True when options confirm ribbon signal
    }
    Returns None for crypto or symbols without options.
    """
    if is_crypto_or_non_equity(symbol):
        return None

    sym_clean = symbol.upper().strip()
    now = time.time()

    if use_cache and sym_clean in _OPTIONS_CACHE:
        cached_time, cached_data = _OPTIONS_CACHE[sym_clean]
        if (now - cached_time) < CACHE_TTL:
            if cached_data is not None:
                # Return copy with updated confluence boost if ribbon_state specified
                result = dict(cached_data)
                result["confluence_boost"] = _evaluate_confluence(
                    result.get("net_sentiment", "NEUTRAL"),
                    ribbon_state,
                    sym_clean,
                )
                return result
            return None

    try:
        ticker = yf.Ticker(sym_clean)
        options_dates = ticker.options
        if not options_dates or len(options_dates) == 0:
            if use_cache:
                _OPTIONS_CACHE[sym_clean] = (now, None)
            return None

        # Nearest expiration date
        nearest_expiry = options_dates[0]
        chain = ticker.option_chain(nearest_expiry)
        calls = chain.calls
        puts = chain.puts

        if calls is None or puts is None or (len(calls) == 0 and len(puts) == 0):
            if use_cache:
                _OPTIONS_CACHE[sym_clean] = (now, None)
            return None

        flow_data = _analyze_option_chain(
            ticker=ticker,
            symbol=sym_clean,
            nearest_expiry=nearest_expiry,
            calls=calls,
            puts=puts,
            ribbon_state=ribbon_state,
        )

        if use_cache:
            _OPTIONS_CACHE[sym_clean] = (now, flow_data)

        return flow_data

    except Exception as e:
        logger.debug(f"Failed to fetch options flow for {sym_clean}: {e}")
        if use_cache:
            _OPTIONS_CACHE[sym_clean] = (now, None)
        return None


def _evaluate_confluence(net_sentiment: str, ribbon_state: Optional[str], symbol: str) -> bool:
    """Evaluates whether options flow confirms the technical ribbon signal."""
    state = None
    if ribbon_state:
        state = ribbon_state.upper()
    else:
        try:
            from src.storage.database import Database
            db = Database()
            row = db.get_current_state(symbol, "1D")
            if row:
                state = row["current_state"]
        except Exception:
            state = None

    if not state:
        return False

    is_bullish_state = state in ("GOLD", "BULLISH", "LONG", "BUY")
    is_bearish_state = state in ("BLUE", "BEARISH", "SHORT", "SELL")

    if is_bullish_state and net_sentiment == "BULLISH":
        return True
    if is_bearish_state and net_sentiment == "BEARISH":
        return True
    return False


def _analyze_option_chain(
    ticker: yf.Ticker,
    symbol: str,
    nearest_expiry: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    ribbon_state: Optional[str] = None,
) -> dict:
    """Computes PCR, unusual call sweep, max pain, gamma wall, and net sentiment."""
    # Ensure DataFrames
    calls_df = calls if isinstance(calls, pd.DataFrame) else pd.DataFrame(calls)
    puts_df = puts if isinstance(puts, pd.DataFrame) else pd.DataFrame(puts)

    # 1. Total OI and Volume
    call_oi = float(calls_df["openInterest"].fillna(0).sum()) if "openInterest" in calls_df.columns else 0.0
    put_oi = float(puts_df["openInterest"].fillna(0).sum()) if "openInterest" in puts_df.columns else 0.0
    call_vol = float(calls_df["volume"].fillna(0).sum()) if "volume" in calls_df.columns else 0.0
    put_vol = float(puts_df["volume"].fillna(0).sum()) if "volume" in puts_df.columns else 0.0

    # 2. Put / Call Ratio (OI of nearest expiry)
    if call_oi > 0:
        pcr = round(put_oi / call_oi, 2)
    elif put_oi > 0:
        pcr = 2.0
    else:
        pcr = 1.0

    # 3. Unusual Call Sweep Activity (Call Volume / Call OI > 2.0)
    call_vol_oi_ratio = (call_vol / call_oi) if call_oi > 0 else 0.0
    unusual_call_sweep = bool(call_vol_oi_ratio > 2.0)

    # 4. Net Options Sentiment
    # 'BULLISH' (PCR < 0.7 or high call vol), 'BEARISH' (PCR > 1.3), 'NEUTRAL'
    if pcr < 0.7 or (unusual_call_sweep and pcr <= 1.0):
        net_sentiment = "BULLISH"
    elif pcr > 1.3 and not unusual_call_sweep:
        net_sentiment = "BEARISH"
    else:
        net_sentiment = "NEUTRAL"

    # 5. Strike Aggregations for Max Pain and Gamma Wall
    strike_oi: Dict[float, float] = {}
    strike_call_oi: Dict[float, float] = {}
    strike_put_oi: Dict[float, float] = {}
    strike_iv: Dict[float, float] = {}

    if "strike" in calls_df.columns:
        for _, row in calls_df.iterrows():
            k = float(row["strike"])
            oi = float(row.get("openInterest", 0) or 0)
            if math.isnan(oi):
                oi = 0.0
            iv = float(row.get("impliedVolatility", 0) or 0)
            strike_oi[k] = strike_oi.get(k, 0.0) + oi
            strike_call_oi[k] = strike_call_oi.get(k, 0.0) + oi
            if iv > 0 and not math.isnan(iv):
                strike_iv[k] = iv

    if "strike" in puts_df.columns:
        for _, row in puts_df.iterrows():
            k = float(row["strike"])
            oi = float(row.get("openInterest", 0) or 0)
            if math.isnan(oi):
                oi = 0.0
            iv = float(row.get("impliedVolatility", 0) or 0)
            strike_oi[k] = strike_oi.get(k, 0.0) + oi
            strike_put_oi[k] = strike_put_oi.get(k, 0.0) + oi
            if iv > 0 and not math.isnan(iv) and k not in strike_iv:
                strike_iv[k] = iv

    # 6. Max Pain Strike (strike with maximum options OI)
    max_pain: Optional[float] = None
    if strike_oi:
        max_pain = float(max(strike_oi, key=lambda k: strike_oi[k]))

    # 7. Gamma Wall Strike (largest absolute gamma exposure strike)
    # Estimate spot price
    spot_price = None
    try:
        if hasattr(ticker, "fast_info") and ticker.fast_info is not None:
            spot_price = getattr(ticker.fast_info, "last_price", None) or ticker.fast_info.get("lastPrice")
    except Exception:
        pass

    if not spot_price and max_pain is not None:
        spot_price = max_pain

    # Time to expiration in years
    t_years = 7.0 / 365.0  # default 1 week
    try:
        exp_dt = datetime.strptime(nearest_expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        diff_days = max(1.0, (exp_dt - now_dt).total_seconds() / 86400.0)
        t_years = diff_days / 365.0
    except Exception:
        pass

    gamma_wall: Optional[float] = None
    if strike_oi and spot_price and spot_price > 0:
        max_gex = -1.0
        best_strike = None
        for k, tot_oi in strike_oi.items():
            iv = strike_iv.get(k, 0.30)
            if iv <= 0 or math.isnan(iv):
                iv = 0.30
            gamma = _calculate_gamma(spot=spot_price, strike=k, iv=iv, t=t_years)
            abs_gex = tot_oi * gamma * (spot_price ** 2) * 0.01
            if abs_gex > max_gex:
                max_gex = abs_gex
                best_strike = k

        gamma_wall = float(best_strike) if best_strike is not None else max_pain
    else:
        gamma_wall = max_pain

    # 8. Confluence Boost
    confluence_boost = _evaluate_confluence(net_sentiment, ribbon_state, symbol)

    return {
        "put_call_ratio": pcr,
        "unusual_call_sweep": unusual_call_sweep,
        "unusual_call_volume": unusual_call_sweep,
        "net_sentiment": net_sentiment,
        "net_options_sentiment": net_sentiment,
        "max_pain": max_pain,
        "gamma_wall": gamma_wall,
        "confluence_boost": confluence_boost,
        "call_volume": round(call_vol, 1),
        "call_oi": round(call_oi, 1),
        "put_volume": round(put_vol, 1),
        "put_oi": round(put_oi, 1),
        "expiration": nearest_expiry,
    }
