"""
BlockHorizon Data Ingestion Engine.

Ingests Bitcoin on-chain cycle signals and metrics from BlockHorizon (blockhorizon.io):
1. CSV import mode: parses manual or automated CSV exports dropped into data/blockhorizon/
2. API mode: queries BlockHorizon API endpoints if api_key is configured
3. Free fallback mode: computes/retrieves public proxy metrics (Fear & Greed, Mayer Multiple, Hashrate momentum)
   when BlockHorizon is offline or no export is available.
"""

from __future__ import annotations

import csv
import glob
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.storage.database import Database

logger = logging.getLogger(__name__)

DEFAULT_CSV_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "blockhorizon",
)

# Standard metric aliases mapping various CSV column titles to canonical metric keys
METRIC_ALIASES: Dict[str, str] = {
    "cycle_signal": "cycle_signal",
    "cycle_score": "cycle_signal",
    "cycle signal": "cycle_signal",
    "blockhorizon cycle signal": "cycle_signal",
    "mvrv": "mvrv",
    "mvrv_ratio": "mvrv",
    "mvrv-z": "mvrv_z",
    "mvrv_z": "mvrv_z",
    "mvrv z-score": "mvrv_z",
    "mvrv_zscore": "mvrv_z",
    "nupl": "nupl",
    "net unrealized profit/loss": "nupl",
    "sopr": "sopr",
    "asopr": "asopr",
    "adjusted sopr": "asopr",
    "puell": "puell_multiple",
    "puell_multiple": "puell_multiple",
    "puell multiple": "puell_multiple",
    "reserve_risk": "reserve_risk",
    "reserve risk": "reserve_risk",
    "hash_ribbon": "hash_ribbon",
    "hashrate": "hashrate",
    "realized_price": "realized_price",
    "realized price": "realized_price",
    "fear_and_greed": "fear_and_greed",
    "fng": "fear_and_greed",
}


def canonicalize_metric_name(name: str) -> str:
    """Normalizes header or metric string into canonical identifier."""
    cleaned = name.strip().lower().replace("-", "_").replace(" ", "_")
    return METRIC_ALIASES.get(name.strip().lower(), METRIC_ALIASES.get(cleaned, cleaned))


