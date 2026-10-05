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
