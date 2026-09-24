import time
from datetime import datetime, timezone, timedelta
import pytest
from src.alerts.bot_listener import TelegramCommandListener
from src.alerts.telegram import TelegramNotifier
from src.engine.smma import LarssonState
from src.storage.database import Database
from src.trading.paper_trader import PaperTrader


class MockNotifier(TelegramNotifier):
    def __init__(self):
        super().__init__(bot_token="mock_token", chat_id="12345")
        self.sent_messages = []
        self.edited_messages = []
        self.answered_callbacks = []

    def send_message_with_markup(self, text, reply_markup=None):
        msg_id = len(self.sent_messages) + 1
        self.sent_messages.append({"message_id": msg_id, "text": text, "reply_markup": reply_markup})
        return msg_id

    def send_raw_message(self, text, reply_markup=None):
        self.sent_messages.append({"text": text, "reply_markup": reply_markup})
        return True

    def edit_message_text(self, message_id, text, reply_markup=None, chat_id=None):
        self.edited_messages.append({"message_id": message_id, "text": text, "reply_markup": reply_markup})
        return True

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        self.answered_callbacks.append({"id": callback_query_id, "text": text, "show_alert": show_alert})
        return True


def test_paper_trading_db_methods(tmp_path):
    db_file = str(tmp_path / "test_db.db")
    db = Database(db_file)

    # Initial balance check
    bal = db.get_paper_balance(initial_balance=5000.0)
    assert bal["available_cash"] == 5000.0
    assert bal["initial_balance"] == 5000.0

    # Cash update
    new_bal = db.update_paper_balance(-200.0)
    assert new_bal == 4800.0

    # Proposals
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    exp_iso = (now + timedelta(minutes=15)).isoformat()

    db.create_trade_proposal(
        proposal_id="prop_1",
        ticker="BTCUSDT",
        timeframe="4H",
        action="BUY",
        entry_price=65000.0,
        stop_loss=62000.0,
        tp1=70000.0,
        tp2=75000.0,
        position_size_usd=100.0,
        units=0.001538,
        risk_usd=4.61,
        tier="A",
        score=75,
        reason="Bullish Momentum",
        created_at=now_iso,
        expires_at=exp_iso,
        status="PENDING",
    )

    p = db.get_proposal("prop_1")
    assert p is not None
    assert p["ticker"] == "BTCUSDT"
    assert p["status"] == "PENDING"

    pending = db.get_pending_proposals()
    assert len(pending) == 1

    # Update proposal message_id and status
    db.update_proposal_message_id("prop_1", 999)
    p_updated = db.get_proposal("prop_1")
    assert p_updated["message_id"] == 999

    db.update_proposal_status("prop_1", "APPROVED")
    assert db.get_proposal("prop_1")["status"] == "APPROVED"
    assert len(db.get_pending_proposals()) == 0

    # Open paper position
    db.open_paper_position(
        position_id="pos_1",
        ticker="BTCUSDT",
        entry_price=65000.0,
        units=0.001538,
        position_size_usd=100.0,
        stop_loss=62000.0,
        tp1=70000.0,
        tp2=75000.0,
        opened_at=now_iso,
        proposal_id="prop_1",
        fee_paid_usd=0.1,
    )

    open_pos = db.get_open_paper_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["ticker"] == "BTCUSDT"

    pos_btc = db.get_open_paper_position_by_ticker("BTCUSDT")
    assert pos_btc is not None

    # Close paper position
    db.close_paper_position(
        position_id="pos_1",
        exit_price=70000.0,
        realized_pnl_usd=7.69,
        realized_pnl_pct=7.69,
        fee_paid_usd=0.1,
        exit_reason="TAKE_PROFIT_1",
    )

    assert len(db.get_open_paper_positions()) == 0
    closed = db.get_closed_paper_positions()
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TAKE_PROFIT_1"
    assert closed[0]["realized_pnl_usd"] == 7.69


