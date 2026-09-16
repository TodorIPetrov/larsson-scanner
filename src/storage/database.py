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
    def __init__(self, db_path: str = DEFAULT_DB_PATH, auto_restore: bool = False):
        self.db_path = db_path
        self._init_db()
        if auto_restore:
            self.restore_from_json_if_empty()

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

            # Table for user personal watchlist
            cur.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                added_at TEXT NOT NULL
            );
            """)

            # Table for internal key-value system metadata (e.g. last digest date)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Table for Support & Resistance (S/R) levels and zone clustering
            cur.execute("""
            CREATE TABLE IF NOT EXISTS symbol_sr_levels (
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                current_price REAL NOT NULL,
                atr REAL NOT NULL,
                s1 REAL,
                s1_touches INTEGER DEFAULT 0,
                s1_dist_pct REAL,
                s2 REAL,
                s2_touches INTEGER DEFAULT 0,
                r1 REAL,
                r1_touches INTEGER DEFAULT 0,
                r1_dist_pct REAL,
                r2 REAL,
                r2_touches INTEGER DEFAULT 0,
                context_flag TEXT,
                context_desc TEXT,
                all_zones_json TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (ticker, timeframe)
            );
            """)

            # Table for rule-based Trade Suggestions
            cur.execute("""
            CREATE TABLE IF NOT EXISTS symbol_trade_suggestions (
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                action TEXT NOT NULL,
                direction TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                rr_ratio REAL,
                score INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'NONE',
                reason_bg TEXT,
                reason_en TEXT,
                fund_verdict TEXT,
                fair_value REAL,
                mos_pct REAL,
                moat TEXT,
                z_score REAL,
                quantamental_tag TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (ticker, timeframe)
            );
            """)

            # Automatic column migrations for existing symbol_trade_suggestions table
            cur.execute("PRAGMA table_info(symbol_trade_suggestions)")
            existing_cols = {col[1] for col in cur.fetchall()}
            for col_name, col_type in [
                ("fund_verdict", "TEXT"),
                ("fair_value", "REAL"),
                ("mos_pct", "REAL"),
                ("moat", "TEXT"),
                ("z_score", "REAL"),
                ("quantamental_tag", "TEXT"),
            ]:
                if col_name not in existing_cols:
                    cur.execute(f"ALTER TABLE symbol_trade_suggestions ADD COLUMN {col_name} {col_type}")

    def restore_from_json_if_empty(self, json_path: Optional[str] = None) -> int:
        """
        If the database is fresh/empty (e.g., in a stateless CI/cloud runner),
        restores last known states from dashboard/data.json.
        """
        if json_path is None:
            json_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "dashboard",
                "data.json",
            )
        if not os.path.exists(json_path):
            return 0

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM symbol_states")
            count = cur.fetchone()[0]
            if count > 0:
                return count

            import json
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                symbols = []
                states = []
                for s in data.get("symbols", []):
                    symbols.append((s["ticker"], s["asset_class"], s["tv_symbol"]))
                    states.append((
                        s["ticker"],
                        s["timeframe"],
                        s.get("v1", 0.0),
                        s.get("m1", 0.0),
                        s.get("m2", 0.0),
                        s.get("v2", 0.0),
                        s["state"],
                        s.get("price", 0.0),
                        s.get("last_change", ""),
                        s.get("updated_at", ""),
                    ))

                if symbols:
                    cur.executemany("""
                    INSERT OR IGNORE INTO symbols (ticker, asset_class, tv_symbol, is_active)
                    VALUES (?, ?, ?, 1)
                    """, symbols)
                if states:
                    cur.executemany("""
                    INSERT OR REPLACE INTO symbol_states
                    (ticker, timeframe, v1, m1, m2, v2, current_state, last_price, last_state_change, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, states)
                return len(states)
            except Exception:
                return 0

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
        """Fetch all states across all symbols and timeframes, enriched with macro S/R levels and trade suggestions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT s.ticker, s.asset_class, s.tv_symbol, st.timeframe, st.v1, st.m1, st.m2, st.v2,
                   st.current_state, st.last_price, st.last_state_change, st.updated_at,
                   sr.s1, sr.s1_touches, sr.s1_dist_pct, sr.r1, sr.r1_touches, sr.r1_dist_pct,
                   sr.context_flag, sr.context_desc,
                   ts.action AS ts_action, ts.direction AS ts_direction, ts.setup_type AS ts_setup_type,
                   ts.entry_price AS ts_entry, ts.stop_loss AS ts_sl, ts.tp1 AS ts_tp1, ts.tp2 AS ts_tp2,
                   ts.rr_ratio AS ts_rr, ts.score AS ts_score, ts.tier AS ts_tier,
                   ts.reason_bg AS ts_reason_bg, ts.reason_en AS ts_reason_en,
                   ts.fund_verdict AS ts_fund_verdict, ts.fair_value AS ts_fair_value,
                   ts.mos_pct AS ts_mos_pct, ts.moat AS ts_moat, ts.z_score AS ts_z_score,
                   ts.quantamental_tag AS ts_quantamental_tag
            FROM symbols s
            JOIN symbol_states st ON s.ticker = st.ticker
            LEFT JOIN symbol_sr_levels sr ON s.ticker = sr.ticker 
                 AND sr.timeframe = COALESCE((SELECT timeframe FROM symbol_sr_levels WHERE ticker = s.ticker AND timeframe = '1D'), st.timeframe)
            LEFT JOIN symbol_trade_suggestions ts ON s.ticker = ts.ticker AND st.timeframe = ts.timeframe
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

    def add_to_watchlist(self, ticker: str) -> bool:
        """Adds a ticker to personal watchlist."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR IGNORE INTO watchlist (ticker, added_at) VALUES (?, ?)
            """, (ticker.upper(), now_iso))
            return cur.rowcount > 0

    def remove_from_watchlist(self, ticker: str) -> bool:
        """Removes a ticker from personal watchlist."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
            return cur.rowcount > 0

    def get_watchlist(self) -> List[str]:
        """Returns list of all watched tickers."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ticker FROM watchlist ORDER BY ticker")
            return [row["ticker"] for row in cur.fetchall()]

    def get_watchlist_states(self) -> List[sqlite3.Row]:
        """Returns all states for symbols in the personal watchlist."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT s.ticker, s.asset_class, s.tv_symbol, st.timeframe, st.v1, st.m1, st.m2, st.v2,
                   st.current_state, st.last_price, st.last_state_change, st.updated_at
            FROM watchlist w
            JOIN symbols s ON w.ticker = s.ticker
            JOIN symbol_states st ON s.ticker = st.ticker
            ORDER BY w.ticker, st.timeframe
            """)
            return cur.fetchall()

    def get_metadata(self, key: str) -> Optional[str]:
        """Retrieves a system metadata value by key."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_metadata WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def set_metadata(self, key: str, value: str):
        """Sets or updates a system metadata key-value pair."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO system_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """, (key, value, now_iso))

    def get_recent_alerts(self, hours: int = 24) -> List[sqlite3.Row]:
        """
        Retrieves alert logs recorded within the last N hours.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT ticker, timeframe, old_state, new_state, price, tv_symbol, created_at
            FROM alert_logs
            WHERE created_at >= ?
            ORDER BY created_at DESC
            """, (cutoff,))
            return cur.fetchall()

    def upsert_sr_levels(
        self,
        ticker: str,
        timeframe: str,
        current_price: float,
        atr: float,
        s1: Optional[float] = None,
        s1_touches: int = 0,
        s1_dist_pct: Optional[float] = None,
        s2: Optional[float] = None,
        s2_touches: int = 0,
        r1: Optional[float] = None,
        r1_touches: int = 0,
        r1_dist_pct: Optional[float] = None,
        r2: Optional[float] = None,
        r2_touches: int = 0,
        context_flag: str = "IN_VALUE_RANGE",
        context_desc: str = "",
        all_zones_json: str = "[]",
        now_iso: Optional[str] = None,
    ):
        """Inserts or updates the computed S/R levels for a symbol and timeframe."""
        if not now_iso:
            now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO symbol_sr_levels
            (ticker, timeframe, current_price, atr, s1, s1_touches, s1_dist_pct, s2, s2_touches,
             r1, r1_touches, r1_dist_pct, r2, r2_touches, context_flag, context_desc, all_zones_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, timeframe) DO UPDATE SET
                current_price = excluded.current_price,
                atr = excluded.atr,
                s1 = excluded.s1,
                s1_touches = excluded.s1_touches,
                s1_dist_pct = excluded.s1_dist_pct,
                s2 = excluded.s2,
                s2_touches = excluded.s2_touches,
                r1 = excluded.r1,
                r1_touches = excluded.r1_touches,
                r1_dist_pct = excluded.r1_dist_pct,
                r2 = excluded.r2,
                r2_touches = excluded.r2_touches,
                context_flag = excluded.context_flag,
                context_desc = excluded.context_desc,
                all_zones_json = excluded.all_zones_json,
                updated_at = excluded.updated_at;
            """, (
                ticker, timeframe, current_price, atr, s1, s1_touches, s1_dist_pct, s2, s2_touches,
                r1, r1_touches, r1_dist_pct, r2, r2_touches, context_flag, context_desc, all_zones_json, now_iso
            ))

    def get_sr_levels(self, ticker: str, timeframe: str) -> Optional[sqlite3.Row]:
        """Retrieves S/R levels for a specific ticker and timeframe."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM symbol_sr_levels WHERE ticker = ? AND timeframe = ?", (ticker, timeframe))
            return cur.fetchone()

    def upsert_trade_suggestion(
        self,
        ticker: str,
        timeframe: str,
        action: str,
        direction: str,
        setup_type: str,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        rr_ratio: Optional[float] = None,
        score: int = 0,
        tier: str = "NONE",
        reason_bg: str = "",
        reason_en: str = "",
        fund_verdict: Optional[str] = None,
        fair_value: Optional[float] = None,
        mos_pct: Optional[float] = None,
        moat: Optional[str] = None,
        z_score: Optional[float] = None,
        quantamental_tag: Optional[str] = None,
        now_iso: Optional[str] = None,
    ):
        """Inserts or updates a trade suggestion for a symbol and timeframe."""
        if not now_iso:
            now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO symbol_trade_suggestions
            (ticker, timeframe, action, direction, setup_type, entry_price, stop_loss,
             tp1, tp2, rr_ratio, score, tier, reason_bg, reason_en,
             fund_verdict, fair_value, mos_pct, moat, z_score, quantamental_tag, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, timeframe) DO UPDATE SET
                action = excluded.action,
                direction = excluded.direction,
                setup_type = excluded.setup_type,
                entry_price = excluded.entry_price,
                stop_loss = excluded.stop_loss,
                tp1 = excluded.tp1,
                tp2 = excluded.tp2,
                rr_ratio = excluded.rr_ratio,
                score = excluded.score,
                tier = excluded.tier,
                reason_bg = excluded.reason_bg,
                reason_en = excluded.reason_en,
                fund_verdict = excluded.fund_verdict,
                fair_value = excluded.fair_value,
                mos_pct = excluded.mos_pct,
                moat = excluded.moat,
                z_score = excluded.z_score,
                quantamental_tag = excluded.quantamental_tag,
                updated_at = excluded.updated_at;
            """, (
                ticker, timeframe, action, direction, setup_type, entry_price, stop_loss,
                tp1, tp2, rr_ratio, score, tier, reason_bg, reason_en,
                fund_verdict, fair_value, mos_pct, moat, z_score, quantamental_tag, now_iso
            ))

    def get_trade_suggestion(self, ticker: str, timeframe: str) -> Optional[sqlite3.Row]:
        """Retrieves trade suggestion for a specific ticker and timeframe."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM symbol_trade_suggestions WHERE ticker = ? AND timeframe = ?", (ticker, timeframe))
            return cur.fetchone()


