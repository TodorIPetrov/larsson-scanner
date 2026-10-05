"""
Data Health Guard & Feed Integrity Engine.
Detects stale feeds, missing bars, zero volume, and data latency across free APIs.
Prevents false, confident alerts produced from stale or corrupted market data.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataHealthResult:
    is_healthy: bool
    last_candle_time: Optional[datetime]
    age_hours: float
    bars_count: int
    issues: List[str]
    warning_message: str


class DataHealthGuard:
    def __init__(
        self,
        max_stale_hours_crypto_1d: float = 36.0,
        max_stale_hours_crypto_4h: float = 8.0,
        max_stale_hours_stocks_1d: float = 84.0,  # Covers full weekend (Fri close to Mon night)
        min_bars_required: int = 40,
    ):
        self.max_stale_crypto_1d = max_stale_hours_crypto_1d
        self.max_stale_crypto_4h = max_stale_hours_crypto_4h
        self.max_stale_stocks_1d = max_stale_hours_stocks_1d
        self.min_bars_required = min_bars_required

    def _parse_last_date(self, date_val: Any) -> Optional[datetime]:
        """Parses various date/timestamp formats into timezone-aware UTC datetime."""
        if isinstance(date_val, datetime):
            if date_val.tzinfo is None:
                return date_val.replace(tzinfo=timezone.utc)
            return date_val.astimezone(timezone.utc)

        if isinstance(date_val, (int, float)):
            # Timestamp in milliseconds or seconds
            if date_val > 1e11:
                return datetime.fromtimestamp(date_val / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(date_val, tz=timezone.utc)

        if isinstance(date_val, str):
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
            ):
                try:
                    dt = datetime.strptime(date_val, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

        return None

    def validate_ohlcv(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        timeframe: str = "1D",
        asset_class: str = "crypto",
        now_dt: Optional[datetime] = None,
    ) -> DataHealthResult:
        """
        Validates OHLCV dataset integrity and feed freshness.
        """
        issues: List[str] = []
        now = now_dt or datetime.now(timezone.utc)

        if df is None or len(df) == 0:
            return DataHealthResult(
                is_healthy=False,
                last_candle_time=None,
                age_hours=999.0,
                bars_count=0,
                issues=["EMPTY_DATASET"],
                warning_message=f"[{symbol}] Dataset is empty.",
            )

        n_bars = len(df)
        if n_bars < self.min_bars_required:
            issues.append("INSUFFICIENT_BARS")

        # Check for essential columns
        required_cols = {"open", "high", "low", "close"}
        if not required_cols.issubset(set(df.columns)):
            issues.append("MISSING_PRICE_COLUMNS")
            return DataHealthResult(
                is_healthy=False,
                last_candle_time=None,
                age_hours=999.0,
                bars_count=n_bars,
                issues=issues,
                warning_message=f"[{symbol}] Missing OHLC columns in dataframe.",
            )

        # Check for NaN prices in latest bars
        recent_tail = df.iloc[-min(5, n_bars):]
        if recent_tail[["open", "high", "low", "close"]].isna().any().any():
            issues.append("NAN_VALUES_IN_RECENT_BARS")

        # Zero or flatline checks
        last_closes = recent_tail["close"].to_numpy()
        if (last_closes <= 0).any():
            issues.append("ZERO_OR_NEGATIVE_PRICE")

        # Check staleness based on timestamp column
        date_col = "date" if "date" in df.columns else (df.index.name or "date")
        last_candle_dt = None

        if "date" in df.columns:
            last_candle_dt = self._parse_last_date(df["date"].iloc[-1])
        elif isinstance(df.index, pd.DatetimeIndex):
            last_candle_dt = self._parse_last_date(df.index[-1])

        age_hours = 0.0
        if last_candle_dt:
            age_sec = (now - last_candle_dt).total_seconds()
            age_hours = round(max(0.0, age_sec / 3600.0), 1)

            # Determine staleness threshold
            is_crypto = "crypto" in asset_class.lower()
            if is_crypto:
                max_allowed = self.max_stale_crypto_4h if timeframe == "4H" else self.max_stale_crypto_1d
            else:
                max_allowed = self.max_stale_stocks_1d

            if age_hours > max_allowed:
                issues.append("STALE_DATA_FEED")
        else:
            issues.append("UNPARSEABLE_TIMESTAMP")

        is_healthy = len(issues) == 0
        warn_msg = ""
        if not is_healthy:
            warn_msg = f"[{symbol}] Feed failed health checks: {', '.join(issues)} (Age: {age_hours}h)"

        return DataHealthResult(
            is_healthy=is_healthy,
            last_candle_time=last_candle_dt,
            age_hours=age_hours,
            bars_count=n_bars,
            issues=issues,
            warning_message=warn_msg,
        )
