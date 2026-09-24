"""
Tests for the Setup Monitor Engine.
Verifies detection of trade setups like imminent gold, dip buys, s/r approaches,
accumulation patterns, and divergences.
"""

import pytest
import numpy as np
from src.engine.setup_monitor import (
    SetupMonitor,
    PendingSetup,
    calculate_rsi,
    format_queue_telegram
)


class MockFundProfile:
    def __init__(self, is_bullish=False):
        self.is_bullish = is_bullish


def test_calculate_rsi():
    # Steady up trend
    prices_up = np.linspace(10, 100, 30)
    rsi_up = calculate_rsi(prices_up)
    assert rsi_up[-1] > 70.0

    # Steady down trend
    prices_down = np.linspace(100, 10, 30)
    rsi_down = calculate_rsi(prices_down)
    assert rsi_down[-1] < 30.0

    # Short array (< 15 bars)
    prices_short = np.array([10, 20, 30, 40])
    rsi_short = calculate_rsi(prices_short)
    assert np.all(rsi_short == 50.0)


def test_detect_imminent_gold():
    monitor = SetupMonitor()
    
    # Asset with NEUTRAL state, v1 just crossed m1, gap narrowing
    asset_imminent = {
        'symbol': 'BTC',
        'asset_class': 'CRYPTO',
        'price': 65000,
        'state': 'NEUTRAL',
        'weekly_state': 'GOLD',
        'v1': 60100,
        'm1': 60000,
        'm2': 59000,
        'v2': 58500,
        'prev_m2': 59000,
        'prev_v2': 58000, # Gap was 1000, now 500
        'atr': 1000,
        'tier': 'S'
    }
    
    setup = monitor.detect_imminent_gold(asset_imminent)
    assert setup is not None
    assert setup.setup_type == 'IMMINENT_GOLD'
    assert setup.priority == 'HIGH'
    
    # Already GOLD -> should return None
    asset_gold = asset_imminent.copy()
    asset_gold['state'] = 'GOLD'
    assert monitor.detect_imminent_gold(asset_gold) is None
    
    # Not crossed (v1 < m1) -> should return None
    asset_not_crossed = asset_imminent.copy()
    asset_not_crossed['v1'] = 59900
    assert monitor.detect_imminent_gold(asset_not_crossed) is None


def test_detect_quality_dip_buy():
    monitor = SetupMonitor()
    
    asset = {
        'symbol': 'ETH',
        'asset_class': 'CRYPTO',
        'price': 3500,
        'state': 'NEUTRAL',
        'weekly_state': 'GOLD',
        'tier': 'S',
        'fund_profile': MockFundProfile(is_bullish=True)
    }
    
    setup = monitor.detect_quality_dip_buy(asset)
    assert setup is not None
    assert setup.setup_type == 'QUALITY_DIP_BUY'
    assert setup.priority == 'HIGH'
    
    # Tier C -> should return None
    asset_c = asset.copy()
    asset_c['tier'] = 'C'
    assert monitor.detect_quality_dip_buy(asset_c) is None
    
    # Weekly BLUE -> should return None
    asset_blue = asset.copy()
    asset_blue['weekly_state'] = 'BLUE'
    assert monitor.detect_quality_dip_buy(asset_blue) is None


def test_detect_sr_approach():
    monitor = SetupMonitor()
    
    # Support approach
    asset_support = {
        'symbol': 'SOL',
        'asset_class': 'CRYPTO',
        'price': 102,
        'state': 'GOLD',
        'atr': 2,
        'tier': 'A',
        'sr_analysis': {'s1': 100, 'r1': 120, 'atr': 2}
    }
    
    setup_s = monitor.detect_sr_approach(asset_support)
    assert setup_s is not None
    assert setup_s.setup_type == 'SR_APPROACH'
    assert setup_s.direction == 'LONG'
    assert setup_s.key_level == 100
    
    # Resistance approach
    asset_resistance = {
        'symbol': 'SOL',
        'asset_class': 'CRYPTO',
        'price': 118,
        'state': 'GOLD',
        'atr': 2,
        'tier': 'A',
        'sr_analysis': {'s1': 100, 'r1': 120, 'atr': 2}
    }
    
    setup_r = monitor.detect_sr_approach(asset_resistance)
    assert setup_r is not None
    assert setup_r.setup_type == 'SR_APPROACH'
    assert setup_r.direction == 'SHORT'
    assert setup_r.key_level == 120


