"""
Alert Logger and Forward Outcome Tracking Engine.
Logs every dispatched trade alert with its entry price, invalidation stop, and time stop horizon.
Rigorously tracks forward price paths, calculates actual realized hit rates, MFE/MAE excursions,
and builds an auditable, compounding Track Record in SQLite.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "state.db",
)


@dataclass
class AlertOutcomeRecord:
    alert_id: str
    ticker: str
    timeframe: str
    asset_class: str
    transition_type: str
    signal_timestamp: str
    entry_price: float
    invalidation_price: Optional[float]
    time_stop_bars: int
    current_status: str  # 'OPEN', 'STOPPED_OUT', 'TIME_EXPIRED', 'PROFIT_CLOSED'
    mfe_pct: float
    mae_pct: float
    realized_return_pct: Optional[float]
    bars_elapsed: int
    updated_at: str


class AlertOutcomeTracker:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite schema for alert outcomes tracking."""
        try:
            with sqlite3.connect(self.db_path, timeout=15.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT UNIQUE NOT NULL,
                    ticker TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    transition_type TEXT NOT NULL,
                    signal_timestamp TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    invalidation_price REAL,
                    time_stop_bars INTEGER DEFAULT 60,
                    current_status TEXT NOT NULL DEFAULT 'OPEN',
                    mfe_pct REAL DEFAULT 0.0,
                    mae_pct REAL DEFAULT 0.0,
                    realized_return_pct REAL,
                    bars_elapsed INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """)
        except Exception as e:
            logger.error(f"Failed to initialize alert_outcomes table: {e}")

    def log_alert(
        self,
        ticker: str,
        timeframe: str,
        asset_class: str,
        transition_type: str,
        entry_price: float,
        invalidation_price: Optional[float] = None,
        time_stop_bars: int = 60,
        timestamp: Optional[str] = None,
    ) -> str:
        """
        Logs a fresh alert to SQLite database for continuous forward tracking.
        Returns unique alert_id.
        """
        now_ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        alert_id = f"{ticker}_{timeframe}_{now_ts.replace(' ', '_').replace(':', '')}"

        try:
            with sqlite3.connect(self.db_path, timeout=15.0) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO alert_outcomes (
                        alert_id, ticker, timeframe, asset_class, transition_type,
                        signal_timestamp, entry_price, invalidation_price,
                        time_stop_bars, current_status, mfe_pct, mae_pct,
                        realized_return_pct, bars_elapsed, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 0.0, 0.0, NULL, 0, ?)
                    """,
                    (
                        alert_id,
                        ticker,
                        timeframe,
                        asset_class,
                        transition_type,
                        now_ts,
                        float(entry_price),
                        float(invalidation_price) if invalidation_price is not None else None,
                        int(time_stop_bars),
                        now_ts,
                    ),
                )
            logger.info(f"Logged alert for forward outcome tracking: {alert_id} (Entry: {entry_price}, SL: {invalidation_price})")
        except Exception as e:
            logger.error(f"Error logging alert {alert_id}: {e}")

        return alert_id

    def evaluate_alert_bars(
        self,
        record: Dict[str, Any],
        future_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Replays closed candles that occurred after signal_timestamp.
        Evaluates invalidation stop triggers, MFE, MAE, and time stops.
        """
        if future_df is None or len(future_df) == 0:
            return record

        entry = float(record["entry_price"])
        inv = float(record["invalidation_price"]) if record.get("invalidation_price") is not None else None
        time_stop = int(record.get("time_stop_bars", 60))
        is_long = "GOLD" in record.get("transition_type", "GOLD")

        highs = future_df["high"].to_numpy(dtype=np.float64)
        lows = future_df["low"].to_numpy(dtype=np.float64)
        closes = future_df["close"].to_numpy(dtype=np.float64)
        n_bars = len(future_df)

        running_mfe = 0.0
        running_mae = 0.0
        status = "OPEN"
        realized_ret = None
        bars_eval = 0

        for i in range(min(n_bars, time_stop)):
            bars_eval = i + 1
            h = highs[i]
            l = lows[i]
            c = closes[i]

            # Update excursions
            if is_long:
                bar_mfe = (h - entry) / entry * 100.0
                bar_mae = (l - entry) / entry * 100.0
            else:
                bar_mfe = (entry - l) / entry * 100.0
                bar_mae = (entry - h) / entry * 100.0

            running_mfe = max(running_mfe, bar_mfe)
            running_mae = min(running_mae, bar_mae)

            # Check invalidation level
            if inv is not None:
                if is_long and l <= inv:
                    status = "STOPPED_OUT"
                    realized_ret = (inv - entry) / entry * 100.0
                    break
                elif (not is_long) and h >= inv:
                    status = "STOPPED_OUT"
                    realized_ret = (entry - inv) / entry * 100.0
                    break

        # If not stopped out and reached time stop horizon
        if status == "OPEN" and bars_eval >= time_stop:
            status = "TIME_EXPIRED"
            last_close = closes[bars_eval - 1]
            realized_ret = (last_close - entry) / entry * 100.0 if is_long else (entry - last_close) / entry * 100.0

        updated = dict(record)
        updated["current_status"] = status
        updated["mfe_pct"] = round(running_mfe, 2)
        updated["mae_pct"] = round(running_mae, 2)
        updated["realized_return_pct"] = round(realized_ret, 2) if realized_ret is not None else None
        updated["bars_elapsed"] = bars_eval
        updated["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        return updated

    def save_evaluated_record(self, updated: Dict[str, Any]) -> bool:
        """Persists updated evaluation results back to SQLite."""
        try:
            with sqlite3.connect(self.db_path, timeout=15.0) as conn:
                conn.execute(
                    """
                    UPDATE alert_outcomes
                    SET current_status = ?,
                        mfe_pct = ?,
                        mae_pct = ?,
                        realized_return_pct = ?,
                        bars_elapsed = ?,
                        updated_at = ?
                    WHERE alert_id = ?
                    """,
                    (
                        updated["current_status"],
                        updated["mfe_pct"],
                        updated["mae_pct"],
                        updated["realized_return_pct"],
                        updated["bars_elapsed"],
                        updated["updated_at"],
                        updated["alert_id"],
                    ),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update alert record {updated.get('alert_id')}: {e}")
            return False

    def load_all_records(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Loads logged alerts from SQLite."""
        results = []
        try:
            with sqlite3.connect(self.db_path, timeout=15.0) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                if status_filter:
                    cur.execute("SELECT * FROM alert_outcomes WHERE current_status = ? ORDER BY id DESC", (status_filter,))
                else:
                    cur.execute("SELECT * FROM alert_outcomes ORDER BY id DESC")
                for row in cur.fetchall():
                    results.append(dict(row))
        except Exception as e:
            logger.error(f"Failed to fetch alert outcomes: {e}")
        return results

    def calculate_track_record_metrics(self) -> Dict[str, Any]:
        """
        Aggregates closed and running alerts into an auditable track record.
        """
        records = self.load_all_records()
        total = len(records)
        if total == 0:
            return {
                "total_alerts": 0,
                "closed_count": 0,
                "open_count": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "mean_return_pct": 0.0,
                "avg_mfe_pct": 0.0,
                "avg_mae_pct": 0.0,
                "edge_ratio": 1.0,
            }

        closed = [r for r in records if r["current_status"] in ["STOPPED_OUT", "TIME_EXPIRED", "PROFIT_CLOSED"]]
        open_alerts = [r for r in records if r["current_status"] == "OPEN"]

        if not closed:
            return {
                "total_alerts": total,
                "closed_count": 0,
                "open_count": len(open_alerts),
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "mean_return_pct": 0.0,
                "avg_mfe_pct": round(float(np.mean([r["mfe_pct"] for r in records])), 2),
                "avg_mae_pct": round(float(np.mean([r["mae_pct"] for r in records])), 2),
                "edge_ratio": 1.0,
            }

        returns = [r["realized_return_pct"] for r in closed if r["realized_return_pct"] is not None]
        wins = [ret for ret in returns if ret > 0]
        losses = [ret for ret in returns if ret < 0]

        win_rate = len(wins) / len(returns) if returns else 0.0
        sum_wins = sum(wins) if wins else 0.0
        sum_losses = abs(sum(losses)) if losses else 0.0
        pf = (sum_wins / sum_losses) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)

        all_mfes = [r["mfe_pct"] for r in records]
        all_maes = [r["mae_pct"] for r in records]
        avg_mfe = float(np.mean(all_mfes)) if all_mfes else 0.0
        avg_mae = float(np.mean(all_maes)) if all_maes else 0.0
        edge_r = (avg_mfe / abs(avg_mae)) if abs(avg_mae) > 1e-4 else 1.0

        return {
            "total_alerts": total,
            "closed_count": len(closed),
            "open_count": len(open_alerts),
            "stopped_out_count": sum(1 for r in closed if r["current_status"] == "STOPPED_OUT"),
            "time_expired_count": sum(1 for r in closed if r["current_status"] == "TIME_EXPIRED"),
            "win_rate": round(win_rate * 100.0, 1),
            "profit_factor": round(pf, 2),
            "mean_return_pct": round(float(np.mean(returns)), 2) if returns else 0.0,
            "avg_mfe_pct": round(avg_mfe, 2),
            "avg_mae_pct": round(avg_mae, 2),
            "edge_ratio": round(edge_r, 2),
        }

    def format_track_record_telegram(self) -> str:
        """Renders an auditable HTML Telegram Track Record summary."""
        m = self.calculate_track_record_metrics()
        lines = [
            "🏆 <b>LARSSON SCANNER: AUDITED TRACK RECORD</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• Регистрирани алерти: <b>{m['total_alerts']}</b> (Отворени: {m['open_count']} | Приключени: {m['closed_count']})",
            f"• Win Rate: <b>{m['win_rate']}%</b>",
            f"• Profit Factor: <b>{m['profit_factor']}</b>",
            f"• Средна реализирана доходност: <b>{m['mean_return_pct']:+.2f}%</b>",
            f"• Макс. благоприятно движение (Avg MFE): <b>+{m['avg_mfe_pct']:.1f}%</b>",
            f"• Макс. неблагоприятно движение (Avg MAE): <b>{m['avg_mae_pct']:.1f}%</b>",
            f"• Индекс на предимство (Edge Ratio): <b>{m['edge_ratio']:.2f}x</b>",
        ]
        return "\n".join(lines)