def parse_date_string(date_val: str) -> Optional[str]:
    """Parses various date string formats to standard YYYY-MM-DD."""
    date_val = str(date_val).strip()
    if not date_val:
        return None
    # Handle ISO timestamps with T or space
    date_clean = date_val.split("T")[0].split(" ")[0]
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_clean, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class BlockHorizonFetcher:
    """Ingests Bitcoin on-chain metrics from CSV exports, API, or public fallbacks."""

    def __init__(
        self,
        db: Database,
        csv_dir: str = DEFAULT_CSV_DIR,
        api_key: Optional[str] = None,
        base_url: str = "https://blockhorizon.io/api",
        session: Optional[requests.Session] = None,
    ):
        self.db = db
        self.csv_dir = csv_dir
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        os.makedirs(self.csv_dir, exist_ok=True)

    def import_csv_file(self, file_path: str) -> int:
        """
        Parses a CSV file containing on-chain data and saves records into SQLite.
        Supports both wide format (Date, Metric1, Metric2...) and long format (Date, Metric, Value).
        """
        if not os.path.exists(file_path):
            logger.warning(f"CSV file not found: {file_path}")
            return 0

        records: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return 0

            header_clean = [h.strip() for h in header]
            header_lower = [h.lower() for h in header_clean]

            # Find date column index
            date_idx = -1
            for idx, h in enumerate(header_lower):
                if h in ("date", "timestamp", "time", "day", "datetime"):
                    date_idx = idx
                    break

            if date_idx == -1:
                # Default to first column if no date header found
                date_idx = 0

            # Check if this is long format: Date, Metric, Value
            is_long_format = False
            metric_idx = -1
            val_idx = -1
            for idx, h in enumerate(header_lower):
                if h in ("metric", "indicator", "key", "name"):
                    metric_idx = idx
                elif h in ("value", "val", "score"):
                    val_idx = idx

            if metric_idx != -1 and val_idx != -1:
                is_long_format = True

            for row in reader:
                if not row or len(row) <= date_idx:
                    continue
                raw_date = row[date_idx]
                parsed_date = parse_date_string(raw_date)
                if not parsed_date:
                    continue

                if is_long_format:
                    if len(row) <= max(metric_idx, val_idx):
                        continue
                    metric_raw = row[metric_idx].strip()
                    val_str = row[val_idx].strip()
                    try:
                        val = float(val_str)
                    except ValueError:
                        continue
                    canonical_metric = canonicalize_metric_name(metric_raw)
                    records.append({
                        "date": parsed_date,
                        "metric": canonical_metric,
                        "value": val,
                        "source": f"csv:{os.path.basename(file_path)}",
                        "fetched_at": now_iso,
                    })
                else:
                    # Wide format: each column is a metric
                    for col_idx, cell in enumerate(row):
                        if col_idx == date_idx or col_idx >= len(header_clean):
                            continue
                        metric_raw = header_clean[col_idx]
                        val_str = cell.strip()
                        if not val_str:
                            continue
                        try:
                            val = float(val_str)
                        except ValueError:
                            continue
                        canonical_metric = canonicalize_metric_name(metric_raw)
                        records.append({
                            "date": parsed_date,
                            "metric": canonical_metric,
                            "value": val,
                            "source": f"csv:{os.path.basename(file_path)}",
                            "fetched_at": now_iso,
                        })

        inserted = self.db.record_onchain_metrics_bulk(records)
        logger.info(f"Imported {inserted} on-chain records from {file_path}")
        return inserted

    def import_all_csvs(self) -> int:
        """Scans CSV directory and imports all CSV files."""
        csv_files = glob.glob(os.path.join(self.csv_dir, "*.csv"))
        total = 0
        for f in sorted(csv_files):
            total += self.import_csv_file(f)
        return total

    def fetch_api(self) -> int:
        """
        Attempts to fetch metrics from BlockHorizon API if API key is provided.
        Returns number of records stored.
        """
        if not self.api_key:
            logger.debug("No BlockHorizon API key configured; skipping API fetch.")
            return 0

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }
        url = f"{self.base_url}/metrics/daily"
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"BlockHorizon API returned status {resp.status_code}")
                return 0

            data = resp.json()
            records: List[Dict[str, Any]] = []
            now_iso = datetime.now(timezone.utc).isoformat()

            items = data if isinstance(data, list) else data.get("data", [])
            for item in items:
                date_str = parse_date_string(item.get("date") or item.get("timestamp"))
                if not date_str:
                    continue
                for k, v in item.items():
                    if k in ("date", "timestamp"):
                        continue
                    try:
                        val = float(v)
                    except (ValueError, TypeError):
                        continue
                    metric_name = canonicalize_metric_name(k)
                    records.append({
                        "date": date_str,
                        "metric": metric_name,
                        "value": val,
                        "source": "blockhorizon_api",
                        "fetched_at": now_iso,
                    })

            return self.db.record_onchain_metrics_bulk(records)
        except Exception as e:
            logger.warning(f"BlockHorizon API fetch failed: {e}")
            return 0

    def fetch_fallback_indicators(self) -> int:
        """
        Fetches free public Bitcoin sentiment & proxy cycle indicators
        (Alternative.me Fear & Greed index, Mayer Multiple, Network data).
        """
        records: List[Dict[str, Any]] = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Alternative.me Crypto Fear & Greed Index (0-100)
        try:
            fng_resp = self.session.get("https://api.alternative.me/fng/?limit=7", timeout=5)
            if fng_resp.status_code == 200:
                data = fng_resp.json().get("data", [])
                for entry in data:
                    ts = int(entry.get("timestamp", 0))
                    d_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    val = float(entry.get("value", 50))
                    records.append({
                        "date": d_str,
                        "metric": "fear_and_greed",
                        "value": val,
                        "source": "alternative_me_fng",
                        "fetched_at": now_iso,
                    })
        except Exception as e:
            logger.debug(f"Fear & Greed fetch failed: {e}")

        # 2. CoinGecko BTC data for Mayer Multiple & MVRV proxy calculation
        try:
            cg_resp = self.session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=200&interval=daily",
                timeout=8,
            )
            if cg_resp.status_code == 200:
                prices = [p[1] for p in cg_resp.json().get("prices", [])]
                if prices:
                    current_price = prices[-1]
                    # 200-day Simple Moving Average (Mayer Multiple denominator)
                    sma_200 = sum(prices) / len(prices)
                    mayer_multiple = current_price / sma_200 if sma_200 > 0 else 1.0

                    # Classic Mayer Multiple cycle regimes:
                    # < 0.8: Deep undervaluation (Value zone)
                    # 0.8 - 1.5: Normal bull / neutral
                    # 1.5 - 2.4: Overheating
                    # > 2.4: Historical cycle top zone
                    # Rescale Mayer Multiple to 0-100 proxy cycle score:
                    # Mayer 0.5 -> ~10, 1.0 -> ~40, 1.5 -> ~65, 2.4 -> ~90, 3.0 -> ~100
                    mayer_scaled = min(100.0, max(0.0, (mayer_multiple - 0.4) / (2.6 - 0.4) * 100.0))

                    records.append({
                        "date": today,
                        "metric": "mayer_multiple",
                        "value": round(mayer_multiple, 3),
                        "source": "coingecko_derived",
                        "fetched_at": now_iso,
                    })
                    records.append({
                        "date": today,
                        "metric": "mvrv_proxy",
                        "value": round(mayer_multiple * 1.15, 3),
                        "source": "coingecko_derived",
                        "fetched_at": now_iso,
                    })
                    records.append({
                        "date": today,
                        "metric": "cycle_signal_proxy",
                        "value": round(mayer_scaled, 1),
                        "source": "coingecko_derived",
                        "fetched_at": now_iso,
                    })
        except Exception as e:
            logger.debug(f"CoinGecko Mayer Multiple derivation failed: {e}")

        if records:
            return self.db.record_onchain_metrics_bulk(records)
        return 0

    def sync(self, source_preference: str = "csv") -> Dict[str, Any]:
        """
        Coordinates synchronization across available sources:
        1. If source_preference is 'csv': imports CSVs, falls back to public indicators if empty
        2. If 'api': tries API first, then CSVs, then public indicators
        3. Returns sync summary dict.
        """
        csv_count = self.import_all_csvs()
        api_count = 0
        fallback_count = 0

        if source_preference == "api" or (csv_count == 0 and self.api_key):
            api_count = self.fetch_api()

        # If still no on-chain metrics exist or CSV had 0 new entries today, ensure fallback is populated
        latest = self.db.get_latest_onchain_metrics()
        if not latest:
            fallback_count = self.fetch_fallback_indicators()

        return {
            "csv_records_imported": csv_count,
            "api_records_imported": api_count,
            "fallback_records_imported": fallback_count,
            "latest_metrics_count": len(self.db.get_latest_onchain_metrics()),
        }
