"""
Asset-Class Specific Trading Profiles & Quality Tier System.
Provides per-class risk parameters and assigns quality tiers to all monitored assets.
"""

from dataclasses import dataclass
from typing import Dict, Optional

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
        allows_short=True,
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
    """Returns the quality tier (S/A/B/C) for a ticker. Default is B."""
    return QUALITY_TIERS.get(ticker, 'B')

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

