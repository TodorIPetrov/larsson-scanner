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
}


class YFinanceFetcher:
    def __init__(self, chunk_size: int = 50):
        self.chunk_size = chunk_size

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
                # yf.download with group_by='ticker'
                df = yf.download(
                    tickers=chunk_str,
                    interval=params["interval"],
                    period=params["period"],
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )

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
        """Fallback to fetch single ticker candles."""
        batch_res = self.fetch_batch([ticker], timeframe=timeframe)
        return batch_res.get(ticker)
