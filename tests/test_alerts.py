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
    assert "BTCUSDT" in msg and "| 1D" in msg
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


def test_dispatch_alerts_filtering(monkeypatch):
    notifier = TelegramNotifier()
    sent = []
    monkeypatch.setattr(notifier, "send_raw_message", lambda text: sent.append(text))

    alerts = [
        # Should be filtered out
        {"ticker": "SOLUSDT", "timeframe": "1D", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 140.0, "tv_symbol": "BINANCE:SOLUSDT"},
        # Should pass (GOLD)
        {"ticker": "ETHUSDT", "timeframe": "1D", "old_state": LarssonState.NEUTRAL, "new_state": LarssonState.GOLD, "price": 2600.0, "tv_symbol": "BINANCE:ETHUSDT"},
        # Should pass (priority BTC to BLUE)
        {"ticker": "BTCUSDT", "timeframe": "1D", "old_state": LarssonState.GOLD, "new_state": LarssonState.BLUE, "price": 62000.0, "tv_symbol": "BINANCE:BTCUSDT"},
        # Should pass (priority Metaplanet to NEUTRAL)
        {"ticker": "3350.T", "timeframe": "1D", "old_state": LarssonState.BLUE, "new_state": LarssonState.NEUTRAL, "price": 1100.0, "tv_symbol": "TSE:3350"},
    ]

    notifier.dispatch_alerts(alerts)
    # 3 messages should be sent (ETHUSDT, BTCUSDT, 3350.T)
    assert len(sent) == 3
    assert any("ETHUSDT" in m for m in sent)
    assert any("BTCUSDT" in m for m in sent)
    assert any("3350.T" in m for m in sent)
    assert not any("SOLUSDT" in m for m in sent)


def test_telegram_disabled_suppresses_messages(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    notifier = TelegramNotifier()
    assert notifier.enabled is False
    res = notifier.send_message_with_markup("<b>Test should not send</b>")
    assert res is None
    assert notifier.send_raw_message("<b>Test raw</b>") is False


