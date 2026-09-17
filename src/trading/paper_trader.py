"""
Paper Trading Engine for Larsson Line Scanner (Spot Simulation).
Enables zero-risk simulated crypto trading with human-in-the-loop confirmation
via Telegram interactive inline buttons.
"""

from datetime import datetime, timezone, timedelta
import logging
import math
import time
from typing import Dict, List, Optional, Tuple

from src.alerts.formatter import get_tradingview_link
from src.alerts.telegram import TelegramNotifier
from src.storage.database import Database

logger = logging.getLogger(__name__)


def format_price_str(price: float) -> str:
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.5f}"


class PaperTrader:
    def __init__(
        self,
        db: Optional[Database] = None,
        notifier: Optional[TelegramNotifier] = None,
        config: Optional[dict] = None,
    ):
        self.db = db or Database()
        self.notifier = notifier or TelegramNotifier()
        self.config = (config or {}).get("trading", {})

        self.enabled = bool(self.config.get("enabled", True))
        self.initial_balance = float(self.config.get("initial_balance_usd", 10000.0))
        self.default_position_size = float(self.config.get("default_position_size_usd", 100.0))
        self.max_active_positions = int(self.config.get("max_active_positions", 5))
        self.proposal_ttl_minutes = int(self.config.get("proposal_ttl_minutes", 15))
        self.fee_pct = float(self.config.get("fee_pct", 0.1))
        self.btc_safety_filter = bool(self.config.get("btc_safety_filter", True))
        self.min_confluence_score = int(self.config.get("min_confluence_score", 60))
        self.allowed_tiers = self.config.get("allowed_tiers", ["A+", "A", "B"])

        # Initialize account in DB if empty
        self.db.get_paper_balance(initial_balance=self.initial_balance)

    def is_btc_bullish(self) -> bool:
        """Checks if BTCUSDT 1D state is non-bearish (not BLUE)."""
        row = self.db.get_current_state("BTCUSDT", "1D")
        if not row:
            return True
        return row["current_state"] != "BLUE"

    def handle_new_signal(
        self,
        ticker: str,
        timeframe: str,
        trade_suggestion: Optional[dict],
        current_price: float,
        tv_symbol: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Evaluates a new signal for a crypto ticker. If eligible, creates a Trade Proposal,
        stores it in DB, and dispatches an interactive Telegram alert.
        """
        if not self.enabled:
            return None

        if not trade_suggestion or trade_suggestion.get("action") != "SPOT_BUY":
            return None

        score = trade_suggestion.get("score", 0)
        tier = trade_suggestion.get("tier", "NONE")
        if score < self.min_confluence_score or tier not in self.allowed_tiers:
            logger.debug(f"[PaperTrader] Skipping {ticker}: score={score}, tier={tier} below threshold.")
            return None

        # Check if active position already exists
        existing_pos = self.db.get_open_paper_position_by_ticker(ticker)
        if existing_pos:
            logger.info(f"[PaperTrader] Position already open for {ticker}. Skipping.")
            return None

        # Check if pending proposal already exists
        pending = self.db.get_pending_proposals()
        for p in pending:
            if p["ticker"] == ticker:
                logger.info(f"[PaperTrader] Proposal already pending for {ticker}. Skipping.")
                return None

        # Check max active positions
        open_positions = self.db.get_open_paper_positions()
        if len(open_positions) >= self.max_active_positions:
            logger.info(f"[PaperTrader] Max active positions ({self.max_active_positions}) reached. Skipping.")
            return None

        # BTC safety check only for crypto assets
        is_crypto = ticker.endswith("USDT") or ticker.endswith("USDC")
        if is_crypto and self.btc_safety_filter and ticker != "BTCUSDT":
            if not self.is_btc_bullish():
                logger.info(f"[PaperTrader] BTC is in Bearish (BLUE) state on 1D. Skipping altcoin proposal {ticker}.")
                return None

        balance = self.db.get_paper_balance(initial_balance=self.initial_balance)
        pos_size_usd = self.default_position_size
        if balance["available_cash"] < pos_size_usd:
            logger.warning(f"[PaperTrader] Insufficient cash for {ticker}: {balance['available_cash']:.2f} < {pos_size_usd}")
            return None

        entry_price = float(trade_suggestion.get("entry_price") or current_price)
        if entry_price <= 0:
            return None

        stop_loss = trade_suggestion.get("stop_loss")
        tp1 = trade_suggestion.get("tp1")
        tp2 = trade_suggestion.get("tp2")
        reason = trade_suggestion.get("reason_bg") or trade_suggestion.get("setup_type", "Larsson Line Gold Setup")

        units = round(pos_size_usd / entry_price, 6 if entry_price < 10 else 4)
        risk_usd = round(abs(entry_price - stop_loss) * units, 2) if stop_loss else None

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.proposal_ttl_minutes)
        now_iso = now.isoformat()
        expires_at_iso = expires_at.isoformat()

        proposal_id = f"prop_{ticker}_{int(time.time())}"

        created = self.db.create_trade_proposal(
            proposal_id=proposal_id,
            ticker=ticker,
            timeframe=timeframe,
            action="BUY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            position_size_usd=pos_size_usd,
            units=units,
            risk_usd=risk_usd,
            tier=tier,
            score=score,
            reason=reason,
            created_at=now_iso,
            expires_at=expires_at_iso,
            status="PENDING",
        )

        if not created:
            return None

        msg_text, reply_markup = self.format_proposal_message(
            proposal_id=proposal_id,
            ticker=ticker,
            timeframe=timeframe,
            entry_price=entry_price,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            position_size_usd=pos_size_usd,
            units=units,
            tier=tier,
            score=score,
            reason=reason,
            expires_minutes=self.proposal_ttl_minutes,
            tv_symbol=tv_symbol,
        )

        message_id = self.notifier.send_message_with_markup(msg_text, reply_markup=reply_markup)
        if message_id:
            self.db.update_proposal_message_id(proposal_id, message_id)

        logger.info(f"[PaperTrader] Created trade proposal {proposal_id} for {ticker} (msg_id={message_id})")
        return {
            "proposal_id": proposal_id,
            "ticker": ticker,
            "entry_price": entry_price,
            "position_size_usd": pos_size_usd,
        }

    def format_proposal_message(
        self,
        proposal_id: str,
        ticker: str,
        timeframe: str,
        entry_price: float,
        stop_loss: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        position_size_usd: float,
        units: float,
        tier: str,
        score: int,
        reason: str,
        expires_minutes: int,
        tv_symbol: Optional[str] = None,
    ) -> Tuple[str, dict]:
        """Generates HTML text and inline keyboard markup for a proposal."""
        tv_sym = tv_symbol or f"BINANCE:{ticker}"
        tv_url = get_tradingview_link(tv_sym, timeframe)

        p_str = format_price_str(entry_price)
        sl_pct = f"-{round(abs(entry_price - stop_loss) / entry_price * 100, 1)}%" if stop_loss else "N/A"
        sl_str = f"{format_price_str(stop_loss)} ({sl_pct})" if stop_loss else "Няма зададен"

        tp1_pct = f"+{round((tp1 - entry_price) / entry_price * 100, 1)}%" if tp1 else ""
        tp1_str = f"{format_price_str(tp1)} ({tp1_pct})" if tp1 else "Няма"

        tp2_pct = f"+{round((tp2 - entry_price) / entry_price * 100, 1)}%" if tp2 else ""
        tp2_str = f"{format_price_str(tp2)} ({tp2_pct})" if tp2 else "Няма"

        tier_badge = "🏆 Tier A+" if tier == "A+" else ("🥇 Tier A" if tier == "A" else f"🥈 Tier {tier}")

        is_crypto = ticker.endswith("USDT") or ticker.endswith("USDC")
        asset_label = "CRYPTO" if is_crypto else "АКЦИЯ / СУРОВИНА"
        asset_emoji = "🪙" if is_crypto else "🏛️"
        units_label = ticker.replace('USDT', '').replace('USDC', '') if is_crypto else "бр."

        text = (
            f"🚨 <b>{asset_emoji} ПРЕДЛОЖЕНИЕ ЗА ПОКУПКА ({asset_label})</b>\n\n"
            f"• Актив: <a href=\"{tv_url}\"><b>{ticker}</b></a> [{timeframe}]\n"
            f"• Ранг / Скор: <b>{tier_badge}</b> | Confluence: <b>{score}/100</b>\n"
            f"• Входна цена: <code>{p_str}</code>\n"
            f"• Размер на сделката: <b>${position_size_usd:.2f}</b> (~{units} {units_label})\n"
            f"• 🛑 Stop-Loss: <code>{sl_str}</code>\n"
            f"• 🎯 Take-Profit 1: <code>{tp1_str}</code>\n"
        )
        if tp2:
            text += f"• 🎯 Take-Profit 2: <code>{tp2_str}</code>\n"

        text += (
            f"\n💡 <i>Логика: {reason}</i>\n\n"
            f"⏳ <i>Валидност на предложението: {expires_minutes} минути.</i>\n"
            f"<i>Натиснете бутон за изпълнение в симулатора:</i>"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": f"✅ Потвърди BUY (${position_size_usd:.0f})", "callback_data": f"trade:approve:{proposal_id}"},
                    {"text": "❌ Откажи", "callback_data": f"trade:reject:{proposal_id}"},
                ]
            ]
        }
        return text, reply_markup

    def approve_proposal(self, proposal_id: str, chat_id: Optional[str] = None) -> dict:
        """
        User clicked 'Approve'. Validates balance, opens paper position,
        updates status, and edits the Telegram message to reflect approval.
        """
        self.db.expire_old_proposals()

        row = self.db.get_proposal(proposal_id)
        if not row:
            return {"success": False, "error": "Предложението не беше намерено."}

        status = row["status"]
        if status != "PENDING":
            return {"success": False, "error": f"Предложението вече е със статус: {status}."}

        ticker = row["ticker"]
        pos_size = row["position_size_usd"]
        entry_price = row["entry_price"]
        units = row["units"]
        stop_loss = row["stop_loss"]
        tp1 = row["tp1"]
        tp2 = row["tp2"]
        msg_id = row["message_id"]

        bal = self.db.get_paper_balance(initial_balance=self.initial_balance)
        fee_entry = round(pos_size * (self.fee_pct / 100.0), 4)
        total_required = pos_size + fee_entry

        if bal["available_cash"] < total_required:
            return {"success": False, "error": f"Недостатъчен свободен баланс (${bal['available_cash']:.2f} < ${total_required:.2f})."}

        open_positions = self.db.get_open_paper_positions()
        if len(open_positions) >= self.max_active_positions:
            return {"success": False, "error": f"Достигнат е лимитът от {self.max_active_positions} отворени позиции."}

        now_iso = datetime.now(timezone.utc).isoformat()
        position_id = f"pos_{ticker}_{int(time.time())}"

        self.db.update_paper_balance(-total_required, initial_balance=self.initial_balance)

        self.db.open_paper_position(
            position_id=position_id,
            ticker=ticker,
            entry_price=entry_price,
            units=units,
            position_size_usd=pos_size,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            opened_at=now_iso,
            proposal_id=proposal_id,
            fee_paid_usd=fee_entry,
        )

        self.db.update_proposal_status(proposal_id, "APPROVED", responded_at=now_iso)

        if msg_id:
            p_str = format_price_str(entry_price)
            updated_text = (
                f"✅ <b>ОДОБРЕНО И ИЗПЪЛНЕНО (Paper Spot)</b>\n\n"
                f"• Актив: <b>{ticker}</b>\n"
                f"• Купени: <b>{units}</b> единици на цена <code>{p_str}</code>\n"
                f"• Инвестирана сума: <b>${pos_size:.2f}</b> (Такса: ${fee_entry:.2f})\n"
                f"• 🛑 Stop-Loss: <code>{format_price_str(stop_loss) if stop_loss else 'Няма'}</code>\n"
                f"• 🎯 Take-Profit: <code>{format_price_str(tp1) if tp1 else 'Няма'}</code>\n\n"
                f"🟢 <i>Позицията е активна в симулатора. Следи се за SL/TP или /close.</i>"
            )
            self.notifier.edit_message_text(message_id=msg_id, text=updated_text, reply_markup=None, chat_id=chat_id)

        logger.info(f"[PaperTrader] Approved proposal {proposal_id}, opened position {position_id} for {ticker}")
        return {
            "success": True,
            "position_id": position_id,
            "ticker": ticker,
            "entry_price": entry_price,
            "units": units,
        }

    def reject_proposal(self, proposal_id: str, chat_id: Optional[str] = None) -> dict:
        """User clicked 'Reject'. Marks proposal as REJECTED and removes buttons."""
        row = self.db.get_proposal(proposal_id)
        if not row:
            return {"success": False, "error": "Предложението не беше намерено."}

        status = row["status"]
        if status != "PENDING":
            return {"success": False, "error": f"Предложението вече е със статус: {status}."}

        now_iso = datetime.now(timezone.utc).isoformat()
        self.db.update_proposal_status(proposal_id, "REJECTED", responded_at=now_iso)

        msg_id = row["message_id"]
        if msg_id:
            ticker = row["ticker"]
            updated_text = (
                f"❌ <b>ОТХВЪРЛЕНО ОТ ПОТРЕБИТЕЛЯ</b>\n\n"
                f"Предложението за покупка на <b>{ticker}</b> беше отхвърлено.\n"
                f"<i>Не са отворени позиции и балансът не е променян.</i>"
            )
            self.notifier.edit_message_text(message_id=msg_id, text=updated_text, reply_markup=None, chat_id=chat_id)

        logger.info(f"[PaperTrader] Rejected proposal {proposal_id} for {row['ticker']}")
        return {"success": True, "ticker": row["ticker"]}

    def evaluate_open_positions(
        self,
        prices: Dict[str, float],
        states: Optional[Dict[str, str]] = None,
    ) -> List[dict]:
        """
        Checks all open positions against latest market prices and indicator states.
        Triggers Stop-Loss, Take-Profit 1, Take-Profit 2, or Signal Exit (BLUE).
        """
        closed_events = []
        open_positions = self.db.get_open_paper_positions()
        if not open_positions:
            return closed_events

        states = states or {}

        for pos in open_positions:
            pos_id = pos["position_id"]
            ticker = pos["ticker"]
            entry_price = pos["entry_price"]
            units = pos["units"]
            pos_size = pos["position_size_usd"]
            stop_loss = pos["stop_loss"]
            tp1 = pos["tp1"]
            tp2 = pos["tp2"]

            current_price = prices.get(ticker)
            if not current_price or current_price <= 0:
                continue

            current_state = states.get(ticker)

            exit_reason = None
            exit_price = current_price

            if stop_loss and current_price <= stop_loss:
                exit_reason = "STOP_LOSS"
                exit_price = stop_loss
            elif tp2 and current_price >= tp2:
                exit_reason = "TAKE_PROFIT_2"
                exit_price = tp2
            elif tp1 and current_price >= tp1:
                exit_reason = "TAKE_PROFIT_1"
                exit_price = tp1
            elif current_state == "BLUE":
                exit_reason = "SIGNAL_BLUE"
                exit_price = current_price

            if exit_reason:
                closed = self._execute_position_close(
                    position=pos,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                )
                if closed:
                    closed_events.append(closed)

        return closed_events

    def _execute_position_close(
        self,
        position: dict,
        exit_price: float,
        exit_reason: str,
    ) -> Optional[dict]:
        """Calculates realized PnL, updates DB, credits cash, and notifies Telegram."""
        pos_id = position["position_id"]
        ticker = position["ticker"]
        entry_price = position["entry_price"]
        units = position["units"]
        pos_size = position["position_size_usd"]

        gross_proceeds = round(units * exit_price, 4)
        fee_exit = round(gross_proceeds * (self.fee_pct / 100.0), 4)
        net_proceeds = round(gross_proceeds - fee_exit, 4)

        realized_pnl_usd = round(net_proceeds - pos_size, 2)
        realized_pnl_pct = round((realized_pnl_usd / pos_size) * 100.0, 2)

        now_iso = datetime.now(timezone.utc).isoformat()

        self.db.update_paper_balance(net_proceeds, initial_balance=self.initial_balance)

        self.db.close_paper_position(
            position_id=pos_id,
            exit_price=exit_price,
            realized_pnl_usd=realized_pnl_usd,
            realized_pnl_pct=realized_pnl_pct,
            fee_paid_usd=fee_exit,
            exit_reason=exit_reason,
            closed_at=now_iso,
        )

        reason_labels = {
            "STOP_LOSS": "🛑 УДАРЕН СТОП-ЛОС (SL)",
            "TAKE_PROFIT_1": "🎯 ДОСТИГНАТ ТЕЙК-ПРОФИТ 1 (TP1)",
            "TAKE_PROFIT_2": "🚀 ДОСТИГНАТ ТЕЙК-ПРОФИТ 2 (TP2)",
            "SIGNAL_BLUE": "🔵 МЕЧИ СИГНАЛ ЗА ИЗХОД (Larsson Blue)",
            "MANUAL": "✋ РЪЧНО ЗАТВАРЯНЕ (/close)",
        }
        title = reason_labels.get(exit_reason, f"ЗАТВОРЕНА ПОЗИЦИЯ: {exit_reason}")
        pnl_emoji = "🟢" if realized_pnl_usd >= 0 else "🔴"
        pnl_sign = "+" if realized_pnl_usd >= 0 else ""

        msg = (
            f"{pnl_emoji} <b>{title}: {ticker}</b>\n\n"
            f"• Вход: <code>{format_price_str(entry_price)}</code> | Изход: <code>{format_price_str(exit_price)}</code>\n"
            f"• Реализиран PnL: <b>{pnl_sign}${realized_pnl_usd:,.2f} ({pnl_sign}{realized_pnl_pct}%)</b>\n"
            f"• Върнати средства в баланса: <b>${net_proceeds:,.2f}</b> (Такса: ${fee_exit:.2f})\n"
        )
        self.notifier.send_raw_message(msg)

        logger.info(f"[PaperTrader] Closed {pos_id} for {ticker}: exit={exit_price}, PnL=${realized_pnl_usd} ({realized_pnl_pct}%)")
        return {
            "position_id": pos_id,
            "ticker": ticker,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_usd": realized_pnl_usd,
            "pnl_pct": realized_pnl_pct,
        }

    def close_manually(self, ticker: str, current_price: Optional[float] = None) -> Tuple[bool, str]:
        """Manually closes an open paper position."""
        clean = ticker.upper().strip()
        pos = self.db.get_open_paper_position_by_ticker(clean)
        if not pos:
            return False, f"Няма активна отворена позиция за <b>{clean}</b>."

        if not current_price:
            state_row = self.db.get_current_state(clean, "4H") or self.db.get_current_state(clean, "1D")
            if state_row and state_row["last_price"]:
                current_price = state_row["last_price"]
            else:
                current_price = pos["entry_price"]

        res = self._execute_position_close(pos, current_price, "MANUAL")
        pnl_sign = "+" if res["pnl_usd"] >= 0 else ""
        return True, f"✅ Позицията за <b>{clean}</b> е затворена на цена <code>{format_price_str(current_price)}</code>. PnL: <b>{pnl_sign}${res['pnl_usd']:.2f} ({pnl_sign}{res['pnl_pct']}%)</b>."

    def get_portfolio_summary(self, price_lookup: Optional[Dict[str, float]] = None) -> str:
        """Generates comprehensive portfolio summary report for /portfolio."""
        price_lookup = price_lookup or {}
        bal = self.db.get_paper_balance(initial_balance=self.initial_balance)
        open_positions = self.db.get_open_paper_positions()

        cash = bal["available_cash"]
        initial = bal["initial_balance"]

        total_positions_val = 0.0
        unrealized_pnl_total = 0.0

        pos_lines = []
        for pos in open_positions:
            ticker = pos["ticker"]
            entry = pos["entry_price"]
            units = pos["units"]
            pos_size = pos["position_size_usd"]
            sl = pos["stop_loss"]
            tp1 = pos["tp1"]

            curr = price_lookup.get(ticker)
            if not curr:
                st = self.db.get_current_state(ticker, "4H") or self.db.get_current_state(ticker, "1D")
                curr = st["last_price"] if st else entry

            val = units * curr
            total_positions_val += val
            u_pnl_usd = val - pos_size
            u_pnl_pct = (u_pnl_usd / pos_size) * 100.0
            unrealized_pnl_total += u_pnl_usd

            sign = "+" if u_pnl_usd >= 0 else ""
            emoji = "🟢" if u_pnl_usd >= 0 else "🔴"
            pos_lines.append(
                f"• {emoji} <b>{ticker}</b>: <code>{format_price_str(curr)}</code> "
                f"(Вход: <code>{format_price_str(entry)}</code>)\n"
                f"  Стойност: <b>${val:.2f}</b> | PnL: <b>{sign}${u_pnl_usd:.2f} ({sign}{u_pnl_pct:.1f}%)</b>\n"
                f"  SL: <code>{format_price_str(sl) if sl else 'Няма'}</code> | TP: <code>{format_price_str(tp1) if tp1 else 'Няма'}</code>"
            )

        total_equity = cash + total_positions_val
        overall_pnl_usd = total_equity - initial
        overall_pnl_pct = (overall_pnl_usd / initial) * 100.0 if initial > 0 else 0.0
        overall_sign = "+" if overall_pnl_usd >= 0 else ""

        header = (
            f"💼 <b>Larsson Paper Spot Портфолио</b>\n\n"
            f"• Общ капитал (Equity): <b>${total_equity:,.2f}</b>\n"
            f"• Свободен USDT кеш: <b>${cash:,.2f}</b>\n"
            f"• В позиции: <b>${total_positions_val:,.2f}</b> ({len(open_positions)}/{self.max_active_positions})\n"
            f"• Общ резултат: <b>{overall_sign}${overall_pnl_usd:,.2f} ({overall_sign}{overall_pnl_pct:.2f}%)</b>\n\n"
        )

        if not pos_lines:
            body = "<i>В момента няма отворени позиции. Парите са 100% в кеш (USDT).</i>"
        else:
            body = "📌 <b>Активни Позиции:</b>\n" + "\n\n".join(pos_lines)

        footer = "\n\n<i>За затваряне на позиция: /close [тикер] | За история: /trades</i>"
        return header + body + footer

    def get_trade_history_summary(self) -> str:
        """Generates closed trades and performance metrics for /trades."""
        closed = self.db.get_closed_paper_positions(limit=30)
        if not closed:
            return "📜 <b>История на търговията:</b>\n\nВсе още няма завършени сделки в симулатора."

        total_trades = len(closed)
        winners = [t for t in closed if t["realized_pnl_usd"] > 0]
        losers = [t for t in closed if t["realized_pnl_usd"] < 0]

        win_rate = (len(winners) / total_trades * 100.0) if total_trades > 0 else 0.0
        total_pnl = sum(t["realized_pnl_usd"] for t in closed)
        total_fee = sum(t["fee_paid_usd"] or 0.0 for t in closed)

        pnl_sign = "+" if total_pnl >= 0 else ""
        emoji = "🟢" if total_pnl >= 0 else "🔴"

        header = (
            f"📜 <b>Larsson Paper Trading История ({total_trades} сделки)</b>\n\n"
            f"• Win Rate: <b>{win_rate:.1f}%</b> (🟢 {len(winners)} / 🔴 {len(losers)})\n"
            f"• Нетна реализирана печалба: {emoji} <b>{pnl_sign}${total_pnl:,.2f}</b>\n"
            f"• Платени такси (симулирани): <b>${total_fee:,.2f}</b>\n\n"
            f"<b>Последни сделки:</b>\n"
        )

        lines = []
        for t in closed[:10]:
            ticker = t["ticker"]
            pnl = t["realized_pnl_usd"]
            pct = t["realized_pnl_pct"]
            reason = t["exit_reason"]
            sign = "+" if pnl >= 0 else ""
            t_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"• {t_emoji} <b>{ticker}</b>: {sign}${pnl:.2f} ({sign}{pct:.1f}%) [{reason}]")

        return header + "\n".join(lines)
