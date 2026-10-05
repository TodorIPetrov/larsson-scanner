"""
Unit tests for Institutional Risk Budgeting Engine (src/engine/risk_budget.py).
Verifies:
1. Trade risk calculation bounded by 0.5% - 1.0% of equity to SMMA-29 stop loss.
2. Factor cluster risk limits (max 2.0% equity risk per cluster).
3. Portfolio-level open risk limits (max 6.0% equity risk total).
4. Cross-Asset Regime Breadth scaling multipliers (from 100% down to 0% in Liquidity Drain).
"""

import pytest
from src.engine.risk_budget import PortfolioRiskManager, RiskBudgetCheck


def test_risk_budget_initialization():
    rm = PortfolioRiskManager(
        max_risk_per_trade_pct=0.75,
        max_risk_per_cluster_pct=2.0,
        max_total_portfolio_risk_pct=5.0,
    )
    assert rm.max_trade_risk == 0.75
    assert rm.max_cluster_risk == 2.0
    assert rm.max_portfolio_risk == 5.0


def test_effective_portfolio_cap_by_regime():
    rm = PortfolioRiskManager(max_total_portfolio_risk_pct=6.0)

    # Aggressive Risk On -> 100% of 6% = 6.0%
    assert rm.get_effective_portfolio_cap("AGGRESSIVE_RISK_ON") == 6.0

    # Broad Risk On -> 90% of 6% = 5.4%
    assert rm.get_effective_portfolio_cap("BROAD_RISK_ON") == 5.4

    # Selective / Decoupled -> 60% of 6% = 3.6%
    assert rm.get_effective_portfolio_cap("EQUITY_SELECTIVE_BULL") == 3.6
    assert rm.get_effective_portfolio_cap("CRYPTO_DECOUPLED_BULL") == 3.6

    # Chop -> 35% of 6% = 2.1%
    assert rm.get_effective_portfolio_cap("CONSOLIDATION_CHOP") == 2.1

    # Defensive -> 20% of 6% = 1.2%
    assert rm.get_effective_portfolio_cap("DEFENSIVE_RISK_OFF") == 1.2

    # Broad Liquidity Drain -> 0% (Capital Lockdown)
    assert rm.get_effective_portfolio_cap("BROAD_LIQUIDITY_DRAIN") == 0.0


def test_trade_approved_under_risk_limit():
    rm = PortfolioRiskManager()
    equity = 100_000.0
    entry = 100.0
    stop = 95.0  # 5% stop distance

    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=entry,
        stop_loss=stop,
        cluster_id="MEGA_TECH",
        current_open_positions=[],
        macro_regime="AGGRESSIVE_RISK_ON",
    )

    assert check.allowed is True
    # Default max trade risk is 1.0% -> $1,000 risk
    assert check.risk_pct_equity == 1.0
    assert check.risk_usd == 1000.0
    # units = 1000 / (100 - 95) = 200 units -> $20,000 position
    assert check.units == 200.0
    assert check.adjusted_position_usd == 20000.0
    assert check.cluster_open_risk_pct == 1.0
    assert check.portfolio_open_risk_pct == 1.0


def test_cluster_cap_truncation_and_rejection():
    rm = PortfolioRiskManager(max_risk_per_trade_pct=1.0, max_risk_per_cluster_pct=2.0)
    equity = 100_000.0

    # Existing open position in cluster 'CRYPTO_L1' already using 1.4% risk ($1,400)
    open_positions = [
        {"symbol": "SOLUSDT", "cluster_id": "CRYPTO_L1", "risk_usd": 1400.0}
    ]

    # New order in same cluster asking for 1.0% risk -> only 0.6% remaining in cluster budget
    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=2000.0,
        stop_loss=1900.0,  # $100 per unit stop
        cluster_id="CRYPTO_L1",
        current_open_positions=open_positions,
        macro_regime="AGGRESSIVE_RISK_ON",
    )

    assert check.allowed is True
    # Risk is truncated from requested 1.0% to remaining 0.6% ($600)
    assert check.risk_pct_equity == 0.6
    assert check.risk_usd == 600.0
    # units = 600 / 100 = 6 units -> $12,000 position
    assert check.units == 6.0
    assert check.cluster_open_risk_pct == 2.0

    # Another order when cluster is full (already at 2.0%) -> rejected
    open_positions_full = [
        {"symbol": "SOLUSDT", "cluster_id": "CRYPTO_L1", "risk_usd": 1400.0},
        {"symbol": "ETHUSDT", "cluster_id": "CRYPTO_L1", "risk_usd": 600.0},
    ]

    check_rejected = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=50.0,
        stop_loss=45.0,
        cluster_id="CRYPTO_L1",
        current_open_positions=open_positions_full,
        macro_regime="AGGRESSIVE_RISK_ON",
    )

    assert check_rejected.allowed is False
    assert "Cluster risk cap" in check_rejected.reason


