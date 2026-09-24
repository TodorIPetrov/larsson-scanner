import logging
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class PendingSetup:
    symbol: str
    asset_class: str
    setup_type: str  # 'IMMINENT_GOLD', 'QUALITY_DIP_BUY', 'SR_APPROACH', 'ACCUMULATION_PATTERN', 'DIVERGENCE_FORMING'
    direction: str  # 'LONG', 'SHORT'
    priority: str  # 'HIGH', 'MEDIUM', 'LOW'
    quality_score: float  # 0.0 - 1.0
    description_bg: str
    description_en: str
    conditions_met: List[str]  # conditions already satisfied
    conditions_pending: List[str]  # conditions we're waiting for
    estimated_trigger: str  # '1-2 бара', 'при достигане на $X', etc.
    current_price: float
    target_entry: Optional[float] = None
    target_sl: Optional[float] = None
    target_tp1: Optional[float] = None
    key_level: Optional[float] = None  # the S/R level or ribbon value to watch
    timeframe: str = '1D'
    tier: str = 'B'  # S/A/B/C quality tier of the asset
    first_detected: str = ''
    last_updated: str = ''
    
    def to_dict(self) -> dict:
        return asdict(self)

def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    if len(prices) < period + 1:
        return np.full_like(prices, 50.0)
    
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
            
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        
        if down == 0:
            rsi[i] = 100.
        else:
            rs = up / down
            rsi[i] = 100. - 100. / (1. + rs)
            
    return rsi