def test_paper_trader_flow(tmp_path):
    db_file = str(tmp_path / "trader_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    config = {
        "trading": {
            "enabled": True,
            "initial_balance_usd": 1000.0,
            "default_position_size_usd": 100.0,
            "max_active_positions": 2,
            "fee_pct": 0.1,
            "min_confluence_score": 50,
            "allowed_tiers": ["A+", "A", "B"],
            "btc_safety_filter": False,
        }
    }

    trader = PaperTrader(db=db, notifier=notifier, config=config)

    # 1. Generate Proposal
    res = trader.handle_new_signal(
        ticker="SOLUSDT",
        timeframe="4H",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 150.0,
            "stop_loss": 140.0,
            "tp1": 170.0,
            "tp2": 190.0,
            "score": 80,
            "tier": "A",
            "reason_bg": "Консолидация над S1 подкрепа",
        },
        current_price=150.0,
        tv_symbol="BINANCE:SOLUSDT",
    )

    assert res is not None
    prop_id = res["proposal_id"]
    assert len(notifier.sent_messages) == 1
    sent = notifier.sent_messages[0]
    assert "ПРЕДЛОЖЕНИЕ ЗА ПОКУПКА" in sent["text"]
    assert "SOLUSDT" in sent["text"]
    assert sent["reply_markup"] is not None
    assert f"trade:approve:{prop_id}" in str(sent["reply_markup"])

    # 2. Approve Proposal
    approve_res = trader.approve_proposal(prop_id, chat_id="12345")
    assert approve_res["success"] is True
    assert approve_res["ticker"] == "SOLUSDT"

    # Verify balance was deducted ($100 + $0.10 fee = $100.10)
    bal = db.get_paper_balance()
    assert round(bal["available_cash"], 2) == 899.90

    # Verify message was edited to show approved state
    assert len(notifier.edited_messages) == 1
    assert "ОДОБРЕНО И ИЗПЪЛНЕНО" in notifier.edited_messages[0]["text"]

    # 3. Position Evaluation: Take Profit hit
    closed = trader.evaluate_open_positions(prices={"SOLUSDT": 172.0})
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "TAKE_PROFIT_1"
    assert closed[0]["pnl_usd"] > 0

    # Verify cash was credited back with profit
    bal_after = db.get_paper_balance()
    assert bal_after["available_cash"] > 1000.0


def test_telegram_listener_interactive_callbacks(tmp_path):
    db_file = str(tmp_path / "listener_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(db=db, notifier=notifier, config={"trading": {"enabled": True, "initial_balance_usd": 1000.0}})
    listener = TelegramCommandListener(notifier=notifier, db=db, paper_trader=trader)

    # Generate a proposal
    res = trader.handle_new_signal(
        ticker="ETHUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 3000.0,
            "stop_loss": 2850.0,
            "tp1": 3300.0,
            "score": 75,
            "tier": "A",
            "reason_bg": "Larsson Gold Ribbon Breakout",
        },
        current_price=3000.0,
    )
    prop_id = res["proposal_id"]

    # Test unauthorized callback query
    unauth_update = {
        "callback_query": {
            "id": "cb_unauth",
            "from": {"id": 99999},  # Unauthorized
            "message": {"message_id": 1, "chat": {"id": 99999}},
            "data": f"trade:approve:{prop_id}",
        }
    }
    listener.process_update(unauth_update)
    assert len(notifier.answered_callbacks) == 1
    assert notifier.answered_callbacks[0]["show_alert"] is True
    assert "Нямате права" in notifier.answered_callbacks[0]["text"]

    # Proposal still pending
    assert db.get_proposal(prop_id)["status"] == "PENDING"

    # Test authorized approval
    auth_update = {
        "callback_query": {
            "id": "cb_auth",
            "from": {"id": 12345},  # Authorized
            "message": {"message_id": 1, "chat": {"id": 12345}},
            "data": f"trade:approve:{prop_id}",
        }
    }
    listener.process_update(auth_update)
    assert len(notifier.answered_callbacks) == 2
    assert "Покупката на ETHUSDT е потвърдена" in notifier.answered_callbacks[1]["text"]
    assert db.get_proposal(prop_id)["status"] == "APPROVED"

    # Test /portfolio command
    portfolio_text = trader.get_portfolio_summary()
    assert "ETHUSDT" in portfolio_text
    assert "Larsson Paper Spot Портфолио" in portfolio_text

    # Test /close ETHUSDT
    ok, close_msg = trader.close_manually("ETHUSDT", current_price=3100.0)
    assert ok is True
    assert "ETHUSDT" in close_msg
    assert "затворена" in close_msg

    # Test /trades command
    trades_text = trader.get_trade_history_summary()
    assert "ETHUSDT" in trades_text
    assert "100.0%" in trades_text