def test_portfolio_regime_cap_enforcement():
    rm = PortfolioRiskManager(max_total_portfolio_risk_pct=6.0)
    equity = 100_000.0

    # Regime is CONSOLIDATION_CHOP: cap is 35% of 6% = 2.1% ($2,100)
    open_positions = [
        {"symbol": "AAPL", "cluster_id": "TECH", "risk_usd": 1000.0},
        {"symbol": "XOM", "cluster_id": "ENERGY", "risk_usd": 1000.0},
    ]
    # Total open risk is 2.0%. Remaining portfolio risk is 0.1%.
    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=50.0,
        stop_loss=45.0,
        cluster_id="HEALTHCARE",
        current_open_positions=open_positions,
        macro_regime="CONSOLIDATION_CHOP",
    )

    # 0.1% risk available -> truncated to 0.1% ($100)
    assert check.allowed is True
    assert check.risk_pct_equity == 0.1
    assert check.risk_usd == 100.0

    # If already at 2.1%, new order rejected
    open_positions_full = [
        {"symbol": "AAPL", "cluster_id": "TECH", "risk_usd": 1100.0},
        {"symbol": "XOM", "cluster_id": "ENERGY", "risk_usd": 1000.0},
    ]
    check_full = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=50.0,
        stop_loss=45.0,
        cluster_id="HEALTHCARE",
        current_open_positions=open_positions_full,
        macro_regime="CONSOLIDATION_CHOP",
    )
    assert check_full.allowed is False
    assert "Portfolio risk cap" in check_full.reason


def test_broad_liquidity_drain_lockdown():
    rm = PortfolioRiskManager()
    check = rm.evaluate_order_risk(
        account_equity=50_000.0,
        entry_price=100.0,
        stop_loss=95.0,
        cluster_id="MEGA_TECH",
        macro_regime="BROAD_LIQUIDITY_DRAIN",
    )
    assert check.allowed is False
    assert "Risk lockdown active" in check.reason


def test_invalid_parameters():
    rm = PortfolioRiskManager()
    check = rm.evaluate_order_risk(
        account_equity=-1000.0,
        entry_price=100.0,
        stop_loss=95.0,
        cluster_id="MEGA_TECH",
    )
    assert check.allowed is False
    assert "Invalid price or equity" in check.reason


