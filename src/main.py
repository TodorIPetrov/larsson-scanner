"""
Larsson Line Scanner Application Entry Point.
Provides CLI commands for on-demand scanning, state status inspection,
dashboard data generation, and the automated APScheduler daemon.
Supports Crypto, US Stocks, International Stocks, Commodities, and Indices.
"""

import argparse
from datetime import datetime, timezone
import logging
import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import threading
import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.alerts.bot_listener import TelegramCommandListener
from src.alerts.healthcheck import send_heartbeat_ping
from src.alerts.telegram import TelegramNotifier
from src.dashboard.generator import export_dashboard_data
from src.dashboard.git_sync import sync_dashboard_to_git
from src.data.binance_fetch import BinanceFetcher
from src.data.yfinance_fetch import YFinanceFetcher
from src.scanner import LarssonScanner
from src.storage.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def run_scan(
    scanner: LarssonScanner,
    asset_class: str = "all",
    timeframe: str = "1D",
    limit: int = 50,
):
    """Executes a market scan for specified asset class and timeframe."""
    logger.info(f"=== Starting scan [Asset Class: {asset_class.upper()} | TF: {timeframe}] ===")
    start_t = time.time()

    if asset_class == "all":
        res = scanner.scan_all_assets(timeframe=timeframe, crypto_limit=limit)
    elif asset_class == "crypto":
        res = scanner.scan_top_crypto(limit=limit, timeframe=timeframe)
    elif asset_class == "sp500":
        res = scanner.scan_sp500(limit=limit if limit > 50 else None, timeframe=timeframe)
    else:
        res = scanner.scan_yfinance_assets(asset_class=asset_class, timeframe=timeframe)

    elapsed = time.time() - start_t

    logger.info(
        f"Scan complete in {elapsed:.2f}s | "
        f"Total: {res['total_scanned']} | "
        f"🟡 Gold: {res['gold_count']} | "
        f"🔵 Blue: {res['blue_count']} | "
        f"⚪ Neutral: {res['neutral_count']} | "
        f"Changes: {len(res['state_changes'])}"
    )

    # Export latest data for dashboard
    export_dashboard_data(scanner.db)

    # Sync to GitHub Pages repository if configured
    sync_dashboard_to_git()

    # Send heartbeat ping to Healthchecks.io if configured
    hc_url = scanner.config.get("monitoring", {}).get("healthcheck_url")
    if hc_url:
        send_heartbeat_ping(hc_url)


def print_status(db: Database, asset_class: str = "all"):
    """Prints a terminal summary table of all tracked assets."""
    states = db.get_all_states()
    if not states:
        print("\nNo symbols recorded in database yet. Run a scan first: python src/main.py --scan\n")
        return

    if asset_class != "all":
        states = [s for s in states if s["asset_class"] == asset_class]

    print("\n" + "=" * 95)
    print(f"{'TICKER':<12} | {'CLASS':<12} | {'TF':<4} | {'STATE':<10} | {'PRICE':<12} | {'LAST CHANGE':<20}")
    print("-" * 95)
    for s in states[:60]:  # Show up to 60
        state_str = s["current_state"]
        if state_str == "GOLD":
            state_str = "🟡 GOLD"
        elif state_str == "BLUE":
            state_str = "🔵 BLUE"
        else:
            state_str = "⚪ NEUTRAL"

        price = s['last_price']
        if price >= 1000:
            price_str = f"${price:,.2f}"
        elif price >= 1:
            price_str = f"${price:.2f}"
        else:
            price_str = f"${price:.5f}"

        change_time = s["last_state_change"][:19].replace("T", " ")
        a_class = s["asset_class"]

        print(f"{s['ticker']:<12} | {a_class:<12} | {s['timeframe']:<4} | {state_str:<10} | {price_str:<12} | {change_time:<20}")

    print("=" * 95)
    print(f"Showing up to 60 of {len(states)} tracked symbol states.\n")


