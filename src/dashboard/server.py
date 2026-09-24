"""
High-Performance Local Web & API Server for Larsson Line Scanner Dashboard.
Serves static dashboard assets and exposes REST endpoints for on-demand market analysis,
trade proposals generation, and live system status.
"""

import http.server
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

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


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def end_headers(self):
        # Disable caching for live data and dynamic files
        if self.path.startswith("/data.json") or self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            self.handle_api_status()
        elif self.path == "/api/scan" or self.path == "/api/analyze-proposals":
            self.handle_api_scan()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/scan" or self.path == "/api/analyze-proposals":
            self.handle_api_scan()
        else:
            self.send_error(404, "Not Found")

    def handle_api_status(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        res = {
            "status": "ok",
            "is_scanning": IS_SCANNING,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.wfile.write(json.dumps(res).encode("utf-8"))

    def handle_api_scan(self):
        global IS_SCANNING
        if IS_SCANNING:
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "message": "В момента вече се изпълнява пазарен анализ. Моля изчакайте."
            }).encode("utf-8"))
            return

        with SCAN_LOCK:
            IS_SCANNING = True

        try:
            logger.info("⚡ [API Trigger] Running market analysis for actionable trade proposals...")
            db = Database()

            # 1. Run paper trader evaluation across current states
            from src.trading.paper_trader import PaperTrader
            paper_trader = PaperTrader(db=db)

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

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            response_payload = {
                "success": True,
                "message": f"Анализът завърши успешно! Открити {pending_count} активни предложения за търговия.",
                "proposals_count": pending_count,
                "new_created": generated_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))
            logger.info(f"✅ [API Trigger] Analysis completed. {pending_count} pending proposals in dashboard.")
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
                IS_SCANNING = False


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
