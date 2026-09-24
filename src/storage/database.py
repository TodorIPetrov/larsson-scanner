"""
Database and State Persistence for Larsson Line Scanner.
Uses SQLite with Write-Ahead Logging (WAL) mode for maximum concurrency and safety.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple

from src.engine.smma import LarssonState

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "state.db")


class Database:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, auto_restore: bool = False):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
        if auto_restore:
            self.restore_from_json_if_empty()

    def _get_thread_conn(self) -> sqlite3.Connection:
        """Returns or creates a thread-local SQLite connection with optimized PRAGMAs."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            # Enforce PRAGMAs on every new physical connection
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA cache_size=-64000;")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _get_connection(self):
        """Transactional context manager reusing the thread-local connection."""
        conn = self._get_thread_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        """Closes the thread-local database connection if active."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

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
                ("tech_action", "TEXT"),
                ("tech_label_bg", "TEXT"),
                ("tech_thesis_bg", "TEXT"),
                ("fund_action", "TEXT"),
                ("fund_label_bg", "TEXT"),
                ("fund_thesis_bg", "TEXT"),
                ("synthesis_badge_bg", "TEXT"),
                ("synthesis_label_bg", "TEXT"),
                ("btc_ratio_state", "TEXT DEFAULT 'NA'"),
                ("btc_alpha_30d", "REAL"),
                ("btc_alpha_7d", "REAL"),
                ("btc_ratio_spread", "REAL"),
                ("btc_verdict", "TEXT"),
                ("btc_badge_bg", "TEXT"),
                ("btc_thesis_bg", "TEXT"),
                ("btc_leverage_allowed", "INTEGER DEFAULT 1"),
            ]:
                if col_name not in existing_cols:
                    cur.execute(f"ALTER TABLE symbol_trade_suggestions ADD COLUMN {col_name} {col_type}")

            # Table for Trade Proposals requiring user confirmation
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                position_size_usd REAL NOT NULL,
                units REAL NOT NULL,
                risk_usd REAL,
                tier TEXT,
                score INTEGER,
                reason TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                responded_at TEXT,
                message_id INTEGER,
                direction TEXT DEFAULT 'LONG',
                max_leverage INTEGER DEFAULT 1,
                recommended_leverage INTEGER DEFAULT 1,
                leverage_selected INTEGER,
                margin_usd REAL,
                notional_usd REAL,
                liquidation_price REAL
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_proposals_status ON trade_proposals(status);")

            # Automatic column migrations for trade_proposals
            cur.execute("PRAGMA table_info(trade_proposals)")
            tp_cols = {col[1] for col in cur.fetchall()}
            for col_name, col_type in [
                ("direction", "TEXT DEFAULT 'LONG'"),
                ("max_leverage", "INTEGER DEFAULT 1"),
                ("recommended_leverage", "INTEGER DEFAULT 1"),
                ("leverage_selected", "INTEGER"),
                ("margin_usd", "REAL"),
                ("notional_usd", "REAL"),
                ("liquidation_price", "REAL"),
            ]:
                if col_name not in tp_cols:
                    cur.execute(f"ALTER TABLE trade_proposals ADD COLUMN {col_name} {col_type}")

            # Table for Paper Positions (simulated spot/leverage portfolio)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_price REAL NOT NULL,
                units REAL NOT NULL,
                position_size_usd REAL NOT NULL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                realized_pnl_usd REAL,
                realized_pnl_pct REAL,
                fee_paid_usd REAL DEFAULT 0.0,
                exit_reason TEXT,
                proposal_id TEXT,
                direction TEXT DEFAULT 'LONG',
                leverage INTEGER DEFAULT 1,
                margin_usd REAL,
                notional_usd REAL,
                liquidation_price REAL,
                funding_fee_usd REAL DEFAULT 0.0
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status);")

            # Automatic column migrations for paper_positions
            cur.execute("PRAGMA table_info(paper_positions)")
            pp_cols = {col[1] for col in cur.fetchall()}
            for col_name, col_type in [
                ("direction", "TEXT DEFAULT 'LONG'"),
                ("leverage", "INTEGER DEFAULT 1"),
                ("margin_usd", "REAL"),
                ("notional_usd", "REAL"),
                ("liquidation_price", "REAL"),
                ("funding_fee_usd", "REAL DEFAULT 0.0"),
            ]:
                if col_name not in pp_cols:
                    cur.execute(f"ALTER TABLE paper_positions ADD COLUMN {col_name} {col_type}")

            # Table for Paper Account balance
            cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_account (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Table for Real Live Positions (Separated from Paper Trading)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS real_positions (
                position_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL,  -- 'OPEN', 'CLOSED'
                asset_class TEXT NOT NULL,
                entry_price REAL NOT NULL,
                units REAL NOT NULL,
                position_size_usd REAL NOT NULL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                realized_pnl_usd REAL,
                realized_pnl_pct REAL,
                fee_paid_usd REAL DEFAULT 0.0,
                broker_exchange TEXT,
                notes TEXT
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_real_positions_status ON real_positions(status);")

            # Table for Real Account balance
            cur.execute("""
            CREATE TABLE IF NOT EXISTS real_account (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # Portfolio equity snapshots (daily tracking)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_equity REAL NOT NULL,
                cash REAL NOT NULL,
                invested REAL NOT NULL,
                daily_pnl REAL DEFAULT 0.0,
                daily_pnl_pct REAL DEFAULT 0.0,
                open_positions_count INTEGER DEFAULT 0,
                cumulative_win_rate REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Detailed trade log / journal (supports both 'PAPER' and 'REAL')
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                portfolio_type TEXT NOT NULL DEFAULT 'PAPER',  -- 'PAPER' or 'REAL'
                action TEXT NOT NULL,  -- 'OPEN', 'PARTIAL_CLOSE', 'CLOSE', 'SL_UPDATE', 'TP_UPDATE', 'NOTE'
                price REAL,
                quantity REAL,
                pnl_usd REAL,
                pnl_pct REAL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Migration in case trade_log was created without portfolio_type
            try:
                cur.execute("ALTER TABLE trade_log ADD COLUMN portfolio_type TEXT NOT NULL DEFAULT 'PAPER';")
            except Exception:
                pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_ticker ON trade_log(ticker);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_position ON trade_log(position_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_log_port_type ON trade_log(portfolio_type);")

            # Pending setup queue
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_setups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'MEDIUM',
                quality_score REAL DEFAULT 0.0,
                description_bg TEXT,
                description_en TEXT,
                conditions_met TEXT,  -- JSON array of strings
                conditions_pending TEXT,  -- JSON array of strings
                estimated_trigger TEXT,
                current_price REAL,
                target_entry REAL,
                target_sl REAL,
                target_tp1 REAL,
                key_level REAL,
                timeframe TEXT DEFAULT '1D',
                tier TEXT DEFAULT 'B',
                status TEXT NOT NULL DEFAULT 'ACTIVE',  -- 'ACTIVE', 'TRIGGERED', 'EXPIRED', 'CANCELLED'
                first_detected TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                triggered_at TEXT,
                UNIQUE(symbol, setup_type, timeframe)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pending_setups_status ON pending_setups(status);")

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
                   ts.quantamental_tag AS ts_quantamental_tag,
                   ts.tech_action AS ts_tech_action, ts.tech_label_bg AS ts_tech_label_bg, ts.tech_thesis_bg AS ts_tech_thesis_bg,
                   ts.fund_action AS ts_fund_action, ts.fund_label_bg AS ts_fund_label_bg, ts.fund_thesis_bg AS ts_fund_thesis_bg,
                   ts.synthesis_badge_bg AS ts_synthesis_badge_bg, ts.synthesis_label_bg AS ts_synthesis_label_bg,
                   ts.btc_ratio_state AS ts_btc_ratio_state, ts.btc_alpha_30d AS ts_btc_alpha_30d,
                   ts.btc_alpha_7d AS ts_btc_alpha_7d, ts.btc_ratio_spread AS ts_btc_ratio_spread,
                   ts.btc_verdict AS ts_btc_verdict, ts.btc_badge_bg AS ts_btc_badge_bg,
                   ts.btc_thesis_bg AS ts_btc_thesis_bg, ts.btc_leverage_allowed AS ts_btc_leverage_allowed
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
        tech_action: str = "WAIT",
        tech_label_bg: str = "⏳ ИЗЧАКАЙ",
        tech_thesis_bg: str = "",
        fund_action: str = "SPECULATIVE_NA",
        fund_label_bg: str = "⚪ МАКРО / СПЕКУЛАТИВЕН",
        fund_thesis_bg: str = "",
        synthesis_badge_bg: str = "⏳ WAIT",
        synthesis_label_bg: str = "",
        btc_ratio_state: str = "NA",
        btc_alpha_30d: Optional[float] = None,
        btc_alpha_7d: Optional[float] = None,
        btc_ratio_spread: Optional[float] = None,
        btc_verdict: Optional[str] = None,
        btc_badge_bg: Optional[str] = None,
        btc_thesis_bg: Optional[str] = None,
        btc_leverage_allowed: int = 1,
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
             fund_verdict, fair_value, mos_pct, moat, z_score, quantamental_tag,
             tech_action, tech_label_bg, tech_thesis_bg,
             fund_action, fund_label_bg, fund_thesis_bg,
             synthesis_badge_bg, synthesis_label_bg,
             btc_ratio_state, btc_alpha_30d, btc_alpha_7d, btc_ratio_spread,
             btc_verdict, btc_badge_bg, btc_thesis_bg, btc_leverage_allowed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                tech_action = excluded.tech_action,
                tech_label_bg = excluded.tech_label_bg,
                tech_thesis_bg = excluded.tech_thesis_bg,
                fund_action = excluded.fund_action,
                fund_label_bg = excluded.fund_label_bg,
                fund_thesis_bg = excluded.fund_thesis_bg,
                synthesis_badge_bg = excluded.synthesis_badge_bg,
                synthesis_label_bg = excluded.synthesis_label_bg,
                btc_ratio_state = excluded.btc_ratio_state,
                btc_alpha_30d = excluded.btc_alpha_30d,
                btc_alpha_7d = excluded.btc_alpha_7d,
                btc_ratio_spread = excluded.btc_ratio_spread,
                btc_verdict = excluded.btc_verdict,
                btc_badge_bg = excluded.btc_badge_bg,
                btc_thesis_bg = excluded.btc_thesis_bg,
                btc_leverage_allowed = excluded.btc_leverage_allowed,
                updated_at = excluded.updated_at;
            """, (
                ticker, timeframe, action, direction, setup_type, entry_price, stop_loss,
                tp1, tp2, rr_ratio, score, tier, reason_bg, reason_en,
                fund_verdict, fair_value, mos_pct, moat, z_score, quantamental_tag,
                tech_action, tech_label_bg, tech_thesis_bg,
                fund_action, fund_label_bg, fund_thesis_bg,
                synthesis_badge_bg, synthesis_label_bg,
                btc_ratio_state, btc_alpha_30d, btc_alpha_7d, btc_ratio_spread,
                btc_verdict, btc_badge_bg, btc_thesis_bg, btc_leverage_allowed, now_iso
            ))

    def get_trade_suggestion(self, ticker: str, timeframe: str) -> Optional[sqlite3.Row]:
        """Retrieves trade suggestion for a specific ticker and timeframe."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM symbol_trade_suggestions WHERE ticker = ? AND timeframe = ?", (ticker, timeframe))
            return cur.fetchone()

    # --- Paper Trading & Trade Proposals ---

    def create_trade_proposal(
        self,
        proposal_id: str,
        ticker: str,
        timeframe: str,
        action: str,
        entry_price: float,
        stop_loss: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        position_size_usd: float,
        units: float,
        risk_usd: Optional[float],
        tier: str,
        score: int,
        reason: str,
        created_at: str,
        expires_at: str,
        status: str = "PENDING",
        direction: str = "LONG",
        max_leverage: int = 1,
        recommended_leverage: int = 1,
        margin_usd: Optional[float] = None,
        notional_usd: Optional[float] = None,
        liquidation_price: Optional[float] = None,
    ) -> bool:
        """Inserts a new trade proposal."""
        if notional_usd is None:
            notional_usd = position_size_usd
        if margin_usd is None:
            margin_usd = round(position_size_usd / max(1, recommended_leverage), 2)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO trade_proposals
            (proposal_id, ticker, timeframe, action, status, entry_price, stop_loss,
             tp1, tp2, position_size_usd, units, risk_usd, tier, score, reason,
             created_at, expires_at, direction, max_leverage, recommended_leverage,
             margin_usd, notional_usd, liquidation_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proposal_id, ticker, timeframe, action, status, entry_price, stop_loss,
                tp1, tp2, position_size_usd, units, risk_usd, tier, score, reason,
                created_at, expires_at, direction, max_leverage, recommended_leverage,
                margin_usd, notional_usd, liquidation_price
            ))
            return True

    def get_proposal(self, proposal_id: str) -> Optional[sqlite3.Row]:
        """Retrieves a proposal by its ID."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trade_proposals WHERE proposal_id = ?", (proposal_id,))
            return cur.fetchone()

    def get_pending_proposals(self) -> List[sqlite3.Row]:
        """Returns all currently pending proposals."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trade_proposals WHERE status = 'PENDING' ORDER BY created_at DESC")
            return cur.fetchall()

    def update_proposal_status(
        self,
        proposal_id: str,
        status: str,
        responded_at: Optional[str] = None,
        leverage_selected: Optional[int] = None,
    ) -> bool:
        """Updates proposal status (APPROVED, REJECTED, EXPIRED, FILLED)."""
        if not responded_at and status in ["APPROVED", "REJECTED"]:
            responded_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE trade_proposals
            SET status = ?,
                responded_at = COALESCE(?, responded_at),
                leverage_selected = COALESCE(?, leverage_selected)
            WHERE proposal_id = ?
            """, (status, responded_at, leverage_selected, proposal_id))
            return cur.rowcount > 0

    def update_proposal_message_id(self, proposal_id: str, message_id: int) -> bool:
        """Saves the Telegram message_id corresponding to this proposal for editing."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE trade_proposals SET message_id = ? WHERE proposal_id = ?", (message_id, proposal_id))
            return cur.rowcount > 0

    def expire_old_proposals(self, now_iso: Optional[str] = None) -> int:
        """Marks proposals past their expires_at as EXPIRED."""
        if not now_iso:
            now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE trade_proposals
            SET status = 'EXPIRED'
            WHERE status = 'PENDING' AND expires_at <= ?
            """, (now_iso,))
            return cur.rowcount

    def open_paper_position(
        self,
        position_id: str,
        ticker: str,
        entry_price: float,
        units: float,
        position_size_usd: float,
        stop_loss: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        opened_at: str,
        proposal_id: Optional[str] = None,
        fee_paid_usd: float = 0.0,
        direction: str = "LONG",
        leverage: int = 1,
        margin_usd: Optional[float] = None,
        notional_usd: Optional[float] = None,
        liquidation_price: Optional[float] = None,
        funding_fee_usd: float = 0.0,
    ) -> bool:
        """Opens a new simulated spot or leverage paper position."""
        if notional_usd is None:
            notional_usd = position_size_usd
        if margin_usd is None:
            margin_usd = round(position_size_usd / max(1, leverage), 2)

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO paper_positions
            (position_id, ticker, status, entry_price, units, position_size_usd,
             stop_loss, tp1, tp2, opened_at, proposal_id, fee_paid_usd,
             direction, leverage, margin_usd, notional_usd, liquidation_price, funding_fee_usd)
            VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_id, ticker, entry_price, units, position_size_usd,
                stop_loss, tp1, tp2, opened_at, proposal_id, fee_paid_usd,
                direction, leverage, margin_usd, notional_usd, liquidation_price, funding_fee_usd
            ))
            return True

    def get_open_paper_positions(self) -> List[sqlite3.Row]:
        """Returns all open paper positions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY opened_at DESC")
            return cur.fetchall()

    def get_open_paper_position_by_ticker(self, ticker: str) -> Optional[sqlite3.Row]:
        """Returns the active open position for a given ticker, if any."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM paper_positions WHERE ticker = ? AND status = 'OPEN' LIMIT 1", (ticker,))
            return cur.fetchone()

    def close_paper_position(
        self,
        position_id: str,
        exit_price: float,
        realized_pnl_usd: float,
        realized_pnl_pct: float,
        fee_paid_usd: float,
        exit_reason: str,
        closed_at: Optional[str] = None,
    ) -> bool:
        """Closes an open paper position and logs realized PnL."""
        if not closed_at:
            closed_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE paper_positions
            SET status = 'CLOSED',
                exit_price = ?,
                realized_pnl_usd = ?,
                realized_pnl_pct = ?,
                fee_paid_usd = fee_paid_usd + ?,
                exit_reason = ?,
                closed_at = ?
            WHERE position_id = ? AND status = 'OPEN'
            """, (exit_price, realized_pnl_usd, realized_pnl_pct, fee_paid_usd, exit_reason, closed_at, position_id))
            return cur.rowcount > 0

    def update_paper_position_after_tp1(
        self,
        position_id: str,
        remaining_units: float,
        remaining_size_usd: float,
        realized_pnl_usd: float,
        fee_paid_usd: float,
        new_stop_loss: float,
        remaining_margin_usd: Optional[float] = None,
    ) -> bool:
        """
        Partially closes 50% of position at TP1, updates remaining units and size,
        adds to realized PnL, adjusts Stop-Loss to Breakeven, and clears tp1.
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            if remaining_margin_usd is not None:
                cur.execute("""
                UPDATE paper_positions
                SET units = ?,
                    position_size_usd = ?,
                    margin_usd = ?,
                    realized_pnl_usd = COALESCE(realized_pnl_usd, 0.0) + ?,
                    fee_paid_usd = fee_paid_usd + ?,
                    stop_loss = ?,
                    tp1 = NULL
                WHERE position_id = ? AND status = 'OPEN'
                """, (remaining_units, remaining_size_usd, remaining_margin_usd, realized_pnl_usd, fee_paid_usd, new_stop_loss, position_id))
            else:
                cur.execute("""
                UPDATE paper_positions
                SET units = ?,
                    position_size_usd = ?,
                    margin_usd = margin_usd * 0.5,
                    realized_pnl_usd = COALESCE(realized_pnl_usd, 0.0) + ?,
                    fee_paid_usd = fee_paid_usd + ?,
                    stop_loss = ?,
                    tp1 = NULL
                WHERE position_id = ? AND status = 'OPEN'
                """, (remaining_units, remaining_size_usd, realized_pnl_usd, fee_paid_usd, new_stop_loss, position_id))
            return cur.rowcount > 0

    def get_closed_paper_positions(self, limit: int = 50) -> List[sqlite3.Row]:
        """Returns closed paper positions ordered by close time."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM paper_positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def get_paper_balance(self, initial_balance: float = 10000.0) -> Dict[str, float]:
        """Returns paper account balance (available cash and initial balance)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM paper_account WHERE key = 'available_cash'")
            row = cur.fetchone()
            if row is None:
                # Initialize
                now_iso = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    "INSERT INTO paper_account (key, value, updated_at) VALUES ('available_cash', ?, ?)",
                    (initial_balance, now_iso),
                )
                cur.execute(
                    "INSERT INTO paper_account (key, value, updated_at) VALUES ('initial_balance', ?, ?)",
                    (initial_balance, now_iso),
                )
                return {"available_cash": initial_balance, "initial_balance": initial_balance}

            cur.execute("SELECT value FROM paper_account WHERE key = 'initial_balance'")
            init_row = cur.fetchone()
            init_val = init_row["value"] if init_row else initial_balance
            return {"available_cash": row["value"], "initial_balance": init_val}

    def update_paper_balance(self, cash_delta: float, initial_balance: float = 10000.0) -> float:
        """Modifies available paper cash by cash_delta (positive or negative)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            bal = self.get_paper_balance(initial_balance=initial_balance)
            new_cash = bal["available_cash"] + cash_delta
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "UPDATE paper_account SET value = ?, updated_at = ? WHERE key = 'available_cash'",
                (new_cash, now_iso),
            )
            return new_cash

    # === Portfolio Equity Tracking ===

    def record_portfolio_equity(self, date: str, total_equity: float, cash: float, 
                                invested: float, daily_pnl: float = 0.0, 
                                daily_pnl_pct: float = 0.0, open_positions_count: int = 0,
                                cumulative_win_rate: Optional[float] = None):
        """Records daily portfolio equity snapshot. Upserts on date."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO portfolio_equity 
            (date, total_equity, cash, invested, daily_pnl, daily_pnl_pct, open_positions_count, cumulative_win_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_equity = excluded.total_equity,
                cash = excluded.cash,
                invested = excluded.invested,
                daily_pnl = excluded.daily_pnl,
                daily_pnl_pct = excluded.daily_pnl_pct,
                open_positions_count = excluded.open_positions_count,
                cumulative_win_rate = excluded.cumulative_win_rate;
            """, (date, total_equity, cash, invested, daily_pnl, daily_pnl_pct, open_positions_count, cumulative_win_rate))

    def get_portfolio_equity_history(self, days: int = 90) -> List[sqlite3.Row]:
        """Returns the last N days of portfolio equity snapshots."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM portfolio_equity ORDER BY date DESC LIMIT ?", (days,))
            return cur.fetchall()

    def get_latest_portfolio_equity(self) -> Optional[sqlite3.Row]:
        """Returns the most recent portfolio equity snapshot."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM portfolio_equity ORDER BY date DESC LIMIT 1")
            return cur.fetchone()

    # === Trade Log / Journal ===

    def add_trade_log_entry(self, position_id: str, ticker: str, action: str, 
                            price: Optional[float] = None, quantity: Optional[float] = None,
                            pnl_usd: Optional[float] = None, pnl_pct: Optional[float] = None,
                            notes: Optional[str] = None, portfolio_type: str = "PAPER"):
        """Adds an entry to the trade journal ('PAPER' or 'REAL')."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO trade_log (position_id, ticker, portfolio_type, action, price, quantity, pnl_usd, pnl_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (position_id, ticker, portfolio_type, action, price, quantity, pnl_usd, pnl_pct, notes))

    def get_trade_log(self, ticker: Optional[str] = None, portfolio_type: Optional[str] = None, limit: int = 50) -> List[sqlite3.Row]:
        """Returns recent trade log entries, optionally filtered by ticker and portfolio_type ('PAPER'/'REAL')."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT * FROM trade_log"
            clauses = []
            params = []
            if ticker:
                clauses.append("ticker = ?")
                params.append(ticker)
            if portfolio_type:
                clauses.append("portfolio_type = ?")
                params.append(portfolio_type)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC, id DESC LIMIT ?"
            params.append(limit)
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def get_trade_log_for_position(self, position_id: str) -> List[sqlite3.Row]:
        """Returns all trade log entries for a specific position."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trade_log WHERE position_id = ? ORDER BY created_at ASC", (position_id,))
            return cur.fetchall()

    # === Pending Setups Queue ===

    def upsert_pending_setup(self, symbol: str, asset_class: str, setup_type: str,
                              direction: str, priority: str, quality_score: float,
                              description_bg: str, description_en: str,
                              conditions_met: str, conditions_pending: str,
                              estimated_trigger: str, current_price: float,
                              target_entry: Optional[float], target_sl: Optional[float],
                              target_tp1: Optional[float], key_level: Optional[float],
                              timeframe: str, tier: str):
        """Inserts or updates a pending setup in the queue."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO pending_setups 
            (symbol, asset_class, setup_type, direction, priority, quality_score, description_bg, description_en,
             conditions_met, conditions_pending, estimated_trigger, current_price, target_entry, target_sl,
             target_tp1, key_level, timeframe, tier, status, first_detected, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', COALESCE((SELECT first_detected FROM pending_setups WHERE symbol=? AND setup_type=? AND timeframe=?), ?), ?)
            ON CONFLICT(symbol, setup_type, timeframe) DO UPDATE SET
                asset_class = excluded.asset_class,
                direction = excluded.direction,
                priority = excluded.priority,
                quality_score = excluded.quality_score,
                description_bg = excluded.description_bg,
                description_en = excluded.description_en,
                conditions_met = excluded.conditions_met,
                conditions_pending = excluded.conditions_pending,
                estimated_trigger = excluded.estimated_trigger,
                current_price = excluded.current_price,
                target_entry = excluded.target_entry,
                target_sl = excluded.target_sl,
                target_tp1 = excluded.target_tp1,
                key_level = excluded.key_level,
                tier = excluded.tier,
                status = 'ACTIVE',
                last_updated = excluded.last_updated;
            """, (symbol, asset_class, setup_type, direction, priority, quality_score, description_bg, description_en,
                  conditions_met, conditions_pending, estimated_trigger, current_price, target_entry, target_sl,
                  target_tp1, key_level, timeframe, tier, symbol, setup_type, timeframe, now, now))

    def get_active_pending_setups(self, asset_class: Optional[str] = None,
                                   priority: Optional[str] = None,
                                   tier: Optional[str] = None) -> List[sqlite3.Row]:
        """Returns all active pending setups, optionally filtered."""
        query = "SELECT * FROM pending_setups WHERE status = 'ACTIVE'"
        params = []
        if asset_class:
            query += " AND asset_class = ?"
            params.append(asset_class)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        query += " ORDER BY quality_score DESC"
        
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            return cur.fetchall()

    def mark_setup_triggered(self, symbol: str, setup_type: str, timeframe: str):
        """Marks a pending setup as triggered when it becomes an active trade suggestion."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE pending_setups
            SET status = 'TRIGGERED', triggered_at = ?, last_updated = ?
            WHERE symbol = ? AND setup_type = ? AND timeframe = ? AND status = 'ACTIVE'
            """, (now, now, symbol, setup_type, timeframe))

    def expire_stale_setups(self, max_age_hours: int = 168):
        """Expires setups that have been pending for too long without triggering."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE pending_setups
            SET status = 'EXPIRED', last_updated = ?
            WHERE status = 'ACTIVE' AND last_updated < ?
            """, (now, cutoff))

    def clear_triggered_setups(self):
        """Removes setups with status='TRIGGERED' older than 24 hours."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            DELETE FROM pending_setups
            WHERE status = 'TRIGGERED' AND triggered_at < ?
            """, (cutoff,))

    # === Enhanced Portfolio Queries ===

    def get_portfolio_allocation(self) -> Dict[str, float]:
        """Returns allocation breakdown by asset class from open positions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT s.asset_class, SUM(p.position_size_usd) as total_size
            FROM paper_positions p
            JOIN symbols s ON p.ticker = s.ticker
            WHERE p.status = 'OPEN'
            GROUP BY s.asset_class
            """)
            allocations = {}
            for row in cur.fetchall():
                allocations[row["asset_class"]] = float(row["total_size"])
            
            total = sum(allocations.values())
            if total > 0:
                return {k: (v / total) * 100.0 for k, v in allocations.items()}
            return {}

    def get_portfolio_performance_stats(self) -> dict:
        """Returns aggregate performance stats from closed positions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl_usd <= 0 THEN 1 ELSE 0 END) as losses,
                AVG(realized_pnl_pct) as avg_pnl_pct,
                MAX(realized_pnl_pct) as best_trade_pct,
                MIN(realized_pnl_pct) as worst_trade_pct,
                SUM(realized_pnl_usd) as total_realized_pnl,
                SUM(fee_paid_usd) as total_fees
            FROM paper_positions
            WHERE status = 'CLOSED'
            """)
            row = cur.fetchone()
            
            if not row or row["total_trades"] == 0:
                return {
                    "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "avg_pnl_pct": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
                    "total_realized_pnl": 0.0, "total_fees": 0.0
                }
                
            total_trades = row["total_trades"]
            wins = row["wins"]
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            
            return {
                "total_trades": total_trades,
                "wins": wins,
                "losses": row["losses"],
                "win_rate": round(win_rate, 2),
                "avg_pnl_pct": round(row["avg_pnl_pct"] or 0.0, 2),
                "best_trade": round(row["best_trade_pct"] or 0.0, 2),
                "worst_trade": round(row["worst_trade_pct"] or 0.0, 2),
                "total_realized_pnl": round(row["total_realized_pnl"] or 0.0, 2),
                "total_fees": round(row["total_fees"] or 0.0, 2)
            }

    # =========================================================================
    # REAL PORTFOLIO (LIVE / ACTUAL USER HOLDINGS) OPERATIONS
    # =========================================================================

    def open_real_position(
        self,
        position_id: str,
        ticker: str,
        asset_class: str,
        entry_price: float,
        units: float,
        position_size_usd: float,
        stop_loss: Optional[float] = None,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        opened_at: Optional[str] = None,
        broker_exchange: Optional[str] = None,
        notes: Optional[str] = None,
        fee_paid_usd: float = 0.0,
    ) -> bool:
        """Opens a real-money position record."""
        if not opened_at:
            opened_at = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO real_positions
            (position_id, ticker, status, asset_class, entry_price, units, position_size_usd,
             stop_loss, tp1, tp2, opened_at, broker_exchange, notes, fee_paid_usd)
            VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_id, ticker, asset_class, entry_price, units, position_size_usd,
                stop_loss, tp1, tp2, opened_at, broker_exchange, notes, fee_paid_usd
            ))
            return True

    def get_open_real_positions(self) -> List[sqlite3.Row]:
        """Returns all open real-money positions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM real_positions WHERE status = 'OPEN' ORDER BY opened_at DESC")
            return cur.fetchall()

    def get_open_real_position_by_ticker(self, ticker: str) -> Optional[sqlite3.Row]:
        """Returns active open real position for a ticker."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM real_positions WHERE ticker = ? AND status = 'OPEN' LIMIT 1", (ticker,))
            return cur.fetchone()

    def close_real_position(
        self,
        position_id: str,
        exit_price: float,
        realized_pnl_usd: float,
        realized_pnl_pct: float,
        fee_paid_usd: float = 0.0,
        notes: Optional[str] = None,
        closed_at: Optional[str] = None,
    ) -> bool:
        """Closes a real-money position and logs realized PnL."""
        if not closed_at:
            closed_at = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE real_positions
            SET status = 'CLOSED',
                exit_price = ?,
                realized_pnl_usd = ?,
                realized_pnl_pct = ?,
                fee_paid_usd = fee_paid_usd + ?,
                notes = COALESCE(?, notes),
                closed_at = ?
            WHERE position_id = ? AND status = 'OPEN'
            """, (exit_price, realized_pnl_usd, realized_pnl_pct, fee_paid_usd, notes, closed_at, position_id))
            return cur.rowcount > 0

    def get_closed_real_positions(self, limit: int = 50) -> List[sqlite3.Row]:
        """Returns closed real positions ordered by close time."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM real_positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def get_real_balance(self, initial_balance: float = 0.0) -> Dict[str, float]:
        """Returns real cash balance."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM real_account WHERE key = 'available_cash'")
            row = cur.fetchone()
            if row is None:
                now_iso = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    "INSERT INTO real_account (key, value, updated_at) VALUES ('available_cash', ?, ?)",
                    (initial_balance, now_iso),
                )
                cur.execute(
                    "INSERT INTO real_account (key, value, updated_at) VALUES ('initial_balance', ?, ?)",
                    (initial_balance, now_iso),
                )
                return {"available_cash": initial_balance, "initial_balance": initial_balance}
            
            cur.execute("SELECT value FROM real_account WHERE key = 'initial_balance'")
            init_row = cur.fetchone()
            init_val = init_row["value"] if init_row else initial_balance
            return {"available_cash": row["value"], "initial_balance": init_val}

    def update_real_balance(self, amount: float, initial_balance: float = 0.0) -> float:
        """Updates real cash balance (adds positive amount, subtracts negative)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            bal = self.get_real_balance(initial_balance=initial_balance)
            new_val = max(0.0, bal["available_cash"] + amount)
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "UPDATE real_account SET value = ?, updated_at = ? WHERE key = 'available_cash'",
                (new_val, now_iso),
            )
            return new_val

    def set_real_cash(self, cash: float) -> float:
        """Explicitly sets the real available cash."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO real_account (key, value, updated_at) VALUES ('available_cash', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (cash, now_iso))
            return cash

    def get_real_portfolio_allocation(self) -> dict:
        """Returns allocation percentage breakdown by asset class for real portfolio."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT asset_class, SUM(position_size_usd) as total_size
            FROM real_positions
            WHERE status = 'OPEN'
            GROUP BY asset_class
            """)
            allocations = {}
            for row in cur.fetchall():
                allocations[row["asset_class"]] = float(row["total_size"])
            total = sum(allocations.values())
            if total > 0:
                return {k: (v / total) * 100.0 for k, v in allocations.items()}
            return {}

    def get_real_portfolio_performance_stats(self) -> dict:
        """Returns aggregate performance stats from closed real positions."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl_usd <= 0 THEN 1 ELSE 0 END) as losses,
                AVG(realized_pnl_pct) as avg_pnl_pct,
                MAX(realized_pnl_pct) as best_trade_pct,
                MIN(realized_pnl_pct) as worst_trade_pct,
                SUM(realized_pnl_usd) as total_realized_pnl,
                SUM(fee_paid_usd) as total_fees
            FROM real_positions
            WHERE status = 'CLOSED'
            """)
            row = cur.fetchone()
            if not row or row["total_trades"] == 0:
                return {
                    "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "avg_pnl_pct": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
                    "total_realized_pnl": 0.0, "total_fees": 0.0
                }
            total_trades = row["total_trades"]
            wins = row["wins"]
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            return {
                "total_trades": total_trades,
                "wins": wins,
                "losses": row["losses"],
                "win_rate": round(win_rate, 2),
                "avg_pnl_pct": round(row["avg_pnl_pct"] or 0.0, 2),
                "best_trade": round(row["best_trade_pct"] or 0.0, 2),
                "worst_trade": round(row["worst_trade_pct"] or 0.0, 2),
                "total_realized_pnl": round(row["total_realized_pnl"] or 0.0, 2),
                "total_fees": round(row["total_fees"] or 0.0, 2)
            }