def test_paper_trader_partial_tp1_scale_out(tmp_path):
    db_file = str(tmp_path / "partial_tp_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 1000.0,
                "partial_take_profit": True,
                "default_position_size_usd": 100.0,
            }
        },
    )

    # 1. Proposal
    res = trader.handle_new_signal(
        ticker="SOLUSDT",
        timeframe="4H",
        trade_suggestion={
            "action": "SPOT_BUY",
            "entry_price": 150.0,
            "stop_loss": 140.0,
            "tp1": 170.0,
            "tp2": 200.0,
            "score": 85,
            "tier": "A+",
            "reason_bg": "Тест",
        },
        current_price=150.0,
    )
    assert res is not None
    prop_id = res["proposal_id"]

    # 2. Approve
    approve_res = trader.approve_proposal(prop_id, chat_id="12345")
    assert approve_res["success"] is True

    # Initial position: units = ~0.6667
    pos = db.get_open_paper_position_by_ticker("SOLUSDT")
    initial_units = pos["units"]
    assert initial_units > 0

    # 3. Price touches TP1 (170.0) -> Triggers partial 50% scale-out!
    events = trader.evaluate_open_positions(prices={"SOLUSDT": 170.0})
    assert len(events) == 1
    assert events[0]["exit_reason"] == "TAKE_PROFIT_1_PARTIAL"
    assert events[0]["pnl_usd"] > 0

    # 4. Verify position is STILL open with 50% units, SL at breakeven (150.0), and tp1 cleared
    pos_after = db.get_open_paper_position_by_ticker("SOLUSDT")
    assert pos_after is not None
    assert pos_after["status"] == "OPEN"
    assert abs(pos_after["units"] - (initial_units * 0.5)) < 0.001
    assert pos_after["stop_loss"] == 150.0  # Breakeven!
    assert pos_after["tp1"] is None

    # 5. Check trade log entry
    logs = db.get_trade_log_for_position(approve_res["position_id"])
    assert len(logs) == 1
    assert logs[0]["action"] == "PARTIAL_CLOSE"

    # 6. Price hits TP2 (200.0) -> Closes remaining 50%
    tp2_events = trader.evaluate_open_positions(prices={"SOLUSDT": 200.0})
    assert len(tp2_events) == 1
    assert tp2_events[0]["exit_reason"] == "TAKE_PROFIT_2"

    # Position is now fully CLOSED
    assert db.get_open_paper_position_by_ticker("SOLUSDT") is None


def test_paper_trading_leverage_3x_lifecycle(tmp_path):
    db_file = str(tmp_path / "leverage_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 1000.0,
                "partial_take_profit": True,
                "default_position_size_usd": 300.0,
            }
        },
    )

    # 1. Propose BTCUSDT setup with max_leverage=3
    res = trader.handle_new_signal(
        ticker="BTCUSDT",
        timeframe="4H",
        trade_suggestion={
            "action": "SPOT_BUY",
            "direction": "LONG",
            "entry_price": 60000.0,
            "stop_loss": 57000.0,
            "tp1": 66000.0,
            "tp2": 72000.0,
            "score": 85,
            "tier": "A+",
            "reason_bg": "Конфлуентен пробив",
            "max_leverage": 3,
            "recommended_leverage": 2,
        },
        current_price=60000.0,
    )
    assert res is not None
    prop_id = res["proposal_id"]

    # Verify Telegram message contains 1x, 2x, 3x interactive buttons
    assert len(notifier.sent_messages) == 1
    last_msg = notifier.sent_messages[-1]
    markup = last_msg["reply_markup"]
    assert "inline_keyboard" in markup
    buttons = markup["inline_keyboard"][0]
    callbacks = [b["callback_data"] for b in buttons]
    assert f"trade:approve:{prop_id}:1" in callbacks
    assert f"trade:approve:{prop_id}:2" in callbacks
    assert f"trade:approve:{prop_id}:3" in callbacks

    # 2. Approve with 3x leverage
    approve_res = trader.approve_proposal(prop_id, chat_id="12345", leverage=3)
    assert approve_res["success"] is True

    # Initial cash: $1000. Pos size: $300.
    # 3x isolated margin required: $300 / 3 = $100.
    # Entry fee: 300 * 0.001 = $0.30.
    # Balance should be approx 1000 - 100.30 = $899.70
    bal = db.get_paper_balance(initial_balance=1000.0)
    assert round(bal["available_cash"], 2) == 899.70

    # Verify open position DB record
    pos = db.get_open_paper_position_by_ticker("BTCUSDT")
    assert pos is not None
    assert pos["direction"] == "LONG"
    assert pos["leverage"] == 3
    assert pos["margin_usd"] == 100.0
    assert pos["notional_usd"] == 300.0
    assert pos["liquidation_price"] is not None
    assert pos["liquidation_price"] < 45000.0

    # 3. Portfolio summary should show 3x LONG tag and correct equity
    summary_text = trader.get_portfolio_summary()
    assert "3x LONG" in summary_text
    assert "BTCUSDT" in summary_text
    assert "Маржин: <b>$100.00</b>" in summary_text

    # 4. Price moves up from 60,000 to 66,000 (TP1 partial scale-out)
    events = trader.evaluate_open_positions(prices={"BTCUSDT": 66000.0})
    assert len(events) == 1
    assert events[0]["exit_reason"] == "TAKE_PROFIT_1_PARTIAL"
    # PnL on 50% = (66000 - 60000) * 0.0025 = +$15.00 (gross)
    assert events[0]["pnl_usd"] > 14.0


