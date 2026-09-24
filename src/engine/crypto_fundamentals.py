"""
Crypto Fundamental Analysis Engine.
Provides on-chain and market-structure scoring for cryptocurrency assets
using the CoinGecko free API (no API key required).
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BINANCE_TO_COINGECKO = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano",
    "AVAXUSDT": "avalanche-2",
    "SUIUSDT": "sui",
    "LINKUSDT": "chainlink",
    "PAXGUSDT": "pax-gold",
}

CRYPTO_CATEGORIES = {
    "bitcoin": "Store of Value",
    "ethereum": "L1 Smart Contracts",
    "solana": "L1 Smart Contracts",
    "binancecoin": "Exchange Token",
    "ripple": "Payments",
    "dogecoin": "Meme",
    "cardano": "L1 Smart Contracts",
    "avalanche-2": "L1 Smart Contracts",
    "sui": "L1 Smart Contracts",
    "chainlink": "Oracle / Infrastructure",
    "pax-gold": "Tokenized Commodity",
}


@dataclass
class CryptoFundamentalProfile:
    ticker: str
    name: str
    # Market Structure
    market_cap: float
    market_cap_rank: int
    volume_24h: float
    liquidity_score: float  # vol/mcap ratio
    # Supply Analysis
    circulating_supply: float
    total_supply: Optional[float]
    max_supply: Optional[float]
    supply_ratio: float  # circulating/total (dilution risk)
    # Price Context
    ath: float
    ath_distance_pct: float  # how far from ATH
    atl: float
    price_vs_range_pct: float  # position within ATL-ATH range
    # Scoring
    liquidity_score_value: int  # -2 to +2
    dilution_risk_score: int  # -2 to +2
    ath_opportunity_score: int  # -2 to +2
    market_cap_tier_score: int  # -2 to +2
    final_score: float
    signal: str  # 'Bullish', 'Neutral', 'Bearish'
    summary_bg: str
    summary_en: str
    category: str  # 'L1', 'L2', 'DeFi', 'Meme', 'Store of Value', etc.
    timestamp: str

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


class CryptoFundamentalEngine:
    def __init__(self, cache_dir: Optional[str] = None, cache_max_age_hours: int = 4):
        if cache_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            self.cache_dir = os.path.join(base_dir, "data", "cache", "crypto")
        else:
            self.cache_dir = cache_dir

        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_max_age_hours = cache_max_age_hours
        self.base_url = "https://api.coingecko.com/api/v3"
        self.call_delay = 2.5  # Rate limit safety

    def analyze_single(self, ticker: str) -> Optional[CryptoFundamentalProfile]:
        cg_id = BINANCE_TO_COINGECKO.get(ticker)
        if not cg_id:
            logger.warning(f"Ticker {ticker} not found in CoinGecko mapping.")
            return None

        # Check cache
        cache_path = os.path.join(self.cache_dir, f"{cg_id}.json")
        if os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if datetime.now() - mtime < timedelta(hours=self.cache_max_age_hours):
                logger.debug(f"Loading {ticker} from cache.")
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return self._compute_scores(ticker, data)
                except Exception as e:
                    logger.error(f"Error loading cache for {ticker}: {e}")

        # Fetch from API
        data = self._fetch_from_coingecko(cg_id)
        if data:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return self._compute_scores(ticker, data)
            except Exception as e:
                logger.error(f"Error processing data for {ticker}: {e}")
        return None

    def analyze_watchlist(self, tickers: List[str]) -> Dict[str, CryptoFundamentalProfile]:
        results = {}
        for ticker in tickers:
            profile = self.analyze_single(ticker)
            if profile:
                results[ticker] = profile
        return results

    def _fetch_from_coingecko(self, coingecko_id: str) -> dict:
        url = f"{self.base_url}/coins/{coingecko_id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
        logger.info(f"Fetching CoinGecko data for {coingecko_id}...")
        
        try:
            time.sleep(self.call_delay)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
                else:
                    logger.error(f"HTTP Error {response.status} for {coingecko_id}")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning(f"Rate limited by CoinGecko. Waiting 30s...")
                time.sleep(30)
                # Retry once
                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status == 200:
                            return json.loads(response.read().decode('utf-8'))
                except Exception as retry_e:
                    logger.error(f"Retry failed for {coingecko_id}: {retry_e}")
            else:
                logger.error(f"HTTPError {e.code} for {coingecko_id}: {e.reason}")
        except Exception as e:
            logger.error(f"Failed to fetch {coingecko_id} from CoinGecko: {e}")
            
        return {}

    def _compute_scores(self, ticker: str, data: dict) -> CryptoFundamentalProfile:
        cg_id = data.get("id", BINANCE_TO_COINGECKO.get(ticker, ""))
        name = data.get("name", ticker)
        market_data = data.get("market_data", {})
        
        current_price = market_data.get("current_price", {}).get("usd", 0)
        market_cap = market_data.get("market_cap", {}).get("usd", 0)
        market_cap_rank = data.get("market_cap_rank", 999)
        volume_24h = market_data.get("total_volume", {}).get("usd", 0)
        
        circulating_supply = market_data.get("circulating_supply", 0)
        total_supply = market_data.get("total_supply")
        max_supply = market_data.get("max_supply")
        
        ath = market_data.get("ath", {}).get("usd", 0)
        ath_change_pct = market_data.get("ath_change_percentage", {}).get("usd", 0) # usually negative
        ath_distance_pct = abs(ath_change_pct) if ath_change_pct else 0
        
        atl = market_data.get("atl", {}).get("usd", 0)
        
        # Derived metrics
        liquidity_score_raw = (volume_24h / market_cap * 100) if market_cap > 0 else 0
        
        reference_supply = max_supply if max_supply else total_supply
        supply_ratio = (circulating_supply / reference_supply * 100) if reference_supply and reference_supply > 0 else 100
        
        price_range = ath - atl
        price_vs_range_pct = ((current_price - atl) / price_range * 100) if price_range > 0 else 0
        
        # Liquidity Score (-2 to +2)
        if liquidity_score_raw > 15:
            liq_val = 2
            liq_bg = "Отлична"
            liq_en = "Excellent"
        elif liquidity_score_raw > 8:
            liq_val = 1
            liq_bg = "Много добра"
            liq_en = "Very Good"
        elif liquidity_score_raw > 3:
            liq_val = 0
            liq_bg = "Адекватна"
            liq_en = "Adequate"
        elif liquidity_score_raw > 1:
            liq_val = -1
            liq_bg = "Ниска"
            liq_en = "Low"
        else:
            liq_val = -2
            liq_bg = "Неликвиден"
            liq_en = "Illiquid"
            
        # Dilution Risk Score (-2 to +2)
        if supply_ratio > 90:
            dil_val = 2
            dil_bg = "напълно разредено"
            dil_en = "fully diluted"
        elif supply_ratio > 70:
            dil_val = 1
            dil_bg = "висока циркулация"
            dil_en = "high circulation"
        elif supply_ratio > 50:
            dil_val = 0
            dil_bg = "умерено"
            dil_en = "moderate"
        elif supply_ratio > 30:
            dil_val = -1
            dil_bg = "значително предстоящо разреждане"
            dil_en = "significant upcoming dilution"
        else:
            dil_val = -2
            dil_bg = "висок риск от разреждане"
            dil_en = "high dilution risk"
            
        # ATH Opportunity Score (-2 to +2)
        if ath_distance_pct > 70:
            ath_val = 2
            ath_desc_bg = "дълбока отстъпка"
            ath_desc_en = "deep discount"
        elif ath_distance_pct > 50:
            ath_val = 1
            ath_desc_bg = "добра отстъпка"
            ath_desc_en = "good discount"
        elif ath_distance_pct > 20:
            ath_val = 0
            ath_desc_bg = "справедлива стойност"
            ath_desc_en = "fairly valued"
        elif ath_distance_pct > 5:
            ath_val = -1
            ath_desc_bg = "близо до ATH, ограничен потенциал"
            ath_desc_en = "near ATH, limited upside"
        else:
            ath_val = -2
            ath_desc_bg = "на ATH, разтегнат"
            ath_desc_en = "at ATH, overextended"
            
        # Market Cap Tier (-2 to +2)
        if market_cap_rank <= 10:
            mcap_val = 2
            tier_bg = "Blue chip крипто"
            tier_en = "Blue chip crypto"
        elif market_cap_rank <= 30:
            mcap_val = 1
            tier_bg = "Large cap"
            tier_en = "Large cap"
        elif market_cap_rank <= 100:
            mcap_val = 0
            tier_bg = "Mid cap"
            tier_en = "Mid cap"
        elif market_cap_rank <= 300:
            mcap_val = -1
            tier_bg = "Small cap"
            tier_en = "Small cap"
        else:
            mcap_val = -2
            tier_bg = "Micro cap / Спекулативно"
            tier_en = "Micro cap / Speculative"
            
        # Final Score (Weighted average)
        # Liquidity: 25%, Dilution: 20%, ATH: 30%, Mcap: 25%
        # Max score: 2 * 0.25 + 2 * 0.20 + 2 * 0.30 + 2 * 0.25 = 2.0
        final_score = (liq_val * 0.25) + (dil_val * 0.20) + (ath_val * 0.30) + (mcap_val * 0.25)
        
        if final_score >= 0.5:
            signal = "Bullish"
        elif final_score > -0.5:
            signal = "Neutral"
        else:
            signal = "Bearish"
            
        ticker_base = ticker.replace("USDT", "")
        summary_bg = f"{ticker_base}: {tier_bg} (Rank #{market_cap_rank}). Ликвидност: {liq_bg}. {ath_distance_pct:.1f}% от ATH — {ath_desc_bg}. Предлагане: {dil_bg}. Сигнал: {signal}."
        summary_en = f"{ticker_base}: {tier_en} (Rank #{market_cap_rank}). Liquidity: {liq_en}. {ath_distance_pct:.1f}% from ATH — {ath_desc_en}. Supply: {dil_en}. Signal: {signal}."

        category = CRYPTO_CATEGORIES.get(cg_id, "Unknown")
        
        return CryptoFundamentalProfile(
            ticker=ticker,
            name=name,
            market_cap=market_cap,
            market_cap_rank=market_cap_rank,
            volume_24h=volume_24h,
            liquidity_score=liquidity_score_raw,
            circulating_supply=circulating_supply,
            total_supply=total_supply,
            max_supply=max_supply,
            supply_ratio=supply_ratio,
            ath=ath,
            ath_distance_pct=ath_distance_pct,
            atl=atl,
            price_vs_range_pct=price_vs_range_pct,
            liquidity_score_value=liq_val,
            dilution_risk_score=dil_val,
            ath_opportunity_score=ath_val,
            market_cap_tier_score=mcap_val,
            final_score=final_score,
            signal=signal,
            summary_bg=summary_bg,
            summary_en=summary_en,
            category=category,
            timestamp=datetime.now().isoformat()
        )