def test_detect_accumulation_pattern():
    monitor = SetupMonitor()
    
    asset = {
        'symbol': 'LINK',
        'asset_class': 'CRYPTO',
        'price': 15,
        'state': 'NEUTRAL',
        'recent_states': ['NEUTRAL'] * 15,
        'tier': 'B',
        'fund_profile': MockFundProfile(is_bullish=True)
    }
    
    setup = monitor.detect_accumulation_pattern(asset)
    assert setup is not None
    assert setup.setup_type == 'ACCUMULATION_PATTERN'
    assert setup.priority == 'HIGH'
    
    # Not enough neutral history
    asset_short = asset.copy()
    asset_short['recent_states'] = ['NEUTRAL'] * 5
    assert monitor.detect_accumulation_pattern(asset_short) is None


def test_detect_divergence_forming():
    monitor = SetupMonitor()
    
    # Construct a price array with a steep drop to 50, bounce, and slow drop to 48
    prices = [100.0] * 15
    prices.extend([90, 80, 70, 60, 50])  # Steep drop (Low 1)
    prices.extend([60, 70, 80])          # Bounce
    prices.extend([75, 70, 65, 60, 55, 50, 48])  # Slow drop (Low 2)
    prices.extend([55, 60, 65, 70, 75])  # Current bounce
    
    asset = {
        'symbol': 'AVAX',
        'asset_class': 'CRYPTO',
        'price': 75,
        'state': 'NEUTRAL',
        'recent_prices': prices,
        'tier': 'A'
    }
    
    setup = monitor.detect_divergence_forming(asset)
    assert setup is not None
    assert setup.setup_type == 'DIVERGENCE_FORMING'
    assert setup.direction == 'LONG'


def test_scan_for_pending_setups():
    monitor = SetupMonitor()
    
    assets = [
        # Asset 1: Imminent Gold (score ~ 0.85)
        {
            'symbol': 'BTC',
            'asset_class': 'CRYPTO',
            'price': 65000,
            'state': 'NEUTRAL',
            'weekly_state': 'GOLD',
            'v1': 60100, 'm1': 60000, 'm2': 59000, 'v2': 58500,
            'prev_m2': 59000, 'prev_v2': 58000,
            'atr': 1000,
            'tier': 'S'
        },
        # Asset 2: Quality Dip Buy (score ~ 0.90)
        {
            'symbol': 'ETH',
            'asset_class': 'CRYPTO',
            'price': 3500,
            'state': 'NEUTRAL',
            'weekly_state': 'GOLD',
            'tier': 'S',
            'fund_profile': MockFundProfile(is_bullish=True)
        },
        # Asset 3: Same as Asset 1 (duplicate)
        {
            'symbol': 'BTC',
            'asset_class': 'CRYPTO',
            'price': 65000,
            'state': 'NEUTRAL',
            'weekly_state': 'GOLD',
            'v1': 60100, 'm1': 60000, 'm2': 59000, 'v2': 58500,
            'prev_m2': 59000, 'prev_v2': 58000,
            'atr': 1000,
            'tier': 'S'
        }
    ]
    
    setups = monitor.scan_for_pending_setups(assets)
    
    assert len(setups) == 2
    
    # Sorted by score descending
    assert setups[0].setup_type == 'QUALITY_DIP_BUY'  # 0.90
    assert setups[1].setup_type == 'IMMINENT_GOLD'    # 0.85
    
    # Duplicate filtered out
    assert len([s for s in setups if s.symbol == 'BTC']) == 1


def test_format_queue_telegram():
    setup1 = PendingSetup(
        symbol='BTC',
        asset_class='CRYPTO',
        setup_type='IMMINENT_GOLD',
        direction='LONG',
        priority='HIGH',
        quality_score=0.85,
        description_bg='БТК е готов за полет',
        description_en='BTC ready to fly',
        conditions_met=['v1 > m1'],
        conditions_pending=['v1 > v2'],
        estimated_trigger='1-2 бара',
        current_price=65000,
        tier='S'
    )
    
    setup2 = PendingSetup(
        symbol='ETH',
        asset_class='CRYPTO',
        setup_type='QUALITY_DIP_BUY',
        direction='LONG',
        priority='HIGH',
        quality_score=0.90,
        description_bg='ЕТР е в корекция',
        description_en='ETH is in pullback',
        conditions_met=['Weekly GOLD'],
        conditions_pending=['Daily GOLD'],
        estimated_trigger='1-2 бара',
        current_price=3500,
        tier='S'
    )
    
    msg = format_queue_telegram([setup1, setup2])
    
    assert '<b>⏳ Pending Setups Monitor (1-3 Bars)</b>' in msg
    assert '<b>BTC</b> (S Tier)' in msg
    assert 'БТК е готов за полет' in msg
    assert '✅ v1 > m1' in msg
    assert '⬜ v1 > v2' in msg
    assert '<a href=\'https://www.tradingview.com/chart/?symbol=BTC\'>📈 TradingView</a>' in msg
    assert '<b>ETH</b> (S Tier)' in msg
