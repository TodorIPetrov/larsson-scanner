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

# Define all target assets with full metadata
NEW_ASSETS = [
    # 1. Минен UCITS ETF
    {
        "ticker": "GDIG.MI",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:GDIG",
        "name": "VanEck S&P Global Mining UCITS ETF (Acc)",
        "isin": "IE00BDFBTQ78",
        "category": "Минен UCITS ETF",
        "exchange": "Xetra / Borsa Italiana",
        "tax": "0%"
    },
    {
        "ticker": "ASWD.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:ASWD",
        "name": "HANetf Sprott Pure Play Copper Miners UCITS ETF (Acc)",
        "isin": "IE000IQQEL77",
        "category": "Минен UCITS ETF",
        "exchange": "Xetra",
        "tax": "0%"
    },
    {
        "ticker": "COPR.MI",
        "asset_class": "intl_stocks",
        "tv_symbol": "MIL:COPR",
        "name": "HANetf Sprott Pure Play Copper Miners (Milan)",
        "isin": "IE000IQQEL77",
        "category": "Минен UCITS ETF",
        "exchange": "Borsa Italiana",
        "tax": "0%"
    },
    {
        "ticker": "EXV6.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:EXV6",
        "name": "iShares STOXX Europe 600 Basic Resources UCITS ETF",
        "isin": "DE000A0F5UK5",
        "category": "Минен UCITS ETF",
        "exchange": "Xetra",
        "tax": "0% (капиталов)"
    },

    # 2. Батериен UCITS ETF
    {
        "ticker": "BATE.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:BATE",
        "name": "L&G Battery Value-Chain UCITS ETF (Acc)",
        "isin": "IE00BF0M2Z96",
        "category": "Батериен UCITS ETF",
        "exchange": "Xetra",
        "tax": "0%"
    },
    {
        "ticker": "BATT.MI",
        "asset_class": "intl_stocks",
        "tv_symbol": "MIL:BATT",
        "name": "L&G Battery Value-Chain UCITS ETF (Milan)",
        "isin": "IE00BF0M2Z96",
        "category": "Батериен UCITS ETF",
        "exchange": "Borsa Italiana",
        "tax": "0%"
    },
    {
        "ticker": "RARE.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:RARE",
        "name": "WisdomTree Strategic Metals & Rare Earths Miners",
        "isin": "IE000KHX9DX6",
        "category": "Батериен UCITS ETF",
        "exchange": "Xetra",
        "tax": "0%"
    },

    # 3. Европейска акция
    {
        "ticker": "BOL.ST",
        "asset_class": "intl_stocks",
        "tv_symbol": "OMXSTO:BOL",
        "name": "Boliden AB",
        "isin": "SE0020050417",
        "category": "Европейска акция",
        "exchange": "Nasdaq Stockholm",
        "tax": "0%"
    },
    {
        "ticker": "KGH.WA",
        "asset_class": "intl_stocks",
        "tv_symbol": "GPW:KGH",
        "name": "KGHM Polska Miedź SA",
        "isin": "PLKGHM000017",
        "category": "Европейска акция",
        "exchange": "Warsaw Stock Exchange",
        "tax": "0%"
    },
    {
        "ticker": "NDA.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:NDA",
        "name": "Aurubis AG",
        "isin": "DE0006766504",
        "category": "Европейска акция",
        "exchange": "Xetra Prime Standard",
        "tax": "0%"
    },
    {
        "ticker": "AMG.AS",
        "asset_class": "intl_stocks",
        "tv_symbol": "EURONEXT:AMG",
        "name": "AMG Critical Materials N.V.",
        "isin": "NL0000888691",
        "category": "Европейска акция",
        "exchange": "Euronext Amsterdam",
        "tax": "0%"
    },
    {
        "ticker": "ADG.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:ADG",
        "name": "AMG Critical Materials N.V. (Frankfurt)",
        "isin": "NL0000888691",
        "category": "Европейска акция",
        "exchange": "Xetra Regulated Market",
        "tax": "0%"
    },
    {
        "ticker": "UMI.BR",
        "asset_class": "intl_stocks",
        "tv_symbol": "EURONEXT:UMI",
        "name": "Umicore SA",
        "isin": "BE0974320526",
        "category": "Европейска акция",
        "exchange": "Euronext Brussels",
        "tax": "0%"
    },
    {
        "ticker": "VUL.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:VUL",
        "name": "Vulcan Energy Resources Ltd",
        "isin": "AU0000066086",
        "category": "Европейска акция",
        "exchange": "Xetra Prime Standard",
        "tax": "0% (само на XETA)"
    },
    {
        "ticker": "ERA.PA",
        "asset_class": "intl_stocks",
        "tv_symbol": "EURONEXT:ERA",
        "name": "Eramet SA",
        "isin": "FR0000131757",
        "category": "Европейска акция",
        "exchange": "Euronext Paris",
        "tax": "0%"
    },

    # 4. Международна акция
    {
        "ticker": "BHP",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:BHP",
        "name": "BHP Group Ltd (NYSE)",
        "isin": "AU000000BHP4",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "RIO",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:RIO",
        "name": "Rio Tinto plc (NYSE)",
        "isin": "GB0007188757",
        "category": "Международна акция",
        "exchange": "NYSE / LSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "GLEN.L",
        "asset_class": "intl_stocks",
        "tv_symbol": "LSE:GLEN",
        "name": "Glencore plc",
        "isin": "JE00B4T3BW64",
        "category": "Международна акция",
        "exchange": "LSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "FCX",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:FCX",
        "name": "Freeport-McMoRan Inc.",
        "isin": "US35671D8570",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "IVN.TO",
        "asset_class": "intl_stocks",
        "tv_symbol": "TSX:IVN",
        "name": "Ivanhoe Mines Ltd",
        "isin": "CA46579R1047",
        "category": "Международна акция",
        "exchange": "TSX (Торонто)",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "ALB",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:ALB",
        "name": "Albemarle Corp.",
        "isin": "US0126531013",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "SQM",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:SQM",
        "name": "SQM (Sociedad Química y Minera)",
        "isin": "US8336351056",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "PLS.AX",
        "asset_class": "intl_stocks",
        "tv_symbol": "ASX:PLS",
        "name": "Pilbara Minerals Ltd",
        "isin": "AU000000PLS6",
        "category": "Международна акция",
        "exchange": "ASX (Австралия)",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "MP",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:MP",
        "name": "MP Materials Corp.",
        "isin": "US5533681012",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "SBSW",
        "asset_class": "us_stocks",
        "tv_symbol": "NYSE:SBSW",
        "name": "Sibanye-Stillwater (Keliber)",
        "isin": "US82575P1075",
        "category": "Международна акция",
        "exchange": "NYSE",
        "tax": "9% (акция извън ЕС)"
    },
    {
        "ticker": "TLG.AX",
        "asset_class": "intl_stocks",
        "tv_symbol": "ASX:TLG",
        "name": "Talga Group Ltd",
        "isin": "AU000000TLG7",
        "category": "Международна акция",
        "exchange": "ASX / Xetra Open Market",
        "tax": "9% (Open Market/ASX)"
    },

    # 5. Short Автосектор
    {
        "ticker": "LYQL.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:LYQL",
        "name": "Amundi ShortDAX Daily (-2x) Inverse UCITS ETF",
        "isin": "FR0010869495",
        "category": "Short Автосектор (ETF)",
        "exchange": "Xetra",
        "tax": "0%"
    },
    {
        "ticker": "BXX.PA",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:BXX",
        "name": "Amundi EURO STOXX 50 Daily (-2x) Inverse UCITS ETF",
        "isin": "FR0010424143",
        "category": "Short Автосектор (ETF)",
        "exchange": "Xetra / Euronext Paris",
        "tax": "0%"
    },
    {
        "ticker": "EXV5.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:EXV5",
        "name": "iShares STOXX Europe 600 Auto & Parts UCITS ETF",
        "isin": "DE000A0Q4R28",
        "category": "Short Автосектор (Секторен)",
        "exchange": "Xetra",
        "tax": "9% (при маржин къса)"
    },
    {
        "ticker": "STLAM.MI",
        "asset_class": "intl_stocks",
        "tv_symbol": "MIL:STLAM",
        "name": "Stellantis N.V. (Put/Short)",
        "isin": "NL00150001Q9",
        "category": "Short Автосектор (Базова акция)",
        "exchange": "Borsa Italiana / Euronext",
        "tax": "9% (при деривати)"
    },
    {
        "ticker": "VOW3.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:VOW3",
        "name": "Volkswagen AG Pref. (Put/Short)",
        "isin": "DE0007664039",
        "category": "Short Автосектор (Базова акция)",
        "exchange": "Xetra",
        "tax": "9% (при деривати)"
    },
    {
        "ticker": "BMW.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:BMW",
        "name": "BMW AG (Put/Short)",
        "isin": "DE0005190003",
        "category": "Short Автосектор (Базова акция)",
        "exchange": "Xetra",
        "tax": "9% (при деривати)"
    },
    {
        "ticker": "MBG.DE",
        "asset_class": "intl_stocks",
        "tv_symbol": "XETR:MBG",
        "name": "Mercedes-Benz Group AG (Put/Short)",
        "isin": "DE0007100000",
        "category": "Short Автосектор (Базова акция)",
        "exchange": "Xetra",
        "tax": "9% (при деривати)"
    },

    # 6. Суровини
    {
        "ticker": "HG=F",
        "asset_class": "commodities",
        "tv_symbol": "COMEX:HG1!",
        "name": "Мед (Copper Futures / Spot)",
        "isin": "—",
        "category": "Суровина (TradingView)",
        "exchange": "COMEX / TVC",
        "tax": "—"
    },
    {
        "ticker": "LTH=F",
        "asset_class": "commodities",
        "tv_symbol": "COMEX:LTH1!",
        "name": "Литиев хидроксид (Fastmarkets / COMEX)",
        "isin": "—",
        "category": "Суровина (TradingView)",
        "exchange": "COMEX",
        "tax": "—"
    },
    {
        "ticker": "LNIK.L",
        "asset_class": "commodities",
        "tv_symbol": "LME:NI1!",
        "name": "Никел (Nickel Spot / Futures)",
        "isin": "JE00BN707722",
        "category": "Суровина (TradingView)",
        "exchange": "LME / LSE",
        "tax": "—"
    },
    {
        "ticker": "ZNC=F",
        "asset_class": "commodities",
        "tv_symbol": "COMEX:ZNC1!",
        "name": "Цинк (Zinc Futures)",
        "isin": "—",
        "category": "Суровина (TradingView)",
        "exchange": "COMEX / MCX",
        "tax": "—"
    },
    {
        "ticker": "GC=F",
        "asset_class": "commodities",
        "tv_symbol": "COMEX:GC1!",
        "name": "Злато (Gold Futures / Spot)",
        "isin": "—",
        "category": "Суровина (TradingView)",
        "exchange": "COMEX / TVC",
        "tax": "—"
    },
    {
        "ticker": "SI=F",
        "asset_class": "commodities",
        "tv_symbol": "COMEX:SI1!",
        "name": "Сребро (Silver Futures / Spot)",
        "isin": "—",
        "category": "Суровина (TradingView)",
        "exchange": "COMEX / TVC",
        "tax": "—"
    }
]

