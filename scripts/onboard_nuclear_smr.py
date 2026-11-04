import os
import sys
import json
import yaml
import sqlite3
import numpy as np
from datetime import datetime, timezone

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series, LarssonState
from src.engine.sr_levels import analyze_sr_levels
from src.storage.database import Database
from src.dashboard.generator import export_dashboard_data

NUCLEAR_ASSETS = [
    # 1. Pure-Play SMR & Микрореактори (Спекулативен растеж)
    {
        "ticker": "SMR",
        "asset_class": "ai_stocks",
        "tv_symbol": "NYSE:SMR",
        "name": "NuScale Power Corporation (SMR)",
        "isin": "US67090S1087",
        "category": "Pure-Play SMR & Микрореактори (Спекулативен растеж)",
        "exchange": "NYSE / Xetra (1UY)",
        "tax": "10% (US) / 0% (Xetra Reg.)",
        "german_ticker": "1UY",
    },
    {
        "ticker": "OKLO",
        "asset_class": "ai_stocks",
        "tv_symbol": "NYSE:OKLO",
        "name": "Oklo Inc. (Fast Fission & Microreactors)",
        "isin": "US02156V1098",
        "category": "Pure-Play SMR & Микрореактори (Спекулативен растеж)",
        "exchange": "NYSE / Tradegate (7X5)",
        "tax": "10% (US)",
        "german_ticker": "7X5",
    },
    {
        "ticker": "XE",
        "asset_class": "ai_stocks",
        "tv_symbol": "NASDAQ:XE",
        "name": "X-Energy, Inc. (High-Temperature Gas-Cooled SMR)",
        "isin": "US98389B1008",
        "category": "Pure-Play SMR & Микрореактори (Спекулативен растеж)",
        "exchange": "NASDAQ",
        "tax": "10% (US)",
        "german_ticker": "XE",
    },
    {
        "ticker": "NNE",
        "asset_class": "ai_stocks",
        "tv_symbol": "NASDAQ:NNE",
        "name": "NANO Nuclear Energy Inc. (Microreactors ZEUS/ODIN)",
        "isin": "US63010H1086",
        "category": "Pure-Play SMR & Микрореактори (Спекулативен растеж)",
        "exchange": "NASDAQ / Tradegate (7NO)",
        "tax": "10% (US)",
        "german_ticker": "7NO",
    },

    # 2. Индустриални производители и интегратори (Хардуер и Cash Flow)
    {
        "ticker": "BWXT",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:BWXT",
        "name": "BWX Technologies, Inc. (Naval Reactors & Commercial SMR)",
        "isin": "US05605H1005",
        "category": "Индустриални производители и интегратори (Хардуер и Cash Flow)",
        "exchange": "NYSE / Tradegate (0BX)",
        "tax": "10% (US)",
        "german_ticker": "0BX",
    },
    {
        "ticker": "GEV",
        "asset_class": "ai_stocks",
        "tv_symbol": "NYSE:GEV",
        "name": "GE Vernova Inc. (BWRX-300 SMR & Power Grid)",
        "isin": "US3687361044",
        "category": "Индустриални производители и интегратори (Хардуер и Cash Flow)",
        "exchange": "NYSE / Xetra (2GV)",
        "tax": "10% (US) / 0% (Xetra Reg.)",
        "german_ticker": "2GV",
    },
    {
        "ticker": "RR.L",
        "asset_class": "intl_stocks",
        "tv_symbol": "LSE:RR.",
        "name": "Rolls-Royce Holdings plc (UK SMR Program)",
        "isin": "GB00B63H8491",
        "category": "Индустриални производители и интегратори (Хардуер и Cash Flow)",
        "exchange": "LSE (RR.) / Xetra (RRY) / US OTC (RYCEY)",
        "tax": "10% (LSE/US) / 0% (Xetra Reg.)",
        "german_ticker": "RRY",
        "uk_ticker": "RR.",
    },
    {
        "ticker": "RYCEY",
        "asset_class": "us_stocks",
        "tv_symbol": "OTC:RYCEY",
        "name": "Rolls-Royce Holdings plc (ADR)",
        "isin": "US7757812067",
        "category": "Индустриални производители и интегратори (Хардуер и Cash Flow)",
        "exchange": "US OTC (ADR)",
        "tax": "10% (US)",
        "german_ticker": "RRY",
    },

    # 3. Горивен цикъл и обогатяване (HALEU / Уран)
    {
        "ticker": "LEU",
        "asset_class": "us_stocks",
        "tv_symbol": "AMEX:LEU",
        "name": "Centrus Energy Corp. (HALEU & Uranium Enrichment)",
        "isin": "US15643U1043",
        "category": "Горивен цикъл и обогатяване (HALEU / Уран)",
        "exchange": "NYSE American / Tradegate (USE)",
        "tax": "10% (US)",
        "german_ticker": "USE",
    },
    {
        "ticker": "CCJ",
        "asset_class": "commodities",
        "tv_symbol": "NYSE:CCJ",
        "name": "Cameco Corporation (Uranium Mining & Westinghouse JV)",
        "isin": "CA13321L1085",
        "category": "Горивен цикъл и обогатяване (HALEU / Уран)",
        "exchange": "NYSE / TSX (CCO) / Xetra (CJU)",
        "tax": "10% (US)",
        "german_ticker": "CJU",
    },

    # 4. Данъчно-оптимизиран ETF (0% данък по ЗДДФЛ / Xetra)
    {
        "ticker": "NUKL.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:NUKL",
        "name": "VanEck Uranium and Nuclear Technologies UCITS ETF",
        "isin": "IE000M7V94E1",
        "category": "Данъчно-оптимизиран ETF (0% данък по ЗДДФЛ / Xetra)",
        "exchange": "Xetra (NUKL) / LSE (NUCL)",
        "tax": "0% (ЗДДФЛ - Регулиран пазар в ЕС)",
        "german_ticker": "NUKL",
        "wkn": "A3D47K",
    },
]

