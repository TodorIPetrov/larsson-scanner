"""
Asset-Class Specific Trading Profiles & Quality Tier System.
Provides per-class risk parameters and assigns quality tiers to all monitored assets.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

OPTIMAL_PROFILES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "asset_optimal_profiles.json",
)
SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "settings.yaml",
)

_OPTIMAL_PROFILES_CACHE: Optional[Dict[str, dict]] = None


def load_optimal_profiles() -> Dict[str, dict]:
    global _OPTIMAL_PROFILES_CACHE
    if _OPTIMAL_PROFILES_CACHE is not None:
        return _OPTIMAL_PROFILES_CACHE
    if os.path.exists(OPTIMAL_PROFILES_FILE):
        try:
            with open(OPTIMAL_PROFILES_FILE, "r", encoding="utf-8") as f:
                _OPTIMAL_PROFILES_CACHE = json.load(f)
                return _OPTIMAL_PROFILES_CACHE
        except Exception as e:
            logger.warning(f"Could not load asset_optimal_profiles.json: {e}")
    _OPTIMAL_PROFILES_CACHE = {}
    return _OPTIMAL_PROFILES_CACHE


def get_empirical_asset_profile(ticker: Optional[str]) -> Optional[dict]:
    """Returns the empirical backtest profile (best strategy, tier, metrics) for a ticker."""
    if not ticker:
        return None
    clean = ticker.split(":")[-1].strip().upper()
    profiles = load_optimal_profiles()
    return profiles.get(clean)

@dataclass
class AssetClassProfile:
    """Trading parameters specific to each asset class."""
    name: str
    atr_multiplier_sl: float  # ATR multiplier for stop-loss distance
    atr_multiplier_tp1: float  # ATR multiplier for TP1 target
    atr_multiplier_tp2: float  # ATR multiplier for TP2 target
    min_confidence: int  # Minimum confluence score to generate suggestion (0-100)
    max_position_pct: float  # Maximum position size as % of portfolio
    min_rr_threshold: float  # Minimum risk-reward ratio
    volatility_regime: str  # 'LOW', 'MEDIUM', 'MEDIUM_HIGH', 'HIGH'
    typical_hold_days: str  # '2-14', '5-30', etc.
    trading_hours: str  # '24/7', 'US_MARKET', 'EU_MARKET', 'ASIA_MARKET'
    allows_short: bool
    description_bg: str

ASSET_CLASS_PROFILES: Dict[str, AssetClassProfile] = {
    'crypto': AssetClassProfile(
        name='Crypto',
        atr_multiplier_sl=2.0,
        atr_multiplier_tp1=2.0,
        atr_multiplier_tp2=4.0,
        min_confidence=35,
        max_position_pct=5.0,
        min_rr_threshold=1.8,
        volatility_regime='HIGH',
        typical_hold_days='2-14',
        trading_hours='24/7',
        allows_short=False,
        description_bg='Крипто активи — висока волатилност, 24/7 търговия, по-широки стопове',
    ),
    'us_stocks': AssetClassProfile(
        name='US Stocks',
        atr_multiplier_sl=1.5,
        atr_multiplier_tp1=1.8,
        atr_multiplier_tp2=3.5,
        min_confidence=40,
        max_position_pct=8.0,
        min_rr_threshold=1.8,
        volatility_regime='MEDIUM',
        typical_hold_days='5-30',
        trading_hours='US_MARKET',
        allows_short=False,
        description_bg='Американски акции — средна волатилност, борсови часове, добра ликвидност',
    ),
    'ai_stocks': AssetClassProfile(
        name='AI Stocks',
        atr_multiplier_sl=1.8,
        atr_multiplier_tp1=2.0,
        atr_multiplier_tp2=4.0,
        min_confidence=40,
        max_position_pct=6.0,
        min_rr_threshold=1.8,
        volatility_regime='MEDIUM_HIGH',
        typical_hold_days='5-20',
        trading_hours='US_MARKET',
        allows_short=False,
        description_bg='AI акции — повишена волатилност, секторна концентрация, growth-ориентирани',
    ),
    'crypto_stocks': AssetClassProfile(
        name='Crypto Stocks',
        atr_multiplier_sl=2.0,
        atr_multiplier_tp1=2.0,
        atr_multiplier_tp2=4.5,
        min_confidence=40,
        max_position_pct=5.0,
        min_rr_threshold=2.0,
        volatility_regime='HIGH',
        typical_hold_days='3-20',
        trading_hours='US_MARKET',
        allows_short=False,
        description_bg='Крипто-свързани акции — висока волатилност, корелирани с BTC',
    ),
    'intl_stocks': AssetClassProfile(
        name='International Stocks',
        atr_multiplier_sl=1.5,
        atr_multiplier_tp1=1.8,
        atr_multiplier_tp2=3.5,
        min_confidence=45,
        max_position_pct=7.0,
        min_rr_threshold=1.8,
        volatility_regime='MEDIUM',
        typical_hold_days='5-30',
        trading_hours='EU_MARKET',
        allows_short=False,
        description_bg='Международни акции — различни борси и часови зони, валутен риск',
    ),
    'commodities': AssetClassProfile(
        name='Commodities',
        atr_multiplier_sl=1.8,
        atr_multiplier_tp1=2.0,
        atr_multiplier_tp2=3.5,
        min_confidence=40,
        max_position_pct=6.0,
        min_rr_threshold=1.8,
        volatility_regime='MEDIUM_HIGH',
        typical_hold_days='5-20',
        trading_hours='US_MARKET',
        allows_short=False,
        description_bg='Суровини — циклични, сезонни, реагират на макро фактори',
    ),
    'indices': AssetClassProfile(
        name='Indices',
        atr_multiplier_sl=1.2,
        atr_multiplier_tp1=1.5,
        atr_multiplier_tp2=3.0,
        min_confidence=45,
        max_position_pct=10.0,
        min_rr_threshold=1.5,
        volatility_regime='LOW_MEDIUM',
        typical_hold_days='5-30',
        trading_hours='US_MARKET',
        allows_short=False,
        description_bg='Индекси — нисък риск, широка диверсификация, benchmark-ориентирани',
    ),
}

# Quality Tiers:
# S-Tier: 'Always watch' - Blue chip stocks, BTC/ETH. Pullback = prime opportunity. Larger position allowed.
# A-Tier: 'Quality asset' - Proven growth, tier-1 altcoins. Good setups deserve full sizing.
# B-Tier: 'Promising' - Higher risk but potential. Reduced position size.
# C-Tier: 'Speculative' - Meme coins, penny stocks. Minimum size, strict SL.

QUALITY_TIERS: Dict[str, str] = {
    # === CRYPTO ===
    'BTCUSDT': 'S',
    'ETHUSDT': 'S',
    'SOLUSDT': 'A',
    'BNBUSDT': 'A',
    'XRPUSDT': 'B',
    'LINKUSDT': 'A',
    'AVAXUSDT': 'B',
    'ADAUSDT': 'B',
    'SUIUSDT': 'B',
    'DOGEUSDT': 'C',
    'PAXGUSDT': 'A',
    
    # === US STOCKS - S Tier (Blue Chips / Dominant Market Position) ===
    'AAPL': 'S', 'MSFT': 'S', 'GOOGL': 'S', 'AMZN': 'S', 'META': 'S',
    'NVDA': 'S', 'JPM': 'S', 'V': 'S', 'JNJ': 'S', 'WMT': 'S', 'PG': 'S',
    'UNH': 'S', 'HD': 'S', 'MA': 'S', 'LLY': 'S', 'AVGO': 'S', 'COST': 'S',
    
    # === US STOCKS - A Tier (Strong Growth / Quality) ===
    'TSLA': 'A', 'NFLX': 'A', 'AMD': 'A', 'CRM': 'A', 'PLTR': 'A', 'UBER': 'A',
    'XOM': 'A', 'CVX': 'A', 'ABBV': 'A', 'MRK': 'A', 'INTU': 'A', 'ADBE': 'A',
    'MELI': 'A', 'AXP': 'A', 'BAC': 'A', 'KO': 'A', 'OXY': 'A', 'MCO': 'A', 'CB': 'A',
    
    # === US STOCKS - B Tier ===
    'RKLB': 'B', 'ASTS': 'B', 'LUNR': 'B', 'RDW': 'B', 'DECK': 'B', 'NU': 'B',
    'NDAQ': 'B', 'EFX': 'B', 'KHC': 'B', 'PSUS': 'B', 'PS': 'B', 'SIRI': 'C',
    
    # === AI STOCKS ===
    'ASML': 'S', 'TSM': 'S', '005930.KS': 'S',
    'CRWD': 'A', 'MSTR': 'A', 'COIN': 'A', 'DELL': 'A', 'AMAT': 'A', 'LRCX': 'A',
    'SNPS': 'A', 'CDNS': 'A', 'CSCO': 'A', 'MRVL': 'A', 'INTC': 'A', 'QCOM': 'A',
    'ARM': 'A', 'KLAC': 'A', 'TER': 'A', 'MU': 'A', 'ORCL': 'A', 'HPE': 'A',
    'NOW': 'A', 'WDAY': 'A', 'PANW': 'A', 'FTNT': 'A', 'NET': 'A', 'TXN': 'A', 'NXPI': 'A',
    'SMCI': 'B', 'SNOW': 'B', 'CEG': 'B', 'VST': 'B', 'TLN': 'B', 'NEE': 'A', 'SO': 'A',
    'EQIX': 'A', 'DLR': 'B', 'AMT': 'A', 'ANET': 'A', 'BIDU': 'B', 'MDB': 'A',
    'ESTC': 'B', 'DDOG': 'A', 'DT': 'B', 'GTLB': 'B', 'AI': 'C', 'SOUN': 'C', 'SERV': 'C',
    'CRWV': 'A', 'IBM': 'A', '1810.HK': 'A', '9880.HK': 'B', '9660.HK': 'B', '9888.HK': 'A', '9988.HK': 'A', '005380.KS': 'A', '688836.SS': 'B', 'CCXI': 'B',
    
    # === CRYPTO STOCKS ===
    'HOOD': 'B', 'MARA': 'B', 'RIOT': 'B', 'CLSK': 'B', 'HUT': 'B', 'HIVE': 'B',
    'CIFR': 'B', 'CORZ': 'B', 'IREN': 'B', 'WULF': 'B', 'BTBT': 'B', 'CAN': 'C',
    'BKKT': 'C', 'APLD': 'B', 'EBON': 'C', 'SOS': 'C', 'BTCS': 'C', 'ANY': 'C',
    'IBIT': 'B', 'FBTC': 'B', 'ARKB': 'B', 'BITB': 'B', 'GBTC': 'B', 'HODL': 'B',
    'BITX': 'B', 'BITO': 'B', 'ETHE': 'B', 'ETHA': 'B', 'CME': 'A', 'CBOE': 'A',
    'PYPL': 'A', 'SOFI': 'B',
    
    # === INTERNATIONAL ===
    'MC.PA': 'S',  # LVMH
    'RMS.PA': 'S',  # Hermes
    'NOVO-B.CO': 'S',  # Novo Nordisk
    'SAP': 'S',
    'SAP.DE': 'S',
    'ASML.AS': 'S',
    'AZN.L': 'A',  # AstraZeneca
    'SHEL.L': 'A',  # Shell
    '7203.T': 'A',  # Toyota
    '6758.T': 'A',  # Sony
    '0700.HK': 'A',  # Tencent
    'RACE.MI': 'A',  # Ferrari
    'OR.PA': 'A', 'ITX.MC': 'A', 'NESN.SW': 'A', 'HEIA.AS': 'A', 'ULVR.L': 'A',
    'DGE.L': 'A', 'SU.PA': 'A', 'SIE.DE': 'A', 'ABBN.SW': 'A', 'ADYEN.AS': 'A',
    'NOVN.SW': 'A', 'RO.SW': 'A', 'SAN.PA': 'A', 'GSK.L': 'A', 'AIR.PA': 'A',
    'TTE.PA': 'A', 'IBE.MC': 'A', 'ALV.DE': 'A', 'BNP.PA': 'A', 'ISP.MI': 'A',
    'HSBA.L': 'A', 'DTE.DE': 'A', 'MBG.DE': 'A', 'BABA': 'A', 'BHP.AX': 'A',
    'RIO.L': 'A', 'CBA.AX': 'A', 'CSL.AX': 'A',
    
    # === COMMODITIES ===
    'GC=F': 'S',  # Gold
    'SI=F': 'A',  # Silver
    'CL=F': 'A',  # Crude Oil
    'BZ=F': 'A',  # Brent
    'HG=F': 'B',  # Copper
    'NG=F': 'B',  # Natural Gas
    'PL=F': 'B',  # Platinum
    'URA': 'B',  # Uranium
    'URNM': 'B',
    'CCJ': 'B',
    
    # === INDICES ===
    '^GSPC': 'S',  # S&P 500
    '^IXIC': 'S',  # Nasdaq
    '^DJI': 'S',  # Dow Jones
    '^RUT': 'A',  # Russell 2000
    '^FTSE': 'A',  # FTSE 100
    '^GDAXI': 'A',  # DAX
    '^FCHI': 'A',
    '^N225': 'A',
    '^HSI': 'A',
    '^AXJO': 'A',
    '^VIX': 'B',
    'DX-Y.NYB': 'A',
}

# Canonical Registry mapping tickers to asset classes (keyed by institutional data source)
ASSET_CLASS_REGISTRY: Dict[str, str] = {
    # === CRYPTO ===
    'BTCUSDT': 'crypto', 'ETHUSDT': 'crypto', 'SOLUSDT': 'crypto', 'BNBUSDT': 'crypto',
    'XRPUSDT': 'crypto', 'LINKUSDT': 'crypto', 'AVAXUSDT': 'crypto', 'ADAUSDT': 'crypto',
    'SUIUSDT': 'crypto', 'DOGEUSDT': 'crypto', 'PAXGUSDT': 'crypto',
    
    # === US STOCKS ===
    'AAPL': 'us_stocks', 'MSFT': 'us_stocks', 'GOOGL': 'us_stocks', 'AMZN': 'us_stocks',
    'META': 'us_stocks', 'NVDA': 'us_stocks', 'JPM': 'us_stocks', 'V': 'us_stocks',
    'JNJ': 'us_stocks', 'WMT': 'us_stocks', 'PG': 'us_stocks', 'UNH': 'us_stocks',
    'HD': 'us_stocks', 'MA': 'us_stocks', 'LLY': 'us_stocks', 'AVGO': 'us_stocks',
    'COST': 'us_stocks', 'TSLA': 'us_stocks', 'NFLX': 'us_stocks', 'AMD': 'us_stocks',
    'CRM': 'us_stocks', 'PLTR': 'us_stocks', 'UBER': 'us_stocks', 'XOM': 'us_stocks',
    'CVX': 'us_stocks', 'ABBV': 'us_stocks', 'MRK': 'us_stocks', 'INTU': 'us_stocks',
    'ADBE': 'us_stocks', 'MELI': 'us_stocks', 'AXP': 'us_stocks', 'BAC': 'us_stocks',
    'KO': 'us_stocks', 'OXY': 'us_stocks', 'MCO': 'us_stocks', 'CB': 'us_stocks',
    'RKLB': 'us_stocks', 'ASTS': 'us_stocks', 'LUNR': 'us_stocks', 'RDW': 'us_stocks',
    'DECK': 'us_stocks', 'NU': 'us_stocks', 'NDAQ': 'us_stocks', 'EFX': 'us_stocks',
    'KHC': 'us_stocks', 'PSUS': 'us_stocks', 'PS': 'us_stocks', 'SIRI': 'us_stocks',
    
    # === AI STOCKS ===
    'ASML': 'ai_stocks', 'TSM': 'ai_stocks', '005930.KS': 'ai_stocks',
    'CRWD': 'ai_stocks', 'MSTR': 'ai_stocks', 'COIN': 'ai_stocks', 'DELL': 'ai_stocks',
    'AMAT': 'ai_stocks', 'LRCX': 'ai_stocks', 'SNPS': 'ai_stocks', 'CDNS': 'ai_stocks',
    'CSCO': 'ai_stocks', 'MRVL': 'ai_stocks', 'INTC': 'ai_stocks', 'QCOM': 'ai_stocks',
    'ARM': 'ai_stocks', 'KLAC': 'ai_stocks', 'TER': 'ai_stocks', 'MU': 'ai_stocks',
    'ORCL': 'ai_stocks', 'HPE': 'ai_stocks', 'NOW': 'ai_stocks', 'WDAY': 'ai_stocks',
    'PANW': 'ai_stocks', 'FTNT': 'ai_stocks', 'NET': 'ai_stocks', 'TXN': 'ai_stocks',
    'NXPI': 'ai_stocks', 'SMCI': 'ai_stocks', 'SNOW': 'ai_stocks', 'CEG': 'ai_stocks',
    'VST': 'ai_stocks', 'TLN': 'ai_stocks', 'NEE': 'ai_stocks', 'SO': 'ai_stocks',
    'EQIX': 'ai_stocks', 'DLR': 'ai_stocks', 'AMT': 'ai_stocks', 'ANET': 'ai_stocks',
    'BIDU': 'ai_stocks', 'MDB': 'ai_stocks', 'ESTC': 'ai_stocks', 'DDOG': 'ai_stocks',
    'DT': 'ai_stocks', 'GTLB': 'ai_stocks', 'AI': 'ai_stocks', 'SOUN': 'ai_stocks',
    'SERV': 'ai_stocks',
    'CRWV': 'ai_stocks', 'IBM': 'ai_stocks', '1810.HK': 'ai_stocks', '9880.HK': 'ai_stocks',
    '9660.HK': 'ai_stocks', '9888.HK': 'ai_stocks', '9988.HK': 'ai_stocks', '005380.KS': 'ai_stocks',
    '688836.SS': 'ai_stocks', 'CCXI': 'ai_stocks',
    
    # === CRYPTO STOCKS (Equities / ETFs, NOT Pure Crypto) ===
    'HOOD': 'crypto_stocks', 'MARA': 'crypto_stocks', 'RIOT': 'crypto_stocks',
    'CLSK': 'crypto_stocks', 'HUT': 'crypto_stocks', 'HIVE': 'crypto_stocks',
    'CIFR': 'crypto_stocks', 'CORZ': 'crypto_stocks', 'IREN': 'crypto_stocks',
    'WULF': 'crypto_stocks', 'BTBT': 'crypto_stocks', 'CAN': 'crypto_stocks',
    'BKKT': 'crypto_stocks', 'APLD': 'crypto_stocks', 'EBON': 'crypto_stocks',
    'SOS': 'crypto_stocks', 'BTCS': 'crypto_stocks', 'ANY': 'crypto_stocks',
    'IBIT': 'crypto_stocks', 'FBTC': 'crypto_stocks', 'ARKB': 'crypto_stocks',
    'BITB': 'crypto_stocks', 'GBTC': 'crypto_stocks', 'HODL': 'crypto_stocks',
    'BITX': 'crypto_stocks', 'BITO': 'crypto_stocks', 'ETHE': 'crypto_stocks',
    'ETHA': 'crypto_stocks', 'CME': 'crypto_stocks', 'CBOE': 'crypto_stocks',
    'PYPL': 'crypto_stocks', 'SOFI': 'crypto_stocks',
    
    # === INTERNATIONAL ===
    'MC.PA': 'intl_stocks', 'RMS.PA': 'intl_stocks', 'NOVO-B.CO': 'intl_stocks',
    'SAP': 'intl_stocks', 'SAP.DE': 'intl_stocks', 'ASML.AS': 'intl_stocks',
    'AZN.L': 'intl_stocks', 'SHEL.L': 'intl_stocks', '7203.T': 'intl_stocks',
    '6758.T': 'intl_stocks', '0700.HK': 'intl_stocks', 'RACE.MI': 'intl_stocks',
    'OR.PA': 'intl_stocks', 'ITX.MC': 'intl_stocks', 'NESN.SW': 'intl_stocks',
    'HEIA.AS': 'intl_stocks', 'ULVR.L': 'intl_stocks', 'DGE.L': 'intl_stocks',
    'SU.PA': 'intl_stocks', 'SIE.DE': 'intl_stocks', 'ABBN.SW': 'intl_stocks',
    'ADYEN.AS': 'intl_stocks', 'NOVN.SW': 'intl_stocks', 'RO.SW': 'intl_stocks',
    'SAN.PA': 'intl_stocks', 'GSK.L': 'intl_stocks', 'AIR.PA': 'intl_stocks',
    'TTE.PA': 'intl_stocks', 'IBE.MC': 'intl_stocks', 'ALV.DE': 'intl_stocks',
    'BNP.PA': 'intl_stocks', 'ISP.MI': 'intl_stocks', 'HSBA.L': 'intl_stocks',
    'DTE.DE': 'intl_stocks', 'MBG.DE': 'intl_stocks', 'BABA': 'intl_stocks',
    'BHP.AX': 'intl_stocks', 'RIO.L': 'intl_stocks', 'CBA.AX': 'intl_stocks',
    'CSL.AX': 'intl_stocks',
    
    # === COMMODITIES ===
    'GC=F': 'commodities', 'SI=F': 'commodities', 'CL=F': 'commodities',
    'BZ=F': 'commodities', 'HG=F': 'commodities', 'NG=F': 'commodities',
    'PL=F': 'commodities', 'URA': 'commodities', 'URNM': 'commodities',
    'CCJ': 'commodities',
    
    # === INDICES ===
    '^GSPC': 'indices', '^IXIC': 'indices', '^DJI': 'indices', '^RUT': 'indices',
    '^FTSE': 'indices', '^GDAXI': 'indices', '^FCHI': 'indices', '^N225': 'indices',
    '^HSI': 'indices', '^AXJO': 'indices', '^VIX': 'indices', 'DX-Y.NYB': 'indices',
}


def get_asset_class_for_ticker(ticker: Optional[str]) -> Optional[str]:
    """Resolves asset class from registry lookup table rather than string guessing (Opus Patch 2)."""
    if not ticker:
        return None
    clean = ticker.split(":")[-1].strip().upper()
    return ASSET_CLASS_REGISTRY.get(clean)


def get_asset_profile(asset_class: str) -> AssetClassProfile:
    """Returns the trading profile for an asset class. Falls back to us_stocks if unknown."""
    return ASSET_CLASS_PROFILES.get(asset_class, ASSET_CLASS_PROFILES['us_stocks'])

def get_quality_tier(ticker: str) -> str:
    """Returns the quality tier (S/A/B/C) for a ticker. Fallback to empirical backtest tier, then B."""
    if not ticker:
        return 'B'
    clean = ticker.split(":")[-1].strip().upper()
    if clean in QUALITY_TIERS:
        return QUALITY_TIERS[clean]
    emp = get_empirical_asset_profile(clean)
    if emp and "empirical_tier" in emp:
        return emp["empirical_tier"]
    return 'B'


GOLD_VOL_EXEMPT = {"GC=F", "PAXGUSDT"}
DEFAULT_EXCLUDED_ASSET_CLASSES = {"indices"}
DEFAULT_EXCLUDED_SECTORS = {
    "Utilities",
    "Real Estate",
    "Consumer Defensive",
    "Consumer Staples",
    "Basic Materials",
    "Materials",
    "Базови материали",
}


def get_larsson_trend_tier(ticker: str) -> str:
    """
    Returns empirical Larsson trend tier (S/A/B/C) strictly from backtest profiles.
    Unlike `get_quality_tier` (fundamental brand stature), this measures historical
    trend-following suitability and falls back conservatively to 'B'.
    """
    if not ticker:
        return "B"
    clean = ticker.split(":")[-1].strip().upper()
    emp = get_empirical_asset_profile(clean)
    if emp and emp.get("empirical_tier") in ("S", "A", "B", "C"):
        return str(emp["empirical_tier"])
    return "B"


def get_effective_exit_on_neutral(
    ticker: str,
    asset_class: Optional[str] = None,
    default_crypto_fast_exit: bool = True,
) -> bool:
    """
    Returns True if an asset should exit to Cash on NEUTRAL rather than holding to BLUE.
    Gold proxies stay on Classic Blue Exit; non-gold crypto uses Fast Exit when
    `default_crypto_fast_exit` is enabled; equities honor their empirical profile flag.
    """
    clean = (ticker or "").split(":")[-1].strip().upper()
    emp = get_empirical_asset_profile(clean)
    if clean in GOLD_VOL_EXEMPT:
        return bool(emp.get("exit_on_neutral", False)) if emp else False
    resolved_cls = (asset_class or get_asset_class_for_ticker(clean) or "").lower()
    if resolved_cls == "crypto" and default_crypto_fast_exit:
        return True
    if emp and "exit_on_neutral" in emp:
        return bool(emp["exit_on_neutral"])
    return False


def check_larsson_eligibility(
    ticker: str,
    asset_class: str = "",
    sector: str = "",
    annualized_vol_pct: Optional[float] = None,
    min_vol_pct: float = 25.0,
    gold_vol_exempt: Optional[set] = None,
    excluded_asset_classes: Optional[set] = None,
    excluded_sectors: Optional[set] = None,
) -> Tuple[bool, str]:
    """Evaluates empirical trend, walk-forward, sector, asset-class, and volatility gates."""
    clean = (ticker or "").split(":")[-1].strip().upper()
    exempt = GOLD_VOL_EXEMPT if gold_vol_exempt is None else {str(x).upper() for x in gold_vol_exempt}
    excl_cls = DEFAULT_EXCLUDED_ASSET_CLASSES if excluded_asset_classes is None else {str(x).lower() for x in excluded_asset_classes}
    excl_sec = DEFAULT_EXCLUDED_SECTORS if excluded_sectors is None else set(excluded_sectors)
    excl_sec_norm = {str(s).strip().casefold() for s in excl_sec if s}

    resolved_cls = (asset_class or get_asset_class_for_ticker(clean) or "").lower()
    if resolved_cls in excl_cls:
        return False, "excluded_asset_class"

    emp = get_empirical_asset_profile(clean)
    resolved_sector = sector or (emp.get("sector", "") if emp else "")
    if clean not in exempt and str(resolved_sector).strip().casefold() in excl_sec_norm:
        return False, "excluded_sector"

    trend_tier = get_larsson_trend_tier(clean)
    if trend_tier not in ("S", "A"):
        return False, "tier_below_a"

    if emp and not emp.get("walk_forward_stable", True):
        return False, "walk_forward_unstable"

    if annualized_vol_pct is not None and clean not in exempt and float(annualized_vol_pct) < float(min_vol_pct):
        return False, "low_volatility"

    return True, "eligible"


def is_larsson_eligible(
    ticker: str,
    asset_class: str = "",
    sector: str = "",
    annualized_vol_pct: Optional[float] = None,
    min_vol_pct: float = 25.0,
    gold_vol_exempt: Optional[set] = None,
    excluded_asset_classes: Optional[set] = None,
    excluded_sectors: Optional[set] = None,
) -> bool:
    """Boolean wrapper for `check_larsson_eligibility`."""
    ok, _ = check_larsson_eligibility(
        ticker=ticker,
        asset_class=asset_class,
        sector=sector,
        annualized_vol_pct=annualized_vol_pct,
        min_vol_pct=min_vol_pct,
        gold_vol_exempt=gold_vol_exempt,
        excluded_asset_classes=excluded_asset_classes,
        excluded_sectors=excluded_sectors,
    )
    return ok

def get_tier_emoji(tier: str) -> str:
    """Returns emoji for quality tier."""
    return {'S': '💎', 'A': '⭐', 'B': '🔵', 'C': '⚪'}.get(tier, '⚪')

def get_tier_position_multiplier(tier: str) -> float:
    """Position size multiplier based on tier. S gets full, C gets minimal."""
    return {'S': 1.0, 'A': 0.85, 'B': 0.6, 'C': 0.3}.get(tier, 0.5)

def get_tier_description_bg(tier: str) -> str:
    """Bulgarian description of what each tier means."""
    descs = {
        'S': 'Blue chip — винаги следи, pullback = prime opportunity',
        'A': 'Качествен актив — доказан растеж, достоен за пълен sizing',
        'B': 'Перспективен — по-рисков, намален position size',
        'C': 'Спекулативен — минимален размер, строг SL',
    }
    return descs.get(tier, 'Неизвестен tier')


def get_max_allowed_leverage(
    ticker: str,
    asset_class: str = "crypto",
    score: int = 50,
    tier: str = "B",
    atr_pct: float = 3.0,
    direction: str = "LONG",
) -> int:
    """
    Returns the maximum allowable leverage (1, 2, or 3) for an asset given market context.
    - Tier C or extreme volatility (ATR% >= 6.5%) -> 1 (Spot only)
    - If direction == 'SHORT' and asset profile does not allow short -> 1
    - Tier S with high conviction (score >= 70, tier in ['A+', 'A'], ATR% < 6.0%) -> 3
    - Tier A with high conviction (score >= 75, tier in ['A+', 'A'], ATR% < 5.0%) -> 3
    - Tier S / A with moderate conviction (score >= 50) -> 2
    - Tier B with good conviction (score >= 65, ATR% < 5.0%) -> 2
    - All others -> 1
    """
    profile = get_asset_profile(asset_class)
    if direction.upper() == "SHORT" and not profile.allows_short:
        return 1

    quality_tier = get_quality_tier(ticker)
    if quality_tier == "C" or atr_pct >= 6.5:
        return 1
    emp = get_empirical_asset_profile(ticker)
    if emp and emp.get("empirical_tier") == "C":
        return 1

    if quality_tier == "S":
        if score >= 70 and tier in ["A+", "A"] and atr_pct < 6.0:
            return 3
        if score >= 50:
            return 2
        return 1

    if quality_tier == "A":
        if score >= 75 and tier in ["A+", "A"] and atr_pct < 5.0:
            return 3
        if score >= 50:
            return 2
        return 1

    if quality_tier == "B":
        if score >= 65 and atr_pct < 5.0:
            return 2
        return 1

    return 1


_DEFAULT_ROTATION_SETTINGS: Dict[str, object] = {
    "target_positions_count": 8,
    "base_capital_eur": 10000.0,
    "min_annualized_vol_pct": 25.0,
    "gold_vol_exempt": ["GC=F", "PAXGUSDT"],
    "excluded_asset_classes": ["indices"],
    "excluded_sectors": [
        "Utilities",
        "Real Estate",
        "Consumer Defensive",
        "Consumer Staples",
        "Basic Materials",
        "Materials",
        "Базови материали",
    ],
    "crypto_fast_exit_default": True,
    "inverse_vol_sizing": True,
    "min_slot_weight_pct": 7.0,
    "max_slot_weight_pct": 20.0,
    "cluster_caps": {
        "semi_ai_hardware": 2,
        "mega_software_cloud": 2,
        "crypto_risk": 2,
        "gold_commodities": 2,
        "industrial_defense": 2,
        "finance_fintech": 2,
        "consumer_media": 2,
        "healthcare_biotech": 1,
        "energy_resources": 2,
        "other_equity": 2,
    },
    "core_focus_bonus": 15.0,
    "core_focus_tickers": [
        "NVDA", "AVGO", "TSM", "MU", "ASML", "PLTR", "META", "GOOGL", "NFLX", "APP",
        "GEV", "RYCEY", "SAP.DE", "ABBN.SW", "CCJ", "HOOD",
        "BTCUSDT", "SOLUSDT", "BNBUSDT", "PAXGUSDT",
    ],
}


def load_rotation_settings(settings_path: str = SETTINGS_FILE) -> Dict[str, object]:
    """Loads rotation portfolio settings from YAML with validated fallbacks."""
    cfg = {
        k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
        for k, v in _DEFAULT_ROTATION_SETTINGS.items()
    }
    if settings_path and os.path.exists(settings_path):
        try:
            import yaml
            with open(settings_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            rot = raw.get("rotation") or {}
            if isinstance(rot, dict):
                for k, v in rot.items():
                    if k == "cluster_caps" and isinstance(v, dict):
                        merged_caps = dict(cfg["cluster_caps"])
                        merged_caps.update(v)
                        cfg["cluster_caps"] = merged_caps
                    elif v is not None:
                        cfg[k] = v
        except Exception as e:
            logger.warning(f"Could not load rotation settings from {settings_path}: {e}")
    return cfg


_GOLD_CLUSTER_TICKERS = {
    "GC=F", "PAXGUSDT", "XAUTUSDT", "GLD", "IAU", "SLV", "SI=F",
    "GDX", "NEM", "AEM", "GOLD", "WPM", "FNV", "KGC",
}
_ENERGY_CLUSTER_TICKERS = {
    "CCJ", "UEC", "NXE", "URA", "URNM", "XOM", "CVX", "COP", "SLB",
    "EOG", "OXY", "MPC", "VLO", "PSX", "HAL", "BKR", "CL=F", "BZ=F", "NG=F",
}
_CRYPTO_RISK_TICKERS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "AVAXUSDT", "SUIUSDT", "LINKUSDT", "DOTUSDT", "TONUSDT", "TRXUSDT", "MATICUSDT",
    "NEARUSDT", "APTUSDT", "INJUSDT", "COIN", "MSTR", "MARA", "RIOT", "CLSK",
    "HOOD", "GBTC", "IBIT", "FBTC", "BITO", "HUT", "CIFR", "IREN", "CORZ", "WULF",
}
_SEMI_AI_HW_TICKERS = {
    "NVDA", "AVGO", "TSM", "MU", "ASML", "AMD", "SMCI", "ARM", "INTC", "QCOM",
    "MRVL", "KLAC", "LRCX", "AMAT", "TXN", "ON", "NXPI", "ADI", "MCHP", "MPWR",
    "TER", "ENTG", "SWKS", "QRVO", "STM", "SNPS", "CDNS", "ANET", "VRT", "CRDO",
    "ALAB", "CLS", "FN", "COHR", "LITE", "CIEN", "HPE", "DELL", "PSTG", "WDC",
    "STX", "NTAP", "INFY", "005930.KS", "000660.KS", "2330.TW", "2454.TW",
    "6857.T", "8035.T", "ASX", "UMC",
}
_MEGA_SW_CLOUD_TICKERS = {
    "MSFT", "AAPL", "GOOGL", "GOOG", "META", "AMZN", "ORCL", "CRM", "ADBE",
    "NOW", "INTU", "PANW", "CRWD", "SNOW", "DDOG", "ZS", "NET", "FTNT",
    "PLTR", "APP", "SAP.DE", "TEAM", "WDAY", "HUBS", "MDB", "OKTA", "DT",
    "TTD", "IBM", "ACN", "Shop".upper(), "DUOL", "SOUN", "BBAI",
}
_INDUSTRIAL_DEF_TICKERS = {
    "GE", "GEV", "RYCEY", "RR.L", "ABBN.SW", "RHM.DE", "BAESY", "LMT", "RTX", "NOC",
    "GD", "HWM", "TDG", "HEI", "AXON", "CAT", "DE", "HON", "ETN", "PH",
    "EMR", "ROK", "URI", "PWR", "ITT", "SIE.DE", "SAF.PA", "AIR.PA", "SU.PA",
    "SAAB-B.ST", "LDO.MI", "PL", "RKLB", "ASTS", "JOBY", "ACHR", "BA",
}
_FINANCE_FINTECH_TICKERS = {
    "V", "MA", "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP",
    "PYPL", "XYZ", "SQ", "SOFI", "NU", "AFRM", "BRK-B", "SPGI", "MCO", "ICE",
    "CME", "CB", "PGR", "TRV", "ALL", "KKR", "APO", "BX", "ARES",
}
_CONSUMER_MEDIA_TICKERS = {
    "NFLX", "DIS", "SPOT", "RBLX", "UBER", "DASH", "ABNB", "BKNG", "TSLA",
    "HD", "LOW", "COST", "WMT", "NKE", "SBUX", "MCD", "CMG", "TJX", "LULU",
    "MELI", "SE", "CELH", "ONON",
}
_HEALTHCARE_TICKERS = {
    "LLY", "NVO", "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR",
    "ISRG", "SYK", "BSX", "VRTX", "REGN", "AMGN", "GILD", "MRNA", "BNTX", "HIMS",
}


def classify_risk_cluster(
    ticker: str,
    asset_class: str = "",
    sector: str = "",
    name: str = "",
) -> str:
    """Assigns a correlation-aware risk cluster for Top-N concentration caps."""
    clean = (ticker or "").split(":")[-1].strip().upper()
    cls_l = (asset_class or get_asset_class_for_ticker(clean) or "").lower()
    sec_l = (sector or "").strip().lower()
    name_l = (name or "").strip().lower()

    # Explicit curated cluster ticker mappings take precedence over generic asset_class
    if clean in _GOLD_CLUSTER_TICKERS:
        return "gold_commodities"
    if clean in _ENERGY_CLUSTER_TICKERS:
        return "energy_resources"
    if clean in _CRYPTO_RISK_TICKERS:
        return "crypto_risk"
    if clean in _FINANCE_FINTECH_TICKERS:
        return "finance_fintech"
    if clean in _SEMI_AI_HW_TICKERS or any(k in name_l for k in ("semiconductor", "microchip", "hynix", "tsmc")):
        return "semi_ai_hardware"
    if clean in _MEGA_SW_CLOUD_TICKERS:
        return "mega_software_cloud"
    if clean in _INDUSTRIAL_DEF_TICKERS:
        return "industrial_defense"
    if clean in _HEALTHCARE_TICKERS:
        return "healthcare_biotech"
    if clean in _CONSUMER_MEDIA_TICKERS:
        return "consumer_media"

    # Generic fallback by asset class and fundamental sector
    if sec_l == "energy":
        return "energy_resources"
    if cls_l == "commodities":
        return "gold_commodities"
    if cls_l in ("crypto", "crypto_stocks"):
        return "crypto_risk"
    if sec_l == "industrials":
        return "industrial_defense"
    if sec_l == "healthcare":
        return "healthcare_biotech"
    if sec_l == "financial services":
        return "finance_fintech"
    if sec_l in ("communication services", "consumer cyclical"):
        return "consumer_media"
    if sec_l == "technology":
        return "mega_software_cloud"
    return "other_equity"


def compute_normalized_invvol_weights(
    vols_by_ticker: Dict[str, Optional[float]],
    target_slots: int = 8,
    min_weight_pct: float = 7.0,
    max_weight_pct: float = 20.0,
    default_vol_pct: float = 40.0,
) -> Dict[str, float]:
    """
    Computes inverse-volatility weights normalized to deploy `100 * min(1, n / target_slots)`%
    so cash buffers scale down linearly when few candidates are active while a full book reaches 100%,
    bounded within `[min_weight_pct, max_weight_pct]` via capped-simplex projection.
    """
    if not vols_by_ticker or target_slots <= 0:
        return {}

    tickers = list(vols_by_ticker.keys())
    n = len(tickers)
    deployed_pct = 100.0 * min(1.0, float(n) / float(target_slots))
    avg_w = deployed_pct / n
    eff_min = min(float(min_weight_pct), avg_w)
    eff_max = max(float(max_weight_pct), avg_w)

    raw = {}
    for tk in tickers:
        v = vols_by_ticker.get(tk)
        try:
            v_num = float(v) if v is not None else float(default_vol_pct)
        except (TypeError, ValueError):
            v_num = float(default_vol_pct)
        if v_num != v_num or v_num <= 0:
            v_num = float(default_vol_pct)
        raw[tk] = 1.0 / max(10.0, v_num)

    fixed: Dict[str, float] = {}
    free = list(tickers)
    while free:
        rem = deployed_pct - sum(fixed.values())
        free_raw_sum = sum(raw[t] for t in free)
        cand = {
            t: (rem * (raw[t] / free_raw_sum) if free_raw_sum > 0 else rem / len(free))
            for t in free
        }
        over = [t for t in free if cand[t] > eff_max + 1e-9]
        under = [t for t in free if cand[t] < eff_min - 1e-9]
        if not over and not under:
            fixed.update(cand)
            free = []
            break
        over_excess = sum(cand[t] - eff_max for t in over)
        under_deficit = sum(eff_min - cand[t] for t in under)
        if over_excess >= under_deficit and over:
            for t in over:
                fixed[t] = eff_max
            free = [t for t in free if t not in over]
        elif under:
            for t in under:
                fixed[t] = eff_min
            free = [t for t in free if t not in under]
        else:
            fixed.update(cand)
            free = []

    rounded = {t: round(fixed[t], 2) for t in tickers}
    diff = round(deployed_pct - sum(rounded.values()), 2)
    if abs(diff) >= 0.01:
        for t in sorted(tickers, key=lambda k: rounded[k], reverse=(diff < 0)):
            adj = round(rounded[t] + diff, 2)
            if eff_min - 1e-6 <= adj <= eff_max + 1e-6:
                rounded[t] = adj
                break
    return rounded

