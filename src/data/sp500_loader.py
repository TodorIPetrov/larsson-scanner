"""
S&P 500 Constituents Loader.
Fetches and caches the complete 500+ US market components list.
"""

import json
import logging
import os
from typing import List, Optional
import pandas as pd

logger = logging.getLogger(__name__)

SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
LOCAL_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "sp500_tickers.json",
)


def load_sp500_tickers(refresh: bool = False, limit: Optional[int] = None) -> List[str]:
    """
    Returns list of S&P 500 tickers formatted for yfinance.
    Uses local cache if available unless refresh=True.
    """
    if not refresh and os.path.exists(LOCAL_CACHE_PATH):
        try:
            with open(LOCAL_CACHE_PATH, "r", encoding="utf-8") as f:
                tickers = json.load(f)
                if tickers and len(tickers) > 400:
                    return tickers[:limit] if limit else tickers
        except Exception as e:
            logger.warning(f"Could not read local SP500 cache: {e}")

    try:
        logger.info("Fetching fresh S&P 500 constituents from GitHub repository...")
        import io
        import requests
        resp = requests.get(SP500_URL, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        raw_tickers = df["Symbol"].dropna().tolist()

        # Format for yfinance (BRK.B -> BRK-B, BF.B -> BF-B)
        clean_tickers = [t.replace(".", "-").strip() for t in raw_tickers if t.strip()]

        # Cache locally
        os.makedirs(os.path.dirname(LOCAL_CACHE_PATH), exist_ok=True)
        with open(LOCAL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(clean_tickers, f, indent=2)

        logger.info(f"Cached {len(clean_tickers)} S&P 500 tickers locally.")
        return clean_tickers[:limit] if limit else clean_tickers
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 list: {e}")
        # Fallback to core top 20
        return [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
            "JPM", "V", "LLY", "WMT", "XOM", "UNH", "MA", "PG", "JNJ", "COST",
            "HD", "ABBV"
        ][:limit]