def onboard_nuclear_assets():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_yaml_path = os.path.join(base_dir, "config", "assets.yaml")
    tv_mapping_path = os.path.join(base_dir, "config", "tv_mapping.json")
    names_mapping_path = os.path.join(base_dir, "config", "names_mapping.json")
    db_path = os.path.join(base_dir, "state.db")

    print(f"Loading configurations from {base_dir}...")
    with open(assets_yaml_path, "r", encoding="utf-8") as f:
        assets_data = yaml.safe_load(f) or {}

    with open(tv_mapping_path, "r", encoding="utf-8") as f:
        tv_data = json.load(f)

    with open(names_mapping_path, "r", encoding="utf-8") as f:
        names_data = json.load(f)

    db = Database(db_path)
    yf_fetcher = YFinanceFetcher()

    symbols_to_upsert = []
    tickers_to_fetch = []
    added_to_yaml = 0

    for item in NUCLEAR_ASSETS:
        ticker = item["ticker"]
        a_class = item["asset_class"]
        tv_sym = item["tv_symbol"]
        name = item["name"]
        cat = item["category"]
        isin = item["isin"]
        tax = item["tax"]
        exch = item["exchange"]

        # 1. Update YAML
        if a_class not in assets_data:
            assets_data[a_class] = []
        existing_list = assets_data[a_class]
        found = False
        for ex in existing_list:
            if isinstance(ex, dict) and ex.get("ticker") == ticker:
                ex["tv_symbol"] = tv_sym
                found = True
                break
        if not found:
            existing_list.append({"ticker": ticker, "tv_symbol": tv_sym})
            added_to_yaml += 1

        # 2. Update TV mapping
        tv_data[ticker] = tv_sym

        # 3. Update Names mapping
        names_data[ticker] = name

        # 4. Symbols table
        symbols_to_upsert.append((ticker, a_class, tv_sym))

        # 5. Add to personal Watchlist with note
        user_note = f"{cat} | ISIN: {isin} | {exch} | ЗДДФЛ: {tax}"
        db.add_to_watchlist(ticker=ticker, user_note=user_note)

        tickers_to_fetch.append(ticker)

    # Save configs
    with open(assets_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(assets_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    with open(tv_mapping_path, "w", encoding="utf-8") as f:
        json.dump(tv_data, f, indent=2, ensure_ascii=False)

    with open(names_mapping_path, "w", encoding="utf-8") as f:
        json.dump(names_data, f, indent=2, ensure_ascii=False)

    db.upsert_symbols(symbols_to_upsert)

    print(f"Updated configuration files! Added {added_to_yaml} new entries to assets.yaml.")
    print("Now fetching candle data and computing Larsson Line states...")

    fetched_data = yf_fetcher.fetch_batch(tickers_to_fetch, timeframe="1D")
    print(f"Successfully fetched {len(fetched_data)} / {len(tickers_to_fetch)} tickers.")

    scanned_results = []
    for ticker, (highs, lows, closes, latest_price) in fetched_data.items():
        if len(highs) >= 30:
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
                scanned_results.append({
                    "ticker": ticker,
                    "state": current_state.value,
                    "price": float(latest_price)
                })
            except Exception as e:
                print(f"Error computing state for {ticker}: {e}")

    try:
        export_dashboard_data(db)
        print("Exported dashboard data.json successfully!")
    except Exception as e:
        print(f"Notice during export: {e}")

    print("\n--- Summary of Scanned States ---")
    for res in scanned_results:
        print(f"  {res['ticker']:10s} | {res['state']:7s} | {res['price']:10.2f}")

if __name__ == "__main__":
    onboard_nuclear_assets()
