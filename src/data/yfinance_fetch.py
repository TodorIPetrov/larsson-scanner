"""
Yahoo Finance Batch Market Data Fetcher.
Retrieves historical and recent OHLCV candles for US Stocks, International Stocks,
Commodities, and Market Indices.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TIMEFRAME_TO_YF_PARAMS = {
    "1D": {"interval": "1d", "period": "2y"},
    "1W": {"interval": "1wk", "period": "5y"},
    "4H": {"interval": "4h", "period": "60d"},
}


class YFinanceFetcher:
    def __init__(self, chunk_size: int = 50, session=None):
        self.chunk_size = chunk_size
        if session is not None:
            self.session = session
        else:
            try:
                from curl_cffi.requests import Session as CurlSession
                self.session = CurlSession(impersonate="chrome")
            except Exception:
                self.session = None

    def fetch_batch(
        self,
        tickers: List[str],
        timeframe: str = "1D",
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """
        Fetches candles for multiple tickers simultaneously using yfinance batch download.
        Returns a dictionary: ticker -> (highs, lows, closes, latest_price).
        """
        if not tickers:
            return {}

        params = TIMEFRAME_TO_YF_PARAMS.get(timeframe)
        if not params:
            raise ValueError(f"Unsupported timeframe for yfinance: {timeframe}")

        results: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}

        # Process in chunks of chunk_size to avoid massive payloads
        for i in range(0, len(tickers), self.chunk_size):
            chunk = tickers[i : i + self.chunk_size]
            chunk_str = " ".join(chunk)

            try:
                # yf.download with group_by='ticker' and custom browser session
                download_kwargs = {
                    "tickers": chunk_str,
                    "interval": params["interval"],
                    "period": params["period"],
                    "group_by": "ticker",
                    "auto_adjust": True,
                    "progress": False,
                    "threads": True,
                }
                if self.session is not None:
                    download_kwargs["session"] = self.session

                df = yf.download(**download_kwargs)

                if df.empty:
                    logger.warning(f"Empty dataframe returned for batch: {chunk}")
                    continue

                for sym in chunk:
                    try:
                        if isinstance(df.columns, pd.MultiIndex):
                            if sym in df.columns.levels[0]:
                                sym_df = df[sym]
                            elif sym in df.columns.levels[1]:
                                sym_df = df.xs(sym, level=1, axis=1)
                            else:
                                continue
                        else:
                            sym_df = df

                        # Drop any rows where Close or High or Low is NaN
                        clean_df = sym_df.dropna(subset=["High", "Low", "Close"])
                        if len(clean_df) < 30:
                            continue

                        highs = clean_df["High"].to_numpy(dtype=np.float64)
                        lows = clean_df["Low"].to_numpy(dtype=np.float64)
                        closes = clean_df["Close"].to_numpy(dtype=np.float64)
                        latest_price = float(closes[-1])

                        results[sym] = (highs, lows, closes, latest_price)
                    except Exception as e:
                        logger.debug(f"Could not parse ticker {sym} from batch: {e}")
            except Exception as e:
                logger.error(f"Error executing yfinance batch download for {chunk}: {e}")

        return results

    def fetch_single(
        self,
        ticker: str,
        timeframe: str = "1D",
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """Fetch single ticker candles with chart API fallback."""
        batch_res = self.fetch_batch([ticker], timeframe=timeframe)
        res = batch_res.get(ticker)
        if res is not None:
            return res
        return self.fetch_via_chart_api(ticker, timeframe=timeframe)

    def fetch_weekly(
        self,
        ticker: str,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """Fetches Weekly (1wk, 5y) OHLCV data for a single ticker via yfinance.

        Returns (highs, lows, closes, latest_price) or None on failure.
        """
        return self.fetch_single(ticker, timeframe="1W")

    def fetch_4h(
        self,
        ticker: str,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """Fetches 4-Hour (4h, 60d) OHLCV data for a single ticker via yfinance.

        Returns (highs, lows, closes, latest_price) or None on failure.
        """
        return self.fetch_single(ticker, timeframe="4H")

    def fetch_via_chart_api(
        self,
        ticker: str,
        timeframe: str = "1D",
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
        """Direct Yahoo Finance chart API fetch using browser session."""
        range_param = "5y" if timeframe == "1W" else "2y"
        interval_param = "1wk" if timeframe == "1W" else "1d"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_param}&interval={interval_param}"

        try:
            session = self.session
            if session is None:
                from curl_cffi.requests import Session as CurlSession
                session = CurlSession(impersonate="chrome")
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return None
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            highs_raw = quotes.get("high", [])
            lows_raw = quotes.get("low", [])
            closes_raw = quotes.get("close", [])

            # Filter valid points
            valid = [(h, l, c) for h, l, c in zip(highs_raw, lows_raw, closes_raw) if h is not None and l is not None and c is not None]
            if len(valid) < 30:
                return None

            highs = np.array([v[0] for v in valid], dtype=np.float64)
            lows = np.array([v[1] for v in valid], dtype=np.float64)
            closes = np.array([v[2] for v in valid], dtype=np.float64)
            latest_price = float(closes[-1])
            return highs, lows, closes, latest_price
        except Exception as e:
            logger.debug(f"Direct chart API fetch failed for {ticker}: {e}")
            return None

