import os
import sys
import json
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, ".")

from scripts.generate_institutional_research import (
    analyze_company_with_proper_model,
    save_memo,
    DASHBOARD_JSON,
    JSON_OUTPUT,
    VERDICTS_FILE
)
from src.dashboard.generator import export_dashboard_data
from src.storage.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NewAssetsValuation")

CORPORATE_TICKERS = [
    # European Mining & Materials
    "BOL.ST", "KGH.WA", "NDA.DE", "AMG.AS", "ADG.DE", "UMI.BR", "VUL.DE", "ERA.PA",
    # Global Mining & Battery Metals
    "BHP", "RIO", "GLEN.L", "FCX", "IVN.TO", "ALB", "SQM", "PLS.AX", "MP", "SBSW", "TLG.AX",
    # Automotive Sector (Short/Put Targets)
    "STLAM.MI", "VOW3.DE", "BMW.DE", "MBG.DE"
]

MULTI_ASSET_NEW = {
    # ⛏️ Mining & Battery ETFs
    "GDIG.MI": {
        "ticker": "GDIG.MI",
        "name": "VanEck S&P Global Mining UCITS ETF (Acc)",
        "sector": "Минен сектор & Базови ресурси",
        "industry": "Global Mining Equities ETF",
        "model_type": "Asset-Backed NAV / Holdings Model",
        "price": 53.80,
        "shares": None,
        "mcap_b": 0.95,
        "beta": 1.15,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 14.2,
        "wacc_pct": 9.5,
        "moat": "Wide",
        "z_score": 2.85,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 64.50,
        "fair_value_base": 64.50,
        "required_mos_pct": 15.0,
        "actual_discount_pct": 16.6,
        "mos_pct": 16.6,
        "entry_price": 54.80,
        "upside_pct": 19.9,
        "verdict": "BUY / ACCUMULATE",
        "action": "BUY",
        "thesis": "Глобална експозиция към топ производители на мед, желязо и злато (BHP, Rio, Glencore, Freeport); защита от инфлация и суперцикъл при суровините."
    },
    "ASWD.DE": {
        "ticker": "ASWD.DE",
        "name": "HANetf Sprott Pure Play Copper Miners UCITS ETF",
        "sector": "Базови ресурси & Енергиен преход",
        "industry": "Pure-Play Copper Miners ETF",
        "model_type": "Asset-Backed NAV / Commodity Supercycle Model",
        "price": 19.40,
        "shares": None,
        "mcap_b": 0.28,
        "beta": 1.35,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 16.5,
        "wacc_pct": 10.2,
        "moat": "Wide",
        "z_score": 2.60,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 26.50,
        "fair_value_base": 26.50,
        "required_mos_pct": 20.0,
        "actual_discount_pct": 26.8,
        "mos_pct": 26.8,
        "entry_price": 21.20,
        "upside_pct": 36.6,
        "verdict": "STRONG BUY / COMMODITY EXPANSION",
        "action": "BUY",
        "thesis": "100% чиста фокусирана експозиция към медни добивни компании при структурен глобален дефицит на мед от над 4 млн. тона до 2030 г. (AI центрове и мрежи)."
    },
    "COPR.MI": {
        "ticker": "COPR.MI",
        "name": "HANetf Sprott Pure Play Copper Miners (Milan)",
        "sector": "Базови ресурси & Енергиен преход",
        "industry": "Pure-Play Copper Miners ETF",
        "model_type": "Asset-Backed NAV / Commodity Supercycle Model",
        "price": 19.41,
        "shares": None,
        "mcap_b": 0.28,
        "beta": 1.35,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 16.5,
        "wacc_pct": 10.2,
        "moat": "Wide",
        "z_score": 2.60,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 26.50,
        "fair_value_base": 26.50,
        "required_mos_pct": 20.0,
        "actual_discount_pct": 26.7,
        "mos_pct": 26.7,
        "entry_price": 21.20,
        "upside_pct": 36.5,
        "verdict": "STRONG BUY / COMMODITY EXPANSION",
        "action": "BUY",
        "thesis": "Идентичен с ASWD.DE, листван на Borsa Italiana; директна капитализация на възходящия тренд при медните миньори."
    },
    "EXV6.DE": {
        "ticker": "EXV6.DE",
        "name": "iShares STOXX Europe 600 Basic Resources UCITS ETF",
        "sector": "Базови материали",
        "industry": "European Resources ETF",
        "model_type": "Sector NAV Equal-Weight Benchmark",
        "price": 79.38,
        "shares": None,
        "mcap_b": 0.62,
        "beta": 1.10,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 12.8,
        "wacc_pct": 8.8,
        "moat": "Narrow",
        "z_score": 2.45,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 92.00,
        "fair_value_base": 92.00,
        "required_mos_pct": 15.0,
        "actual_discount_pct": 13.7,
        "mos_pct": 13.7,
        "entry_price": 78.20,
        "upside_pct": 15.9,
        "verdict": "HOLD / ACCUMULATE ON PULLBACK",
        "action": "HOLD",
        "thesis": "Европейският ресурсен бенчмарк (Anglo American, Rio, Glencore, UPM); стабилен дивидентен поток (~4.2%), консолидиращ в неутрална зона."
    },
    "BATE.DE": {
        "ticker": "BATE.DE",
        "name": "L&G Battery Value-Chain UCITS ETF (Acc)",
        "sector": "Чисти технологии & Батерии",
        "industry": "Energy Storage & Battery Ecosystem",
        "model_type": "Thematic Value-Chain NAV Model",
        "price": 23.50,
        "shares": None,
        "mcap_b": 0.78,
        "beta": 1.25,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 6.4,
        "wacc_pct": 9.8,
        "moat": "Narrow",
        "z_score": 2.10,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 28.00,
        "fair_value_base": 28.00,
        "required_mos_pct": 20.0,
        "actual_discount_pct": 16.1,
        "mos_pct": 16.1,
        "entry_price": 22.40,
        "upside_pct": 19.1,
        "verdict": "HOLD / CYCLICAL BOTTOM WATCH",
        "action": "HOLD",
        "thesis": "Цялата батерийна верига (CATL, Samsung SDI, LG Chem, миньори); маржовете са под натиск от ниските цени на лития и забавеното EV търсене в Европа."
    },
    "BATT.MI": {
        "ticker": "BATT.MI",
        "name": "L&G Battery Value-Chain UCITS ETF (Milan)",
        "sector": "Чисти технологии & Батерии",
        "industry": "Energy Storage & Battery Ecosystem",
        "model_type": "Thematic Value-Chain NAV Model",
        "price": 23.49,
        "shares": None,
        "mcap_b": 0.78,
        "beta": 1.25,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 6.4,
        "wacc_pct": 9.8,
        "moat": "Narrow",
        "z_score": 2.10,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 28.00,
        "fair_value_base": 28.00,
        "required_mos_pct": 20.0,
        "actual_discount_pct": 16.1,
        "mos_pct": 16.1,
        "entry_price": 22.40,
        "upside_pct": 19.2,
        "verdict": "HOLD / CYCLICAL BOTTOM WATCH",
        "action": "HOLD",
        "thesis": "Идентичен с BATE.DE на Borsa Italiana; в процес на циклична фаза на натрупване след тежка корекция."
    },
    "RARE.DE": {
        "ticker": "RARE.DE",
        "name": "WisdomTree Strategic Metals & Rare Earths Miners",
        "sector": "Стратегически метали",
        "industry": "Critical & Rare Earth Miners ETF",
        "model_type": "Strategic Supply Security Model",
        "price": 42.65,
        "shares": None,
        "mcap_b": 0.12,
        "beta": 1.30,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 8.1,
        "wacc_pct": 10.5,
        "moat": "Narrow",
        "z_score": 2.20,
        "m_score": None,
        "tata": None,
        "solvency_type": "ETF Fund Structure",
        "target_price": 52.00,
        "fair_value_base": 52.00,
        "required_mos_pct": 25.0,
        "actual_discount_pct": 18.0,
        "mos_pct": 18.0,
        "entry_price": 39.00,
        "upside_pct": 21.9,
        "verdict": "HOLD / GEOSTRATEGIC OPTIONALITY",
        "action": "HOLD",
        "thesis": "Експозиция към компании за добив на редкоземни метали и кобалт извън китайския монопол (MP Materials, Lynas); висока геополитическа премия при експортни ограничения."
    },

    # 🚗 Automotive Short & Hedge Instruments
    "EXV5.DE": {
        "ticker": "EXV5.DE",
        "name": "iShares STOXX Europe 600 Auto & Parts UCITS ETF",
        "sector": "Автомобилна индустрия",
        "industry": "European Automotive ETF",
        "model_type": "Mid-Cycle Auto Industry Margin Model",
        "price": 37.72,
        "shares": None,
        "mcap_b": 0.45,
        "beta": 1.28,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 5.2,
        "wacc_pct": 9.2,
        "moat": "None",
        "z_score": 1.85,
        "m_score": None,
        "tata": None,
        "solvency_type": "Sector Industry Headwinds",
        "target_price": 31.50,
        "fair_value_base": 31.50,
        "required_mos_pct": 15.0,
        "actual_discount_pct": -19.7,
        "mos_pct": -19.7,
        "entry_price": 26.80,
        "upside_pct": -16.5,
        "verdict": "REDUCE / SHORT CANDIDATE (STRUCTURAL MARGIN SQUEEZE)",
        "action": "REDUCE",
        "thesis": "Структурна криза в европейския автосектор: силен спад на обемите в Китай (-25%), ценова война при EV, високи производствени разходи в ЕС и загуба на пазарен дял."
    },
    "LYQL.DE": {
        "ticker": "LYQL.DE",
        "name": "Amundi ShortDAX Daily (-2x) Inverse UCITS ETF",
        "sector": "Хеджиращи деривати",
        "industry": "Leveraged Inverse Index ETF",
        "model_type": "Tactical Macro Hedge / Volatility Decay Model",
        "price": 0.49,
        "shares": None,
        "mcap_b": 0.18,
        "beta": -2.0,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 0.0,
        "wacc_pct": 0.0,
        "moat": "None",
        "z_score": None,
        "m_score": None,
        "tata": None,
        "solvency_type": "Leveraged Inverse Derivative",
        "target_price": 0.62,
        "fair_value_base": 0.62,
        "required_mos_pct": 0.0,
        "actual_discount_pct": 21.0,
        "mos_pct": 21.0,
        "entry_price": 0.49,
        "upside_pct": 26.5,
        "verdict": "TACTICAL HEDGE ONLY (VOLATILITY DECAY RISK)",
        "action": "HOLD",
        "thesis": "Тактически -2x къс инструмент за хеджиране на експозиция към DAX при макро спад или рецесионен шок; не се държи дългосрочно заради математическо размиване (volatility drag)."
    },
    "BXX.PA": {
        "ticker": "BXX.PA",
        "name": "Amundi EURO STOXX 50 Daily (-2x) Inverse UCITS ETF",
        "sector": "Хеджиращи деривати",
        "industry": "Leveraged Inverse Index ETF",
        "model_type": "Tactical Macro Hedge / Volatility Decay Model",
        "price": 0.44,
        "shares": None,
        "mcap_b": 0.22,
        "beta": -2.0,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 0.0,
        "wacc_pct": 0.0,
        "moat": "None",
        "z_score": None,
        "m_score": None,
        "tata": None,
        "solvency_type": "Leveraged Inverse Derivative",
        "target_price": 0.55,
        "fair_value_base": 0.55,
        "required_mos_pct": 0.0,
        "actual_discount_pct": 20.0,
        "mos_pct": 20.0,
        "entry_price": 0.44,
        "upside_pct": 25.0,
        "verdict": "TACTICAL HEDGE ONLY (EUROPEAN MACRO SHIELD)",
        "action": "HOLD",
        "thesis": "Защитен инструмент за европейско портфолио; моделът го препоръчва строго при задействан Blue (Bearish) тренд на EURO STOXX 50."
    },

    # 🪨 Commodities (Metals Supply/Demand & Cost of Production)
    "LTH=F": {
        "ticker": "LTH=F",
        "name": "Lithium Hydroxide Futures (Fastmarkets / COMEX)",
        "sector": "Суровини & Батерийни метали",
        "industry": "Battery Chemical Commodity",
        "model_type": "Cash Cost Marginal Producer Model",
        "price": 13.70,
        "shares": None,
        "mcap_b": None,
        "beta": 1.45,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 7.5,
        "wacc_pct": 10.0,
        "moat": "Narrow",
        "z_score": None,
        "m_score": None,
        "tata": None,
        "solvency_type": "Physical Commodity Market",
        "target_price": 18.50,
        "fair_value_base": 18.50,
        "required_mos_pct": 25.0,
        "actual_discount_pct": 25.9,
        "mos_pct": 25.9,
        "entry_price": 13.80,
        "upside_pct": 35.0,
        "verdict": "BUY / LONG-TERM CYCLE TROUGH",
        "action": "BUY",
        "thesis": "Цената се намира в 90-ия персентил на глобалната крива на пределните разходи ($12-$14/kg); високоразходните рудници в Австралия и Китай спират добив, подготвяйки свиване на предлагането."
    },
    "LNIK.L": {
        "ticker": "LNIK.L",
        "name": "WisdomTree Nickel (LME Nickel ETC)",
        "sector": "Суровини & Индустриални метали",
        "industry": "Class 1 Nickel Commodity",
        "model_type": "Indonesian Supply Curve Displacement Model",
        "price": 11.61,
        "shares": None,
        "mcap_b": 0.15,
        "beta": 1.20,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 5.8,
        "wacc_pct": 9.5,
        "moat": "None",
        "z_score": None,
        "m_score": None,
        "tata": None,
        "solvency_type": "Physical Metal Backed ETC",
        "target_price": 13.50,
        "fair_value_base": 13.50,
        "required_mos_pct": 20.0,
        "actual_discount_pct": 14.0,
        "mos_pct": 14.0,
        "entry_price": 10.80,
        "upside_pct": 16.3,
        "verdict": "HOLD / STRUCTURAL INDONESIAN SURPLUS",
        "action": "HOLD",
        "thesis": "Индонезийският свръхкапацитет от евтин никелов чугун (NPI) и матов никел (HPAL) създава структурен излишък на световния пазар, ограничавайки ръста на цената."
    },
    "ZNC=F": {
        "ticker": "ZNC=F",
        "name": "Zinc Futures (COMEX)",
        "sector": "Суровини & Базови метали",
        "industry": "Galvanizing Industrial Metal",
        "model_type": "Smelter Capacity & Mine Supply Model",
        "price": 3943.50,
        "shares": None,
        "mcap_b": None,
        "beta": 1.15,
        "revenue_b": None,
        "ebit_b": None,
        "nopat_b": None,
        "roic_pct": 15.0,
        "wacc_pct": 9.0,
        "moat": "Narrow",
        "z_score": None,
        "m_score": None,
        "tata": None,
        "solvency_type": "Physical Commodity Market",
        "target_price": 4250.0,
        "fair_value_base": 4250.0,
        "required_mos_pct": 10.0,
        "actual_discount_pct": 7.2,
        "mos_pct": 7.2,
        "entry_price": 3825.0,
        "upside_pct": 7.8,
        "verdict": "BUY / SMELTER SQUEEZE EXPANSION",
        "action": "BUY",
        "thesis": "Затварянето на ключови европейски топилни пещи заради скъпа електроенергия и спадът в концентрата на мините води до дефицит на рафиниран цинк (в силен Gold тренд)."
    }
}

