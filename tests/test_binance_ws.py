"""
Unit tests for Binance WebSocket client and candle close handler.
"""

import json
from unittest.mock import MagicMock
import pytest
from src.data.binance_ws import BinanceKlineWebSocket
from src.engine.smma import LarssonState
from src.scanner import LarssonScanner


def test_ws_stream_names():
    ws = BinanceKlineWebSocket(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=["1D", "4H"],
    )
    streams = ws.build_stream_names()
    assert "btcusdt@kline_1d" in streams
    assert "btcusdt@kline_4h" in streams
    assert "ethusdt@kline_1d" in streams
    assert "ethusdt@kline_4h" in streams
    assert len(streams) == 4


def test_ws_candle_close_event_triggered():
    callback = MagicMock()
    ws = BinanceKlineWebSocket(
        symbols=["BTCUSDT"],
        timeframes=["1D"],
        on_candle_close=callback,
    )

    # Event with closed candle (x = True)
    msg_closed = json.dumps({
        "stream": "btcusdt@kline_1d",
        "data": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "s": "BTCUSDT",
                "i": "1d",
                "h": "65000.5",
                "l": "63000.0",
                "c": "64500.0",
                "x": True,
            }
        }
    })

    ws._handle_message(msg_closed)
    callback.assert_called_once_with("BTCUSDT", "1D", 65000.5, 63000.0, 64500.0)


def test_ws_candle_not_closed_ignored():
    callback = MagicMock()
    ws = BinanceKlineWebSocket(
        symbols=["BTCUSDT"],
        timeframes=["1D"],
        on_candle_close=callback,
    )

    # Incomplete candle (x = False)
    msg_open = json.dumps({
        "stream": "btcusdt@kline_1d",
        "data": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "s": "BTCUSDT",
                "i": "1d",
                "h": "65000.5",
                "l": "63000.0",
                "c": "64500.0",
                "x": False,
            }
        }
    })

    ws._handle_message(msg_open)
    callback.assert_not_called()


def test_scanner_handle_candle_close():
    scanner = MagicMock()
    scanner.scan_crypto_symbols.return_value = {
        "total_scanned": 1,
        "state_changes": [],
    }

    # Test invoking handle_candle_close_event
    res = LarssonScanner.handle_candle_close_event(
        scanner,
        symbol="BTCUSDT",
        timeframe="1D",
        high=65000.0,
        low=63000.0,
        close=64500.0,
    )
    scanner.scan_crypto_symbols.assert_called_once_with(["BTCUSDT"], timeframe="1D", delay_s=0.0)
    assert res["total_scanned"] == 1
