"""
Institutional Portfolio & Cluster Risk Budget Engine.
Enforces multi-layer risk governance:
1. Fixed trade risk cap (0.5% - 1.0% per trade to SMMA-29 stop).
2. Correlated cluster risk cap (max 2.0% open risk per factor cluster).
3. Total open portfolio risk cap (max 6.0%).
4. Dynamic exposure scaling based on the Cross-Asset Regime Breadth Index.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskBudgetCheck:
    allowed: bool
    adjusted_position_usd: float
    units: float
    risk_usd: float
    risk_pct_equity: float
    cluster_open_risk_pct: float
    portfolio_open_risk_pct: float
    effective_portfolio_cap_pct: float
    reason: str


class PortfolioRiskManager:
    def __init__(
        self,
        max_risk_per_trade_pct: float = 1.0,
        max_risk_per_cluster_pct: float = 2.0,
        max_total_portfolio_risk_pct: float = 6.0,
    ):
        self.max_trade_risk = max_risk_per_trade_pct
        self.max_cluster_risk = max_risk_per_cluster_pct
        self.max_portfolio_risk = max_total_portfolio_risk_pct

        # Regime Breadth Exposure Scaling factors
        self.regime_exposure_multipliers = {
            "AGGRESSIVE_RISK_ON": 1.0,      # 100% of risk budget (6.0% max)
            "BROAD_RISK_ON": 0.9,           # 90% (5.4% max)
            "EQUITY_SELECTIVE_BULL": 0.6,   # 60% (3.6% max)
            "CRYPTO_DECOUPLED_BULL": 0.6,   # 60% (3.6% max)
            "ROTATIONAL_MIXED": 0.5,        # 50% (3.0% max)
            "CONSOLIDATION_CHOP": 0.35,     # 35% (2.1% max)
            "DEFENSIVE_RISK_OFF": 0.20,     # 20% (1.2% max)
            "BROAD_LIQUIDITY_DRAIN": 0.0,   # 0% (Lockdown: No new long risk)
        }

    def get_effective_portfolio_cap(self, macro_regime: str = "AGGRESSIVE_RISK_ON") -> float:
        """Calculates dynamic portfolio open risk cap based on market regime breadth."""
        multiplier = self.regime_exposure_multipliers.get(macro_regime.upper(), 0.5)
        return round(self.max_portfolio_risk * multiplier, 2)

    def evaluate_order_risk(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss: float,
        cluster_id: str,
        current_open_positions: Optional[List[Dict[str, Any]]] = None,
        macro_regime: str = "AGGRESSIVE_RISK_ON",
        requested_risk_pct: Optional[float] = None,
    ) -> RiskBudgetCheck:
        """
        Rigorously evaluates an order against trade, cluster, and macro-scaled portfolio risk limits.
        """
        if account_equity <= 0 or entry_price <= 0 or stop_loss <= 0 or entry_price == stop_loss:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=0.0,
                portfolio_open_risk_pct=0.0,
                effective_portfolio_cap_pct=0.0,
                reason="Invalid price or equity parameters.",
            )

        positions = current_open_positions or []
        effective_cap = self.get_effective_portfolio_cap(macro_regime)

        # Capital lockdown in Broad Liquidity Drain
        if effective_cap <= 0.0:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=0.0,
                portfolio_open_risk_pct=0.0,
                effective_portfolio_cap_pct=0.0,
                reason=f"Risk lockdown active under [{macro_regime}]: New long exposure blocked.",
            )

        # Sum open risks
        total_open_risk_usd = 0.0
        cluster_open_risk_usd = 0.0

        for p in positions:
            p_risk = float(p.get("risk_usd", 0.0))
            total_open_risk_usd += p_risk
            if p.get("cluster_id") == cluster_id:
                cluster_open_risk_usd += p_risk

        total_open_risk_pct = round((total_open_risk_usd / account_equity) * 100.0, 2)
        cluster_open_risk_pct = round((cluster_open_risk_usd / account_equity) * 100.0, 2)

        # Target trade risk
        target_risk_pct = min(self.max_trade_risk, requested_risk_pct or self.max_trade_risk)
        target_risk_usd = account_equity * (target_risk_pct / 100.0)

        # Remaining portfolio budget
        available_portfolio_risk_pct = max(0.0, effective_cap - total_open_risk_pct)
        if available_portfolio_risk_pct <= 0.01:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=cluster_open_risk_pct,
                portfolio_open_risk_pct=total_open_risk_pct,
                effective_portfolio_cap_pct=effective_cap,
                reason=f"Portfolio risk cap of {effective_cap}% reached under [{macro_regime}].",
            )

        # Remaining cluster budget
        available_cluster_risk_pct = max(0.0, self.max_cluster_risk - cluster_open_risk_pct)
        if available_cluster_risk_pct <= 0.01:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=cluster_open_risk_pct,
                portfolio_open_risk_pct=total_open_risk_pct,
                effective_portfolio_cap_pct=effective_cap,
                reason=f"Cluster risk cap of {self.max_cluster_risk}% reached for cluster '{cluster_id}'.",
            )

        # Truncate risk to fit within available cluster and portfolio budgets
        allowed_risk_pct = min(target_risk_pct, available_cluster_risk_pct, available_portfolio_risk_pct)
        allowed_risk_usd = account_equity * (allowed_risk_pct / 100.0)

        # Position sizing to invalidation stop
        risk_per_unit = abs(entry_price - stop_loss)
        units = allowed_risk_usd / risk_per_unit
        position_value_usd = round(units * entry_price, 2)

        return RiskBudgetCheck(
            allowed=True,
            adjusted_position_usd=position_value_usd,
            units=round(units, 4 if entry_price < 100 else 2),
            risk_usd=round(allowed_risk_usd, 2),
            risk_pct_equity=round(allowed_risk_pct, 2),
            cluster_open_risk_pct=round(cluster_open_risk_pct + allowed_risk_pct, 2),
            portfolio_open_risk_pct=round(total_open_risk_pct + allowed_risk_pct, 2),
            effective_portfolio_cap_pct=effective_cap,
            reason=f"Order approved under [{macro_regime}]: Risk ${allowed_risk_usd:,.2f} ({allowed_risk_pct:.2f}% of equity).",
        )
