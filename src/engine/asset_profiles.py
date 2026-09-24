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

