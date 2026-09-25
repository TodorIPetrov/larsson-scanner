"""
Asset Manager Module.
Provides centralized validation, metadata auto-detection, configuration synchronization,
and instant scanning for adding and removing assets across Crypto and Traditional markets.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple
import numpy as np
import requests
import yaml

from src.data.binance_fetch import BinanceFetcher
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series, LarssonState
from src.engine.sr_levels import analyze_sr_levels
from src.storage.database import Database

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS_YAML_PATH = os.path.join(PROJECT_ROOT, "config", "assets.yaml")
TV_MAPPING_PATH = os.path.join(PROJECT_ROOT, "config", "tv_mapping.json")
NAMES_MAPPING_PATH = os.path.join(PROJECT_ROOT, "config", "names_mapping.json")

VALID_ASSET_CLASSES = [
    "crypto",
    "us_stocks",
    "intl_stocks",
    "commodities",
    "indices",
    "ai_stocks",
    "crypto_stocks",
]

# Exchange code translation to TradingView exchange prefixes
EXCHANGE_TO_TV_PREFIX = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NASDAQGS": "NASDAQ",
    "NASDAQGM": "NASDAQ",
    "NYQ": "NYSE",
    "NYS": "NYSE",
    "NYSE": "NYSE",
    "PCX": "AMEX",
    "ASE": "AMEX",
    "GER": "XETR",
    "XETRA": "XETR",
    "XET": "XETR",
    "PAR": "EURONEXT",
    "EPA": "EURONEXT",
    "AMS": "EURONEXT",
    "EAM": "EURONEXT",
    "BRU": "EURONEXT",
    "LIS": "EURONEXT",
    "LSE": "LSE",
    "LON": "LSE",
    "SWX": "SIX",
    "SIX": "SIX",
    "EBS": "SIX",
    "MCE": "BME",
    "BME": "BME",
    "MIL": "MIL",
    "TYO": "TSE",
    "JPX": "TSE",
    "TSE": "TSE",
    "HKG": "HKEX",
    "HKEX": "HKEX",
    "ASX": "ASX",
    "TOR": "TSX",
    "TSX": "TSX",
    "STO": "OMXSTO",
    "CPH": "OMXCOP",
    "HEL": "OMXHEX",
    "KRX": "KRX",
    "TAI": "TWSE",
    "TWO": "TPEX",
}


class AssetManager:
    def __init__(
        self,
        db: Optional[Database] = None,
        binance_fetcher: Optional[BinanceFetcher] = None,
        yf_fetcher: Optional[YFinanceFetcher] = None,
        assets_yaml_path: str = ASSETS_YAML_PATH,
        tv_mapping_path: str = TV_MAPPING_PATH,
        names_mapping_path: str = NAMES_MAPPING_PATH,
    ):
        self.db = db or Database()
        self.binance_fetcher = binance_fetcher or BinanceFetcher()
        self.yf_fetcher = yf_fetcher or YFinanceFetcher()
        self.assets_yaml_path = assets_yaml_path
        self.tv_mapping_path = tv_mapping_path
        self.names_mapping_path = names_mapping_path

    def _resolve_tv_symbol(self, ticker: str, exchange_name: str, asset_class: str) -> str:
        """Derives standard TradingView symbol from ticker and exchange info."""
        if asset_class == "crypto":
            return f"BINANCE:{ticker}"

        # Indices special cases
        if ticker == "^GSPC":
            return "SP:SPX"
        elif ticker == "^IXIC":
            return "NASDAQ:IXIC"
        elif ticker == "^DJI":
            return "TVC:DJI"
        elif ticker == "^RUT":
            return "TVC:RUT"
        elif ticker == "^VIX":
            return "TVC:VIX"
        elif ticker == "DX-Y.NYB":
            return "TVC:DXY"
        elif ticker.startswith("^"):
            return f"TVC:{ticker[1:]}"

        # Commodities special cases
        if ticker.endswith("=F"):
            base = ticker[:-2]
            if base in ["GC", "SI", "HG"]:
                return f"COMEX:{base}1!"
            elif base in ["CL", "BZ", "NG", "PL"]:
                return f"NYMEX:{base}1!"
            return f"CBOT:{base}1!"

        # Foreign tickers with dot suffixes
        if "." in ticker:
            base, suffix = ticker.split(".", 1)
            suffix_map = {
                "PA": f"EURONEXT:{base}",
                "AS": f"EURONEXT:{base}",
                "DE": f"XETR:{base}",
                "L": f"LSE:{base}",
                "SW": f"SIX:{base}",
                "MC": f"BME:{base}",
                "MI": f"MIL:{base}",
                "T": f"TSE:{base}",
                "HK": f"HKEX:{base.lstrip('0')}",
                "AX": f"ASX:{base}",
                "TO": f"TSX:{base}",
                "ST": f"OMXSTO:{base}",
                "CO": f"OMXCOP:{base}",
                "HE": f"OMXHEX:{base}",
                "KS": f"KRX:{base}",
                "TW": f"TWSE:{base}",
                "TWO": f"TPEX:{base}",
            }
            if suffix in suffix_map:
                return suffix_map[suffix]

        # Use exchange code lookup
        prefix = EXCHANGE_TO_TV_PREFIX.get(exchange_name.upper(), "NASDAQ")
        clean_tick = ticker.replace("-", ".")
        return f"{prefix}:{clean_tick}"

    def validate_and_enrich(
        self,
        ticker: str,
        preferred_class: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Validates the existence of a ticker and extracts full metadata
        (short name, exchange, TradingView symbol, and candle history).
        """
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            return None

        # 1. Check Crypto on Binance
        is_crypto_pattern = (
            clean_ticker.endswith("USDT")
            or clean_ticker.endswith("FDUSD")
            or clean_ticker.endswith("BUSD")
            or preferred_class == "crypto"
        )

        if is_crypto_pattern:
            pair = clean_ticker if clean_ticker.endswith("USDT") else f"{clean_ticker}USDT"
            klines = self.binance_fetcher.fetch_klines(pair, timeframe="1D", limit=180)
            if klines:
                highs, lows, closes, latest_price = klines
                base = pair.replace("USDT", "").replace("FDUSD", "")
                name = f"{base} Token"
                tv_symbol = f"BINANCE:{pair}"
                return {
                    "ticker": pair,
                    "asset_class": "crypto",
                    "name": name,
                    "tv_symbol": tv_symbol,
                    "candles_count": len(closes),
                    "latest_price": float(latest_price),
                    "highs": highs,
                    "lows": lows,
                    "closes": closes,
                    "is_crypto": True,
                }
            elif preferred_class == "crypto":
                logger.warning(f"Crypto pair {pair} not found on Binance.")
                return None

        # 2. Check Traditional Asset (Stock, Commodity, Index) via Yahoo Finance
        try:
            # Direct chart API fetch for fast, robust response without rate limits
            candles = self.yf_fetcher.fetch_via_chart_api(clean_ticker, timeframe="1D")
            if not candles:
                candles = self.yf_fetcher.fetch_single(clean_ticker, timeframe="1D")

            if not candles:
                logger.warning(f"Ticker {clean_ticker} not found in market data.")
                return None

            highs, lows, closes, latest_price = candles

            # Extract metadata (name, exchange) from chart API
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_ticker}?range=1d&interval=1d"
            meta = {}
            try:
                session = self.yf_fetcher.session
                if session is None:
                    from curl_cffi.requests import Session as CurlSession
                    session = CurlSession(impersonate="chrome")
                resp = session.get(url, timeout=6)
                if resp.status_code == 200:
                    meta = resp.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
            except Exception as e:
                logger.debug(f"Metadata lookup failed for {clean_ticker}: {e}")

            name = meta.get("shortName") or meta.get("longName") or clean_ticker
            exchange_name = meta.get("exchangeName") or meta.get("fullExchangeName") or "NASDAQ"

            # Determine asset class
            if preferred_class and preferred_class in VALID_ASSET_CLASSES:
                asset_class = preferred_class
            elif clean_ticker.startswith("^"):
                asset_class = "indices"
            elif clean_ticker.endswith("=F"):
                asset_class = "commodities"
            elif "." in clean_ticker and any(clean_ticker.endswith(f".{x}") for x in ["PA", "DE", "L", "SW", "MC", "MI", "T", "HK", "AX", "TO", "ST", "CO", "HE", "KS", "TW"]):
                asset_class = "intl_stocks"
            else:
                asset_class = "us_stocks"

            tv_symbol = self._resolve_tv_symbol(clean_ticker, exchange_name, asset_class)

            return {
                "ticker": clean_ticker,
                "asset_class": asset_class,
                "name": name,
                "tv_symbol": tv_symbol,
                "candles_count": len(closes),
                "latest_price": float(latest_price),
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "is_crypto": False,
            }
        except Exception as e:
            logger.error(f"Error validating ticker {clean_ticker}: {e}")
            return None

    def _load_yaml(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load YAML from {path}: {e}")
        return {}

    def _save_yaml(self, data: dict, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Failed to save YAML to {path}: {e}")

    def _load_json(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_json(self, data: dict, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save JSON to {path}: {e}")

    def add_asset(
        self,
        ticker: str,
        asset_class: Optional[str] = None,
        scan_now: bool = True,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Validates and adds an asset into the system:
        - Updates config/assets.yaml
        - Updates config/tv_mapping.json
        - Updates config/names_mapping.json
        - Updates SQLite symbols table
        - Optionally computes initial Larsson State and updates dashboard data.json
        """
        meta = self.validate_and_enrich(ticker, preferred_class=asset_class)
        if not meta:
            return False, f"Символът '{ticker}' не беше намерен или липсват достатъчно исторически данни.", None

        ticker_sym = meta["ticker"]
        target_class = meta["asset_class"]
        tv_sym = meta["tv_symbol"]
        name = meta["name"]
        highs = meta["highs"]
        lows = meta["lows"]
        closes = meta["closes"]
        latest_price = meta["latest_price"]

        # 1. Update config/assets.yaml
        assets_data = self._load_yaml(self.assets_yaml_path)
        if target_class not in assets_data or not isinstance(assets_data[target_class], list):
            assets_data[target_class] = []

        existing_tickers = {
            item["ticker"]
            for cat, items in assets_data.items()
            if isinstance(items, list)
            for item in items
            if isinstance(item, dict) and "ticker" in item
        }

        if ticker_sym not in existing_tickers:
            assets_data[target_class].append({
                "ticker": ticker_sym,
                "tv_symbol": tv_sym,
            })
            self._save_yaml(assets_data, self.assets_yaml_path)
            logger.info(f"Added {ticker_sym} to {self.assets_yaml_path} under '{target_class}'")

        # 2. Update config/tv_mapping.json
        tv_data = self._load_json(self.tv_mapping_path)
        tv_data[ticker_sym] = tv_sym
        self._save_json(tv_data, self.tv_mapping_path)

        # 3. Update config/names_mapping.json
        names_data = self._load_json(self.names_mapping_path)
        names_data[ticker_sym] = name
        self._save_json(names_data, self.names_mapping_path)

        # 4. Update SQLite database symbols table
        self.db.upsert_symbols([(ticker_sym, target_class, tv_sym)])

        state_info = {
            "ticker": ticker_sym,
            "name": name,
            "asset_class": target_class,
            "tv_symbol": tv_sym,
            "price": latest_price,
            "state": "UNKNOWN",
            "s1": None,
            "r1": None,
        }

        # 5. Optionally run instant scan and calculate Larsson Line states
        if scan_now and len(highs) >= 30:
            try:
                v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
                current_state = states[-1]

                sr_analysis = analyze_sr_levels(highs, lows, closes, current_price=latest_price)
                if sr_analysis:
                    self.db.upsert_sr_levels(
                        ticker=ticker_sym,
                        timeframe="1D",
                        current_price=sr_analysis.current_price,
                        atr=sr_analysis.atr,
                        s1=sr_analysis.s1,
                        s1_touches=sr_analysis.s1_touches,
                        s1_dist_pct=sr_analysis.s1_dist_pct,
                        s2=sr_analysis.s2,
                        s2_touches=sr_analysis.s2_touches,
                        r1=sr_analysis.r1,
                        r1_touches=sr_analysis.r1_touches,
                        r1_dist_pct=sr_analysis.r1_dist_pct,
                        r2=sr_analysis.r2,
                        r2_touches=sr_analysis.r2_touches,
                        context_flag=sr_analysis.context_flag,
                        context_desc=sr_analysis.context_desc,
                        all_zones_json=json.dumps(sr_analysis.zones),
                    )
                    state_info["s1"] = sr_analysis.s1
                    state_info["r1"] = sr_analysis.r1

                self.db.update_state(
                    ticker=ticker_sym,
                    timeframe="1D",
                    v1=float(v1[-1]),
                    m1=float(m1[-1]),
                    m2=float(m2[-1]),
                    v2=float(v2[-1]),
                    new_state=current_state,
                    price=float(latest_price),
                )
                state_info["state"] = current_state.value

                # Refresh dashboard data if using production db
                from src.storage.database import DEFAULT_DB_PATH
                if os.path.abspath(self.db.db_path) == os.path.abspath(DEFAULT_DB_PATH):
                    from src.dashboard.generator import export_dashboard_data
                    export_dashboard_data(self.db)
            except Exception as e:
                logger.warning(f"Failed to calculate instant scan for {ticker_sym}: {e}")

        success_msg = f"Успешно добавен актив {ticker_sym} ({name}) в клас '{target_class}'."
        return True, success_msg, state_info

    def add_multiple(
        self,
        tickers: List[str],
        asset_class: Optional[str] = None,
    ) -> Dict:
        """Adds a list of tickers, reporting added and failed items."""
        summary = {
            "total": len(tickers),
            "added": [],
            "failed": [],
        }
        for t in tickers:
            clean = t.strip()
            if not clean:
                continue
            ok, msg, info = self.add_asset(clean, asset_class=asset_class, scan_now=True)
            if ok:
                summary["added"].append(info)
            else:
                summary["failed"].append({"ticker": clean, "reason": msg})
        return summary

    def remove_asset(self, ticker: str) -> Tuple[bool, str]:
        """
        Removes an asset from assets.yaml and deactivates it in SQLite.
        """
        clean_ticker = ticker.strip().upper()

        # 1. Remove from config/assets.yaml
        assets_data = self._load_yaml(self.assets_yaml_path)
        removed_from_yaml = False
        for cat in assets_data:
            if isinstance(assets_data[cat], list):
                orig_len = len(assets_data[cat])
                assets_data[cat] = [
                    item for item in assets_data[cat]
                    if not (isinstance(item, dict) and item.get("ticker", "").upper() == clean_ticker)
                ]
                if len(assets_data[cat]) < orig_len:
                    removed_from_yaml = True

        if removed_from_yaml:
            self._save_yaml(assets_data, self.assets_yaml_path)

        # 2. Deactivate in database symbols table
        with self.db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE symbols SET is_active = 0 WHERE ticker = ?", (clean_ticker,))
            db_affected = cur.rowcount

        # 3. Remove from watchlist
        self.db.remove_from_watchlist(clean_ticker)

        # 4. Refresh dashboard if using production db
        try:
            from src.storage.database import DEFAULT_DB_PATH
            if os.path.abspath(self.db.db_path) == os.path.abspath(DEFAULT_DB_PATH):
                from src.dashboard.generator import export_dashboard_data
                export_dashboard_data(self.db)
        except Exception:
            pass

        if removed_from_yaml or db_affected > 0:
            return True, f"Активът {clean_ticker} беше успешно премахнат и деактивиран."
        return False, f"Активът {clean_ticker} не беше намерен в списъка."
