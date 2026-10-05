"""
Institutional Portfolio & Cluster Risk Budget Engine (Phase 3 Quant Hardened).
Enforces multi-layer institutional risk governance:
1. Fixed trade risk cap (0.5% - 1.0% per trade to SMMA-29 stop).
2. Correlated cluster risk cap (max 2.0% open risk per factor cluster).
3. Total open portfolio risk cap (max 6.0%).
4. Dynamic exposure scaling based on the Cross-Asset Regime Breadth Index.
5. Strict Leverage Ban: Max Gross Portfolio Notional Exposure <= 100% of equity.
6. Single position notional cap (max 20% of equity).
7. Correlated cluster notional cap (max 35% of equity).
8. Minimum Stop Floor: Stop distance >= k * ATR (k=1.5 crypto, 1.0 equities) to prevent micro-stop gaming.
9. Mark-to-Market Portfolio Heat: Eliminates "0% heat on winners", adds 1.0x ATR overshoot buffer, and 20% crypto stress floor.
10. Order-book depth (5% of 2% depth) and ADV (2% ADV) liquidity caps.
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
    gross_exposure_pct: float = 0.0
    cluster_notional_pct: float = 0.0
    effective_stop_loss: Optional[float] = None


class PortfolioRiskManager:
    def __init__(
        self,
        max_risk_per_trade_pct: float = 1.0,
        max_risk_per_cluster_pct: float = 2.0,
        max_total_portfolio_risk_pct: float = 6.0,
        max_position_notional_pct: float = 20.0,
        max_cluster_notional_pct: float = 35.0,
        max_gross_exposure_pct: float = 100.0,
        min_stop_atr_crypto: float = 1.5,
        min_stop_atr_equity: float = 1.0,
        crypto_stress_floor_pct: float = 20.0,
        overshoot_atr_multiple: float = 1.0,
    ):
        self.max_trade_risk = max_risk_per_trade_pct
        self.max_cluster_risk = max_risk_per_cluster_pct
        self.max_portfolio_risk = max_total_portfolio_risk_pct
        self.max_position_notional_pct = max_position_notional_pct
        self.max_cluster_notional_pct = max_cluster_notional_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct
        self.min_stop_atr_crypto = min_stop_atr_crypto
        self.min_stop_atr_equity = min_stop_atr_equity
        self.crypto_stress_floor_pct = crypto_stress_floor_pct
        self.overshoot_atr_multiple = overshoot_atr_multiple

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
        atr: Optional[float] = None,
        asset_class: str = "crypto",
        adv_usd: Optional[float] = None,
        depth_2pct_usd: Optional[float] = None,
    ) -> RiskBudgetCheck:
        """
        Rigorously evaluates an order against trade, cluster, and macro-scaled portfolio risk limits.
        Enforces Phase 3 institutional controls:
        - Leverage ban (gross notional <= 100% equity).
        - Cluster notional cap (<= 35% equity) and position notional cap (<= 20% equity).
        - Stop distance floor >= k * ATR to eliminate micro-stops.
        - Liquidity caps (order book depth & ADV).
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

        # 1. Stop distance floor: prevents micro-stops from gaming position size
        raw_stop_dist = abs(entry_price - stop_loss)
        effective_stop_dist = raw_stop_dist
        effective_sl = stop_loss
        if atr is not None and atr > 0:
            is_crypto = asset_class.lower() in ("crypto", "cryptocurrency")
            k_atr = self.min_stop_atr_crypto if is_crypto else self.min_stop_atr_equity
            min_stop_dist = k_atr * atr
            if raw_stop_dist < min_stop_dist:
                effective_stop_dist = min_stop_dist
                effective_sl = entry_price - min_stop_dist if entry_price > stop_loss else entry_price + min_stop_dist

        # 2. Sum open risks and open notionals
        total_open_risk_usd = 0.0
        cluster_open_risk_usd = 0.0
        total_open_notional_usd = 0.0
        cluster_open_notional_usd = 0.0

        for p in positions:
            p_risk = float(p.get("risk_usd", 0.0))
            total_open_risk_usd += p_risk
            p_notional = float(p.get("notional_usd", p.get("position_value", 0.0)))
            total_open_notional_usd += p_notional

            if p.get("cluster_id") == cluster_id:
                cluster_open_risk_usd += p_risk
                cluster_open_notional_usd += p_notional

        total_open_risk_pct = round((total_open_risk_usd / account_equity) * 100.0, 2)
        cluster_open_risk_pct = round((cluster_open_risk_usd / account_equity) * 100.0, 2)

        # 3. Check open risk caps
        target_risk_pct = min(self.max_trade_risk, requested_risk_pct or self.max_trade_risk)

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

        # 4. Check notional limits & leverage ban
        max_gross_usd = account_equity * (self.max_gross_exposure_pct / 100.0)
        available_gross_notional_usd = max(0.0, max_gross_usd - total_open_notional_usd)
        if total_open_notional_usd > 0 and available_gross_notional_usd <= 1.0:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=cluster_open_risk_pct,
                portfolio_open_risk_pct=total_open_risk_pct,
                effective_portfolio_cap_pct=effective_cap,
                reason="Gross portfolio exposure cap of 100% reached: Leverage is strictly prohibited.",
            )

        max_cluster_notional_usd = account_equity * (self.max_cluster_notional_pct / 100.0)
        available_cluster_notional_usd = max(0.0, max_cluster_notional_usd - cluster_open_notional_usd)
        if cluster_open_notional_usd > 0 and available_cluster_notional_usd <= 1.0:
            return RiskBudgetCheck(
                allowed=False,
                adjusted_position_usd=0.0,
                units=0.0,
                risk_usd=0.0,
                risk_pct_equity=0.0,
                cluster_open_risk_pct=cluster_open_risk_pct,
                portfolio_open_risk_pct=total_open_risk_pct,
                effective_portfolio_cap_pct=effective_cap,
                reason=f"Cluster notional cap of {self.max_cluster_notional_pct}% reached for cluster '{cluster_id}'.",
            )

        # 5. Position sizing based on allowed risk
        allowed_risk_pct = min(target_risk_pct, available_cluster_risk_pct, available_portfolio_risk_pct)
        allowed_risk_usd = account_equity * (allowed_risk_pct / 100.0)

        units = allowed_risk_usd / effective_stop_dist
        position_usd = units * entry_price

        # Single position notional cap (20% equity)
        max_pos_usd = account_equity * (self.max_position_notional_pct / 100.0)
        if position_usd > max_pos_usd:
            position_usd = max_pos_usd
            units = position_usd / entry_price

        # Correlated cluster notional cap (35% equity)
        if cluster_open_notional_usd > 0 and position_usd > available_cluster_notional_usd:
            position_usd = available_cluster_notional_usd
            units = position_usd / entry_price

        # Gross portfolio exposure cap (100% equity leverage ban)
        if total_open_notional_usd > 0 and position_usd > available_gross_notional_usd:
            position_usd = available_gross_notional_usd
            units = position_usd / entry_price

        # Order-book depth cap (max 5% of +/- 2% book depth)
        if depth_2pct_usd is not None and depth_2pct_usd > 0:
            max_depth_usd = 0.05 * depth_2pct_usd
            if position_usd > max_depth_usd:
                position_usd = max_depth_usd
                units = position_usd / entry_price

        # Average Daily Volume liquidity cap (max 2% ADV)
        if adv_usd is not None and adv_usd > 0:
            max_adv_usd = 0.02 * adv_usd
            if position_usd > max_adv_usd:
                position_usd = max_adv_usd
                units = position_usd / entry_price

        # Recalculate finalized risk USD and % after notional/liquidity capping
        final_risk_usd = round(units * effective_stop_dist, 2)
        final_risk_pct = round((final_risk_usd / account_equity) * 100.0, 2)
        new_cluster_notional_pct = round(((cluster_open_notional_usd + position_usd) / account_equity) * 100.0, 2)
        new_gross_notional_pct = round(((total_open_notional_usd + position_usd) / account_equity) * 100.0, 2)

        return RiskBudgetCheck(
            allowed=True,
            adjusted_position_usd=round(position_usd, 2),
            units=round(units, 4 if entry_price < 100 else 2),
            risk_usd=final_risk_usd,
            risk_pct_equity=final_risk_pct,
            cluster_open_risk_pct=round(cluster_open_risk_pct + final_risk_pct, 2),
            portfolio_open_risk_pct=round(total_open_risk_pct + final_risk_pct, 2),
            effective_portfolio_cap_pct=effective_cap,
            reason=f"Order approved under [{macro_regime}]: Risk ${final_risk_usd:,.2f} ({final_risk_pct:.2f}% of equity). Notional ${position_usd:,.2f} (Gross {new_gross_notional_pct:.1f}%).",
            gross_exposure_pct=new_gross_notional_pct,
            cluster_notional_pct=new_cluster_notional_pct,
            effective_stop_loss=round(effective_sl, 4),
        )

    def calculate_portfolio_heat(
        self,
        account_equity: float,
        open_positions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculates Mark-to-Market Portfolio Heat (Opus Phase 3 Specification):
        - Eliminates the '0% heat on winners' rule.
        - Adds 1.0x ATR overshoot buffer for all open positions.
        - Enforces 20% gap/flash-crash stress floor on crypto positions.
        - Computes total heat USD, heat % of equity, and gross notional exposure %.
        """
        if account_equity <= 0:
            return {
                "account_equity": 0.0,
                "total_heat_usd": 0.0,
                "portfolio_heat_pct": 0.0,
                "total_notional_usd": 0.0,
                "gross_exposure_pct": 0.0,
                "leverage_banned": True,
                "positions": [],
            }

        total_heat_usd = 0.0
        total_notional_usd = 0.0
        position_heats = []

        for p in open_positions:
            symbol = p.get("symbol", "UNKNOWN")
            aclass = p.get("asset_class", "crypto")
            units = float(p.get("units", 0.0))
            current_price = float(p.get("current_price", p.get("entry_price", 0.0)))
            trail_stop = float(p.get("trailing_stop", p.get("stop_loss", 0.0)))
            atr = float(p.get("atr", 0.0))

            if units <= 0 or current_price <= 0:
                continue

            notional = units * current_price
            total_notional_usd += notional

            # Base trail distance (cannot be negative even if stop is in profit)
            trail_dist = max(0.0, current_price - trail_stop)

            # 1.0x ATR overshoot buffer
            risk_per_unit = trail_dist + (self.overshoot_atr_multiple * atr)

            # Crypto 20% stress floor
            if aclass.lower() in ("crypto", "cryptocurrency"):
                stress_floor_unit = current_price * (self.crypto_stress_floor_pct / 100.0)
                risk_per_unit = max(risk_per_unit, stress_floor_unit)

            pos_heat_usd = round(units * risk_per_unit, 2)
            pos_heat_pct = round((pos_heat_usd / account_equity) * 100.0, 2)
            total_heat_usd += pos_heat_usd

            position_heats.append({
                "symbol": symbol,
                "asset_class": aclass,
                "units": units,
                "current_price": current_price,
                "trailing_stop": trail_stop,
                "atr": atr,
                "heat_usd": pos_heat_usd,
                "heat_pct_equity": pos_heat_pct,
                "notional_usd": round(notional, 2),
            })

        portfolio_heat_pct = round((total_heat_usd / account_equity) * 100.0, 2)
        gross_exposure_pct = round((total_notional_usd / account_equity) * 100.0, 2)

        return {
            "account_equity": account_equity,
            "total_heat_usd": round(total_heat_usd, 2),
            "portfolio_heat_pct": portfolio_heat_pct,
            "total_notional_usd": round(total_notional_usd, 2),
            "gross_exposure_pct": gross_exposure_pct,
            "leverage_banned": True,
            "positions": position_heats,
        }