def test_short_position_lifecycle_and_liquidation(tmp_path):
    db_file = str(tmp_path / "short_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(
        db=db,
        notifier=notifier,
        config={
            "trading": {
                "enabled": True,
                "initial_balance_usd": 1000.0,
                "partial_take_profit": False,
                "default_position_size_usd": 200.0,
            }
        },
    )

    # 1. Propose SHORT setup with max_leverage=2
    res = trader.handle_new_signal(
        ticker="ETHUSDT",
        timeframe="4H",
        trade_suggestion={
            "action": "SHORT_2X_OPTIONAL",
            "direction": "SHORT",
            "entry_price": 3000.0,
            "stop_loss": 3200.0,
            "tp1": 2700.0,
            "tp2": 2500.0,
            "score": 75,
            "tier": "A",
            "reason_bg": "Мечи ретест",
            "max_leverage": 2,
            "recommended_leverage": 2,
        },
        current_price=3000.0,
    )
    assert res is not None
    prop_id = res["proposal_id"]

    # Verify buttons for SHORT: [🟢 Hedge 1x], [⚡ Short 2x]
    last_msg = notifier.sent_messages[-1]
    markup = last_msg["reply_markup"]
    buttons = markup["inline_keyboard"][0]
    labels = [b["text"] for b in buttons]
    assert any("1x" in l for l in labels)
    assert any("Short 2x" in l for l in labels)

    # 2. Approve with 2x leverage
    approve_res = trader.approve_proposal(prop_id, chat_id="12345", leverage=2)
    assert approve_res["success"] is True

    pos = db.get_open_paper_position_by_ticker("ETHUSDT")
    assert pos["direction"] == "SHORT"
    assert pos["leverage"] == 2
    assert pos["margin_usd"] == 100.0
    liq_price = pos["liquidation_price"]
    assert liq_price is not None
    assert liq_price > 3200.0  # liquidation price is higher than entry for short

    # 3. Test price rally that triggers liquidation
    # Liq price for 2x short is 3000 * 1.495 = 4485
    events = trader.evaluate_open_positions(prices={"ETHUSDT": 4500.0})
    assert len(events) == 1
    assert events[0]["exit_reason"] == "LIQUIDATION"
    # Realized loss on liquidation is 100% of margin
    assert events[0]["pnl_usd"] == -100.0
    assert events[0]["pnl_pct"] == -100.0

    # Position is closed
    assert db.get_open_paper_position_by_ticker("ETHUSDT") is None


def test_telegram_listener_parses_leverage_callback(tmp_path):
    db_file = str(tmp_path / "listener_lev_test.db")
    db = Database(db_file)
    notifier = MockNotifier()

    trader = PaperTrader(db=db, notifier=notifier, config={"trading": {"enabled": True, "initial_balance_usd": 1000.0}})
    listener = TelegramCommandListener(notifier=notifier, db=db, paper_trader=trader)

    # Propose
    res = trader.handle_new_signal(
        ticker="BTCUSDT",
        timeframe="1D",
        trade_suggestion={
            "action": "SPOT_BUY",
            "direction": "LONG",
            "entry_price": 65000.0,
            "stop_loss": 62000.0,
            "tp1": 70000.0,
            "score": 85,
            "tier": "A+",
            "reason_bg": "Breakout",
            "max_leverage": 3,
            "recommended_leverage": 2,
        },
        current_price=65000.0,
    )
    prop_id = res["proposal_id"]

    # Authorized user clicks "trade:approve:{prop_id}:3"
    auth_update = {
        "callback_query": {
            "id": "cb_lev3",
            "from": {"id": 12345},
            "message": {"message_id": 1, "chat": {"id": 12345}},
            "data": f"trade:approve:{prop_id}:3",
        }
    }
    listener.process_update(auth_update)
    assert len(notifier.answered_callbacks) == 1
    assert "3x левъридж" in notifier.answered_callbacks[0]["text"]
    assert "потвърдена" in notifier.answered_callbacks[0]["text"]

    # Verify DB position has leverage 3
    pos = db.get_open_paper_position_by_ticker("BTCUSDT")
    assert pos is not None
    assert pos["leverage"] == 3
