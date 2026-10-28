"""
X (Twitter) Monitor & Social Sentiment Pipeline.
Automatically monitors investor accounts on X (such as NoLimits),
extracts stock/crypto ticker recommendations using regex and NLP heuristics,
and seamlessly integrates them into the Larsson Line scanner via AssetManager.
"""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple

import requests

from src.alerts.telegram import TelegramNotifier
from src.data.asset_manager import AssetManager
from src.data.binance_fetch import BinanceFetcher
from src.data.yfinance_fetch import YFinanceFetcher
from src.storage.database import Database

logger = logging.getLogger(__name__)

# Common non-ticker capital acronyms to ignore
IGNORED_WORDS: Set[str] = {
    "USD", "USDT", "USDC", "EUR", "BGN", "GBP", "JPY", "CHF", "CAD",
    "CEO", "CFO", "CTO", "COO", "IPO", "ATH", "ATL", "ETF", "GDP",
    "FED", "FOMC", "SEC", "AI", "PE", "EPS", "ROIC", "CAGR", "DD",
    "P/E", "NAV", "DCA", "ROI", "YTD", "Q1", "Q2", "Q3", "Q4",
    "USA", "EU", "UK", "OTC", "NYSE", "NASDAQ", "SPY", "QQQ", "DIA",
    "LONG", "SHORT", "BUY", "SELL", "HOLD", "STOP", "LOSS", "TP", "SL",
}


class XMonitor:
    def __init__(
        self,
        db: Optional[Database] = None,
        asset_manager: Optional[AssetManager] = None,
        notifier: Optional[TelegramNotifier] = None,
        config: Optional[dict] = None,
    ):
        self.db = db or Database()
        yf_fetcher = YFinanceFetcher()
        b_fetcher = BinanceFetcher()
        self.asset_manager = asset_manager or AssetManager(db=self.db, binance_fetcher=b_fetcher, yf_fetcher=yf_fetcher)
        self.notifier = notifier or TelegramNotifier()
        self.config = (config or {}).get("x_monitor", {})
        self.target_account = self.config.get("account", "NoLimits")
        self.bearer_token = self.config.get("bearer_token", "")

    @staticmethod
    def extract_tickers(text: str) -> List[str]:
        """
        Extracts stock and crypto tickers from tweet text using cashtags and keywords.
        Examples: '$NVDA', '$PLTR', 'купувам BABA', 'Long TSLA', 'акция AMD'
        """
        if not text:
            return []

        tickers = []

        # 1. Cashtags: $TICKER (e.g. $NVDA, $SOUN, $BMW.DE)
        cashtags = re.findall(r"\$([A-Za-z]{1,5}(?:\.[A-Za-z]{1,3})?)", text)
        for t in cashtags:
            clean_t = t.upper()
            if clean_t not in IGNORED_WORDS and clean_t not in tickers:
                tickers.append(clean_t)

        # 2. Keyword patterns: 'Long TICKER', 'Buy TICKER', 'купувам TICKER'
        kw_pattern = r"(?:long|buy|купувам|позиция|акция|акции|target)\s+([A-Za-z]{1,5}(?:\.[A-Za-z]{1,3})?)\b"
        kw_matches = re.findall(kw_pattern, text, re.IGNORECASE)
        for t in kw_matches:
            clean_t = t.upper()
            if clean_t not in IGNORED_WORDS and clean_t not in tickers:
                tickers.append(clean_t)

        return tickers

    def process_tweet(
        self,
        tweet_text: str,
        tweet_id: Optional[str] = None,
        source_account: Optional[str] = None,
    ) -> List[dict]:
        """
        Analyzes a tweet, extracts tickers, adds new ones to the scanner,
        records them in the database, and sends a notification.
        """
        source = source_account or self.target_account
        extracted = self.extract_tickers(tweet_text)
        results = []

        now_iso = datetime.now(timezone.utc).isoformat()

        for ticker in extracted:
            # Check if already processed from this tweet/account
            existing = self.db.add_x_recommendation(
                source_account=source,
                tweet_id=tweet_id,
                tweet_text=tweet_text,
                ticker=ticker,
                created_at=now_iso,
                added_to_scanner=1,
            )

            # Add to scanner asset universe if not already tracked
            ok, msg, info = self.asset_manager.add_asset(ticker, scan_now=True)

            status_item = {
                "ticker": ticker,
                "source": source,
                "tweet_id": tweet_id,
                "added_to_scanner": ok,
                "message": msg,
                "info": info,
            }
            results.append(status_item)

            if ok and info:
                logger.info(f"[XMonitor] Successfully added new stock pick from {source}: {ticker} ({info.get('name')})")
                # Send alert to Telegram
                try:
                    price_str = f"${info.get('price', 0.0):,.2f}"
                    st = info.get("state", "N/A")
                    st_emoji = "🟡" if st == "GOLD" else ("🔵" if st == "BLUE" else "⚪")
                    tg_msg = (
                        f"📢 <b>НОВО ПРЕДЛОЖЕНИЕ В X ({source})</b>\n\n"
                        f"• Тикер: <b>{ticker}</b> ({info.get('name', '')})\n"
                        f"• Клас актив: <code>{info.get('asset_class')}</code>\n"
                        f"• Текуща цена: <b>{price_str}</b>\n"
                        f"• Larsson Line състояние: {st_emoji} <b>{st}</b>\n"
                        f"• Източник текст: <i>\"{tweet_text[:120]}...\"</i>\n\n"
                        f"✅ Активът е добавен автоматично към системата за денонощно следене."
                    )
                    self.notifier.send_raw_message(tg_msg)
                except Exception as e:
                    logger.debug(f"Telegram notification error: {e}")

        return results

    def add_historical_recommendations(
        self,
        tickers: List[str],
        source_account: Optional[str] = None,
        notes: str = "Историческо предложение от NoLimits",
    ) -> Dict[str, list]:
        """
        Batch adds all known historical recommendations from NoLimits.
        """
        source = source_account or self.target_account
        summary = {"added": [], "already_tracked": [], "failed": []}
        now_iso = datetime.now(timezone.utc).isoformat()

        for raw_t in tickers:
            ticker = raw_t.strip().upper()
            if not ticker:
                continue

            # Record in x_recommendations table
            self.db.add_x_recommendation(
                source_account=source,
                tweet_id=None,
                tweet_text=notes,
                ticker=ticker,
                created_at=now_iso,
                added_to_scanner=1,
            )

            # Add to scanner
            ok, msg, info = self.asset_manager.add_asset(ticker, scan_now=True)
            if ok:
                summary["added"].append(info)
            elif "вече съществува" in msg.lower() or "already exists" in msg.lower():
                summary["already_tracked"].append(ticker)
            else:
                summary["failed"].append({"ticker": ticker, "reason": msg})

        return summary
