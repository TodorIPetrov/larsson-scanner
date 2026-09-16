"""
Historical Data Manager for Institutional Backtesting.
Fetches, cleans, normalizes, and caches 5 years of multi-asset OHLCV market data.
Supports Binance (Crypto) and Yahoo Finance (US Equities, ETFs, Commodities).
"""

from datetime import datetime, timedelta, timezone
import logging
import os
import time
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "backtest_cache")

# Canonical multi-asset universe
DEFAULT_UNIVERSE = {
    "crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT"],
    "stocks": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA"],
    "commodities": ["GC=F", "SI=F", "CL=F"],
}


class BacktestDataManager:
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "LarssonBacktest/1.0"})

    def get_cache_path(self, symbol: str, timeframe: str = "1D") -> str:
        clean_sym = symbol.replace("=", "_").replace("^", "_")
        return os.path.join(self.cache_dir, f"{clean_sym}_{timeframe}.csv")

    def fetch_binance_history(
        self,
        symbol: str,
        start_date: str = "2021-09-01",
        end_date: Optional[str] = None,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        """
        Paginates Binance REST API to fetch multi-year historical candles.
        """
        interval_map = {"1D": "1d", "4H": "4h", "1W": "1w"}
        interval = interval_map.get(timeframe, "1d")

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start_ms = int(start_dt.timestamp() * 1000)

        end_ms = None
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_ms = int(end_dt.timestamp() * 1000)

        all_rows = []
        current_start = start_ms
        limit = 1000

        logger.info(f"Fetching Binance history for {symbol} [{timeframe}] from {start_date}...")

        while True:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "limit": limit,
            }
            if end_ms:
                params["endTime"] = end_ms

            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    logger.warning("Binance rate limit hit, sleeping 2s...")
                    time.sleep(2)
                    continue
                resp.raise_for_status()
                klines = resp.json()

                if not klines:
                    break

                for k in klines:
                    # kline: [open_time, open, high, low, close, volume, close_time, ...]
                    ts = datetime.fromtimestamp(k[0] / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
                    all_rows.append({
                        "date": ts,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })

                # If returned less than limit, reached the end
                if len(klines) < limit:
                    break

                # Advance next start time beyond last candle close
                last_open_time = klines[-1][0]
                current_start = last_open_time + (24 * 3600 * 1000 if timeframe == "1D" else 4 * 3600 * 1000)

                # Respect Binance public endpoint rate
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error fetching Binance klines for {symbol}: {e}")
                break

        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df

    def fetch_yfinance_history(
        self,
        symbol: str,
        start_date: str = "2021-09-01",
        end_date: Optional[str] = None,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        """
        Fetches historical data via Yahoo Finance for stocks, ETFs, and commodities.
        """
        logger.info(f"Fetching Yahoo Finance history for {symbol} from {start_date}...")
        try:
            raw_df = yf.download(
                tickers=symbol,
                start=start_date,
                end=end_date,
                interval="1d" if timeframe == "1D" else "1wk",
                auto_adjust=True,
                progress=False,
            )

            if raw_df.empty:
                logger.warning(f"No data returned from yfinance for {symbol}")
                return pd.DataFrame()

            # Handle MultiIndex columns if present
            if isinstance(raw_df.columns, pd.MultiIndex):
                raw_df.columns = raw_df.columns.get_level_values(0)

            df = pd.DataFrame()
            df["date"] = pd.to_datetime(raw_df.index).strftime("%Y-%m-%d")
            df["open"] = raw_df["Open"].values.astype(np.float64)
            df["high"] = raw_df["High"].values.astype(np.float64)
            df["low"] = raw_df["Low"].values.astype(np.float64)
            df["close"] = raw_df["Close"].values.astype(np.float64)
            df["volume"] = raw_df["Volume"].values.astype(np.float64) if "Volume" in raw_df else 0.0

            df = df.dropna(subset=["open", "high", "low", "close"]).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch yfinance data for {symbol}: {e}")
            return pd.DataFrame()

    def get_symbol_data(
        self,
        symbol: str,
        asset_class: str,
        start_date: str = "2021-09-01",
        timeframe: str = "1D",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Loads data from local disk cache if present; otherwise downloads and caches it.
        """
        cache_file = self.get_cache_path(symbol, timeframe)

        if not force_refresh and os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                if len(df) >= 200:
                    return df
            except Exception as e:
                logger.warning(f"Could not read cache for {symbol}: {e}")

        # Fetch fresh data
        if asset_class == "crypto":
            df = self.fetch_binance_history(symbol, start_date=start_date, timeframe=timeframe)
        else:
            df = self.fetch_yfinance_history(symbol, start_date=start_date, timeframe=timeframe)

        if not df.empty and len(df) >= 30:
            df.to_csv(cache_file, index=False)
            logger.info(f"Cached {len(df)} candles for {symbol} to {cache_file}")

        return df

    def load_universe(
        self,
        universe: Optional[Dict[str, List[str]]] = None,
        start_date: str = "2021-09-01",
        timeframe: str = "1D",
        force_refresh: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """
        Loads the entire multi-asset universe into memory.
        Returns: {symbol: DataFrame with columns ['date', 'open', 'high', 'low', 'close', 'volume']}
        """
        if universe is None:
            universe = DEFAULT_UNIVERSE

        datasets: Dict[str, pd.DataFrame] = {}

        for asset_class, symbols in universe.items():
            for sym in symbols:
                df = self.get_symbol_data(
                    symbol=sym,
                    asset_class=asset_class,
                    start_date=start_date,
                    timeframe=timeframe,
                    force_refresh=force_refresh,
                )
                if not df.empty and len(df) >= 150:
                    datasets[sym] = df
                else:
                    logger.warning(f"Skipping {sym}: insufficient data ({len(df)} candles)")

        logger.info(f"Successfully loaded {len(datasets)} assets for backtesting.")
        return datasets

    @staticmethod
    def extract_unified_calendar(datasets: Dict[str, pd.DataFrame]) -> List[str]:
        """
        Returns a chronologically sorted list of all unique dates present across all assets.
        """
        all_dates = set()
        for df in datasets.values():
            all_dates.update(df["date"].tolist())
        return sorted(list(all_dates))
