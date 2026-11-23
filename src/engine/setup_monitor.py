import logging
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import numpy as np

logger = logging.getLogger(__name__)

STABLECOIN_TICKERS = {
    "USDCUSDT", "FDUSDUSDT", "USDEUSDT", "XUSDUSDT", "USD1USDT",
    "RWUSDUSDT", "RLUSDUSDT", "TUSDUSDT", "DAIUSDT", "BUSDUSDT", "USDPUSDT",
    "EURUSDT", "AEURUSDT", "PAXGUSDT",
}


def _smma_req_price(lf: float, nf: int, ls: float, ns: int, bars: int) -> Optional[float]:
    """Closed-form constant hl2 price required over k bars for SMMA(nf) >= SMMA(ns)."""
    af = ((nf - 1.0) / nf) ** bars
    as_ = ((ns - 1.0) / ns) ** bars
    denom = as_ - af
    if abs(denom) < 1e-12:
        return None
    return (as_ * ls - af * lf) / denom


def compute_smma_forward_projection(
    v1: float,
    m1: float,
    m2: float,
    v2: float,
    price: float,
    max_bars: int = 10,
) -> Dict[str, Any]:
    """
    Deterministic Wilder SMMA (15/19/25/29) forward projection.
    Computes exact trigger prices for flipping to GOLD in 1, 2, 3, and 5 bars,
    plus the exact number of bars needed at current price or +2% momentum.
    """
    if None in (v1, m1, m2, v2, price) or price <= 0 or v2 <= 0:
        return {
            "p_gold_1bar": None,
            "p_gold_2bar": None,
            "p_gold_3bar": None,
            "p_gold_5bar": None,
            "bars_at_current_price": None,
            "bars_at_plus_2pct": None,
            "bars_at_plus_4pct": None,
            "dist_1bar_pct": 999.0,
            "dist_3bar_pct": 999.0,
        }

    def _p_gold(k: int) -> Optional[float]:
        reqs = [
            _smma_req_price(v1, 15, m1, 19, k),
            _smma_req_price(v1, 15, v2, 29, k),
            _smma_req_price(m2, 25, v2, 29, k),
        ]
        valid = [r for r in reqs if r is not None]
        return max(valid) if valid else None

    def _bars_at_level(level: float) -> Optional[int]:
        tv1, tm1, tm2, tv2 = float(v1), float(m1), float(m2), float(v2)
        for b in range(1, max_bars + 1):
            tv1 = (14.0 * tv1 + level) / 15.0
            tm1 = (18.0 * tm1 + level) / 19.0
            tm2 = (24.0 * tm2 + level) / 25.0
            tv2 = (28.0 * tv2 + level) / 29.0
            if tv1 >= tm1 and tv1 >= tv2 and tm2 >= tv2:
                return b
        return None

    p1 = _p_gold(1)
    p2 = _p_gold(2)
    p3 = _p_gold(3)
    p5 = _p_gold(5)

    dist1 = ((p1 - price) / price) * 100.0 if (p1 is not None and price > 0) else 999.0
    dist3 = ((p3 - price) / price) * 100.0 if (p3 is not None and price > 0) else 999.0

    return {
        "p_gold_1bar": p1,
        "p_gold_2bar": p2,
        "p_gold_3bar": p3,
        "p_gold_5bar": p5,
        "bars_at_current_price": _bars_at_level(float(price)),
        "bars_at_plus_2pct": _bars_at_level(float(price) * 1.02),
        "bars_at_plus_4pct": _bars_at_level(float(price) * 1.04),
        "dist_1bar_pct": dist1,
        "dist_3bar_pct": dist3,
    }

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
            symbol = asset.get('symbol', '')
            if symbol in STABLECOIN_TICKERS:
                return None

            tier = asset.get('tier', 'B')
            if tier in ['C', 'C-']:
                return None

            state = asset.get('state', 'NEUTRAL')
            if state == 'GOLD':
                return None

            v1, m1, m2, v2 = asset.get('v1'), asset.get('m1'), asset.get('m2'), asset.get('v2')
            atr = asset.get('atr', 0)
            price = asset.get('price', 0)
            if None in (v1, m1, m2, v2) or not atr or not price or price <= 0 or v2 <= 0:
                return None

            # Must have fast line crossing or above medium-fast line (v1 >= m1)
            v1_m1_diff = v1 - m1
            if v1_m1_diff < 0:
                return None

            prev_m2 = asset.get('prev_m2', m2)
            prev_v2 = asset.get('prev_v2', v2)
            current_gap = abs(m2 - v2)
            prev_gap = abs(prev_m2 - prev_v2)
            is_narrowing = current_gap < prev_gap if current_gap != prev_gap else current_gap < (0.5 * atr)

            proj = compute_smma_forward_projection(v1, m1, m2, v2, price)
            bars_cur = proj.get('bars_at_current_price')
            bars_2p = proj.get('bars_at_plus_2pct')
            dist_3bar = proj.get('dist_3bar_pct', 999.0)

            path_a = (0 < v1_m1_diff < 0.3 * atr and is_narrowing and state == 'NEUTRAL')
            path_b = (
                state == 'NEUTRAL'
                and price >= v2 * 0.99
                and (
                    (bars_cur is not None and bars_cur <= 7)
                    or dist_3bar <= 4.5
                    or (m2 < v2 and abs(m2 - v2) <= 0.6 * atr)
                )
            )

            if path_a or path_b:
                weekly_state = asset.get('weekly_state', '')
                if path_a:
                    priority = 'HIGH' if weekly_state == 'GOLD' else 'MEDIUM'
                    score = 0.85 if priority == 'HIGH' else 0.70
                else:
                    priority = 'HIGH' if (weekly_state == 'GOLD' or (tier in ('S', 'A') and dist_3bar <= 3.5)) else 'MEDIUM'
                    score = 0.85 if weekly_state == 'GOLD' else (0.82 if (tier in ('S', 'A') and dist_3bar <= 3.5) else 0.74)

                p1 = proj.get('p_gold_1bar') or price
                p3 = proj.get('p_gold_3bar') or price
                target_entry = round(max(price, p3), 6)
                key_lvl = round(max(price, p1), 6) if p1 > price else round(max(v1, m1, m2, v2), 6)
                target_sl = round(min(v2, m2) * 0.99, 6)
                target_tp1 = round(target_entry + (2.5 * atr), 6) if atr > 0 else round(target_entry * 1.08, 6)

                bars_est = bars_cur or bars_2p
                if bars_est and bars_est <= 3:
                    est_str = f"1-{bars_est} бара" if bars_est > 1 else "1 бар"
                elif bars_est:
                    est_str = f"~{bars_est} бара"
                else:
                    est_str = "1-3 бара при пробив"

                cond_met = ["v1 > m1 (Бърз импулс)", f"Цена > v2 ({round(v2, 2)})" if price > v2 else "Конвергенция на лентата"]
                if weekly_state == 'GOLD':
                    cond_met.append("Weekly GOLD")
                cond_pend = [
                    "m2 >= v2 (Бавна лента GOLD)" if m2 < v2 else "Затваряне над GOLD праг",
                    f"Задържане/пробив {round(p3, 2)}",
                ]

                return PendingSetup(
                    symbol=symbol,
                    asset_class=asset['asset_class'],
                    setup_type='IMMINENT_GOLD',
                    direction='LONG',
                    priority=priority,
                    quality_score=score,
                    description_bg=(
                        f"{symbol} е на {est_str} от Gold пробив — v1 ({v1:.2f}) > m1 ({m1:.2f}), "
                        f"3-дневен GOLD тригер ≈ {p3:.2f}"
                    ),
                    description_en=(
                        f"{symbol} is {est_str} from Gold transition — v1 crossing m1, 3-bar trigger ~{p3:.2f}"
                    ),
                    conditions_met=cond_met,
                    conditions_pending=cond_pend,
                    estimated_trigger=est_str,
                    current_price=price,
                    target_entry=target_entry,
                    target_sl=target_sl,
                    target_tp1=target_tp1,
                    key_level=key_lvl,
                    tier=tier,
                    first_detected=self.now_str,
                    last_updated=self.now_str,
                )
        except Exception as e:
            logger.error(f"Error in detect_imminent_gold for {asset.get('symbol')}: {e}")
        return None

    def detect_quality_dip_buy(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            symbol = asset.get('symbol', '')
            if symbol in STABLECOIN_TICKERS:
                return None

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
                if isinstance(fund_profile, dict) and fund_profile.get('is_bullish'):
                    is_bullish = True

            if is_bullish:
                price = asset.get('price', 0)
                v1, m1, m2, v2 = asset.get('v1'), asset.get('m1'), asset.get('m2'), asset.get('v2')
                atr = asset.get('atr', 0)
                target_entry = None
                target_sl = None
                target_tp1 = None
                key_level = None
                est_trigger = "При обръщане на 1D тренд"

                if None not in (v1, m1, m2, v2) and price and price > 0 and v2 and v2 > 0:
                    proj = compute_smma_forward_projection(v1, m1, m2, v2, price)
                    p1 = proj.get('p_gold_1bar') or price
                    p3 = proj.get('p_gold_3bar') or price
                    target_entry = round(max(price, p3), 6)
                    key_level = round(max(price, p1), 6) if p1 > price else round(max(v1, m1, m2, v2), 6)
                    target_sl = round(min(v2, m2) * 0.99, 6)
                    if atr and atr > 0:
                        target_tp1 = round(target_entry + (2.5 * atr), 6)
                    est_trigger = f"GOLD reclaim ≈ {round(p3, 2)}"

                return PendingSetup(
                    symbol=symbol,
                    asset_class=asset['asset_class'],
                    setup_type='QUALITY_DIP_BUY',
                    direction='LONG',
                    priority='HIGH',
                    quality_score=0.90,
                    description_bg=f"{symbol} е в pullback при Weekly Gold — чакайте Daily Gold re-entry за вход",
                    description_en=f"{symbol} is in pullback on Weekly Gold — await Daily Gold re-entry",
                    conditions_met=["Weekly GOLD", "Fundamental Bullish", "Quality S/A"],
                    conditions_pending=["Daily transition to GOLD"],
                    estimated_trigger=est_trigger,
                    current_price=price,
                    target_entry=target_entry,
                    target_sl=target_sl,
                    target_tp1=target_tp1,
                    key_level=key_level,
                    tier=tier,
                    first_detected=self.now_str,
                    last_updated=self.now_str,
                )
        except Exception as e:
            logger.error(f"Error in detect_quality_dip_buy for {asset.get('symbol')}: {e}")
        return None

    def detect_sr_approach(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            tier = asset.get('tier', 'B')
            if tier in ['C', 'C-']:
                return None

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
            # Tightened distance: price approaching S1 within 1.2 * atr (imminent touch)
            if s1 and price > s1 and (price - s1) <= 1.2 * atr and (price - s1) >= 0.1 * atr:
                if state == 'GOLD':
                    setup = PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='SR_APPROACH',
                        direction='LONG',
                        priority='HIGH' if tier in ['S', 'A'] else 'MEDIUM',
                        quality_score=0.85 if tier in ['S', 'A'] else 0.72,
                        description_bg=f"{asset['symbol']} е на прага на support ${s1:,.2f} (≤ 1.2 ATR) — следете за bounce setup",
                        description_en=f"{asset['symbol']} approaching support ${s1:,.2f} (≤ 1.2 ATR) — watch for bounce setup",
                        conditions_met=["Uptrend (GOLD)", "Approaching S1"],
                        conditions_pending=["Price reaches S1", "Bullish reaction/bounce"],
                        estimated_trigger=f"при тест на ${s1:,.2f}",
                        current_price=price,
                        key_level=s1,
                        tier=tier,
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
            elif r1 and price < r1 and (r1 - price) <= 1.2 * atr and (r1 - price) >= 0.1 * atr:
                if state == 'GOLD':
                    setup = PendingSetup(
                        symbol=asset['symbol'],
                        asset_class=asset['asset_class'],
                        setup_type='SR_APPROACH',
                        direction='SHORT',
                        priority='MEDIUM',
                        quality_score=0.70 if tier in ['S', 'A'] else 0.60,
                        description_bg=f"{asset['symbol']} приближава resistance ${r1:,.2f} (≤ 1.2 ATR) — следете за take profit или reversal",
                        description_en=f"{asset['symbol']} approaching resistance ${r1:,.2f} (≤ 1.2 ATR) — watch for take profit or reversal",
                        conditions_met=["Uptrend (GOLD)", "Approaching R1"],
                        conditions_pending=["Price reaches R1", "Bearish rejection"],
                        estimated_trigger=f"при тест на ${r1:,.2f}",
                        current_price=price,
                        key_level=r1,
                        tier=tier,
                        first_detected=self.now_str,
                        last_updated=self.now_str
                    )
            return setup
        except Exception as e:
            logger.error(f"Error in detect_sr_approach for {asset.get('symbol')}: {e}")
        return None

    def detect_accumulation_pattern(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            tier = asset.get('tier', 'B')
            if tier in ['C', 'C-']:
                return None

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
                
            priority = 'HIGH' if is_bullish or tier in ['S', 'A'] else 'MEDIUM'
            score = 0.85 if is_bullish else (0.75 if tier in ['S', 'A'] else 0.65)
            
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
                tier=tier,
                first_detected=self.now_str,
                last_updated=self.now_str
            )
        except Exception as e:
            logger.error(f"Error in detect_accumulation_pattern for {asset.get('symbol')}: {e}")
        return None

    def detect_divergence_forming(self, asset: Dict[str, Any]) -> Optional[PendingSetup]:
        try:
            tier = asset.get('tier', 'B')
            if tier in ['C', 'C-']:
                return None

            prices = asset.get('recent_prices', [])
            if not prices or len(prices) < 20:
                return None
                
            prices_arr = np.array(prices, dtype=np.float64)
            rsi = calculate_rsi(prices_arr)
            
            # Find swing lows in price
            lows = []
            for i in range(2, len(prices)-2):
                if prices[i] < prices[i-1] and prices[i] < prices[i-2] and prices[i] < prices[i+1] and prices[i] < prices[i+2]:
                    lows.append(i)
            
            if len(lows) >= 2:
                idx1, idx2 = lows[-2], lows[-1]
                # Enforce that the second swing low is fresh (within last 7 bars of available prices)
                if idx2 >= len(prices) - 7:
                    p1, p2 = prices[idx1], prices[idx2]
                    r1, r2 = rsi[idx1], rsi[idx2]
                    
                    # Bullish Divergence: Lower low in price, Higher low in RSI
                    if p2 < p1 and r2 > r1 and asset.get('state') != 'GOLD':
                        return PendingSetup(
                            symbol=asset['symbol'],
                            asset_class=asset['asset_class'],
                            setup_type='DIVERGENCE_FORMING',
                            direction='LONG',
                            priority='HIGH' if tier in ['S', 'A'] else 'MEDIUM',
                            quality_score=0.85 if tier in ['S', 'A'] else 0.75,
                            description_bg=f"{asset['symbol']} показва bullish divergence на 1D — пресен суинг за обрат",
                            description_en=f"{asset['symbol']} shows fresh bullish divergence on 1D — potential reversal",
                            conditions_met=["Lower Low in Price", "Higher Low in RSI"],
                            conditions_pending=["Bullish structure breakout", "Gold transition"],
                            estimated_trigger="1-3 бара",
                            current_price=asset['price'],
                            tier=tier,
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
                # Enforce that the second swing high is fresh (within last 7 bars of available prices)
                if idx2 >= len(prices) - 7:
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
                            quality_score=0.75 if tier in ['S', 'A'] else 0.65,
                            description_bg=f"{asset['symbol']} показва bearish divergence на 1D — потенциален обрат надолу",
                            description_en=f"{asset['symbol']} shows bearish divergence on 1D — potential reversal down",
                            conditions_met=["Higher High in Price", "Lower High in RSI"],
                            conditions_pending=["Bearish structure breakdown", "Blue transition"],
                            estimated_trigger="1-3 бара",
                            current_price=asset['price'],
                            tier=tier,
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
            if asset.get('symbol', '') in STABLECOIN_TICKERS:
                continue
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

    from src.alerts.formatter import get_asset_name, get_tradingview_link
    import json
    import os

    # Load TV mapping for exchange-accurate links
    tv_map = {}
    try:
        tv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config",
            "tv_mapping.json",
        )
        if os.path.exists(tv_path):
            with open(tv_path, "r", encoding="utf-8") as f:
                tv_map = json.load(f)
    except Exception:
        tv_map = {}
        
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
        asset_name = get_asset_name(s.symbol)
        name_desc = f" ({asset_name})" if asset_name and asset_name != s.symbol else ""
        
        msg += f"{p_emo} <b>{s.symbol}</b>{name_desc} ({s.tier} Tier) - {t_emo} <i>{s.setup_type.replace('_', ' ')}</i>\n"
        if asset_name and asset_name != s.symbol:
            msg += f"🏢 <i>Профил: {asset_name}</i>\n"
        msg += f"💡 {s.description_bg}\n"
        
        msg += "<b>Условия:</b>\n"
        for cond in s.conditions_met:
            msg += f"✅ {cond}\n"
        for cond in s.conditions_pending:
            msg += f"⬜ {cond}\n"
            
        msg += f"⏱ <i>Тригър: {s.estimated_trigger}</i>\n"
        
        tv_sym = tv_map.get(s.symbol) or (f"BINANCE:{s.symbol}" if (s.symbol.endswith("USDT") or s.symbol.endswith("USDC")) else s.symbol)
        tv_link = get_tradingview_link(tv_sym, s.timeframe or "1D")
        msg += f"📊 <a href='{tv_link}'>TradingView Графика</a>\n\n"
        
    return msg.strip()