class SetupMonitor:
    """
    Setup Monitor Engine.
    Proactively identifies assets approaching potential trade setups 1-3 bars away.
    """
    def __init__(self):
        self.now_str = datetime.now(timezone.utc).isoformat()

    def detect_imminent_gold(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            state = asset.get('state', 'NEUTRAL')
            if state == 'GOLD':
                return None
                
            v1, m1, m2, v2 = asset.get('v1'), asset.get('m1'), asset.get('m2'), asset.get('v2')
            atr = asset.get('atr', 0)
            if None in (v1, m1, m2, v2) or not atr:
                return None
                
            prev_m2 = asset.get('prev_m2', m2)
            prev_v2 = asset.get('prev_v2', v2)
            
            # Ribbon is NEUTRAL but v1 is crossing above m1 AND the gap between m2 and v2 is shrinking
            # Check: (v1 - m1) > 0 AND (v1 - m1) < 0.3 * atr (just crossed) AND (m2 - v2) is narrowing
            v1_m1_diff = v1 - m1
            current_gap = abs(m2 - v2)
            prev_gap = abs(prev_m2 - prev_v2)
            
            # Using a simplified narrowing check if history is missing
            is_narrowing = current_gap < prev_gap if current_gap != prev_gap else current_gap < (0.5 * atr)
            
            if 0 < v1_m1_diff < 0.3 * atr and is_narrowing and state == 'NEUTRAL':
                weekly_state = asset.get('weekly_state', '')
                priority = 'HIGH' if weekly_state == 'GOLD' else 'MEDIUM'
                
                return PendingSetup(
                    symbol=asset['symbol'],
                    asset_class=asset['asset_class'],
                    setup_type='IMMINENT_GOLD',
                    direction='LONG',
                    priority=priority,
                    quality_score=0.85 if priority == 'HIGH' else 0.70,
                    description_bg=f"{asset['symbol']} е на 1-2 бара от Gold transition — v1 пресича m1, ribbon се подрежда",
                    description_en=f"{asset['symbol']} is 1-2 bars from Gold transition — v1 crossing m1, ribbon aligning",
                    conditions_met=["v1 > m1", "m2-v2 gap narrowing"],
                    conditions_pending=["v1 > v2", "m2 < v2"],
                    estimated_trigger="1-2 бара",
                    current_price=asset['price'],
                    tier=asset.get('tier', 'B'),
                    first_detected=self.now_str,
                    last_updated=self.now_str
                )
        except Exception as e:
            logger.error(f"Error in detect_imminent_gold for {asset.get('symbol')}: {e}")
        return None

    def detect_quality_dip_buy(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            tier = asset.get('tier', 'NONE')
            if tier not in ['S', 'A', 'A+']:
                return None
                
            weekly_state = asset.get('weekly_state', '')
            if weekly_state != 'GOLD':
                return None
                
            state = asset.get('state', '')
            if state not in ['NEUTRAL', 'BLUE']:
                return None
                
            fund_profile = asset.get('fund_profile')
            is_bullish = getattr(fund_profile, "is_bullish", False) if fund_profile else False
            
            if not is_bullish:
                # We can also check a dict if it's passed as dict
                if isinstance(fund_profile, dict) and fund_profile.get('is_bullish'):
                    is_bullish = True
                    
            if is_bullish:
                return PendingSetup(
                    symbol=asset['symbol'],
                    asset_class=asset['asset_class'],
                    setup_type='QUALITY_DIP_BUY',
                    direction='LONG',
                    priority='HIGH',
                    quality_score=0.90,
                    description_bg=f"{asset['symbol']} е в pullback при Weekly Gold — чакайте Daily Gold re-entry за вход",
                    description_en=f"{asset['symbol']} is in pullback on Weekly Gold — await Daily Gold re-entry",
                    conditions_met=["Weekly GOLD", "Fundamental Bullish", "Quality S/A"],
                    conditions_pending=["Daily transition to GOLD"],
                    estimated_trigger="При обръщане на 1D тренд",
                    current_price=asset['price'],
                    tier=tier,
                    first_detected=self.now_str,
                    last_updated=self.now_str
                )
        except Exception as e:
            logger.error(f"Error in detect_quality_dip_buy for {asset.get('symbol')}: {e}")
        return None

    def detect_sr_approach(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            sr = asset.get('sr_analysis')
            if not sr:
                return None
            
            if isinstance(sr, dict):
                s1 = sr.get('s1')
                r1 = sr.get('r1')
                atr = sr.get('atr', asset.get('atr', 0))
            else:
                s1 = getattr(sr, 's1', None)
                r1 = getattr(sr, 'r1', None)
                atr = getattr(sr, 'atr', asset.get('atr', 0))
                
            if not atr:
                return None
                
            price = asset['price']
            state = asset.get('state', 'NEUTRAL')
            
            setup = None
            if s1 and price > s1 and (price - s1) <= 3 * atr and (price - s1) > 0.5 * atr:
                if state == 'GOLD':
                    setup = PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='SR_APPROACH',
                        direction='LONG',
                        priority='MEDIUM',
                        quality_score=0.75,
                        description_bg=f"{asset['symbol']} приближава support ${s1:,.2f} — следете за bounce setup",
                        description_en=f"{asset['symbol']} approaching support ${s1:,.2f} — watch for bounce setup",
                        conditions_met=["Uptrend (GOLD)", "Approaching S1"],
                        conditions_pending=["Price reaches S1", "Bullish reaction/bounce"],
                        estimated_trigger=f"при достигане на ${s1:,.2f}",
                        current_price=price,
                        key_level=s1,
                        tier=asset.get('tier', 'B'),
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
            elif r1 and price < r1 and (r1 - price) <= 3 * atr and (r1 - price) > 0.5 * atr:
                if state == 'GOLD':
                    setup = PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='SR_APPROACH',
                        direction='SHORT',
                        priority='MEDIUM',
                        quality_score=0.70,
                        description_bg=f"{asset['symbol']} приближава resistance ${r1:,.2f} — следете за take profit или reversal",
                        description_en=f"{asset['symbol']} approaching resistance ${r1:,.2f} — watch for take profit or reversal",
                        conditions_met=["Uptrend (GOLD)", "Approaching R1"],
                        conditions_pending=["Price reaches R1", "Bearish rejection"],
                        estimated_trigger=f"при достигане на ${r1:,.2f}",
                        current_price=price,
                        key_level=r1,
                        tier=asset.get('tier', 'B'),
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
            return setup
        except Exception as e:
            logger.error(f"Error in detect_sr_approach for {asset.get('symbol')}: {e}")
        return None

    def detect_accumulation_pattern(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            state = asset.get('state')
            if state != 'NEUTRAL':
                return None
                
            # If we don't have enough history, we can't reliably detect >10 bars neutral
            # We'll use a heuristic if recent_states is not provided
            recent_states = asset.get('recent_states', [])
            if len(recent_states) >= 10:
                if not all(s == 'NEUTRAL' for s in recent_states[-10:]):
                    return None
            else:
                # Can't confirm long accumulation
                return None
                
            fund_profile = asset.get('fund_profile')
            is_bullish = getattr(fund_profile, "is_bullish", False) if fund_profile else False
            if isinstance(fund_profile, dict) and fund_profile.get('is_bullish'):
                is_bullish = True
                
            priority = 'HIGH' if is_bullish else 'MEDIUM'
            score = 0.85 if is_bullish else 0.65
            
            return PendingSetup(
                symbol=asset['symbol'],
                asset_class=asset['asset_class'],
                setup_type='ACCUMULATION_PATTERN',
                direction='LONG',
                priority=priority,
                quality_score=score,
                description_bg=f"{asset['symbol']} е в тиха акумулация — breakout е вероятен скоро",
                description_en=f"{asset['symbol']} is in quiet accumulation — breakout likely soon",
                conditions_met=["Neutral for > 10 bars", "Spread contracting"],
                conditions_pending=["Volume spike", "Price breakout above resistance"],
                estimated_trigger="при пробив",
                current_price=asset['price'],
                tier=asset.get('tier', 'B'),
                first_detected=self.now_str,
                last_updated=self.now_str
            )
        except Exception as e:
            logger.error(f"Error in detect_accumulation_pattern for {asset.get('symbol')}: {e}")
        return None

    def detect_divergence_forming(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            prices = asset.get('recent_prices', [])
            if not prices or len(prices) < 20:
                return None
                
            prices_arr = np.array(prices, dtype=np.float64)
            rsi = calculate_rsi(prices_arr)
            
            # Very basic divergence check (last 2 swing lows)
            # Find swing lows in price
            lows = []
            for i in range(2, len(prices)-2):
                if prices[i] < prices[i-1] and prices[i] < prices[i-2] and prices[i] < prices[i+1] and prices[i] < prices[i+2]:
                    lows.append(i)
            
            if len(lows) >= 2:
                idx1, idx2 = lows[-2], lows[-1]
                p1, p2 = prices[idx1], prices[idx2]
                r1, r2 = rsi[idx1], rsi[idx2]
                
                # Bullish Divergence: Lower low in price, Higher low in RSI
                if p2 < p1 and r2 > r1 and asset.get('state') != 'GOLD':
                    return PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='DIVERGENCE_FORMING',
                        direction='LONG',
                        priority='HIGH',
                        quality_score=0.80,
                        description_bg=f"{asset['symbol']} показва bullish divergence на 1D — потенциален обрат",
                        description_en=f"{asset['symbol']} shows bullish divergence on 1D — potential reversal",
                        conditions_met=["Lower Low in Price", "Higher Low in RSI"],
                        conditions_pending=["Bullish structure breakout", "Gold transition"],
                        estimated_trigger="1-3 бара",
                        current_price=asset['price'],
                        tier=asset.get('tier', 'B'),
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
                    
            # Check for bearish divergence
            highs = []
            for i in range(2, len(prices)-2):
                if prices[i] > prices[i-1] and prices[i] > prices[i-2] and prices[i] > prices[i+1] and prices[i] > prices[i+2]:
                    highs.append(i)
                    
            if len(highs) >= 2:
                idx1, idx2 = highs[-2], highs[-1]
                p1, p2 = prices[idx1], prices[idx2]
                r1, r2 = rsi[idx1], rsi[idx2]
                
                # Bearish Divergence: Higher high in price, Lower high in RSI
                if p2 > p1 and r2 < r1 and asset.get('state') == 'GOLD':
                    return PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='DIVERGENCE_FORMING',
                        direction='SHORT',
                        priority='MEDIUM',
                        quality_score=0.75,
                        description_bg=f"{asset['symbol']} показва bearish divergence на 1D — потенциален обрат надолу",
                        description_en=f"{asset['symbol']} shows bearish divergence on 1D — potential reversal down",
                        conditions_met=["Higher High in Price", "Lower High in RSI"],
                        conditions_pending=["Bearish structure breakdown", "Blue transition"],
                        estimated_trigger="1-3 бара",
                        current_price=asset['price'],
                        tier=asset.get('tier', 'B'),
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
        except Exception as e:
            logger.error(f"Error in detect_divergence_forming for {asset.get('symbol')}: {e}")
        return None

    def scan_for_pending_setups(self, assets: List[Dict[str, Any]]) -> List[PendingSetup]:
        """
        Runs all detection methods on each asset.
        Returns List[PendingSetup] sorted by quality_score descending.
        Filters out duplicates (same symbol + same setup_type).
        """
        setups = []
        seen = set()
        
        for asset in assets:
            results = [
                self.detect_imminent_gold(asset),
                self.detect_quality_dip_buy(asset),
                self.detect_sr_approach(asset),
                self.detect_accumulation_pattern(asset),
                self.detect_divergence_forming(asset),
            ]
            
            for res in results:
                if res:
                    key = f"{res.symbol}_{res.setup_type}"
                    if key not in seen:
                        seen.add(key)
                        setups.append(res)
                        
        setups.sort(key=lambda s: s.quality_score, reverse=True)
        return setups

def format_queue_telegram(setups: List[PendingSetup], top_n: int = 5) -> str:
    """
    Formats the top N pending setups into a Telegram HTML message.
    """
    if not setups:
        return "Няма чакащи сетъпи в момента."
        
    prio_emoji = {
        'HIGH': '🔴',
        'MEDIUM': '🟡',
        'LOW': '🟢'
    }
    
    type_emoji = {
        'IMMINENT_GOLD': '🔥',
        'QUALITY_DIP_BUY': '💎',
        'SR_APPROACH': '🎯',
        'ACCUMULATION_PATTERN': '📦',
        'DIVERGENCE_FORMING': '📉'
    }
    
    top_setups = setups[:top_n]
    msg = "<b>⏳ Pending Setups Monitor (1-3 Bars)</b>\n\n"
    
    for s in top_setups:
        p_emo = prio_emoji.get(s.priority, '⚪')
        t_emo = type_emoji.get(s.setup_type, '⚡')
        
        msg += f"{p_emo} <b>{s.symbol}</b> ({s.tier} Tier) - {t_emo} <i>{s.setup_type.replace('_', ' ')}</i>\n"
        msg += f"💡 {s.description_bg}\n"
        
        msg += "<b>Условия:</b>\n"
        for cond in s.conditions_met:
            msg += f"✅ {cond}\n"
        for cond in s.conditions_pending:
            msg += f"⬜ {cond}\n"
            
        msg += f"⏱ <i>Тригър: {s.estimated_trigger}</i>\n"
        
        tv_link = f"https://www.tradingview.com/chart/?symbol={s.symbol}"
        msg += f"<a href='{tv_link}'>📈 TradingView</a>\n\n"
        
    return msg.strip()
