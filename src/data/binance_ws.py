"""
Binance WebSocket Client for Real-Time Candle Closes.
Subscribes to Binance kline multiplex streams and detects exact candle close
events (k.x == True) for sub-second Larsson Line recalculation and instant alerts.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional
import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_STREAM_URL = "wss://stream.binance.com:9443/stream"
BINANCE_WS_RAW_URL = "wss://stream.binance.com:9443/ws"

INTERVAL_MAP = {
    "1h": "4H",  # fallback if needed
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
}

TF_TO_WS_INTERVAL = {
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
}


class BinanceKlineWebSocket:
    """
    Asynchronous WebSocket listener for Binance klines.
    Monitors 1H, 4H, 1D, and 1W candle closes.
    """

    def __init__(
        self,
        symbols: List[str],
        timeframes: Optional[List[str]] = None,
        on_candle_close: Optional[Callable[[str, str, float, float, float], None]] = None,
    ):
        self.symbols = [s.upper() for s in symbols]
        self.timeframes = timeframes or ["1D", "4H"]
        self.on_candle_close = on_candle_close
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def build_stream_names(self) -> List[str]:
        """Builds stream names like btcusdt@kline_1h, ethusdt@kline_4h."""
        streams = []
        for sym in self.symbols:
            s_lower = sym.lower()
            for tf in self.timeframes:
                interval = TF_TO_WS_INTERVAL.get(tf, tf.lower())
                streams.append(f"{s_lower}@kline_{interval}")
        return streams

    def start(self):
        """Starts the WebSocket listener in a dedicated background thread."""
        if self._running:
            logger.warning("Binance WebSocket is already running.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_thread, daemon=True, name="BinanceWSThread")
        self._thread.start()
        logger.info(f"Binance WebSocket listener started for {len(self.symbols)} symbols across {self.timeframes} timeframes.")

    def stop(self):
        """Stops the WebSocket listener gracefully."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Binance WebSocket listener stopped.")

    def _run_thread(self):
        """Thread worker creating its own asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._listen_loop())
        finally:
            self._loop.close()

    async def _listen_loop(self):
        """Main connection and reconnection loop with backoff."""
        streams = self.build_stream_names()
        if not streams:
            logger.warning("No streams configured for Binance WebSocket.")
            return

        # Binance multiplex stream URL
        stream_query = "/".join(streams[:200])  # Connect first batch (up to 200 streams)
        url = f"{BINANCE_WS_STREAM_URL}?streams={stream_query}"

        backoff = 1.0
        while self._running:
            try:
                logger.info(f"Connecting to Binance WebSocket ({len(streams[:200])} streams)...")
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                ) as ws:
                    logger.info("Connected to Binance WebSocket stream successfully.")
                    backoff = 1.0  # Reset backoff upon successful connection

                    while self._running:
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            self._handle_message(raw_msg)
                        except asyncio.TimeoutError:
                            # Send manual ping to keep alive
                            try:
                                pong_waiter = await ws.ping()
                                await asyncio.wait_for(pong_waiter, timeout=10.0)
                            except Exception:
                                logger.warning("WebSocket ping timed out, reconnecting...")
                                break

            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"Binance WebSocket disconnected: {e}. Reconnecting in {backoff:.1f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _handle_message(self, raw_msg: str):
        """Parses kline events and checks for closed candles."""
        try:
            payload = json.loads(raw_msg)
            # Multiplex stream format: {"stream": "...", "data": {"e": "kline", ...}}
            data = payload.get("data", payload)
            if data.get("e") != "kline":
                return

            kline = data.get("k", {})
            is_closed = kline.get("x", False)

            if is_closed:
                ticker = kline.get("s", "").upper()
                raw_interval = kline.get("i", "")
                # Map back to standard timeframes (1h -> 1H, 4h -> 4H, 1d -> 1D, 1w -> 1W)
                tf_map = {"1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}
                timeframe = tf_map.get(raw_interval, raw_interval.upper())

                high = float(kline.get("h", 0.0))
                low = float(kline.get("l", 0.0))
                close = float(kline.get("c", 0.0))

                logger.info(f"⚡ [Binance WS] Candle Closed: {ticker} [{timeframe}] Close: ${close:,.2f}")

                if self.on_candle_close:
                    try:
                        self.on_candle_close(ticker, timeframe, high, low, close)
                    except Exception as err:
                        logger.error(f"Error in on_candle_close callback for {ticker} [{timeframe}]: {err}", exc_info=True)

        except Exception as e:
            logger.debug(f"Error parsing Binance WS message: {e}")
