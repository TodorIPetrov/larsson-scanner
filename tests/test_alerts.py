import pytest
from src.alerts.formatter import format_single_alert, format_batch_alert, get_tradingview_link
from src.alerts.telegram import TelegramNotifier
from src.engine.smma import LarssonState


def test_tradingview_link():
    link_1d = get_tradingview_link("BINANCE:BTCUSDT", "1D")
    assert link_1d == "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT&interval=1D"

    link_4h = get_tradingview_link("BINANCE:ETHUSDT", "4H")
    assert link_4h == "https://www.tradingview.com/chart/?symbol=BINANCE:ETHUSDT&interval=240"


def test_single_alert_formatting():
    msg = format_single_alert(
        ticker="BTCUSDT",
        timeframe="1D",
        old_state=LarssonState.NEUTRAL,
        new_state=LarssonState.GOLD,
        price=65430.50,
        tv_symbol="BINANCE:BTCUSDT",
    )
    assert "BTCUSDT | 1D" in msg
    assert "🟡" in msg
    assert "⚪" in msg
    assert "$65,430.50" in msg
    assert "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT&interval=1D" in msg


def test_batch_alert_formatting():
    changes = [
        {
            "ticker": f"COIN{i}USDT",
            "timeframe": "1D",
            "old_state": LarssonState.NEUTRAL,
            "new_state": LarssonState.GOLD,
            "price": 100.0 + i,
            "tv_symbol": f"BINANCE:COIN{i}USDT",
        }
        for i in range(10)
    ]
    msg = format_batch_alert(changes)
    assert "Пазарен ъпдейт: 10 промени" in msg
    assert "COIN0USDT" in msg
    assert "COIN9USDT" in msg


def test_telegram_dry_run():
    notifier = TelegramNotifier()
    assert notifier.is_configured is False
    res = notifier.send_raw_message("<b>Test message</b>")
    assert res is True


def test_single_alert_formatting_with_sr():
    sr_data = {
        "s1": 64000.0,
        "s1_touches": 3,
        "s1_dist_pct": 5.88,
        "r1": 70000.0,
        "r1_touches": 4,
        "r1_dist_pct": 2.94,
        "context_flag": "IN_VALUE_RANGE",
        "context_desc": "В диапазон",
    }
    msg = format_single_alert(
        ticker="BTCUSDT",
        timeframe="1D",
        old_state=LarssonState.NEUTRAL,
        new_state=LarssonState.GOLD,
        price=68000.0,
        tv_symbol="BINANCE:BTCUSDT",
        sr_data=sr_data,
    )
    assert "S/R Нива (1D Macro):" in msg
    assert "🔴 Съпротива (R1): <code>$70,000.00</code> (+2.9% | 4 теста)" in msg
    assert "🟢 Подкрепа (S1): <code>$64,000.00</code> (-5.9% | 3 теста)" in msg