def test_leverage_ban_and_position_notional_cap():
    rm = PortfolioRiskManager()
    equity = 100_000.0

    # 1. Single position notional cap: 20% of equity = $20,000 max notional.
    # Entry = 100, Stop = 99 (1% stop distance).
    # Allowed risk 1% = $1,000 -> Naive units = 1000 / 1 = 1,000 units ($100,000 notional = 100% equity).
    # Phase 3 cap must clamp notional to exactly $20,000 (200 units).
    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=100.0,
        stop_loss=99.0,
        cluster_id="MEGA_TECH",
        macro_regime="AGGRESSIVE_RISK_ON",
    )
    assert check.allowed is True
    assert check.adjusted_position_usd == 20000.0
    assert check.units == 200.0
    # Risk is now 200 units * $1 = $200 (0.2% equity), clamped from notional
    assert check.risk_usd == 200.0

    # 2. Leverage ban: gross portfolio exposure cannot exceed 100% of equity
    # If open positions already consume 95% notional ($95,000):
    open_pos = [
        {"symbol": "AAPL", "cluster_id": "TECH", "risk_usd": 500.0, "notional_usd": 95000.0}
    ]
    # New order can only take remaining $5,000 notional (5%)
    check_lev = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=100.0,
        stop_loss=95.0,
        cluster_id="CRYPTO_L1",
        current_open_positions=open_pos,
        macro_regime="AGGRESSIVE_RISK_ON",
    )
    assert check_lev.allowed is True
    assert check_lev.adjusted_position_usd == 5000.0
    assert check_lev.units == 50.0

    # If book is at 100% notional, new orders are rejected with leverage ban reason
    open_pos_full = [
        {"symbol": "AAPL", "cluster_id": "TECH", "risk_usd": 500.0, "notional_usd": 100000.0}
    ]
    check_full = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=100.0,
        stop_loss=95.0,
        cluster_id="CRYPTO_L1",
        current_open_positions=open_pos_full,
        macro_regime="AGGRESSIVE_RISK_ON",
    )
    assert check_full.allowed is False
    assert "Gross portfolio exposure cap of 100% reached" in check_full.reason


def test_minimum_stop_floor_atr():
    rm = PortfolioRiskManager()
    equity = 100_000.0
    entry = 100.0
    # Micro-stop requested at 99.8 (0.2% distance)
    # Crypto ATR is 4.0 -> k=1.5 * 4.0 = 6.0 min stop distance
    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=entry,
        stop_loss=99.8,
        cluster_id="CRYPTO_L1",
        macro_regime="AGGRESSIVE_RISK_ON",
        atr=4.0,
        asset_class="crypto",
    )
    assert check.allowed is True
    # Stop distance was clamped to at least 6.0 (effective stop = 94.0)
    assert check.effective_stop_loss == 94.0


def test_portfolio_heat_mtm_and_crypto_stress_floor():
    rm = PortfolioRiskManager()
    equity = 100_000.0

    # Scenario:
    # 1. SOLUSDT: Entry 100, current price 150, trailing stop 140, ATR 5.0, 10 units.
    #    Trail distance is 150 - 140 = 10. + 1.0x ATR (5) = 15.
    #    Crypto 20% stress floor on price 150 is 30.0!
    #    Max(15, 30) = 30.0 risk per unit -> Heat = 10 * 30 = $300.
    # 2. AAPL (Stock): Entry 150, current price 200, trailing stop 195, ATR 3.0, 20 units.
    #    Trail distance = 200 - 195 = 5. + 1.0x ATR (3) = 8.
    #    Heat = 20 * 8 = $160.
    open_positions = [
        {
            "symbol": "SOLUSDT",
            "asset_class": "crypto",
            "units": 10.0,
            "current_price": 150.0,
            "trailing_stop": 140.0,
            "atr": 5.0,
        },
        {
            "symbol": "AAPL",
            "asset_class": "stocks",
            "units": 20.0,
            "current_price": 200.0,
            "trailing_stop": 195.0,
            "atr": 3.0,
        },
    ]

    heat = rm.calculate_portfolio_heat(equity, open_positions)
    assert heat["total_heat_usd"] == 460.0  # 300 + 160
    assert heat["portfolio_heat_pct"] == 0.46
    assert heat["total_notional_usd"] == 5500.0  # (10*150) + (20*200) = 1500 + 4000
    assert heat["gross_exposure_pct"] == 5.5
    assert heat["leverage_banned"] is True


def test_liquidity_depth_and_adv_caps():
    rm = PortfolioRiskManager()
    equity = 100_000.0
    entry = 100.0
    stop = 90.0

    # Normal position would be $10,000 notional (100 units).
    # But 2% order book depth is only $40,000 -> 5% depth cap is $2,000 (20 units).
    check = rm.evaluate_order_risk(
        account_equity=equity,
        entry_price=entry,
        stop_loss=stop,
        cluster_id="CRYPTO_LOW_CAP",
        depth_2pct_usd=40_000.0,
    )
    assert check.allowed is True
    assert check.adjusted_position_usd == 2000.0
    assert check.units == 20.0