def sync_and_scan():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_yaml_path = os.path.join(project_root, "config", "assets.yaml")
    tv_mapping_path = os.path.join(project_root, "config", "tv_mapping.json")
    names_mapping_path = os.path.join(project_root, "config", "names_mapping.json")

    # Load existing configs
    with open(assets_yaml_path, "r", encoding="utf-8") as f:
        assets_data = yaml.safe_load(f) or {}

    with open(tv_mapping_path, "r", encoding="utf-8") as f:
        tv_data = json.load(f)

    with open(names_mapping_path, "r", encoding="utf-8") as f:
        names_data = json.load(f)

    db = Database()
    yf_fetcher = YFinanceFetcher()

    added_to_yaml = 0
    symbols_to_upsert = []
    tickers_to_fetch = []

    for item in NEW_ASSETS:
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
        
        # Check if already in list
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

    print(f"Updated config files! Added {added_to_yaml} new entries to assets.yaml.")
    print("Now fetching candle data and computing Larsson Line states...")

    # Fetch batch candles via yf_fetcher
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
                scanned_results.append((ticker, current_state.value, float(latest_price)))
            except Exception as e:
                print(f"Error computing state for {ticker}: {e}")

    # Export dashboard data
    export_dashboard_data(db)
    print("Exported dashboard data.json successfully!")
    print("\n--- Summary of Scanned States ---")
    for sym, st, pr in scanned_results:
        print(f"  {sym:10s} | {st:7s} | {pr:10.2f}")

if __name__ == "__main__":
    sync_and_scan()