def start_scheduler(scanner: LarssonScanner):
    """Starts the 24/7 automated scheduler."""
    sched = BlockingScheduler(timezone="UTC")

    # 1D Crypto candle closes at 00:00 UTC (Run at 00:02 UTC)
    sched.add_job(
        func=lambda: run_scan(scanner, asset_class="crypto", timeframe="1D", limit=100),
        trigger=CronTrigger(hour=0, minute=2, timezone="UTC"),
        id="crypto_daily",
        name="Crypto Daily Scan (00:02 UTC)",
    )

    # 4H Crypto candles close every 4 hours (00, 04, 08, 12, 16, 20 UTC + 2 min)
    sched.add_job(
        func=lambda: run_scan(scanner, asset_class="crypto", timeframe="4H", limit=100),
        trigger=CronTrigger(hour="0,4,8,12,16,20", minute=2, timezone="UTC"),
        id="crypto_4h",
        name="Crypto 4H Scan",
    )

    # 1W Crypto candle closes on Monday 00:00 UTC (Run at Mon 00:05 UTC)
    sched.add_job(
        func=lambda: run_scan(scanner, asset_class="crypto", timeframe="1W", limit=100),
        trigger=CronTrigger(day_of_week="mon", hour=0, minute=5, timezone="UTC"),
        id="crypto_weekly",
        name="Crypto Weekly Scan (Mon 00:05 UTC)",
    )

    # Daily Stocks/Commodities/Indices/AI: Monday-Friday at 21:05 UTC (after NYSE close at 21:00 UTC)
    sched.add_job(
        func=lambda: [
            run_scan(scanner, asset_class=ac, timeframe="1D")
            for ac in ["us_stocks", "intl_stocks", "ai_stocks", "commodities", "indices"]
        ],
        trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=5, timezone="UTC"),
        id="stocks_daily",
        name="Traditional & AI Markets Daily Scan (Mon-Fri 21:05 UTC)",
    )

    # Weekly Stocks/Commodities/Indices/AI: Friday at 21:10 UTC
    sched.add_job(
        func=lambda: [
            run_scan(scanner, asset_class=ac, timeframe="1W")
            for ac in ["us_stocks", "intl_stocks", "ai_stocks", "commodities", "indices"]
        ],
        trigger=CronTrigger(day_of_week="fri", hour=21, minute=10, timezone="UTC"),
        id="stocks_weekly",
        name="Traditional & AI Markets Weekly Scan (Fri 21:10 UTC)",
    )

    logger.info("Scheduler started with cron jobs:")
    logger.info("  - Crypto 1D: Daily at 00:02 UTC")
    logger.info("  - Crypto 4H: Every 4 hours at :02 UTC")
    logger.info("  - Crypto 1W: Mondays at 00:05 UTC")
    logger.info("  - Stocks/Commodities 1D: Mon-Fri at 21:05 UTC")
    logger.info("  - Stocks/Commodities 1W: Fridays at 21:10 UTC")

    # Start Binance WebSocket listener for sub-second real-time crypto candle close alerts
    try:
        from src.data.binance_ws import BinanceKlineWebSocket
        top_crypto = scanner.binance_fetcher.get_top_usdt_pairs(limit=50)
        # Add any user watchlist crypto symbols
        watchlist_items = scanner.db.get_watchlist()
        for item in watchlist_items:
            t = item["ticker"]
            if t.endswith("USDT") and t not in top_crypto:
                top_crypto.append(t)

        ws_listener = BinanceKlineWebSocket(
            symbols=top_crypto,
            timeframes=["1D", "4H"],
            on_candle_close=scanner.handle_candle_close_event,
        )
        ws_listener.start()
        logger.info(f"Binance Real-Time WebSocket active for {len(top_crypto)} pairs.")
    except Exception as e:
        logger.warning(f"Failed to start Binance WebSocket listener: {e}")

    # Start Telegram interactive bot listener in background thread
    if scanner.notifier.is_configured:
        listener = TelegramCommandListener(notifier=scanner.notifier, db=scanner.db)
        t = threading.Thread(target=listener.run_poll_loop, daemon=True, name="TelegramListener")
        t.start()
        logger.info("Telegram interactive bot listener active (/status, /gold, /blue, /help).")

    logger.info("Press Ctrl+C to terminate.")

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopping...")
        if 'ws_listener' in locals() and ws_listener:
            ws_listener.stop()
        logger.info("Scheduler stopped.")


