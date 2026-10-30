"""
Smart Money Flow Engine for Larsson Market Scanner.
Measures institutional accumulation, volume microstructure, and options whale activity.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.engine.options_flow import get_options_flow, is_crypto_or_non_equity

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "backtest_cache")

# Sector mapping for macro money flow
SECTOR_ETFS: Dict[str, str] = {
    "XLB": "Материали и Ресурси",
    "XLI": "Индустриален Сектор",
    "XLU": "Комунални Услуги (Utilities)",
    "XLE": "Енергетика (Петрол & Газ)",
    "XLF": "Финанси & Банки",
    "XLV": "Здравеопазване",
    "XLY": "Потребителски Цикличен",
    "XLP": "Потребителски Нецикличен",
    "XLRE": "Недвижими Имоти (REITs)",
    "IGV": "Корпоративен Софтуер (SaaS)",
    "XLK": "Технологии (Широк)",
    "XLC": "Комуникационни Услуги",
    "SMH": "Полупроводници (Чипове)",
}


def calculate_chaikin_money_flow(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int = 20,
) -> float:
    """Calculates 20-day Chaikin Money Flow (CMF) from -1.0 to +1.0."""
    if len(closes) < period:
        return 0.0

    h = highs[-period:]
    l = lows[-period:]
    c = closes[-period:]
    v = volumes[-period:]

    hl_range = h - l
    # Avoid zero division
    valid = hl_range > 0
    if not np.any(valid) or np.sum(v) <= 0:
        return 0.0

    mfm = np.zeros(period, dtype=np.float64)
    mfm[valid] = ((c[valid] - l[valid]) - (h[valid] - c[valid])) / hl_range[valid]
    mfv = mfm * v

    total_vol = np.sum(v)
    if total_vol <= 0:
        return 0.0

    return float(np.sum(mfv) / total_vol)


def calculate_up_down_volume_ratio(
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int = 20,
) -> float:
    """Calculates 20-day Up-Volume / Down-Volume ratio."""
    if len(closes) < period + 1:
        return 1.0

    c = closes[-(period + 1):]
    v = volumes[-period:]

    diff = np.diff(c)
    up_vol = np.sum(v[diff > 0])
    dn_vol = np.sum(v[diff < 0])

    if dn_vol <= 0:
        return 2.5 if up_vol > 0 else 1.0

    return float(round(up_vol / dn_vol, 2))


def calculate_intraday_absorption(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 5,
) -> float:
    """
    Calculates average 5-day close location within bar range:
    (Close - Low) / (High - Low) * 100.
    Values > 50% indicate dip-buying absorption into the close.
    """
    if len(closes) < period:
        return 50.0

    h = highs[-period:]
    l = lows[-period:]
    c = closes[-period:]

    hl = h - l
    valid = hl > 0
    if not np.any(valid):
        return 50.0

    locations = np.zeros(period, dtype=np.float64)
    locations[valid] = (c[valid] - l[valid]) / hl[valid]
    return float(round(np.mean(locations[valid]) * 100.0, 1))


def analyze_smart_money(
    symbol: str,
    highs: Optional[np.ndarray] = None,
    lows: Optional[np.ndarray] = None,
    closes: Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
    ribbon_state: Optional[str] = None,
) -> Dict:
    """
    Performs comprehensive Smart Money Flow analysis for a symbol:
    - Volume Microstructure (CMF 20D, Up/Dn Volume, 5D Absorption)
    - Options Whales (Put/Call Ratio, Gamma Wall, Max Pain, Net Sentiment)
    - Composite Smart Money Score (0 - 100) and Bulgarian Verdict.
    """
    # Load from cache if arrays not provided
    if highs is None or lows is None or closes is None or volumes is None:
        clean_sym = symbol.replace("=", "_").replace("^", "_").replace(":", "_").replace("/", "_")
        cache_f = os.path.join(CACHE_DIR, f"{clean_sym}_1D.csv")
        if os.path.exists(cache_f):
            try:
                df = pd.read_csv(cache_f)
                if len(df) >= 30:
                    highs = df["high"].to_numpy(dtype=np.float64)
                    lows = df["low"].to_numpy(dtype=np.float64)
                    closes = df["close"].to_numpy(dtype=np.float64)
                    volumes = df["volume"].to_numpy(dtype=np.float64) if "volume" in df.columns else np.zeros(len(df))
            except Exception as e:
                logger.debug(f"Could not load cache for {symbol}: {e}")

    # Defaults
    cmf_20 = 0.0
    up_down_vol = 1.0
    absorption_5d = 50.0
    vol_shock = 1.0

    if highs is not None:
        highs = np.asarray(highs, dtype=np.float64)
    if lows is not None:
        lows = np.asarray(lows, dtype=np.float64)
    if closes is not None:
        closes = np.asarray(closes, dtype=np.float64)
    if volumes is not None:
        volumes = np.asarray(volumes, dtype=np.float64)

    if closes is not None and len(closes) >= 20 and volumes is not None and np.sum(volumes) > 0:
        cmf_20 = round(calculate_chaikin_money_flow(highs, lows, closes, volumes, 20), 3)
        up_down_vol = calculate_up_down_volume_ratio(closes, volumes, 20)
        absorption_5d = calculate_intraday_absorption(highs, lows, closes, 5)

        avg_vol_20 = np.mean(volumes[-21:-1]) if len(volumes) >= 21 else np.mean(volumes)
        if avg_vol_20 > 0:
            vol_shock = round(float(volumes[-1] / avg_vol_20), 2)

    # Options Flow analysis
    options_data = None
    if not is_crypto_or_non_equity(symbol):
        try:
            options_data = get_options_flow(symbol, ribbon_state=ribbon_state)
        except Exception as e:
            logger.debug(f"Options flow error for {symbol}: {e}")

    pcr = options_data.get("put_call_ratio") if options_data else None
    opt_sentiment = options_data.get("net_sentiment", "NEUTRAL") if options_data else "N/A"
    gamma_wall = options_data.get("gamma_wall") if options_data else None
    max_pain = options_data.get("max_pain") if options_data else None
    unusual_sweep = options_data.get("unusual_call_sweep", False) if options_data else False

    # Composite Smart Money Score (0 to 100)
    score = 50.0

    # 1. Volume structure score component (max +/- 25 pts)
    if cmf_20 > 0.10:
        score += 20.0
    elif cmf_20 > 0.03:
        score += 12.0
    elif cmf_20 < -0.12:
        score -= 15.0
    elif cmf_20 < -0.05:
        score -= 8.0

    if up_down_vol >= 1.25:
        score += 10.0
    elif up_down_vol >= 1.00:
        score += 5.0
    elif up_down_vol < 0.75:
        score -= 10.0

    # 2. Intraday Absorption component (max +/- 15 pts)
    if absorption_5d >= 60.0:
        score += 12.0
    elif absorption_5d >= 50.0:
        score += 5.0
    elif absorption_5d < 35.0:
        score -= 10.0

    # 3. Options Flow component (max +/- 20 pts)
    if pcr is not None:
        if pcr <= 0.40:
            score += 18.0  # Heavy Call buying
        elif pcr <= 0.60:
            score += 10.0
        elif pcr >= 1.40:
            score -= 18.0  # Heavy Put buying / hedging
        elif pcr >= 1.10:
            score -= 8.0

    if unusual_sweep:
        score += 10.0

    # Cap score
    score = max(5.0, min(95.0, round(score, 1)))

    pcr_disp = f"{pcr:.2f}" if pcr is not None else "N/A"
    gw_disp = f"${gamma_wall:.2f}" if gamma_wall is not None else "N/A"

    # Classification & Verdict
    if score >= 75.0 or (cmf_20 > 0.08 and up_down_vol >= 1.0):
        flow_verdict = "STEALTH_ACCUMULATION"
        flow_label_bg = "🐋 СКРИТА АКУМУЛАЦИЯ"
        flow_desc_bg = f"Институциите тихомълком купуват (CMF: {cmf_20:+.2f}, Up/Dn Vol: {up_down_vol}x). Силна скрита подкрепа."
    elif (pcr is not None and pcr <= 0.50) or (score >= 65.0):
        flow_verdict = "OPTIONS_WHALE_ACCUMULATION"
        flow_label_bg = "🟢 ОПЦИОННИ КИТОВЕ (Call Buying)"
        flow_desc_bg = f"Агресивни покупки на Call опции (P/C: {pcr_disp}) с Gamma стена на {gw_disp}. Залог за рязък отскок."
    elif score <= 35.0 or (pcr is not None and pcr >= 1.35 and cmf_20 < 0.0):
        flow_verdict = "INSTITUTIONAL_DISTRIBUTION"
        flow_label_bg = "🔴 ИНСТИТУЦИОНАЛЕН НАТИСК / ХЕДЖ"
        flow_desc_bg = f"Оток на капитал или застраховане с Put опции (P/C: {pcr_disp}, CMF: {cmf_20:+.2f})."
    else:
        flow_verdict = "NEUTRAL_FLOW"
        flow_label_bg = "⚪ НЕУТРАЛЕН / СМЕСЕН ПОТОК"
        flow_desc_bg = f"Балансирани двупосочни обеми (CMF: {cmf_20:+.2f}, P/C: {pcr_disp})." 

    return {
        "symbol": symbol,
        "smart_money_score": score,
        "flow_verdict": flow_verdict,
        "flow_label_bg": flow_label_bg,
        "flow_desc_bg": flow_desc_bg,
        "cmf_20d": cmf_20,
        "up_down_vol_ratio": up_down_vol,
        "absorption_5d_pct": absorption_5d,
        "vol_shock_ratio": vol_shock,
        "put_call_ratio": pcr,
        "options_sentiment": opt_sentiment,
        "gamma_wall": gamma_wall,
        "max_pain": max_pain,
        "unusual_call_sweep": unusual_sweep,
    }


def compute_sector_smart_money_flow() -> List[Dict]:
    """
    Computes 20D Smart Money Flow across the 13 major US sector ETFs.
    Returns list sorted by Chaikin Money Flow (highest accumulation first).
    """
    results = []

    for etf_sym, etf_name in SECTOR_ETFS.items():
        cache_f = os.path.join(CACHE_DIR, f"{etf_sym}_1D.csv")
        cmf_val = 0.0
        r5 = 0.0
        r20 = 0.0
        daily_flow_b = 0.5
        last_price = 0.0

        if not os.path.exists(cache_f):
            try:
                from src.backtest.data_manager import BacktestDataManager
                dm = BacktestDataManager()
                dm.get_symbol_data(etf_sym, asset_class="indices", force_refresh=True)
            except Exception as e:
                logger.debug(f"Could not fetch ETF data for {etf_sym}: {e}")

        if os.path.exists(cache_f):
            try:
                df = pd.read_csv(cache_f)
                if len(df) >= 30:
                    c = df["close"].to_numpy(dtype=np.float64)
                    h = df["high"].to_numpy(dtype=np.float64)
                    l = df["low"].to_numpy(dtype=np.float64)
                    v = df["volume"].to_numpy(dtype=np.float64) if "volume" in df.columns else np.zeros(len(df))

                    last_price = round(float(c[-1]), 2)
                    cmf_val = round(calculate_chaikin_money_flow(h, l, c, v, 20), 3)
                    r5 = round(float(((c[-1] / c[-6]) - 1.0) * 100.0), 2) if len(c) >= 6 else 0.0
                    r20 = round(float(((c[-1] / c[-21]) - 1.0) * 100.0), 2) if len(c) >= 21 else 0.0
                    daily_flow_b = round(float(np.mean(c[-5:] * v[-5:])) / 1e9, 2) if len(c) >= 5 else 0.5
            except Exception as e:
                logger.debug(f"Sector flow cache read error for {etf_sym}: {e}")

        # Classification
        if cmf_val > 0.05:
            flow_status = "INFLOW"
            status_bg = "🟢 ПРИТОК (Акумулация)"
        elif cmf_val < -0.05:
            flow_status = "OUTFLOW"
            status_bg = "🔴 ОТЛИВ (Разтоварване)"
        else:
            flow_status = "NEUTRAL"
            status_bg = "⚪ НЕУТРАЛЕН"

        results.append({
            "ticker": etf_sym,
            "name": etf_name,
            "price": last_price,
            "cmf_20d": cmf_val,
            "return_5d_pct": r5,
            "return_20d_pct": r20,
            "daily_volume_usd_b": daily_flow_b,
            "flow_status": flow_status,
            "status_bg": status_bg,
        })

    # Sort descending by CMF (strongest accumulation on top)
    results.sort(key=lambda x: x["cmf_20d"], reverse=True)
    return results