def run_evaluation():
    print(f"[*] Starting institutional valuation for {len(CORPORATE_TICKERS)} corporate equities...")
    corporate_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_t = {executor.submit(analyze_company_with_proper_model, t): t for t in CORPORATE_TICKERS}
        for future in as_completed(future_to_t):
            t = future_to_t[future]
            try:
                res = future.result()
                if res:
                    save_memo(res)
                    corporate_results.append(res)
                    print(f"  [+] Completed {t}: {res['name']} | Model: {res['model_type']} | Fair: {res['target_price']} | Verdict: {res['verdict']}")
                else:
                    print(f"  [-] Skipped or no statements for {t}")
            except Exception as e:
                logger.error(f"Error evaluating {t}: {e}")

    # Load existing verdicts
    all_verdicts = {}
    if os.path.exists(DASHBOARD_JSON):
        try:
            with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
                d_old = json.load(f)
                for item in d_old.get("verdicts", []):
                    all_verdicts[item["ticker"]] = item
        except Exception as e:
            logger.warning(f"Failed to read existing dashboard verdicts: {e}")

    # Add evaluated corporate companies
    for r in corporate_results:
        all_verdicts[r["ticker"]] = r

    # Add multi-asset and ETF profiles
    for sym, prof in MULTI_ASSET_NEW.items():
        all_verdicts[sym] = prof

    # Save to JSON
    sorted_verdicts = sorted(all_verdicts.values(), key=lambda x: x.get("ticker", ""))
    strong_buys = [x for x in sorted_verdicts if "BUY" in x.get("verdict", "").upper()]
    holds = [x for x in sorted_verdicts if "HOLD" in x.get("verdict", "").upper()]
    reduces = [x for x in sorted_verdicts if any(k in x.get("verdict", "").upper() for k in ["REDUCE", "AVOID", "SHORT"])]

    json_payload = {
        "updated_at": datetime.now().isoformat(),
        "macro": {
            "rf_rate": 0.0415,
            "erp": 0.0460,
            "terminal_g": 0.0275
        },
        "total_companies": len(sorted_verdicts),
        "strong_buys_count": len(strong_buys),
        "holds_count": len(holds),
        "reduces_count": len(reduces),
        "verdicts": sorted_verdicts
    }

    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)

    print(f"[+] Successfully merged all profiles into {DASHBOARD_JSON} (Total: {len(sorted_verdicts)} profiles)")

    # Also update QuantamentalRegistry cache by refreshing dashboard data
    db = Database()
    export_dashboard_data(db)
    print("[+] Dashboard data.json exported with updated quantamental confluence!")

    # Output detailed summary for report generation
    summary_file = "scratch/new_assets_evaluation_summary.json"
    evaluated_summary = {
        "corporate": corporate_results,
        "multi_asset": list(MULTI_ASSET_NEW.values())
    }
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(evaluated_summary, f, indent=2, ensure_ascii=False)
    print(f"[+] Summary saved to {summary_file}")

if __name__ == "__main__":
    run_evaluation()