def main():
    parser = argparse.ArgumentParser(description="Larsson Line Automated Multi-Asset Scanner")
    parser.add_argument("--scan", action="store_true", help="Execute an immediate on-demand scan")
    parser.add_argument(
        "--asset-class",
        type=str,
        default="all",
        choices=["all", "crypto", "us_stocks", "intl_stocks", "commodities", "indices", "sp500"],
        help="Asset class to scan",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1D",
        choices=["1D", "4H", "1W"],
        help="Timeframe to scan (Note: Traditional markets support 1D and 1W)",
    )
    parser.add_argument("--limit", type=int, default=30, help="Number of top crypto pairs to scan")
    parser.add_argument("--scheduler", action="store_true", help="Start background 24/7 scheduler daemon")
    parser.add_argument("--status", action="store_true", help="Print table of currently recorded states")
    parser.add_argument("--export-dashboard", action="store_true", help="Export latest data.json for dashboard")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test notification to Telegram")
    parser.add_argument("--websocket", action="store_true", help="Run standalone Binance WebSocket listener")

    args = parser.parse_args()

    # Load settings with optional local overrides
    settings_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")
    local_settings_path = os.path.join(PROJECT_ROOT, "config", "settings.local.yaml")
    full_settings = {}
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                full_settings = yaml.safe_load(f) or {}
        if os.path.exists(local_settings_path):
            with open(local_settings_path, "r", encoding="utf-8") as f:
                local_settings = yaml.safe_load(f) or {}
                for k, v in local_settings.items():
                    if isinstance(v, dict) and isinstance(full_settings.get(k), dict):
                        full_settings[k].update(v)
                    else:
                        full_settings[k] = v
    except Exception as e:
        logger.warning(f"Error loading configuration files: {e}")

    tg_config = full_settings.get("telegram", {})
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or tg_config.get("bot_token")
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID") or tg_config.get("chat_id") or "")

    db = Database()
    notifier = TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        batch_threshold=tg_config.get("batch_threshold", 5),
    )
    b_fetcher = BinanceFetcher()
    yf_fetcher = YFinanceFetcher()
    scanner = LarssonScanner(
        db=db,
        binance_fetcher=b_fetcher,
        yf_fetcher=yf_fetcher,
        notifier=notifier,
    )

    if args.test_telegram:
        if not notifier.is_configured:
            print("\n❌ Telegram все още НЕ е конфигуриран!")
            print(f"Моля отвори файла: {settings_path}")
            print("И попълни твоите данни:\n")
            print("telegram:")
            print("  bot_token: \"123456789:ABCdefGhIJKlm...\"")
            print("  chat_id: \"987654321\"\n")
        else:
            print("\n🚀 Изпращане на тестово известие към Telegram...")
            ok = notifier.send_test_alert()
            if ok:
                print("✅ Тестовото известие беше изпратено успешно! Провери си Telegram.\n")
            else:
                print("❌ Грешка при изпращане. Провери дали bot_token и chat_id са точни.\n")
    elif args.scan:
        run_scan(scanner, asset_class=args.asset_class, timeframe=args.timeframe, limit=args.limit)
    elif args.status:
        print_status(db, asset_class=args.asset_class)
    elif args.export_dashboard:
        data = export_dashboard_data(db)
        print(f"Exported dashboard data: {data['summary']['total']} symbols to dashboard/data.json")
    elif args.scheduler:
        start_scheduler(scanner)
    elif args.websocket:
        from src.data.binance_ws import BinanceKlineWebSocket
        top_crypto = scanner.binance_fetcher.get_top_usdt_pairs(limit=args.limit or 50)
        print(f"Starting standalone Binance WebSocket listener for {len(top_crypto)} pairs...")
        ws_listener = BinanceKlineWebSocket(
            symbols=top_crypto,
            timeframes=[args.timeframe] if args.timeframe else ["1D", "4H"],
            on_candle_close=scanner.handle_candle_close_event,
        )
        ws_listener.start()
        print("Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            ws_listener.stop()
            print("WebSocket listener stopped.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
