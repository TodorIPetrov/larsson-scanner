"""
Enhanced Portfolio Tracker for Larsson Line Scanner.
Provides comprehensive position management, P&L tracking,
trade journal, and portfolio performance analytics with strict
isolation between Virtual (Paper) and Real (Live) portfolios.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.storage.database import Database
from src.engine.asset_profiles import get_quality_tier, get_tier_position_multiplier, get_asset_profile

logger = logging.getLogger(__name__)


class PortfolioTracker:
    def __init__(self, db: Optional[Database] = None, config: Optional[dict] = None):
        self.db = db or Database()
        self.config = (config or {}).get('portfolio', {})
        self.initial_capital = float(self.config.get('initial_capital', 10000.0))
        self.default_risk_pct = float(self.config.get('risk_per_trade_pct', 1.0))
        self.max_portfolio_risk_pct = float(self.config.get('max_portfolio_risk_pct', 6.0))

    def get_portfolio_summary(self, portfolio_type: str = "PAPER") -> dict:
        """
        Query open positions and calculate portfolio summary for either 'PAPER' or 'REAL'.
        """
        p_type = portfolio_type.upper()
        if p_type == "REAL":
            open_positions = self.db.get_open_real_positions()
            balance = self.db.get_real_balance(initial_balance=0.0)
            closed_positions = self.db.get_closed_real_positions(limit=10000)
            try:
                allocation = self.db.get_real_portfolio_allocation()
            except Exception:
                allocation = {}
        else:
            open_positions = self.db.get_open_paper_positions()
            balance = self.db.get_paper_balance(initial_balance=self.initial_capital)
            closed_positions = self.db.get_closed_paper_positions(limit=10000)
            try:
                allocation = self.db.get_portfolio_allocation()
            except Exception:
                allocation = {}
        
        available_cash = balance["available_cash"]
        initial_balance = balance.get("initial_balance", self.initial_capital if p_type == "PAPER" else 0.0)
        total_invested = sum(
            pos.get("margin_usd") or (pos["position_size_usd"] / max(1, pos.get("leverage") or 1))
            for pos in open_positions
        )
        
        unrealized_pnl = 0.0
        total_equity = available_cash
        
        # Determine unrealized PnL from latest states
        for pos in open_positions:
            ticker = pos["ticker"]
            units = pos["units"]
            pos_size = pos["position_size_usd"]
            entry = pos["entry_price"]
            direction = pos["direction"] if "direction" in pos.keys() and pos["direction"] else "LONG"
            leverage = pos["leverage"] if "leverage" in pos.keys() and pos["leverage"] else 1
            margin = pos["margin_usd"] if "margin_usd" in pos.keys() and pos["margin_usd"] else round(pos_size / max(1, leverage), 2)
            
            state = self.db.get_current_state(ticker, "4H") or self.db.get_current_state(ticker, "1D")
            current_price = state["last_price"] if state else entry
            
            if direction == "SHORT":
                u_pnl = (entry - current_price) * units
            else:
                u_pnl = (current_price - entry) * units
                
            pos_equity = max(0.0, margin + u_pnl)
            unrealized_pnl += u_pnl
            total_equity += pos_equity
            
        unrealized_pnl_pct = (unrealized_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
        
        # Calculate stats from closed positions
        total_realized_pnl = sum(p["realized_pnl_usd"] for p in closed_positions)
        
        winners = [p for p in closed_positions if p["realized_pnl_usd"] > 0]
        losers = [p for p in closed_positions if p["realized_pnl_usd"] < 0]
        
        win_rate = (len(winners) / len(closed_positions) * 100.0) if closed_positions else 0.0
        
        gross_profit = sum(p["realized_pnl_usd"] for p in winners)
        gross_loss = abs(sum(p["realized_pnl_usd"] for p in losers))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
        
        avg_pnl_pct = sum(p["realized_pnl_pct"] for p in closed_positions) / len(closed_positions) if closed_positions else 0.0
        
        best_trade = dict(max(closed_positions, key=lambda x: x["realized_pnl_usd"])) if closed_positions else None
        worst_trade = dict(min(closed_positions, key=lambda x: x["realized_pnl_usd"])) if closed_positions else None
        
        if not allocation and open_positions:
            for pos in open_positions:
                ticker = pos["ticker"]
                tier = get_quality_tier(ticker)
                val = pos.get("margin_usd") or (pos["units"] * pos["entry_price"])
                allocation[tier] = allocation.get(tier, 0.0) + val
                
        return {
            "portfolio_type": p_type,
            "total_equity": total_equity,
            "initial_balance": initial_balance,
            "available_cash": available_cash,
            "total_invested": total_invested,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "total_realized_pnl": total_realized_pnl,
            "open_positions_count": len(open_positions),
            "closed_positions_count": len(closed_positions),
            "wins": len(winners),
            "losses": len(losers),
            "win_rate": win_rate,
            "avg_pnl_pct": avg_pnl_pct,
            "profit_factor": profit_factor,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "allocation": allocation
        }

    def get_open_positions_detail(self, portfolio_type: str = "PAPER") -> List[dict]:
        """
        Get detailed information for each open position (PAPER or REAL).
        """
        p_type = portfolio_type.upper()
        if p_type == "REAL":
            open_positions = self.db.get_open_real_positions()
        else:
            open_positions = self.db.get_open_paper_positions()

        details = []
        now = datetime.now(timezone.utc)
        
        for pos in open_positions:
            ticker = pos["ticker"]
            entry = pos["entry_price"]
            units = pos["units"]
            pos_size = pos["position_size_usd"]
            
            state = self.db.get_current_state(ticker, "4H") or self.db.get_current_state(ticker, "1D")
            current_price = state["last_price"] if state else entry
            
            val = units * current_price
            u_pnl = val - pos_size
            u_pnl_pct = (u_pnl / pos_size * 100.0) if pos_size > 0 else 0.0
            
            opened_at_str = pos["opened_at"] or now.isoformat()
            try:
                opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
                duration_days = (now - opened_at).days
            except Exception:
                duration_days = 0
            
            asset_class = pos["asset_class"] if "asset_class" in pos.keys() and pos["asset_class"] else "crypto"
            if asset_class == "crypto":
                try:
                    symbols = self.db.get_active_symbols()
                    for s in symbols:
                        if s["ticker"] == ticker:
                            asset_class = s["asset_class"]
                            break
                except Exception:
                    pass
            
            details.append({
                "position_id": pos["position_id"],
                "symbol": ticker,
                "direction": "LONG",
                "entry_price": entry,
                "current_price": current_price,
                "units": units,
                "position_size_usd": pos_size,
                "current_value": val,
                "unrealized_pnl": u_pnl,
                "unrealized_pnl_pct": u_pnl_pct,
                "stop_loss": pos["stop_loss"],
                "tp1": pos["tp1"],
                "tp2": pos["tp2"],
                "duration_days": duration_days,
                "opened_at": opened_at_str,
                "tier": get_quality_tier(ticker),
                "asset_class": asset_class,
                "portfolio_type": p_type,
                "broker_exchange": pos["broker_exchange"] if "broker_exchange" in pos.keys() else "Paper Engine",
                "notes": pos["notes"] if "notes" in pos.keys() else "",
                "fee_paid_usd": pos["fee_paid_usd"] if "fee_paid_usd" in pos.keys() else 0.0,
            })
            
        return details

    def get_trade_history(self, limit: int = 50, portfolio_type: str = "PAPER") -> List[dict]:
        """
        Get closed positions history for PAPER or REAL.
        """
        p_type = portfolio_type.upper()
        if p_type == "REAL":
            closed_positions = self.db.get_closed_real_positions(limit=limit)
        else:
            closed_positions = self.db.get_closed_paper_positions(limit=limit)

        history = []
        for pos in closed_positions:
            opened_at_str = pos["opened_at"] or ""
            closed_at_str = pos["closed_at"] or opened_at_str
            try:
                opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
                closed_at = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00")) if closed_at_str else opened_at
                hold_days = (closed_at - opened_at).days
            except Exception:
                hold_days = 0
            
            exit_reason = pos["exit_reason"] if "exit_reason" in pos.keys() and pos["exit_reason"] else (pos["notes"] if "notes" in pos.keys() else "MANUAL_CLOSE")
            broker = pos["broker_exchange"] if "broker_exchange" in pos.keys() else "Paper Engine"

            history.append({
                "position_id": pos["position_id"],
                "symbol": pos["ticker"],
                "entry_date": opened_at_str,
                "exit_date": closed_at_str,
                "entry_price": pos["entry_price"],
                "exit_price": pos["exit_price"],
                "units": pos["units"] if "units" in pos.keys() else 0.0,
                "pnl_usd": pos["realized_pnl_usd"],
                "pnl_pct": pos["realized_pnl_pct"],
                "hold_duration_days": hold_days,
                "exit_reason": exit_reason,
                "broker_exchange": broker,
                "tier": get_quality_tier(pos["ticker"]),
                "portfolio_type": p_type
            })
            
        return sorted(history, key=lambda x: x["exit_date"] or "", reverse=True)

    def add_real_position(
        self,
        ticker: str,
        asset_class: str,
        entry_price: float,
        units: float,
        stop_loss: Optional[float] = None,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        broker_exchange: str = "Manual",
        notes: Optional[str] = None,
        fee_paid_usd: float = 0.0,
    ) -> str:
        """
        Record a real execution from broker/exchange into real_positions and trade_log.
        """
        pos_id = f"real_{ticker}_{int(datetime.now(timezone.utc).timestamp())}"
        pos_size = entry_price * units
        now_iso = datetime.now(timezone.utc).isoformat()
        
        self.db.open_real_position(
            position_id=pos_id,
            ticker=ticker,
            asset_class=asset_class,
            entry_price=entry_price,
            units=units,
            position_size_usd=pos_size,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            broker_exchange=broker_exchange,
            notes=notes,
            fee_paid_usd=fee_paid_usd,
            opened_at=now_iso,
        )
        # Deduct cash if available
        self.db.update_real_balance(-(pos_size + fee_paid_usd))
        # Log trade in unified trade_log
        self.db.add_trade_log_entry(
            position_id=pos_id,
            ticker=ticker,
            action="OPEN",
            price=entry_price,
            quantity=units,
            pnl_usd=0.0,
            pnl_pct=0.0,
            notes=notes or f"Real Buy on {broker_exchange}",
            portfolio_type="REAL",
        )
        logger.info(f"Opened REAL position {pos_id}: {units} {ticker} @ ${entry_price} on {broker_exchange}")
        return pos_id

    def close_real_position(
        self,
        identifier: str,
        exit_price: float,
        notes: Optional[str] = None,
        fee_paid_usd: float = 0.0,
    ) -> bool:
        """
        Closes an open real position by position_id or ticker.
        """
        open_real = self.db.get_open_real_positions()
        target = None
        for p in open_real:
            if p["position_id"] == identifier or p["ticker"].upper() == identifier.upper():
                target = p
                break
        if not target:
            logger.warning(f"No open real position found for identifier: {identifier}")
            return False
            
        units = target["units"]
        entry = target["entry_price"]
        pos_id = target["position_id"]
        ticker = target["ticker"]
        
        gross_pnl = (exit_price - entry) * units
        net_pnl = gross_pnl - fee_paid_usd
        pnl_pct = ((exit_price - entry) / entry * 100.0) if entry > 0 else 0.0
        now_iso = datetime.now(timezone.utc).isoformat()
        
        success = self.db.close_real_position(
            position_id=pos_id,
            exit_price=exit_price,
            realized_pnl_usd=net_pnl,
            realized_pnl_pct=pnl_pct,
            fee_paid_usd=fee_paid_usd,
            notes=notes,
            closed_at=now_iso,
        )
        if success:
            # Add proceeds back to real available cash
            self.db.update_real_balance((units * exit_price) - fee_paid_usd)
            self.db.add_trade_log_entry(
                position_id=pos_id,
                ticker=ticker,
                action="CLOSE",
                price=exit_price,
                quantity=units,
                pnl_usd=net_pnl,
                pnl_pct=pnl_pct,
                notes=notes or "Real Position Exit",
                portfolio_type="REAL",
            )
            logger.info(f"Closed REAL position {pos_id}: {ticker} @ ${exit_price}, Net PnL: ${net_pnl:.2f}")
        return success

    def set_real_cash_balance(self, cash: float) -> float:
        """Set or update available real cash balance."""
        return self.db.set_real_cash(cash)

    def get_equity_curve(self, days: int = 90) -> List[dict]:
        """
        Get equity curve from history.
        """
        try:
            return self.db.get_portfolio_equity_history(days=days)
        except AttributeError:
            logger.warning("get_portfolio_equity_history not implemented in DB.")
            return []

    def record_daily_snapshot(self, portfolio_type: str = "PAPER"):
        """
        Calculate and record portfolio snapshot.
        """
        summary = self.get_portfolio_summary(portfolio_type=portfolio_type)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        try:
            self.db.record_portfolio_equity(
                date=date_str,
                total_equity=summary["total_equity"],
                cash=summary["available_cash"],
                invested=summary["total_invested"],
                daily_pnl=0.0,
                daily_pnl_pct=0.0,
                open_positions_count=summary["open_positions_count"],
                cumulative_win_rate=summary["win_rate"]
            )
            logger.info(f"Recorded daily snapshot ({portfolio_type}) for {date_str}: Equity=${summary['total_equity']:.2f}")
        except AttributeError:
            logger.warning("record_portfolio_equity not implemented in DB.")

    def calculate_risk_exposure(self, portfolio_type: str = "PAPER") -> dict:
        """
        Calculate risk across all open positions for given portfolio type.
        """
        p_type = portfolio_type.upper()
        details = self.get_open_positions_detail(portfolio_type=p_type)
        summary = self.get_portfolio_summary(portfolio_type=p_type)
        total_equity = summary["total_equity"]
        
        total_risk_usd = 0.0
        per_position_risk = {}
        class_counts = {}
        
        for pos in details:
            entry = pos["entry_price"]
            sl = pos["stop_loss"]
            units = pos["units"]
            if sl:
                risk_usd = abs(entry - sl) * units
            else:
                risk_usd = 0.0
            
            per_position_risk[pos["symbol"]] = risk_usd
            total_risk_usd += risk_usd
            
            asset_class = pos["asset_class"]
            class_counts[asset_class] = class_counts.get(asset_class, 0) + 1
            
        total_risk_pct = (total_risk_usd / total_equity * 100.0) if total_equity > 0 else 0.0
        
        correlation_warnings = []
        for ac, count in class_counts.items():
            if count > 3:
                correlation_warnings.append(f"Висок риск от корелация: {count} позиции в клас {ac}")
                
        return {
            "portfolio_type": p_type,
            "total_risk_usd": total_risk_usd,
            "total_risk_pct": total_risk_pct,
            "per_position_risk": per_position_risk,
            "correlation_warnings": correlation_warnings
        }

    def calculate_position_size(self, entry_price: float, stop_loss: float, account_size: Optional[float] = None, 
                                risk_pct: Optional[float] = None, asset_class: str = 'crypto', tier: str = 'B') -> dict:
        """
        Calculate position sizing parameters based on asset profile.
        """
        if account_size is None:
            summary = self.get_portfolio_summary()
            account_size = summary["total_equity"]
            
        risk_pct = risk_pct or self.default_risk_pct
        risk_usd = account_size * (risk_pct / 100.0)
        
        profile = get_asset_profile(asset_class)
        tier_multiplier = get_tier_position_multiplier(tier)
        
        adjusted_risk_usd = risk_usd * tier_multiplier
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit == 0:
            units = 0.0
        else:
            units = adjusted_risk_usd / risk_per_unit
            
        position_value = units * entry_price
        max_position_value = account_size * (profile.max_position_pct / 100.0)
        
        if position_value > max_position_value:
            position_value = max_position_value
            units = position_value / entry_price
            adjusted_risk_usd = units * risk_per_unit
            
        return {
            "units": units,
            "position_value": position_value,
            "risk_usd": adjusted_risk_usd,
            "risk_pct_of_portfolio": (adjusted_risk_usd / account_size * 100.0) if account_size else 0.0,
            "tier_multiplier": tier_multiplier,
            "max_position_value": max_position_value
        }

    def get_performance_by_setup_type(self) -> Dict[str, dict]:
        """
        Group performance by setup type.
        """
        try:
            return self.db.get_portfolio_performance_stats()
        except AttributeError:
            logger.warning("get_portfolio_performance_stats not implemented in DB.")
            return {}

    def format_portfolio_telegram(self, portfolio_type: str = "REAL") -> str:
        """
        Format a comprehensive Telegram HTML message for portfolio.
        """
        p_type = portfolio_type.upper()
        summary = self.get_portfolio_summary(portfolio_type=p_type)
        details = self.get_open_positions_detail(portfolio_type=p_type)
        risk = self.calculate_risk_exposure(portfolio_type=p_type)
        
        u_pnl = summary['unrealized_pnl']
        u_pnl_pct = summary['unrealized_pnl_pct']
        emoji = "🟢" if u_pnl >= 0 else "🔴"
        sign = "+" if u_pnl >= 0 else ""
        
        mode_header = "🟢 <b>РЕАЛЕН КАПИТАЛ & АКТИВИ</b>" if p_type == "REAL" else "🧪 <b>ТЕСТОВ СИМУЛАТОР (PAPER)</b>"
        
        msg = f"💼 {mode_header}\n\n"
        msg += f"• Общ капитал: <b>${summary['total_equity']:,.2f}</b>\n"
        msg += f"• Свободен кеш: <b>${summary['available_cash']:,.2f}</b>\n"
        msg += f"• Инвестирани: <b>${summary['total_invested']:,.2f}</b>\n"
        msg += f"• Нереализиран P&L: {emoji} <b>{sign}${u_pnl:,.2f} ({sign}{u_pnl_pct:.2f}%)</b>\n"
        msg += f"• Реализиран P&L: <b>${summary['total_realized_pnl']:,.2f}</b>\n"
        msg += f"• Win Rate: <b>{summary['win_rate']:.1f}%</b>\n\n"
        
        msg += f"📊 <b>Отворени позиции ({len(details)})</b>\n"
        sorted_details = sorted(details, key=lambda x: x['unrealized_pnl'], reverse=True)
        for d in sorted_details[:5]:
            d_sign = "+" if d['unrealized_pnl'] >= 0 else ""
            d_emoji = "🟢" if d['unrealized_pnl'] >= 0 else "🔴"
            broker_str = f" [{d.get('broker_exchange')}]" if d.get('broker_exchange') else ""
            msg += f"  {d_emoji} {d['symbol']}{broker_str}: {d_sign}${d['unrealized_pnl']:.2f} ({d_sign}{d['unrealized_pnl_pct']:.1f}%)\n"
            
        if len(details) > 5:
            msg += f"  <i>и още {len(details) - 5} позиции...</i>\n"
            
        msg += f"\n⚠️ <b>Общ риск:</b> ${risk['total_risk_usd']:.2f} ({risk['total_risk_pct']:.2f}% от капитала)"
        return msg

    def format_risk_report_telegram(self, portfolio_type: str = "REAL") -> str:
        """
        Format a Telegram HTML message showing risk exposure.
        """
        p_type = portfolio_type.upper()
        risk = self.calculate_risk_exposure(portfolio_type=p_type)
        header = "🟢 <b>Риск Отчет: РЕАЛЕН КАПИТАЛ</b>" if p_type == "REAL" else "🧪 <b>Риск Отчет: ТЕСТОВ СИМУЛАТОР</b>"
        
        msg = f"🛡️ {header}\n\n"
        msg += f"• Максимален възможен спад (Risk USD): <b>${risk['total_risk_usd']:,.2f}</b>\n"
        msg += f"• Риск към портфолио: <b>{risk['total_risk_pct']:.2f}%</b>\n\n"
        
        if risk['per_position_risk']:
            msg += f"📊 <b>Риск по позиции:</b>\n"
            sorted_risks = sorted(risk['per_position_risk'].items(), key=lambda x: x[1], reverse=True)
            for sym, r in sorted_risks[:5]:
                msg += f"  • {sym}: <b>${r:.2f}</b>\n"
            if len(sorted_risks) > 5:
                msg += f"  <i>и още {len(sorted_risks) - 5}...</i>\n\n"
                
        if risk['correlation_warnings']:
            msg += f"⚠️ <b>Предупреждения:</b>\n"
            for w in risk['correlation_warnings']:
                msg += f"  • {w}\n"
        else:
            msg += f"✅ <i>Няма засечени предупреждения за корелация.</i>"
            
        return msg
