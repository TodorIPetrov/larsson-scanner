"""
Portfolio and Execution Manager for Institutional Backtesting.
Simulates realistic order execution, risk-based position sizing (1% risk per trade),
partial take-profits, trailing stops to breakeven, fees, slippage, and equity accounting.
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    direction: str          # 'LONG' or 'SHORT'
    entry_date: str
    entry_price: float
    units: float
    allocated_cash: float
    stop_loss: float
    initial_sl: float
    tp1: Optional[float]
    tp2: Optional[float]
    tp1_reached: bool = False
    setup_type: str = ""
    score: int = 0
    tier: str = "NONE"


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    units: float
    pnl: float
    return_pct: float
    exit_reason: str        # 'STOP_LOSS', 'TAKE_PROFIT_1', 'TAKE_PROFIT_2', 'STRUCTURAL_EXIT'
    fees_paid: float
    r_multiple: float
    setup_type: str


class PortfolioManager:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        risk_per_trade: float = 0.01,
        max_positions: int = 10,
        max_position_size_pct: float = 0.15,
        crypto_fee: float = 0.001,      # 0.1%
        stock_fee: float = 0.0005,      # 0.05%
        crypto_slippage: float = 0.001, # 10 bps
        stock_slippage: float = 0.0005, # 5 bps
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_positions = max_positions
        self.max_position_size_pct = max_position_size_pct
        self.crypto_fee = crypto_fee
        self.stock_fee = stock_fee
        self.crypto_slippage = crypto_slippage
        self.stock_slippage = stock_slippage

        self.open_positions: Dict[str, Position] = {}
        self.closed_trades: List[TradeRecord] = []
        self.equity_curve: List[Dict] = []

    def is_crypto(self, symbol: str) -> bool:
        return symbol.endswith("USDT") or "BTC" in symbol or "ETH" in symbol

    def get_fee_rate(self, symbol: str) -> float:
        return self.crypto_fee if self.is_crypto(symbol) else self.stock_fee

    def get_slippage_rate(self, symbol: str) -> float:
        return self.crypto_slippage if self.is_crypto(symbol) else self.stock_slippage

    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        """Computes current total equity = cash + mark-to-market value of open positions."""
        total = self.cash
        for sym, pos in self.open_positions.items():
            curr_p = current_prices.get(sym, pos.entry_price)
            if pos.direction == "LONG":
                total += pos.units * curr_p
            else:
                # Short position value: cash collateral + unrealized pnl
                unrealized = (pos.entry_price - curr_p) * pos.units
                total += pos.allocated_cash + unrealized
        return total

    def process_intrabar_exits(
        self,
        date: str,
        price_bars: Dict[str, Dict[str, float]],  # sym -> {'open': ..., 'high': ..., 'low': ..., 'close': ...}
        structural_exits: Dict[str, str],        # sym -> 'EXIT_LONG' or 'EXIT_SHORT'
    ):
        """
        Evaluates Stop Loss, TP1, TP2, and Structural Exits for each open position.
        """
        symbols_to_close = []

        for sym, pos in list(self.open_positions.items()):
            if sym not in price_bars:
                continue

            bar = price_bars[sym]
            b_open = bar["open"]
            b_high = bar["high"]
            b_low = bar["low"]
            b_close = bar["close"]
            fee_rate = self.get_fee_rate(sym)
            initial_risk = abs(pos.entry_price - pos.initial_sl) if pos.initial_sl else 1.0

            # -----------------------------------------------------------------
            # 1. LONG POSITION CHECKS
            # -----------------------------------------------------------------
            if pos.direction == "LONG":
                # Check Stop Loss hit
                if b_low <= pos.stop_loss:
                    exit_price = min(b_open, pos.stop_loss)  # Gap down realism
                    gross_pnl = (exit_price - pos.entry_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (exit_price - pos.entry_price) / initial_risk if initial_risk > 0 else -1.0

                    self.cash += (pos.units * exit_price) - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="LONG",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
                            exit_reason="STOP_LOSS",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

                # Check TP1 reached: scale out 50% and move Stop Loss to Breakeven
                if not pos.tp1_reached and pos.tp1 is not None and b_high >= pos.tp1:
                    units_to_sell = pos.units * 0.5
                    exit_price = pos.tp1
                    gross_pnl = (exit_price - pos.entry_price) * units_to_sell
                    fee = exit_price * units_to_sell * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (exit_price - pos.entry_price) / initial_risk if initial_risk > 0 else 1.0

                    self.cash += (units_to_sell * exit_price) - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="LONG",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=units_to_sell,
                            pnl=net_pnl,
                            return_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
                            exit_reason="TAKE_PROFIT_1",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    pos.units -= units_to_sell
                    pos.tp1_reached = True
                    # Lock in breakeven on remaining 50%
                    pos.stop_loss = max(pos.stop_loss, pos.entry_price)

                # Check TP2 reached: close remaining 50%
                if pos.tp1_reached and pos.tp2 is not None and b_high >= pos.tp2:
                    exit_price = pos.tp2
                    gross_pnl = (exit_price - pos.entry_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (exit_price - pos.entry_price) / initial_risk if initial_risk > 0 else 2.5

                    self.cash += (pos.units * exit_price) - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="LONG",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
                            exit_reason="TAKE_PROFIT_2",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

                # Check Structural Exit (Trend turned BLUE or S1 breached)
                if structural_exits.get(sym) == "EXIT_LONG":
                    exit_price = b_close
                    gross_pnl = (exit_price - pos.entry_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (exit_price - pos.entry_price) / initial_risk if initial_risk > 0 else 0.0

                    self.cash += (pos.units * exit_price) - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="LONG",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(exit_price - pos.entry_price) / pos.entry_price * 100.0,
                            exit_reason="STRUCTURAL_EXIT",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

            # -----------------------------------------------------------------
            # 2. SHORT POSITION CHECKS
            # -----------------------------------------------------------------
            elif pos.direction == "SHORT":
                # Check Stop Loss hit
                if b_high >= pos.stop_loss:
                    exit_price = max(b_open, pos.stop_loss)  # Gap up realism
                    gross_pnl = (pos.entry_price - exit_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (pos.entry_price - exit_price) / initial_risk if initial_risk > 0 else -1.0

                    self.cash += pos.allocated_cash + gross_pnl - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="SHORT",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(pos.entry_price - exit_price) / pos.entry_price * 100.0,
                            exit_reason="STOP_LOSS",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

                # Check TP1 reached
                if not pos.tp1_reached and pos.tp1 is not None and b_low <= pos.tp1:
                    units_to_cover = pos.units * 0.5
                    exit_price = pos.tp1
                    gross_pnl = (pos.entry_price - exit_price) * units_to_cover
                    fee = exit_price * units_to_cover * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (pos.entry_price - exit_price) / initial_risk if initial_risk > 0 else 1.0

                    collateral_returned = pos.allocated_cash * 0.5
                    pos.allocated_cash -= collateral_returned
                    self.cash += collateral_returned + gross_pnl - fee

                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="SHORT",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=units_to_cover,
                            pnl=net_pnl,
                            return_pct=(pos.entry_price - exit_price) / pos.entry_price * 100.0,
                            exit_reason="TAKE_PROFIT_1",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    pos.units -= units_to_cover
                    pos.tp1_reached = True
                    pos.stop_loss = min(pos.stop_loss, pos.entry_price)

                # Check TP2 reached
                if pos.tp1_reached and pos.tp2 is not None and b_low <= pos.tp2:
                    exit_price = pos.tp2
                    gross_pnl = (pos.entry_price - exit_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (pos.entry_price - exit_price) / initial_risk if initial_risk > 0 else 2.5

                    self.cash += pos.allocated_cash + gross_pnl - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="SHORT",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(pos.entry_price - exit_price) / pos.entry_price * 100.0,
                            exit_reason="TAKE_PROFIT_2",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

                # Check Structural Exit
                if structural_exits.get(sym) == "EXIT_SHORT":
                    exit_price = b_close
                    gross_pnl = (pos.entry_price - exit_price) * pos.units
                    fee = exit_price * pos.units * fee_rate
                    net_pnl = gross_pnl - fee
                    r_mult = (pos.entry_price - exit_price) / initial_risk if initial_risk > 0 else 0.0

                    self.cash += pos.allocated_cash + gross_pnl - fee
                    self.closed_trades.append(
                        TradeRecord(
                            symbol=sym,
                            direction="SHORT",
                            entry_date=pos.entry_date,
                            exit_date=date,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            units=pos.units,
                            pnl=net_pnl,
                            return_pct=(pos.entry_price - exit_price) / pos.entry_price * 100.0,
                            exit_reason="STRUCTURAL_EXIT",
                            fees_paid=fee,
                            r_multiple=round(r_mult, 2),
                            setup_type=pos.setup_type,
                        )
                    )
                    symbols_to_close.append(sym)
                    continue

        for sym in symbols_to_close:
            if sym in self.open_positions:
                del self.open_positions[sym]

    def execute_entries(
        self,
        date: str,
        signals: List,  # List[BacktestSignal]
        price_bars: Dict[str, Dict[str, float]],
    ):
        """
        Executes approved trade entries on bar Open with slippage and risk sizing.
        """
        available_slots = self.max_positions - len(self.open_positions)
        if available_slots <= 0 or not signals:
            return

        # Sort signals by Confluence Score descending, then R:R descending
        signals = sorted(signals, key=lambda s: (s.score, s.rr_ratio), reverse=True)

        current_closes = {sym: bar["close"] for sym, bar in price_bars.items()}
        total_equity = self.get_total_equity(current_closes)

        for sig in signals:
            if available_slots <= 0:
                break
            if sig.symbol in self.open_positions:
                continue
            if sig.symbol not in price_bars:
                continue

            bar = price_bars[sig.symbol]
            b_open = bar["open"]
            fee_rate = self.get_fee_rate(sig.symbol)
            slippage = self.get_slippage_rate(sig.symbol)

            # Execution price with realistic slippage
            if sig.action == "BUY_LONG":
                exec_price = b_open * (1.0 + slippage)
                direction = "LONG"
                sl = sig.stop_loss
            elif sig.action == "SELL_SHORT":
                exec_price = b_open * (1.0 - slippage)
                direction = "SHORT"
                sl = sig.stop_loss
            else:
                continue

            if sl is None:
                continue

            per_share_risk = abs(exec_price - sl)
            if per_share_risk <= 0:
                continue

            # 1% risk of current equity
            dollar_risk = total_equity * self.risk_per_trade
            desired_units = dollar_risk / per_share_risk

            # Cap position size by max_position_size_pct (e.g. 15% of total equity)
            max_notional = total_equity * self.max_position_size_pct
            max_units_by_notional = max_notional / exec_price
            units = min(desired_units, max_units_by_notional)

            cost = units * exec_price
            entry_fee = cost * fee_rate

            if self.cash >= (cost + entry_fee):
                self.cash -= (cost + entry_fee)
                self.open_positions[sig.symbol] = Position(
                    symbol=sig.symbol,
                    direction=direction,
                    entry_date=date,
                    entry_price=round(exec_price, 4),
                    units=round(units, 4),
                    allocated_cash=round(cost, 2),
                    stop_loss=round(sl, 4),
                    initial_sl=round(sl, 4),
                    tp1=sig.tp1,
                    tp2=sig.tp2,
                    setup_type=sig.setup_type,
                    score=sig.score,
                    tier=sig.tier,
                )
                available_slots -= 1

    def record_daily_equity(self, date: str, price_bars: Dict[str, Dict[str, float]]):
        """Records end-of-day portfolio balance and metrics."""
        current_closes = {sym: bar["close"] for sym, bar in price_bars.items()}
        total_equity = self.get_total_equity(current_closes)

        self.equity_curve.append({
            "date": date,
            "equity": round(total_equity, 2),
            "cash": round(self.cash, 2),
            "open_positions": len(self.open_positions),
            "realized_trades": len(self.closed_trades),
        })
