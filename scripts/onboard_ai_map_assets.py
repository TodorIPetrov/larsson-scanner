import os
import sys
import json
import sqlite3
import numpy as np

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series, LarssonState
from src.engine.sr_levels import analyze_sr_levels
from src.storage.database import Database
from src.dashboard.generator import export_dashboard_data

NEW_AI_ASSETS = [
    {"ticker": "CRWV", "asset_class": "ai_stocks", "tv_symbol": "NASDAQ:CRWV"},
    {"ticker": "IBM", "asset_class": "ai_stocks", "tv_symbol": "NYSE:IBM"},
    {"ticker": "1810.HK", "asset_class": "ai_stocks", "tv_symbol": "HKEX:1810"},
    {"ticker": "9880.HK", "asset_class": "ai_stocks", "tv_symbol": "HKEX:9880"},
    {"ticker": "9660.HK", "asset_class": "ai_stocks", "tv_symbol": "HKEX:9660"},
    {"ticker": "9888.HK", "asset_class": "ai_stocks", "tv_symbol": "HKEX:9888"},
    {"ticker": "9988.HK", "asset_class": "ai_stocks", "tv_symbol": "HKEX:9988"},
    {"ticker": "005380.KS", "asset_class": "ai_stocks", "tv_symbol": "KRX:005380"},
    {"ticker": "688836.SS", "asset_class": "ai_stocks", "tv_symbol": "SSE:688836"},
    {"ticker": "CCXI", "asset_class": "ai_stocks", "tv_symbol": "NASDAQ:CCXI"},
]

def onboard_assets():
    db = Database()
    yf_fetcher = YFinanceFetcher()

    symbols_to_upsert = [
        (item["ticker"], item["asset_class"], item["tv_symbol"])
        for item in NEW_AI_ASSETS
    ]
    db.upsert_symbols(symbols_to_upsert)
    print(f"Upserted {len(symbols_to_upsert)} symbols into database.")

    tickers_to_fetch = [item["ticker"] for item in NEW_AI_ASSETS]
    print(f"Fetching candles for {tickers_to_fetch}...")
    fetched_data = yf_fetcher.fetch_batch(tickers_to_fetch, timeframe="1D")
    print(f"Fetched data for {len(fetched_data)} / {len(tickers_to_fetch)} assets.")

    scanned_results = []
    for ticker, (highs, lows, closes, latest_price) in fetched_data.items():
        if len(highs) >= 10:
            try:
                v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
                current_state = states[-1]

                sr_analysis = analyze_sr_levels(highs, lows, closes, current_price=latest_price)
                if sr_analysis:
                    db.upsert_sr_levels(
                        ticker=ticker,
                        timeframe="1D",
                        current_price=sr_analysis.current_price,
                        atr=sr_analysis.atr,
                        s1=sr_analysis.s1,
                        s1_touches=sr_analysis.s1_touches,
                        s1_dist_pct=sr_analysis.s1_dist_pct,
                        s2=sr_analysis.s2,
                        s2_touches=sr_analysis.s2_touches,
                        r1=sr_analysis.r1,
                        r1_touches=sr_analysis.r1_touches,
                        r1_dist_pct=sr_analysis.r1_dist_pct,
                        r2=sr_analysis.r2,
                        r2_touches=sr_analysis.r2_touches,
                        context_flag=sr_analysis.context_flag,
                        context_desc=sr_analysis.context_desc,
                        all_zones_json=json.dumps(sr_analysis.zones),
                    )

                db.update_state(
                    ticker=ticker,
                    timeframe="1D",
                    v1=float(v1[-1]),
                    m1=float(m1[-1]),
                    m2=float(m2[-1]),
                    v2=float(v2[-1]),
                    new_state=current_state,
                    price=float(latest_price),
                )
                scanned_results.append((ticker, current_state.value, float(latest_price)))
                print(f"  [OK] {ticker:10s} -> {current_state.value} @ {latest_price:.2f}")
            except Exception as e:
                print(f"  [ERR] {ticker}: {e}")
        else:
            print(f"  [WARN] Not enough candles for {ticker} ({len(highs)} bars)")

    print("\nTriggering export_dashboard_data...")
    try:
        export_dashboard_data(db)
        print("Exported dashboard data.json successfully!")
    except Exception as e:
        print(f"Export warning: {e}")

if __name__ == "__main__":
    onboard_assets()
