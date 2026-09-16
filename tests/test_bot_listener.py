import pytest
from src.alerts.bot_listener import TelegramCommandListener
from src.alerts.telegram import TelegramNotifier
from src.engine.smma import LarssonState
from src.storage.database import Database


def test_command_listener_replies(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("AAPL", "us_stocks", "NASDAQ:AAPL"),
    ])
    db.update_state("BTCUSDT", "1D", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 70000.0)
    db.update_state("AAPL", "1D", 7.0, 8.0, 9.0, 10.0, LarssonState.BLUE, 220.0)

    listener = TelegramCommandListener(db=db)

    # Test /status reply
    status_text = listener.handle_status()
    assert "Пазарен Баланс" in status_text
    assert "Gold" in status_text
    assert "Blue" in status_text

    # Test /gold reply
    gold_text = listener.handle_state_list("GOLD", "🟡")
    assert "BTCUSDT" in gold_text

    # Test /blue reply
    blue_text = listener.handle_state_list("BLUE", "🔵")
    assert "AAPL" in blue_text

    # Test timeframe filter
    db.update_state("BTCUSDT", "4H", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 70500.0)
    status_4h = listener.handle_status("4h")
    assert "[4H]" in status_4h

    gold_4h = listener.handle_state_list("GOLD", "🟡", "4h")
    assert "[4H]" in gold_4h
    assert "BTCUSDT" in gold_4h


def test_command_listener_advanced_commands(tmp_path):
    db_file = str(tmp_path / "test_adv.db")
    db = Database(db_file)
    db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("NVDA", "us_stocks", "NASDAQ:NVDA"),
        ("DECK", "us_stocks", "NYSE:DECK"),
    ])
    db.update_state("BTCUSDT", "1D", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 70000.0)
    db.upsert_trade_suggestion(
        ticker="BTCUSDT",
        timeframe="1D",
        action="SPOT_BUY",
        direction="LONG",
        setup_type="QUANTAMENTAL_ALPHA_BUY",
        entry_price=70000.0,
        stop_loss=66500.0,
        tp1=78000.0,
        tp2=95000.0,
        rr_ratio=2.29,
        score=95,
        tier="A+",
        reason_bg="Институционална алфа покупка",
        reason_en="Institutional Alpha Buy",
        fund_verdict="STRONG BUY",
        fair_value=110000.0,
        moat="Wide",
        quantamental_tag="INSTITUTIONAL_ALPHA",
    )

    db.update_state("DECK", "1D", 7.0, 8.0, 9.0, 10.0, LarssonState.BLUE, 77.50)
    db.upsert_trade_suggestion(
        ticker="DECK",
        timeframe="1D",
        action="WAIT",
        direction="NEUTRAL",
        setup_type="VALUE_TRAP_WARNING",
        entry_price=77.50,
        score=40,
        tier="NONE",
        reason_bg="Валуационен капан риск",
        reason_en="Value trap risk",
        fund_verdict="STRONG BUY",
        fair_value=175.0,
        moat="Wide",
        quantamental_tag="VALUE_TRAP_RISK",
    )

    listener = TelegramCommandListener(db=db)

    # 1. Test /analyze (or /a)
    analysis = listener.handle_analyze("BTCUSDT")
    assert "Анализ на BTCUSDT" in analysis
    assert "GOLD" in analysis
    assert "DCF Справедлива стойност" in analysis
    assert "Tier A+" in analysis

    # Test unknown ticker
    unknown = listener.handle_analyze("UNKNOWN123")
    assert "не е намерен" in unknown

    # 2. Test /alpha
    alpha_msg = listener.handle_alpha()
    assert "BTCUSDT" in alpha_msg
    assert "Tier A+" in alpha_msg

    # 3. Test /traps
    traps_msg = listener.handle_traps()
    assert "DECK" in traps_msg
    assert "Валуационни Капани" in traps_msg

    # 4. Test /calc
    calc_msg = listener.handle_calc(["BTCUSDT", "10000", "1"])
    assert "Калкулатор за Размер на Позицията" in calc_msg
    assert "BTCUSDT" in calc_msg
    assert "Препоръчителен брой" in calc_msg
    assert "Максимална загуба" in calc_msg

    # 5. Test /help contains new commands
    help_msg = listener.handle_help()
    assert "/analyze" in help_msg
    assert "/alpha" in help_msg
    assert "/traps" in help_msg
    assert "/calc" in help_msg
