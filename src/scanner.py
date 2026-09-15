"""
Larsson Line Market Scanner Core.
Orchestrates data fetching, SMMA indicator calculations, database state updates,
and alert dispatching across Crypto, US Stocks, International Stocks, Commodities, and Indices.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional
import yaml

from src.alerts.telegram import TelegramNotifier
from src.data.binance_fetch import BinanceFetcher
from src.data.sp500_loader import load_sp500_tickers
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series, LarssonState
from src.storage.database import Database

logger = logging.getLogger(__name__)


class LarssonScanner:
    def __init__(
        self,
        db: Optional[Database] = None,
        binance_fetcher: Optional[BinanceFetcher] = None,
        yf_fetcher: Optional[YFinanceFetcher] = None,
        notifier: Optional[TelegramNotifier] = None,
        config_path: str = "config/settings.yaml",
        assets_path: str = "config/assets.yaml",
        tv_mapping_path: str = "config/tv_mapping.json",
    ):
        self.db = db or Database()
        self.binance_fetcher = binance_fetcher or BinanceFetcher()
        self.yf_fetcher = yf_fetcher or YFinanceFetcher()
        self.notifier = notifier or TelegramNotifier()
        self.config = self._load_yaml(config_path)
        self.assets = self._load_yaml(assets_path)
        self.tv_mapping = self._load_json(tv_mapping_path)

    def _load_yaml(self, path: str) -> dict:
        data = {}
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            # Check for settings.local.yaml override
            if "settings.yaml" in path:
                local_path = path.replace("settings.yaml", "settings.local.yaml")
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as f:
                        local_data = yaml.safe_load(f) or {}
                        for k, v in local_data.items():
                            if isinstance(v, dict) and isinstance(data.get(k), dict):
                                data[k].update(v)
                            else:
                                data[k] = v
        except Exception as e:
            logger.warning(f"Could not load YAML config from {path}: {e}")
        return data

    def _load_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load JSON mapping from {path}: {e}")
            return {}

    def get_tv_symbol(self, ticker: str, asset_class: str) -> str:
        """Resolves the TradingView deep-link symbol for a given ticker."""
        if ticker in self.tv_mapping:
            return self.tv_mapping[ticker]
        if asset_class == "crypto":
            return f"BINANCE:{ticker}"
        elif asset_class in ["us_stocks", "intl_stocks", "ai_stocks"]:
            return f"NASDAQ:{ticker}"
        return ticker

    def scan_crypto_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1D",
        delay_s: float = 0.05,
    ) -> Dict:
        """
        Scans a list of crypto symbols on Binance for Larsson Line state transitions.
        """
        results = {
            "asset_class": "crypto",
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
        }

        min_warmup = self.config.get("scanner", {}).get("min_warmup_candles", 160)

        for sym in symbols:
            tv_symbol = self.get_tv_symbol(sym, "crypto")
            kline_data = self.binance_fetcher.fetch_klines(sym, timeframe, limit=min_warmup)
            if not kline_data:
                results["failed_count"] += 1
                continue

            highs, lows, closes, latest_price = kline_data
            v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
            current_state = states[-1]

            results["total_scanned"] += 1
            if current_state == LarssonState.GOLD:
                results["gold_count"] += 1
            elif current_state == LarssonState.BLUE:
                results["blue_count"] += 1
            else:
                results["neutral_count"] += 1

            # Update database and check for transition
            state_changed, old_state = self.db.update_state(
                ticker=sym,
                timeframe=timeframe,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                new_state=current_state,
                price=float(latest_price),
            )

            self.db.upsert_symbols([(sym, "crypto", tv_symbol)])

            if state_changed and old_state is not None:
                change_event = {
                    "ticker": sym,
                    "timeframe": timeframe,
                    "old_state": old_state,
                    "new_state": current_state,
                    "price": latest_price,
                    "tv_symbol": tv_symbol,
                }
                results["state_changes"].append(change_event)
                self.db.log_alert(
                    ticker=sym,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=current_state,
                    price=latest_price,
                    tv_symbol=tv_symbol,
                )

            if delay_s > 0:
                time.sleep(delay_s)

        if results["state_changes"]:
            self.notifier.dispatch_alerts(results["state_changes"])

        return results

    def scan_yfinance_assets(
        self,
        asset_class: str,
        tickers: Optional[List[str]] = None,
        timeframe: str = "1D",
    ) -> Dict:
        """
        Scans stocks, commodities, or indices using yfinance batch download.
        """
        if not tickers:
            configured = self.assets.get(asset_class, [])
            tickers = [item["ticker"] for item in configured if isinstance(item, dict) and "ticker" in item]

        results = {
            "asset_class": asset_class,
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
        }

        if not tickers:
            return results

        batch_data = self.yf_fetcher.fetch_batch(tickers, timeframe=timeframe)

        for sym in tickers:
            if sym not in batch_data:
                results["failed_count"] += 1
                continue

            highs, lows, closes, latest_price = batch_data[sym]
            v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
            current_state = states[-1]

            results["total_scanned"] += 1
            if current_state == LarssonState.GOLD:
                results["gold_count"] += 1
            elif current_state == LarssonState.BLUE:
                results["blue_count"] += 1
            else:
                results["neutral_count"] += 1

            tv_symbol = self.get_tv_symbol(sym, asset_class)

            state_changed, old_state = self.db.update_state(
                ticker=sym,
                timeframe=timeframe,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                new_state=current_state,
                price=float(latest_price),
            )

            self.db.upsert_symbols([(sym, asset_class, tv_symbol)])

            if state_changed and old_state is not None:
                change_event = {
                    "ticker": sym,
                    "timeframe": timeframe,
                    "old_state": old_state,
                    "new_state": current_state,
                    "price": latest_price,
                    "tv_symbol": tv_symbol,
                }
                results["state_changes"].append(change_event)
                self.db.log_alert(
                    ticker=sym,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=current_state,
                    price=latest_price,
                    tv_symbol=tv_symbol,
                )

        if results["state_changes"]:
            self.notifier.dispatch_alerts(results["state_changes"])

        return results

    def scan_sp500(self, limit: Optional[int] = None, timeframe: str = "1D") -> Dict:
        """Loads all S&P 500 constituents and scans them using batch download."""
        tickers = load_sp500_tickers(limit=limit)
        return self.scan_yfinance_assets(asset_class="us_stocks", tickers=tickers, timeframe=timeframe)

    def scan_all_assets(self, timeframe: str = "1D", crypto_limit: int = 50) -> Dict:
        """
        Runs comprehensive scan across all asset classes for a given timeframe.
        """
        combined = {
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
            "classes": {},
        }

        # 1. Crypto (always scanned on 1D, 4H, 1W)
        crypto_res = self.scan_top_crypto(limit=crypto_limit, timeframe=timeframe)
        combined["classes"]["crypto"] = crypto_res
        self._aggregate_stats(combined, crypto_res)

        # 2. Stocks, Commodities, Indices (only on 1D and 1W)
        if timeframe in ["1D", "1W"]:
            for a_class in ["us_stocks", "intl_stocks", "ai_stocks", "commodities", "indices"]:
                res = self.scan_yfinance_assets(asset_class=a_class, timeframe=timeframe)
                combined["classes"][a_class] = res
                self._aggregate_stats(combined, res)

        return combined

    def scan_top_crypto(self, limit: int = 50, timeframe: str = "1D") -> Dict:
        """Fetches top N USDT pairs by 24h volume and scans them."""
        symbols = self.binance_fetcher.get_top_usdt_pairs(limit=limit)
        return self.scan_crypto_symbols(symbols, timeframe=timeframe)

    @staticmethod
    def _aggregate_stats(combined: dict, part: dict):
        combined["total_scanned"] += part["total_scanned"]
        combined["gold_count"] += part["gold_count"]
        combined["blue_count"] += part["blue_count"]
        combined["neutral_count"] += part["neutral_count"]
        combined["failed_count"] += part["failed_count"]
        combined["state_changes"].extend(part["state_changes"])

    def handle_candle_close_event(
        self,
        symbol: str,
        timeframe: str,
        high: float,
        low: float,
        close: float,
    ) -> Optional[Dict]:
        """
        Handles an instant candle close event from Binance WebSocket.
        Recalculates SMMA ribbon and triggers alerts/dashboard sync if state transitioned.
        """
        logger.info(f"⚡ [WebSocket Trigger] Processing candle close for {symbol} [{timeframe}] @ ${close:,.2f}")
        res = self.scan_crypto_symbols([symbol], timeframe=timeframe, delay_s=0.0)
        if res.get("state_changes"):
            try:
                from src.dashboard.generator import export_dashboard_data
                from src.dashboard.git_sync import sync_dashboard_to_git

                export_dashboard_data(self.db)
                sync_dashboard_to_git()
            except Exception as e:
                logger.warning(f"Failed to sync dashboard after WS candle close: {e}")
        return res

