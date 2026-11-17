"""
High-Performance Local Web & API Server for Larsson Line Scanner Dashboard.
Serves static dashboard assets and exposes REST endpoints for on-demand market analysis,
trade proposals generation, and live system status.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.storage.database import Database
from src.dashboard.generator import export_dashboard_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dashboard_server")

DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")
SCAN_LOCK = threading.Lock()
IS_SCANNING = False
SERVER_START_TIME = time.time()
SCAN_START_TIME = None
LAST_SCAN_COMPLETED_TIME = None
LAST_SCAN_DURATION = None


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def guess_type(self, path):
        """Overrides MIME type guessing for PWA manifest, service worker, and web assets."""
        path_str = str(path).lower()
        if path_str.endswith("manifest.json"):
            return "application/manifest+json"
        if path_str.endswith("sw.js") or path_str.endswith(".js"):
            return "application/javascript"
        if path_str.endswith(".svg"):
            return "image/svg+xml"
        if path_str.endswith(".png"):
            return "image/png"
        return super().guess_type(path)

    def end_headers(self):
        # Service worker header and caching controls
        if self.path.endswith("sw.js"):
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif self.path.endswith("manifest.json"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        elif self.path.startswith("/data.json") or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path_only = parsed.path
        qs = parse_qs(parsed.query)

        if path_only == "/api/status":
            self.handle_api_status()
        elif path_only == "/api/live-quotes":
            self.handle_api_live_quotes()
        elif path_only == "/api/candles":
            self.handle_api_candles(qs)
        elif path_only == "/api/portfolio/sync":
            self.handle_get_portfolio_sync()
        elif path_only in ("/api/scan", "/api/analyze-proposals", "/api/refresh"):
            self.handle_api_scan()
        elif path_only == "/api/state":
            self.handle_serve_file(os.path.join(DASHBOARD_DIR, "data", "state.json"), fallback="data.json")
        elif path_only == "/api/fundamentals":
            self.handle_serve_file(os.path.join(DASHBOARD_DIR, "data", "fundamentals.json"))
        elif path_only == "/api/history":
            self.handle_serve_file(os.path.join(DASHBOARD_DIR, "data", "history.json"))
        else:
            super().do_GET()

    def handle_serve_file(self, file_path: str, fallback: Optional[str] = None):
        """Serves a JSON file directly with no-cache headers."""
        target = file_path
        if not os.path.exists(target) and fallback:
            target = os.path.join(DASHBOARD_DIR, fallback)

        if not os.path.exists(target):
            self.send_error(404, "File Not Found")
            return

        try:
            with open(target, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path_only = parsed.path
        qs = parse_qs(parsed.query)

        if path_only in ("/api/scan", "/api/analyze-proposals", "/api/refresh"):
            self.handle_api_scan()
        elif path_only == "/api/portfolio/sync":
            self.handle_post_portfolio_sync()
        elif path_only == "/api/refresh-fundamentals":
            self.handle_api_refresh_fundamentals(qs=qs)
        else:
            self.send_error(404, "Not Found")

    def handle_api_status(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        symbols_count = 0
        db_healthy = True
        try:
            db = Database()
            symbols_count = len(db.get_all_states())
        except Exception as e:
            logger.warning(f"Database query error in /api/status: {e}")
            db_healthy = False

        data_json_path = os.path.join(DASHBOARD_DIR, "data.json")
        data_json_exists = os.path.exists(data_json_path)
        data_json_size = os.path.getsize(data_json_path) if data_json_exists else 0
        data_json_mtime = None
        if data_json_exists:
            try:
                data_json_mtime = datetime.fromtimestamp(os.path.getmtime(data_json_path), tz=timezone.utc).isoformat()
            except Exception:
                pass

        scan_duration = round(time.time() - SCAN_START_TIME, 1) if (IS_SCANNING and SCAN_START_TIME) else 0

        res = {
            "status": "ok",
            "is_scanning": IS_SCANNING,
            "scan_duration_sec": scan_duration,
            "last_scan_completed": LAST_SCAN_COMPLETED_TIME,
            "last_scan_duration": LAST_SCAN_DURATION,
            "symbols_in_db": symbols_count,
            "db_healthy": db_healthy,
            "data_json_exists": data_json_exists,
            "data_json_size": data_json_size,
            "data_json_mtime": data_json_mtime,
            "server_uptime_sec": round(time.time() - SERVER_START_TIME, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.wfile.write(json.dumps(res).encode("utf-8"))

    def handle_api_scan(self):
        global IS_SCANNING, SCAN_START_TIME, LAST_SCAN_COMPLETED_TIME, LAST_SCAN_DURATION
        if IS_SCANNING:
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            elapsed = round(time.time() - SCAN_START_TIME, 1) if SCAN_START_TIME else 0
            self.wfile.write(json.dumps({
                "success": False,
                "is_scanning": True,
                "elapsed_sec": elapsed,
                "message": f"В момента вече се изпълнява пазарен анализ ({elapsed}s). Моля изчакайте."
            }).encode("utf-8"))
            return

        with SCAN_LOCK:
            IS_SCANNING = True
            SCAN_START_TIME = time.time()

        try:
            logger.info("⚡ [API Trigger] Running market analysis for actionable trade proposals...")
            db = Database()

            # 1. Execute live market scan across all asset classes
            try:
                from src.scanner import LarssonScanner
                from src.data.binance_fetch import BinanceFetcher
                from src.data.yfinance_fetch import YFinanceFetcher
                from src.engine.lifecycle_sync import sync_new_assets_lifecycle
                scanner = LarssonScanner(db=db, binance_fetcher=BinanceFetcher(), yf_fetcher=YFinanceFetcher())
                scanner.scan_top_crypto(limit=40, timeframe="1D")
                for ac in ["us_stocks", "crypto_stocks", "intl_stocks", "ai_stocks", "commodities", "indices"]:
                    scanner.scan_yfinance_assets(asset_class=ac, timeframe="1D")
                sync_new_assets_lifecycle(db)
            except Exception as scan_err:
                logger.warning(f"Live market fetch notice during API scan: {scan_err}")

            # 2. Run paper trader evaluation across current open positions & states
            from src.trading.paper_trader import PaperTrader
            paper_trader = PaperTrader(db=db)
            if hasattr(paper_trader, "update_all_open_positions"):
                try:
                    paper_trader.update_all_open_positions()
                except Exception as pt_err:
                    logger.warning(f"Paper position mark-to-market notice: {pt_err}")

            # Evaluate top assets for proposals
            states = db.get_all_states()
            generated_count = 0

            # Scan eligible candidates
            for row in states:
                ticker = row["ticker"]
                timeframe = row["timeframe"]
                price = row["last_price"]
                tv_symbol = row["tv_symbol"]

                # Get suggestion row
                sug = db.get_trade_suggestion(ticker, timeframe)
                sug_dict = dict(sug) if sug else None
                if sug_dict and sug_dict.get("action") in ["SPOT_BUY", "SHORT_2X_OPTIONAL"]:
                    # Attempt creating trade proposal
                    prop = paper_trader.handle_new_signal(
                        ticker=ticker,
                        timeframe=timeframe,
                        trade_suggestion=sug_dict,
                        current_price=float(price),
                        tv_symbol=tv_symbol,
                    )
                    if prop:
                        generated_count += 1

            # 2. Export updated dashboard
            data = export_dashboard_data(db)
            pending_count = len(data.get("pending_proposals", []))
            duration = round(time.time() - SCAN_START_TIME, 2)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            response_payload = {
                "success": True,
                "message": f"Анализът завърши за {duration}s! Открити {pending_count} активни предложения за търговия.",
                "proposals_count": pending_count,
                "new_created": generated_count,
                "duration_sec": duration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))
            logger.info(f"✅ [API Trigger] Analysis completed in {duration}s. {pending_count} pending proposals in dashboard.")
        except Exception as e:
            logger.error(f"❌ Error during API scan: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": str(e),
                "message": "Възникна грешка по време на анализа."
            }).encode("utf-8"))
        finally:
            with SCAN_LOCK:
                LAST_SCAN_DURATION = round(time.time() - (SCAN_START_TIME or time.time()), 2)
                LAST_SCAN_COMPLETED_TIME = datetime.now(timezone.utc).isoformat()
                IS_SCANNING = False
                SCAN_START_TIME = None



    
    def handle_api_live_quotes(self):
        """Returns lightweight live quotes and current state for fast client polling."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        try:
            db = Database()
            states = db.get_all_states()
            quotes = []
            for r in states:
                quotes.append({
                    "ticker": r["ticker"],
                    "timeframe": r["timeframe"],
                    "price": r["last_price"],
                    "state": r["current_state"],
                    "v1": round(r["v1"], 4),
                    "v2": round(r["v2"], 4),
                    "spread_pct": round(((r["v1"] - r["v2"]) / r["v2"]) * 100.0, 2) if r["v2"] > 0 else 0.0,
                    "updated_at": r["updated_at"],
                })
            res = {"success": True, "count": len(quotes), "quotes": quotes, "timestamp": datetime.now(timezone.utc).isoformat()}
            self.wfile.write(json.dumps(res).encode("utf-8"))
        except Exception as e:
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_api_candles(self, qs: dict):
        """Returns OHLCV candles + Larsson SMMA overlays for any ticker/timeframe."""
        ticker = ((qs or {}).get("ticker") or [""])[0].strip()
        timeframe = ((qs or {}).get("timeframe") or ["1D"])[0].strip().upper()
        if not ticker:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Missing ticker parameter"}).encode("utf-8"))
            return

        try:
            import numpy as np
            import pandas as pd
            from src.backtest.data_manager import BacktestDataManager
            from src.engine.smma import compute_larsson_series

            asset_cls = "crypto" if ticker.endswith("USDT") else ("commodities" if "=F" in ticker else ("indices" if ticker.startswith("^") else "us_stocks"))
            df = None
            source = "cache"

            if timeframe == "1D":
                dm = BacktestDataManager()
                df = dm.get_symbol_data(ticker, asset_class=asset_cls, timeframe="1D", max_stale_days=1)
                source = "backtest_manager"
            elif asset_cls == "crypto":
                from src.data.binance_fetch import BinanceFetcher
                bf = BinanceFetcher()
                highs, lows, closes, _ = bf.fetch_klines(ticker, timeframe=timeframe, limit=300)
                ohlcv = getattr(bf, "last_klines_ohlcv", {}).get(ticker)
                if ohlcv and ohlcv.get("closes"):
                    df = pd.DataFrame({
                        "date": ohlcv.get("dates"),
                        "open": ohlcv.get("opens"),
                        "high": ohlcv.get("highs"),
                        "low": ohlcv.get("lows"),
                        "close": ohlcv.get("closes"),
                        "volume": ohlcv.get("volumes"),
                    })
                    source = "binance_live"
            else:
                from src.data.yfinance_fetch import YFinanceFetcher
                yf_fetch = YFinanceFetcher()
                yf_fetch.fetch_via_chart_api(ticker, period="1y" if timeframe == "4H" else "2y", interval="1d" if timeframe == "1D" else "1h")
                ohlcv = getattr(yf_fetch, "last_batch_ohlcv", {}).get(ticker)
                if ohlcv and ohlcv.get("closes"):
                    df = pd.DataFrame({
                        "date": ohlcv.get("dates"),
                        "open": ohlcv.get("opens"),
                        "high": ohlcv.get("highs"),
                        "low": ohlcv.get("lows"),
                        "close": ohlcv.get("closes"),
                        "volume": ohlcv.get("volumes"),
                    })
                    source = "yfinance_live"

            if df is None or df.empty:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": f"No candles found for {ticker} ({timeframe})"}).encode("utf-8"))
                return

            df = df.copy()
            df.columns = [str(c).lower() for c in df.columns]
            if "date" not in df.columns and "timestamp" in df.columns:
                df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
            if "open" not in df.columns:
                df["open"] = df["close"]

            highs = df["high"].to_numpy(dtype=np.float64)
            lows = df["low"].to_numpy(dtype=np.float64)
            opens = df["open"].to_numpy(dtype=np.float64)
            closes = df["close"].to_numpy(dtype=np.float64)
            dates = df["date"].astype(str).tolist() if "date" in df.columns else [str(i) for i in range(len(df))]
            v1, _m1, _m2, v2, states = compute_larsson_series(highs, lows)

            tail_start = max(0, len(closes) - 360)
            candles = []
            for i in range(tail_start, len(closes)):
                t_val = str(dates[i])[:10] if timeframe == "1D" else str(dates[i])
                candles.append({
                    "time": t_val,
                    "open": round(float(opens[i]), 4),
                    "high": round(float(highs[i]), 4),
                    "low": round(float(lows[i]), 4),
                    "close": round(float(closes[i]), 4),
                    "v1": round(float(v1[i]), 4) if not np.isnan(v1[i]) else None,
                    "v2": round(float(v2[i]), 4) if not np.isnan(v2[i]) else None,
                    "state": states[i].value,
                })

            payload = {
                "success": True,
                "ticker": ticker,
                "timeframe": timeframe,
                "source": source,
                "state": states[-1].value if states else "NEUTRAL",
                "v1": round(float(v1[-1]), 4) if len(v1) and not np.isnan(v1[-1]) else None,
                "v2": round(float(v2[-1]), 4) if len(v2) and not np.isnan(v2[-1]) else None,
                "candles": candles,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error serving candles for {ticker}: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_api_refresh_fundamentals(self, qs: Optional[dict] = None):
        """Triggers filing-aware or targeted corporate fundamentals refresh and cascades to dashboard."""
        try:
            body_params = {}
            content_len = int(self.headers.get("Content-Length", 0) or 0)
            if content_len > 0:
                try:
                    raw = self.rfile.read(content_len)
                    parsed_body = json.loads(raw.decode("utf-8"))
                    if isinstance(parsed_body, dict):
                        body_params = parsed_body
                except Exception:
                    pass

            qs = qs or {}
            ticker_arg = (qs.get("ticker") or [body_params.get("ticker") or ""])[0] if qs.get("ticker") else (body_params.get("ticker") or "")
            tickers_arg = body_params.get("tickers")
            target_tickers = None
            if ticker_arg:
                target_tickers = [t.strip() for t in str(ticker_arg).split(",") if t.strip()]
            elif isinstance(tickers_arg, list) and tickers_arg:
                target_tickers = [str(t).strip() for t in tickers_arg if str(t).strip()]

            force_raw = (qs.get("force") or [body_params.get("force")])[0] if qs.get("force") else body_params.get("force")
            force = str(force_raw).lower() in ("1", "true", "yes") if force_raw is not None else bool(target_tickers)
            limit_raw = (qs.get("limit") or [body_params.get("limit")])[0] if qs.get("limit") else body_params.get("limit")
            try:
                limit = int(limit_raw) if limit_raw is not None else (len(target_tickers) if target_tickers else 40)
            except Exception:
                limit = 40

            from src.engine.lifecycle_sync import refresh_existing_fundamentals
            from src.engine.quantamental import QuantamentalRegistry

            db = Database()
            res = refresh_existing_fundamentals(
                max_age_days=0 if force else 7,
                force=force,
                limit=limit,
                target_tickers=target_tickers,
                db=db,
                check_filings=True,
            )
            QuantamentalRegistry.get_instance().load_profiles()
            export_dashboard_data(db)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "refreshed_count": res.get("refreshed_count", 0),
                "changed_count": res.get("changed_count", 0),
                "tickers": res.get("tickers", []),
                "changed_tickers": res.get("changed_tickers", []),
            }).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_get_portfolio_sync(self):
        sync_file = os.path.join(PROJECT_ROOT, "data", "portfolio_user_sync.json")
        data = {"real": {}, "paper": {}}
        if os.path.exists(sync_file):
            try:
                with open(sync_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def handle_post_portfolio_sync(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            sync_file = os.path.join(PROJECT_ROOT, "data", "portfolio_user_sync.json")
            os.makedirs(os.path.dirname(sync_file), exist_ok=True)
            with open(sync_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            res = {"success": True, "message": "Portfolio backup persisted to server disk"}
        except Exception as e:
            res = {"success": False, "error": str(e)}
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode("utf-8"))

def run_server(port=8080):
    server_address = ("0.0.0.0", port)
    httpd = http.server.ThreadingHTTPServer(server_address, DashboardRequestHandler)
    logger.info(f"🚀 Larsson Dashboard & API Server listening on http://localhost:{port}/ (serving {DASHBOARD_DIR})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
