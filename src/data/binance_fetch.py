"""
Binance Market Data Fetcher.
Retrieves OHLCV klines for cryptocurrency pairs via public REST endpoints.
No API key required for public market data.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import requests

logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"
TIMEFRAME_TO_BINANCE_INTERVAL = {
    "1D": "1d",
    "4H": "4h",
    "1W": "1w",
}


class BinanceFetcher:
    def __init__(self, base_url: str = BINANCE_BASE_URL, timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "LarssonLineScanner/1.0",
            "Accept": "application/json",
        })

    def get_top_usdt_pairs(self, limit: int = 100) -> List[str]:
        """
        Fetches the top USDT pairs by 24h trading volume from Binance.
        Excludes leveraged tokens (UP/DOWN/BEAR/BULL).
        """
        url = f"{self.base_url}/api/v3/ticker/24hr"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            pairs = []
            for item in data:
                symbol = item["symbol"]
                if symbol.endswith("USDT"):
                    # Filter out leveraged and special tokens
                    if any(x in symbol for x in ["UPUSDT", "DOWNUSDT", "BEARUSDT", "BULLUSDT"]):
                        continue
                    volume = float(item.get("quoteVolume", 0.0))
                    pairs.append((symbol, volume))

            # Sort descending by 24h quote volume
            pairs.sort(key=lambda x: x[1], reverse=True)
            return [p[0] for p in pairs[:limit]]
        except Exception as e:
            logger.error(f"Failed to fetch top USDT pairs: {e}")
            return []

    def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 180,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """
        Fetches OHLCV candles for a given symbol and timeframe.
        Returns:
            Tuple of (high_array, low_array, close_array, latest_price)
            or None if request fails.
        """
        interval = TIMEFRAME_TO_BINANCE_INTERVAL.get(timeframe)
        if not interval:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        url = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 429:
                logger.warning(f"Binance rate limit (429) hit when fetching {symbol}")
                return None
            resp.raise_for_status()
            raw_klines = resp.json()

            if not raw_klines or len(raw_klines) < 30:
                logger.warning(f"Insufficient candles for {symbol} ({len(raw_klines)} received)")
                return None

            # Binance kline structure:
            # 0: Open time, 1: Open, 2: High, 3: Low, 4: Close, 5: Volume, 6: Close time, ...
            highs = np.array([float(k[2]) for k in raw_klines], dtype=np.float64)
            lows = np.array([float(k[3]) for k in raw_klines], dtype=np.float64)
            closes = np.array([float(k[4]) for k in raw_klines], dtype=np.float64)
            latest_price = closes[-1]

            return highs, lows, closes, latest_price
        except Exception as e:
            logger.error(f"Error fetching klines for {symbol} [{timeframe}]: {e}")
            return None
