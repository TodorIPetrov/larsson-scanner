"""
Cross-Asset Regime Breadth Index Engine.
Computes macro risk-appetite indices, sector breadth percentages (% Gold, % Blue, % Neutral),
velocity of breadth shifts (Delta Breadth), and classifies institutional macro market regimes.
Persists historical snapshots in SQLite for trend and exhaustion detection.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "state.db")


@dataclass
class SectorBreadth:
    sector_name: str
    total: int
    gold_count: int
    blue_count: int
    neutral_count: int
    gold_pct: float
    blue_pct: float
    neutral_pct: float
    regime: str  # BULL, BEAR, NEUTRAL, MIXED


@dataclass
class RegimeBreadthSnapshot:
    timestamp: str
    total_assets: int
    global_gold_pct: float
    global_blue_pct: float
    global_neutral_pct: float
    macro_regime: str
    sectors: Dict[str, SectorBreadth]
    delta_7d_gold_pct: Optional[float] = None
    delta_30d_gold_pct: Optional[float] = None


class RegimeBreadthEngine:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        """Ensures regime_breadth_history table exists in SQLite database."""
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                CREATE TABLE IF NOT EXISTS regime_breadth_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL UNIQUE,
                    total_assets INTEGER NOT NULL,
                    global_gold_pct REAL NOT NULL,
                    global_blue_pct REAL NOT NULL,
                    global_neutral_pct REAL NOT NULL,
                    macro_regime TEXT NOT NULL,
                    delta_7d_gold_pct REAL,
                    delta_30d_gold_pct REAL,
                    sectors_json TEXT NOT NULL
                );
                """)
        except Exception as e:
            logger.warning(f"Could not initialize regime_breadth_history table: {e}")

    def classify_macro_regime(
        self,
        global_gold: float,
        global_blue: float,
        crypto_gold: Optional[float] = None,
        equities_gold: Optional[float] = None,
    ) -> str:
        """
        Classifies macro regime from aggregate cross-asset breadth percentages.
        """
        if global_blue >= 60.0:
            return "BROAD_LIQUIDITY_DRAIN"

        if global_blue >= 50.0:
            return "DEFENSIVE_RISK_OFF"

        if equities_gold is not None and crypto_gold is not None:
            if equities_gold >= 55.0 and crypto_gold >= 55.0:
                return "AGGRESSIVE_RISK_ON"
            if equities_gold >= 55.0 and crypto_gold < 35.0:
                return "EQUITY_SELECTIVE_BULL"
            if crypto_gold >= 55.0 and equities_gold < 35.0:
                return "CRYPTO_DECOUPLED_BULL"

        if global_gold >= 55.0:
            return "BROAD_RISK_ON"

        if global_gold < 35.0 and global_blue < 35.0:
            return "CONSOLIDATION_CHOP"

        return "ROTATIONAL_MIXED"

    def compute_snapshot(
        self,
        scan_results: List[Dict[str, Any]],
        historical_snapshots: Optional[List[RegimeBreadthSnapshot]] = None,
    ) -> RegimeBreadthSnapshot:
        """
        Aggregates scanned assets into sector and cross-asset breadth index.
        """
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if not scan_results:
            return RegimeBreadthSnapshot(
                timestamp=now_ts,
                total_assets=0,
                global_gold_pct=0.0,
                global_blue_pct=0.0,
                global_neutral_pct=0.0,
                macro_regime="UNKNOWN",
                sectors={},
            )

        # Map asset class to standard sectors
        sector_mapping = {
            "crypto": "Crypto",
            "crypto_stocks": "Crypto Stocks",
            "us_stocks": "US Equities",
            "ai_stocks": "AI & Tech",
            "intl_stocks": "International",
            "commodities": "Commodities",
            "indices": "Indices",
        }

        sector_buckets: Dict[str, List[Dict[str, Any]]] = {}
        global_states = {"GOLD": 0, "BLUE": 0, "NEUTRAL": 0}

        for item in scan_results:
            raw_ac = item.get("asset_class", "other")
            sector = sector_mapping.get(raw_ac, raw_ac.capitalize())
            if sector not in sector_buckets:
                sector_buckets[sector] = []
            sector_buckets[sector].append(item)

            state = str(item.get("state", "NEUTRAL")).upper()
            if state in global_states:
                global_states[state] += 1
            else:
                global_states["NEUTRAL"] += 1

        total_assets = len(scan_results)
        g_gold_pct = round((global_states["GOLD"] / total_assets) * 100.0, 1)
        g_blue_pct = round((global_states["BLUE"] / total_assets) * 100.0, 1)
        g_neutral_pct = round((global_states["NEUTRAL"] / total_assets) * 100.0, 1)

        sector_summaries: Dict[str, SectorBreadth] = {}
        crypto_gold_pct = None
        equities_gold_pct = None

        for sec, items in sector_buckets.items():
            sec_tot = len(items)
            g_cnt = sum(1 for x in items if str(x.get("state", "")).upper() == "GOLD")
            b_cnt = sum(1 for x in items if str(x.get("state", "")).upper() == "BLUE")
            n_cnt = sec_tot - g_cnt - b_cnt

            g_pct = round((g_cnt / sec_tot) * 100.0, 1) if sec_tot > 0 else 0.0
            b_pct = round((b_cnt / sec_tot) * 100.0, 1) if sec_tot > 0 else 0.0
            n_pct = round((n_cnt / sec_tot) * 100.0, 1) if sec_tot > 0 else 0.0

            if g_pct >= 55.0:
                s_reg = "BULL"
            elif b_pct >= 45.0:
                s_reg = "BEAR"
            elif n_pct >= 50.0:
                s_reg = "NEUTRAL"
            else:
                s_reg = "MIXED"

            sector_summaries[sec] = SectorBreadth(
                sector_name=sec,
                total=sec_tot,
                gold_count=g_cnt,
                blue_count=b_cnt,
                neutral_count=n_cnt,
                gold_pct=g_pct,
                blue_pct=b_pct,
                neutral_pct=n_pct,
                regime=s_reg,
            )

            if sec == "Crypto":
                crypto_gold_pct = g_pct
            elif sec in ["US Equities", "AI & Tech"]:
                equities_gold_pct = g_pct

        macro_regime = self.classify_macro_regime(
            global_gold=g_gold_pct,
            global_blue=g_blue_pct,
            crypto_gold=crypto_gold_pct,
            equities_gold=equities_gold_pct,
        )

        # Calculate deltas if history available
        delta_7d = None
        delta_30d = None
        if historical_snapshots:
            if len(historical_snapshots) >= 7:
                delta_7d = round(g_gold_pct - historical_snapshots[-7].global_gold_pct, 1)
            if len(historical_snapshots) >= 30:
                delta_30d = round(g_gold_pct - historical_snapshots[-30].global_gold_pct, 1)

        return RegimeBreadthSnapshot(
            timestamp=now_ts,
            total_assets=total_assets,
            global_gold_pct=g_gold_pct,
            global_blue_pct=g_blue_pct,
            global_neutral_pct=g_neutral_pct,
            macro_regime=macro_regime,
            sectors=sector_summaries,
            delta_7d_gold_pct=delta_7d,
            delta_30d_gold_pct=delta_30d,
        )

    def save_snapshot(self, snapshot: RegimeBreadthSnapshot) -> bool:
        """Saves snapshot to SQLite database."""
        try:
            sec_dict = {k: asdict(v) for k, v in snapshot.sectors.items()}
            sec_json = json.dumps(sec_dict)
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO regime_breadth_history (
                        timestamp, total_assets, global_gold_pct, global_blue_pct,
                        global_neutral_pct, macro_regime, delta_7d_gold_pct,
                        delta_30d_gold_pct, sectors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.timestamp,
                        snapshot.total_assets,
                        snapshot.global_gold_pct,
                        snapshot.global_blue_pct,
                        snapshot.global_neutral_pct,
                        snapshot.macro_regime,
                        snapshot.delta_7d_gold_pct,
                        snapshot.delta_30d_gold_pct,
                        sec_json,
                    ),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to persist regime breadth snapshot: {e}")
            return False

    def load_history(self, limit: int = 30) -> List[RegimeBreadthSnapshot]:
        """Loads trailing snapshots from SQLite."""
        snapshots = []
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT timestamp, total_assets, global_gold_pct, global_blue_pct,
                           global_neutral_pct, macro_regime, delta_7d_gold_pct,
                           delta_30d_gold_pct, sectors_json
                    FROM regime_breadth_history
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                for r in rows:
                    sec_data = json.loads(r[8]) if r[8] else {}
                    sectors = {
                        k: SectorBreadth(**v) for k, v in sec_data.items()
                    }
                    snapshots.append(
                        RegimeBreadthSnapshot(
                            timestamp=r[0],
                            total_assets=r[1],
                            global_gold_pct=r[2],
                            global_blue_pct=r[3],
                            global_neutral_pct=r[4],
                            macro_regime=r[5],
                            delta_7d_gold_pct=r[6],
                            delta_30d_gold_pct=r[7],
                            sectors=sectors,
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to load regime breadth history: {e}")
        return snapshots

    def format_telegram_summary(self, snapshot: RegimeBreadthSnapshot) -> str:
        """Formats clean Telegram HTML overview of Cross-Asset Regime Breadth."""
        regime_emojis = {
            "AGGRESSIVE_RISK_ON": "🟢🚀",
            "BROAD_RISK_ON": "🟢📈",
            "EQUITY_SELECTIVE_BULL": "🟡📊",
            "CRYPTO_DECOUPLED_BULL": "🟣⚡",
            "CONSOLIDATION_CHOP": "⚪⚖️",
            "DEFENSIVE_RISK_OFF": "🟠🛡️",
            "BROAD_LIQUIDITY_DRAIN": "🔴🌊",
            "ROTATIONAL_MIXED": "🔄🔀",
        }
        emoji = regime_emojis.get(snapshot.macro_regime, "🌐")

        delta_str = ""
        if snapshot.delta_7d_gold_pct is not None:
            d_icon = "🔺" if snapshot.delta_7d_gold_pct > 0 else "🔻"
            delta_str = f" (7D Δ: <b>{d_icon}{snapshot.delta_7d_gold_pct:+.1f}%</b>)"

        lines = [
            f"🌐 <b>CROSS-ASSET REGIME BREADTH INDEX</b> {emoji}",
            f"━━━━━━━━━━━━━━━━━━━",
            f"• Макро Режим: <b>{snapshot.macro_regime}</b>",
            f"• Общо активи: <b>{snapshot.total_assets}</b>",
            f"• Глобален Gold Breadth: <b>{snapshot.global_gold_pct:.1f}%</b>{delta_str}",
            f"• Глобален Blue Breadth: <b>{snapshot.global_blue_pct:.1f}%</b>",
            f"• Neutral / Consolidation: <b>{snapshot.global_neutral_pct:.1f}%</b>",
            f"",
            f"<b>Секторно Разпределение:</b>",
        ]

        for sec_name, s in snapshot.sectors.items():
            bar_len = int(round(s.gold_pct / 10.0))
            bar_gold = "🟩" * bar_len + "⬜" * (10 - bar_len)
            lines.append(
                f"• <b>{sec_name}</b> ({s.total}): {s.gold_pct:.0f}% Gold | {s.blue_pct:.0f}% Blue [{s.regime}]\n"
                f"  <code>{bar_gold}</code>"
            )

        return "\n".join(lines)
