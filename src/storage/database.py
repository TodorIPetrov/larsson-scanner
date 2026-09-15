"""
Database and State Persistence for Larsson Line Scanner.
Uses SQLite with Write-Ahead Logging (WAL) mode for maximum concurrency and safety.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
import sqlite3
from typing import Dict, List, Optional, Tuple

from src.engine.smma import LarssonState

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "state.db")


class Database:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")

            # Table for configured symbols
            cur.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                ticker TEXT PRIMARY KEY,
                asset_class TEXT NOT NULL,
                tv_symbol TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            """)

            # Table for tracking latest indicator states per symbol and timeframe
            cur.execute("""
            CREATE TABLE IF NOT EXISTS symbol_states (
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                v1 REAL NOT NULL,
                m1 REAL NOT NULL,
                m2 REAL NOT NULL,
                v2 REAL NOT NULL,
                current_state TEXT NOT NULL,
                last_price REAL NOT NULL,
                last_state_change TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (ticker, timeframe)
            );
            """)

            # Table for recording alert history
            cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                old_state TEXT NOT NULL,
                new_state TEXT NOT NULL,
                price REAL NOT NULL,
                tv_symbol TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

    def upsert_symbols(self, symbols: List[Tuple[str, str, str]]):
        """Insert or update symbols (ticker, asset_class, tv_symbol)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.executemany("""
            INSERT INTO symbols (ticker, asset_class, tv_symbol, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(ticker) DO UPDATE SET
                asset_class=excluded.asset_class,
                tv_symbol=excluded.tv_symbol,
                is_active=1;
            """, symbols)

    def get_active_symbols(self, asset_class: Optional[str] = None) -> List[sqlite3.Row]:
        """Fetch all active symbols, optionally filtered by asset class."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            if asset_class:
                cur.execute("SELECT * FROM symbols WHERE is_active = 1 AND asset_class = ? ORDER BY ticker", (asset_class,))
            else:
                cur.execute("SELECT * FROM symbols WHERE is_active = 1 ORDER BY ticker")
            return cur.fetchall()

    def get_current_state(self, ticker: str, timeframe: str) -> Optional[sqlite3.Row]:
        """Retrieve previous state of a symbol on a specific timeframe."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM symbol_states WHERE ticker = ? AND timeframe = ?", (ticker, timeframe))
            return cur.fetchone()

    def get_all_states(self) -> List[sqlite3.Row]:
        """Fetch all states across all symbols and timeframes."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT s.ticker, s.asset_class, s.tv_symbol, st.timeframe, st.v1, st.m1, st.m2, st.v2,
                   st.current_state, st.last_price, st.last_state_change, st.updated_at
            FROM symbols s
            JOIN symbol_states st ON s.ticker = st.ticker
            WHERE s.is_active = 1
            ORDER BY st.last_state_change DESC
            """)
            return cur.fetchall()

    def update_state(
        self,
        ticker: str,
        timeframe: str,
        v1: float,
        m1: float,
        m2: float,
        v2: float,
        new_state: LarssonState,
        price: float,
        now_iso: Optional[str] = None,
    ) -> Tuple[bool, Optional[LarssonState]]:
        """
        Updates the state of a symbol.
        Returns (state_changed: bool, old_state: Optional[LarssonState]).
        """
        if not now_iso:
            now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_state, last_state_change FROM symbol_states WHERE ticker = ? AND timeframe = ?", (ticker, timeframe))
            row = cur.fetchone()

            if row is None:
                # First time seeing this symbol/timeframe
                cur.execute("""
                INSERT INTO symbol_states
                (ticker, timeframe, v1, m1, m2, v2, current_state, last_price, last_state_change, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticker, timeframe, v1, m1, m2, v2, new_state.value, price, now_iso, now_iso))
                return False, None

            old_state_str = row["current_state"]
            old_state = LarssonState(old_state_str)
            state_changed = (old_state != new_state)
            last_change = now_iso if state_changed else row["last_state_change"]

            cur.execute("""
            UPDATE symbol_states
            SET v1 = ?, m1 = ?, m2 = ?, v2 = ?, current_state = ?, last_price = ?,
                last_state_change = ?, updated_at = ?
            WHERE ticker = ? AND timeframe = ?
            """, (v1, m1, m2, v2, new_state.value, price, last_change, now_iso, ticker, timeframe))

            return state_changed, old_state

    def log_alert(
        self,
        ticker: str,
        timeframe: str,
        old_state: LarssonState,
        new_state: LarssonState,
        price: float,
        tv_symbol: str,
        now_iso: Optional[str] = None,
    ):
        """Records an alert in the alert history table."""
        if not now_iso:
            now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO alert_logs (ticker, timeframe, old_state, new_state, price, tv_symbol, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticker, timeframe, old_state.value, new_state.value, price, tv_symbol, now_iso))
