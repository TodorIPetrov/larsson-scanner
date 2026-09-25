"""
Quantamental Engine: Ingestion and evaluation of institutional fundamental research.
Merges deep equity valuation (DCF, MoS, Moat, Altman Z, ROIC) and multi-asset memos
with technical trade signals.
"""

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _clean_float(val: Optional[float]) -> Optional[float]:
    """Ensures floats are JSON compliant (converts NaN/Inf to None)."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


@dataclass
class FundamentalProfile:
    ticker: str
    name: str
    verdict: str  # 'STRONG BUY', 'BUY', 'HOLD', 'REDUCE', 'OVERWEIGHT', 'NEUTRAL'
    target_price: Optional[float] = None
    fair_value: Optional[float] = None
    mos_pct: Optional[float] = None
    moat: str = "None"  # 'Wide', 'Narrow', 'None'
    roic_pct: Optional[float] = None
    wacc_pct: Optional[float] = None
    z_score: Optional[float] = None
    m_score: Optional[float] = None
    upside_pct: Optional[float] = None
    thesis: str = ""
    # Enriched forensic and company metrics
    sector: Optional[str] = None
    industry: Optional[str] = None
    model_type: Optional[str] = None
    price: Optional[float] = None
    shares: Optional[float] = None
    mcap_b: Optional[float] = None
    beta: Optional[float] = None
    revenue_b: Optional[float] = None
    ebit_b: Optional[float] = None
    nopat_b: Optional[float] = None
    tata: Optional[float] = None
    entry_price: Optional[float] = None
    action: Optional[str] = None
    solvency_type: Optional[str] = None
    production_cost: Optional[float] = None
    mvrv_ratio: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_bullish"] = self.is_bullish
        d["is_bearish_or_distressed"] = self.is_bearish_or_distressed
        d["is_hold"] = self.is_hold
        return d

    @property
    def is_bullish(self) -> bool:
        return any(k in self.verdict.upper() for k in ["STRONG BUY", "BUY", "OVERWEIGHT"])

    @property
    def is_bearish_or_distressed(self) -> bool:
        if any(k in self.verdict.upper() for k in ["REDUCE", "AVOID", "UNDERPERFORM"]):
            return True
        if self.z_score is not None and self.z_score < 1.81:
            return True
        return False

    @property
    def is_hold(self) -> bool:
        return any(k in self.verdict.upper() for k in ["HOLD", "NEUTRAL", "FAIRLY VALUED"])


# Multi-asset registry for Commodities, Crypto, and Macro Indices derived from institutional memos
_MULTI_ASSET_PROFILES: Dict[str, dict] = {
    # 🪙 Digital Assets (CRYPTO_DIGITAL_ASSETS_MEMO.md)
    "BTCUSDT": {
        "name": "Bitcoin",
        "verdict": "STRONG BUY",
        "target_price": 120000.0,
        "fair_value": 110000.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 5.0,
        "upside_pct": 45.0,
        "thesis": "MVRV 1.95 зряла консолидация; себестойност $58k-$64k твърд под; нетни ETF притоци >650k BTC.",
    },
    "ETHUSDT": {
        "name": "Ethereum",
        "verdict": "HOLD",
        "target_price": 2800.0,
        "fair_value": 2600.0,
        "mos_pct": 10.0,
        "moat": "Narrow",
        "z_score": 3.2,
        "upside_pct": 8.0,
        "thesis": "L2 канибализация на такси срещу 3.2% стейкинг доходност; акумулиране при $2,200.",
    },
    "SOLUSDT": {
        "name": "Solana",
        "verdict": "BUY",
        "target_price": 150.0,
        "fair_value": 135.0,
        "mos_pct": 28.0,
        "moat": "Narrow",
        "z_score": 3.8,
        "upside_pct": 39.0,
        "thesis": "Лидер по DEX скорост на капитал; акумулиране в дневната S/R зона $90-$94.",
    },
    "PAXGUSDT": {
        "name": "Pax Gold",
        "verdict": "STRONG BUY",
        "target_price": 4800.0,
        "fair_value": 4650.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 5.0,
        "upside_pct": 11.0,
        "thesis": "1:1 физическо обезпечение със злато; институционален де-доларизационен хедж.",
    },
    "LINKUSDT": {
        "name": "Chainlink",
        "verdict": "STRONG BUY",
        "target_price": 22.0,
        "fair_value": 19.5,
        "mos_pct": 45.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 81.0,
        "thesis": "Монопол при оракулите и токенизацията на реални активи (RWA); силна акумулация под $11.",
    },
    "BNBUSDT": {
        "name": "BNB",
        "verdict": "HOLD",
        "target_price": 750.0,
        "fair_value": 720.0,
        "mos_pct": 5.0,
        "moat": "Narrow",
        "z_score": 3.0,
        "upside_pct": 2.0,
        "thesis": "Launchpool ликвидност и борсова полезност; консолидация в широк рейндж.",
    },
    "XRPUSDT": {
        "name": "Ripple",
        "verdict": "HOLD",
        "target_price": 1.35,
        "fair_value": 1.25,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": 2.5,
        "upside_pct": 0.0,
        "thesis": "Спекулативно задържане след регулаторно облекчение.",
    },
    "SUIUSDT": {
        "name": "Sui Network",
        "verdict": "BUY",
        "target_price": 1.20,
        "fair_value": 1.05,
        "mos_pct": 30.0,
        "moat": "Narrow",
        "z_score": 3.0,
        "upside_pct": 47.0,
        "thesis": "Нов L1 претендент с бързо растящ TVL; селективно натрупване.",
    },
    "DOGEUSDT": {
        "name": "Dogecoin",
        "verdict": "REDUCE",
        "target_price": 0.06,
        "fair_value": 0.05,
        "mos_pct": -37.0,
        "moat": "None",
        "z_score": 1.2,
        "upside_pct": -37.0,
        "thesis": "Високобета мем ликвидност без паричен поток или фундаментален ров.",
    },
    "ADAUSDT": {
        "name": "Cardano",
        "verdict": "REDUCE",
        "target_price": 0.16,
        "fair_value": 0.15,
        "mos_pct": -25.0,
        "moat": "None",
        "z_score": 1.5,
        "upside_pct": -25.0,
        "thesis": "Ниска он-чейн скорост на транзакции и изоставаща DeFi екосистема.",
    },

    # 🥇 Commodities & Metals (COMMODITIES_RESEARCH_MEMO.md)
    "GC=F": {
        "name": "Gold Futures",
        "verdict": "STRONG BUY",
        "target_price": 4900.0,
        "fair_value": 4750.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 5.0,
        "upside_pct": 11.0,
        "thesis": "Секуларен бичи тренд; де-доларизация на централни банки (>1,000 т/год); AISC подкрепа.",
    },
    "SI=F": {
        "name": "Silver Futures",
        "verdict": "BUY",
        "target_price": 75.0,
        "fair_value": 72.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": 4.0,
        "upside_pct": 12.0,
        "thesis": "Структурен индустриален дефицит; соларно (TOPCon) и AI хардуерно търсене.",
    },
    "HG=F": {
        "name": "Copper Futures",
        "verdict": "STRONG BUY",
        "target_price": 8.50,
        "fair_value": 8.20,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 27.0,
        "thesis": "Електропреносен дефицит и тясно място за AI гигаватовите дата центрове.",
    },
    "URA": {
        "name": "Global X Uranium ETF",
        "verdict": "STRONG BUY",
        "target_price": 58.0,
        "fair_value": 55.0,
        "mos_pct": 28.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 32.0,
        "thesis": "Ядрен ренесанс; дългосрочни 20-годишни договори с Microsoft, Google и Amazon.",
    },
    "URNM": {
        "name": "Sprott Uranium Miners ETF",
        "verdict": "STRONG BUY",
        "target_price": 70.0,
        "fair_value": 66.0,
        "mos_pct": 28.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 31.0,
        "thesis": "Институционален спред и недостиг на активни уранови рудници.",
    },
    "CL=F": {
        "name": "Crude Oil WTI",
        "verdict": "HOLD",
        "target_price": 95.0,
        "fair_value": 90.0,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": 3.0,
        "upside_pct": -10.0,
        "thesis": "Вградена геополитическа премия; риск от унищожаване на търсенето над $100.",
    },
    "BZ=F": {
        "name": "Brent Crude Oil",
        "verdict": "HOLD",
        "target_price": 98.0,
        "fair_value": 92.0,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": 3.0,
        "upside_pct": -10.0,
        "thesis": "Ограничен свободен капацитет на OPEC+, но ограничен потенциал за ръст.",
    },
    "NG=F": {
        "name": "Natural Gas",
        "verdict": "BUY",
        "target_price": 4.20,
        "fair_value": 3.90,
        "mos_pct": 30.0,
        "moat": "Narrow",
        "z_score": 2.8,
        "upside_pct": 32.0,
        "thesis": "Търгува се близо до себестойността $2.60; дългосрочно акумулиране за зимния сезон.",
    },
    "PL=F": {
        "name": "Platinum Futures",
        "verdict": "BUY",
        "target_price": 2100.0,
        "fair_value": 2000.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": 3.5,
        "upside_pct": 12.0,
        "thesis": "Зелен водород и заместител на паладия.",
    },

    # 🌐 Macro Indices (MACRO_AND_INDICES_MEMO.md)
    "^GSPC": {
        "name": "S&P 500",
        "verdict": "HOLD",
        "target_price": 7000.0,
        "fair_value": 6800.0,
        "mos_pct": -10.0,
        "moat": "Wide",
        "z_score": 3.5,
        "upside_pct": -10.0,
        "thesis": "Forward P/E 26.8x; компресирана рискова премия; препоръчва се селективен подбор.",
    },
    "^IXIC": {
        "name": "Nasdaq Composite",
        "verdict": "HOLD",
        "target_price": 23500.0,
        "fair_value": 22000.0,
        "mos_pct": -15.0,
        "moat": "Wide",
        "z_score": 3.5,
        "upside_pct": -15.0,
        "thesis": "Forward P/E 33.4x; висока концентрация в Mega-Cap технологични лидери.",
    },
    "^HSI": {
        "name": "Hang Seng Index",
        "verdict": "BUY",
        "target_price": 29000.0,
        "fair_value": 28000.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": 3.0,
        "upside_pct": 12.0,
        "thesis": "P/E 10.4x; дълбоко подценен спрямо глобалните пазари с китайски фискални стимули.",
    },
    "^RUT": {
        "name": "Russell 2000",
        "verdict": "BUY",
        "target_price": 3200.0,
        "fair_value": 3100.0,
        "mos_pct": 10.0,
        "moat": "None",
        "z_score": 2.8,
        "upside_pct": 8.0,
        "thesis": "Лихвена компресия и ротация от надценени мегакапитализации към малки компании.",
    },
    "DX-Y.NYB": {
        "name": "US Dollar Index",
        "verdict": "REDUCE",
        "target_price": 96.0,
        "fair_value": 95.0,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": 3.0,
        "upside_pct": -4.0,
        "thesis": "Спадът под 100 задейства глобална ликвидна експанзия за суровини и рискови активи.",
    },

    # 🌍 European & International Champions (Wide Moats & DCF Intrinsic Valuations)
    "MC.PA": {
        "name": "LVMH Moët Hennessy",
        "verdict": "STRONG BUY",
        "target_price": 780.0,
        "fair_value": 750.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 28.0,
        "thesis": "Глобален луксозен хегемон с незаменима ценова сила и диверсифициран бранд портфейл.",
    },
    "RMS.PA": {
        "name": "Hermès International",
        "verdict": "BUY",
        "target_price": 2400.0,
        "fair_value": 2350.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 5.5,
        "upside_pct": 15.0,
        "thesis": "Върховният ултра-лукс с нулево ценово съпротивление и години чакане за Birkin/Kelly.",
    },
    "OR.PA": {
        "name": "L'Oréal",
        "verdict": "BUY",
        "target_price": 420.0,
        "fair_value": 410.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 4.8,
        "upside_pct": 20.0,
        "thesis": "Световен козметичен лидер с непрекъснат органичен растеж и силни R&D инвестиции.",
    },
    "ITX.MC": {
        "name": "Inditex (Zara)",
        "verdict": "STRONG BUY",
        "target_price": 56.0,
        "fair_value": 54.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 22.0,
        "thesis": "Най-ефективната логистична и бързооборотна модна машина в света (Zara, Massimo Dutti).",
    },
    "NESN.SW": {
        "name": "Nestlé",
        "verdict": "BUY",
        "target_price": 98.0,
        "fair_value": 95.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 3.8,
        "upside_pct": 16.0,
        "thesis": "Глобален защитен потребителски гигант с висока дивидентна устойчивост.",
    },
    "ASML.AS": {
        "name": "ASML Holding",
        "verdict": "STRONG BUY",
        "target_price": 880.0,
        "fair_value": 850.0,
        "mos_pct": 30.0,
        "moat": "Wide",
        "z_score": 5.2,
        "upside_pct": 38.0,
        "thesis": "Абсолютен монопол в EUV литографията за суб-3nm чипове; незаобиколим гръбнак на AI хардуера.",
    },
    "SAP.DE": {
        "name": "SAP SE",
        "verdict": "BUY",
        "target_price": 245.0,
        "fair_value": 240.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 14.0,
        "thesis": "Европейският ERP софтуерен гигант с ускоряващи се cloud приходи и висока лепкавост.",
    },
    "SU.PA": {
        "name": "Schneider Electric",
        "verdict": "STRONG BUY",
        "target_price": 270.0,
        "fair_value": 265.0,
        "mos_pct": 22.0,
        "moat": "Wide",
        "z_score": 4.0,
        "upside_pct": 25.0,
        "thesis": "Ключов бенефициент от електрификацията и охлаждането на новите гигаватови AI центрове.",
    },
    "SIE.DE": {
        "name": "Siemens",
        "verdict": "BUY",
        "target_price": 210.0,
        "fair_value": 205.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 3.9,
        "upside_pct": 19.0,
        "thesis": "Индустриална автоматизация, дигитален софтуер и железопътна инфраструктура.",
    },
    "ABBN.SW": {
        "name": "ABB Ltd",
        "verdict": "BUY",
        "target_price": 56.0,
        "fair_value": 55.0,
        "mos_pct": 16.0,
        "moat": "Wide",
        "z_score": 4.1,
        "upside_pct": 17.0,
        "thesis": "Швейцарски лидер в индустриалната роботика, задвижванията и електрификацията.",
    },
    "ATCO-A.ST": {
        "name": "Atlas Copco",
        "verdict": "BUY",
        "target_price": 200.0,
        "fair_value": 195.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 4.6,
        "upside_pct": 16.0,
        "thesis": "Световен лидер във вакуумните помпи за чипове и индустриални компресори.",
    },
    "ADYEN.AS": {
        "name": "Adyen",
        "verdict": "STRONG BUY",
        "target_price": 1700.0,
        "fair_value": 1650.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 6.0,
        "upside_pct": 32.0,
        "thesis": "Най-модерната глобална финтех платформа за плащания с водеща маржова експанзия.",
    },
    "NOVO-B.CO": {
        "name": "Novo Nordisk",
        "verdict": "STRONG BUY",
        "target_price": 950.0,
        "fair_value": 920.0,
        "mos_pct": 30.0,
        "moat": "Wide",
        "z_score": 6.5,
        "upside_pct": 35.0,
        "thesis": "Дуопол при GLP-1 (Ozempic/Wegovy) срещу затлъстяване с десетилетия пазарен растеж.",
    },
    "RO.SW": {
        "name": "Roche Holding",
        "verdict": "STRONG BUY",
        "target_price": 350.0,
        "fair_value": 340.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 4.8,
        "upside_pct": 28.0,
        "thesis": "Световен онкологичен и диагностичен лидер със силен тръбопровод от нови молекули.",
    },
    "NOVN.SW": {
        "name": "Novartis",
        "verdict": "BUY",
        "target_price": 112.0,
        "fair_value": 110.0,
        "mos_pct": 16.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 18.0,
        "thesis": "Фокусирана иновативна фарматоп компания с отличен баланс и силен свободен паричен поток.",
    },
    "AZN.L": {
        "name": "AstraZeneca",
        "verdict": "STRONG BUY",
        "target_price": 148.0,
        "fair_value": 145.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 26.0,
        "thesis": "Онкологичен двигател с двуцифрен ръст на приходите и широк географски обхват.",
    },
    "AIR.PA": {
        "name": "Airbus",
        "verdict": "STRONG BUY",
        "target_price": 185.0,
        "fair_value": 180.0,
        "mos_pct": 22.0,
        "moat": "Wide",
        "z_score": 3.8,
        "upside_pct": 24.0,
        "thesis": "Глобален търговски авиационен дуопол с рекордна 10-годишна книга с поръчки (A321neo).",
    },
    "AI.PA": {
        "name": "Air Liquide",
        "verdict": "STRONG BUY",
        "target_price": 210.0,
        "fair_value": 205.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 4.4,
        "upside_pct": 20.0,
        "thesis": "Олигопол в индустриалните газове и зеления водород с 20-годишни защитени договори.",
    },
    "BA.L": {
        "name": "BAE Systems",
        "verdict": "BUY",
        "target_price": 16.5,
        "fair_value": 16.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": 3.5,
        "upside_pct": 15.0,
        "thesis": "Европейският лидер в отбранителната индустрия с гарантирани дългосрочни бюджети от НАТО.",
    },
    "ALV.DE": {
        "name": "Allianz",
        "verdict": "STRONG BUY",
        "target_price": 335.0,
        "fair_value": 330.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 4.0,
        "upside_pct": 22.0,
        "thesis": "Световен застрахователен и инвестиционен лидер (PIMCO); 5.5% сигурна дивидентна доходност.",
    },
    "MUV2.DE": {
        "name": "Munich Re",
        "verdict": "STRONG BUY",
        "target_price": 550.0,
        "fair_value": 540.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 21.0,
        "thesis": "Презастрахователен хегемон с най-консервативното ценообразуване на риска.",
    },
    "DTE.DE": {
        "name": "Deutsche Telekom",
        "verdict": "STRONG BUY",
        "target_price": 35.0,
        "fair_value": 34.0,
        "mos_pct": 22.0,
        "moat": "Wide",
        "z_score": 3.6,
        "upside_pct": 24.0,
        "thesis": "Контролен дял в T-Mobile US и водеща европейска оптична и 5G мрежа.",
    },
    "RACE.MI": {
        "name": "Ferrari",
        "verdict": "STRONG BUY",
        "target_price": 460.0,
        "fair_value": 450.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 5.8,
        "upside_pct": 22.0,
        "thesis": "Имунизирана срещу икономически цикли марка с лимитирани бройки и 50% EBITDA марж.",
    },
    "6758.T": {
        "name": "Sony Group",
        "verdict": "STRONG BUY",
        "target_price": 18000.0,
        "fair_value": 17500.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 28.0,
        "thesis": "PlayStation екосистема, музикален каталог и монопол в мобилните CMOS сензори за камери.",
    },
    "7203.T": {
        "name": "Toyota Motor",
        "verdict": "BUY",
        "target_price": 3500.0,
        "fair_value": 3400.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 4.2,
        "upside_pct": 21.0,
        "thesis": "Глобален производствен лидер в хибридните задвижвания с рекорден свободен паричен поток.",
    },
    "6861.T": {
        "name": "Keyence",
        "verdict": "STRONG BUY",
        "target_price": 84000.0,
        "fair_value": 82000.0,
        "mos_pct": 22.0,
        "moat": "Wide",
        "z_score": 6.8,
        "upside_pct": 25.0,
        "thesis": "Фабрична автоматизация и машинно зрение с ненадминати 52% оперативни маржове.",
    },
    "8035.T": {
        "name": "Tokyo Electron",
        "verdict": "STRONG BUY",
        "target_price": 33000.0,
        "fair_value": 32000.0,
        "mos_pct": 24.0,
        "moat": "Wide",
        "z_score": 5.5,
        "upside_pct": 26.0,
        "thesis": "Японски полупроводников гигант в ецването и отлагането на тънки филми за AI памети.",
    },
    "7974.T": {
        "name": "Nintendo",
        "verdict": "BUY",
        "target_price": 9800.0,
        "fair_value": 9500.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 5.9,
        "upside_pct": 20.0,
        "thesis": "Уникално портфолио от защитени гейминг интелектуални права (Mario, Zelda, Pokemon).",
    },
    "8058.T": {
        "name": "Mitsubishi Corp",
        "verdict": "STRONG BUY",
        "target_price": 3700.0,
        "fair_value": 3600.0,
        "mos_pct": 20.0,
        "moat": "Wide",
        "z_score": 3.8,
        "upside_pct": 22.0,
        "thesis": "Ключова японска търговска къща (Sogo Shosha) на Бъфет с експозиция към метали и LNG.",
    },
    "TSM": {
        "name": "Taiwan Semiconductor (TSMC)",
        "verdict": "STRONG BUY",
        "target_price": 240.0,
        "fair_value": 230.0,
        "mos_pct": 30.0,
        "moat": "Wide",
        "z_score": 6.2,
        "upside_pct": 34.0,
        "thesis": "90% пазарен дял при най-авангардните полупроводникови възли (3nm, 2nm) за Nvidia и Apple.",
    },
    "0700.HK": {
        "name": "Tencent Holdings",
        "verdict": "STRONG BUY",
        "target_price": 530.0,
        "fair_value": 520.0,
        "mos_pct": 28.0,
        "moat": "Wide",
        "z_score": 4.8,
        "upside_pct": 30.0,
        "thesis": "WeChat социален монопол, глобален гейминг лидер и силен генеративен AI потенциал.",
    },
    "BABA": {
        "name": "Alibaba Group",
        "verdict": "STRONG BUY",
        "target_price": 150.0,
        "fair_value": 145.0,
        "mos_pct": 40.0,
        "moat": "Wide",
        "z_score": 3.5,
        "upside_pct": 45.0,
        "thesis": "P/E под 10x с $60 млрд. чиста ликвидност и ускоряващ се облачен бизнес (Aliyun).",
    },
    "BHP.AX": {
        "name": "BHP Group",
        "verdict": "BUY",
        "target_price": 50.0,
        "fair_value": 48.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 4.0,
        "upside_pct": 19.0,
        "thesis": "Най-нискоразходният производител на желязна руда и мед в света.",
    },
    "RIO.L": {
        "name": "Rio Tinto",
        "verdict": "BUY",
        "target_price": 64.0,
        "fair_value": 62.0,
        "mos_pct": 18.0,
        "moat": "Wide",
        "z_score": 4.1,
        "upside_pct": 20.0,
        "thesis": "Дивидентна машина с доминиращ дял в мед, боксит и желязна руда.",
    },
    "CSL.AX": {
        "name": "CSL Limited",
        "verdict": "STRONG BUY",
        "target_price": 350.0,
        "fair_value": 340.0,
        "mos_pct": 22.0,
        "moat": "Wide",
        "z_score": 4.5,
        "upside_pct": 24.0,
        "thesis": "Световен лидер при събирането на кръвна плазма и животоспасяващи имуноглобулини.",
    },
    # 🏛️ Closed-End Funds & Special Investment Vehicles
    "PSUS": {
        "name": "Pershing Square USA, Ltd.",
        "verdict": "BUY",
        "target_price": 55.0,
        "fair_value": 50.0,
        "mos_pct": 22.2,
        "moat": "Wide",
        "roic_pct": 24.5,
        "wacc_pct": 9.2,
        "z_score": 4.8,
        "upside_pct": 41.4,
        "thesis": "Затворен фонд на Бил Акман с 22% отстъпка от NAV ($50). Концентриран портфейл в MSFT, META, UBER (~45%). Справедлива стойност $50.00 (+28.5%). Ров: Wide, Z-Score: 4.8.",
    },
    "PS": {
        "name": "Pershing Square Inc.",
        "verdict": "HOLD",
        "target_price": 48.0,
        "fair_value": 45.0,
        "mos_pct": -9.7,
        "moat": "Narrow",
        "roic_pct": 22.0,
        "wacc_pct": 9.8,
        "z_score": 4.2,
        "upside_pct": -3.7,
        "thesis": "Мениджърската компания на Бил Акман. Прибира управленски такси и такси за успех от AUM. Forward P/E >50x след 120% рали от дъното. Справедлива стойност $45.00.",
    },
    # 🎬 Global Entertainment & Streaming Titans
    "NFLX": {
        "name": "Netflix, Inc.",
        "verdict": "STRONG BUY",
        "target_price": 98.0,
        "fair_value": 88.0,
        "mos_pct": 22.6,
        "moat": "Wide",
        "roic_pct": 25.5,
        "wacc_pct": 8.9,
        "z_score": 4.5,
        "upside_pct": 36.5,
        "thesis": "Глобален доминант в стрийминга с над 280 млн. абонати и 33% оперативен марж. Рекламният план (AVOD) и монетизирането на пароли ускоряват FCF. Forward P/E ~18.8x срещу исторически 35x+. Справедлива стойност $88.00 (+22.6% MoS), Таргет $98.00. Ров: Wide, ROIC: 25.5%, Z-Score: 4.5.",
    },
    # 🤖 AI & High-Conviction Tech Leaders
    "NVDA": {
        "name": "NVIDIA Corporation",
        "verdict": "STRONG BUY",
        "target_price": 175.0,
        "fair_value": 155.0,
        "mos_pct": 28.5,
        "moat": "Wide",
        "roic_pct": 62.0,
        "wacc_pct": 9.8,
        "z_score": 11.2,
        "m_score": -2.85,
        "upside_pct": 42.5,
        "thesis": "Хегемон в AI ускорението и центровете за данни с CUDA софтуерен ров. Blackwell архитектурата гарантира висока рентабилност и над 70% брутен марж. Справедлива стойност $155.00 (+28.5% MoS), Таргет $175.00. Ров: Wide, ROIC: 62.0%, Z-Score: 11.2.",
        "sector": "Technology",
        "industry": "Semiconductors",
        "model_type": "Three-Stage DCF & CUDA Ecosystem Model",
        "price": 122.8,
        "shares": 24500000000,
        "mcap_b": 3010.0,
        "beta": 1.68,
        "revenue_b": 115.0,
        "ebit_b": 68.0,
        "nopat_b": 58.5,
        "tata": -0.04,
        "entry_price": 118.0,
        "action": "BUY",
        "solvency_type": "Altman Z-Score (Ultra Safe Zone)",
    },
    "MSTR": {
        "name": "MicroStrategy Inc.",
        "verdict": "STRONG BUY",
        "target_price": 480.0,
        "fair_value": 420.0,
        "mos_pct": 31.0,
        "moat": "Wide",
        "roic_pct": 28.0,
        "wacc_pct": 9.5,
        "z_score": 3.8,
        "m_score": -2.45,
        "upside_pct": 48.0,
        "thesis": "Първата в света Bitcoin Treasury компания с над 400,000 BTC. Използва интелигентен конвертируем дълг с 0-1% лихва за акумулиране на биткойни с положителна акреция (BTC Yield >25%). Справедлива стойност $420.00 (+31% MoS), Таргет $480.00.",
        "sector": "Financial Services",
        "industry": "Bitcoin Treasury & Enterprise Software",
        "model_type": "Look-Through Bitcoin NAV & Treasury Accretion Model",
        "price": 324.0,
        "shares": 225000000,
        "mcap_b": 72.9,
        "beta": 3.1,
        "revenue_b": 0.49,
        "ebit_b": -0.05,
        "nopat_b": -0.04,
        "tata": -0.01,
        "entry_price": 310.0,
        "action": "BUY",
        "solvency_type": "Bitcoin Treasury Solvency (Safe Zone)",
    },
    "TSLA": {
        "name": "Tesla, Inc.",
        "verdict": "BUY",
        "target_price": 290.0,
        "fair_value": 260.0,
        "mos_pct": 18.0,
        "moat": "Narrow",
        "roic_pct": 14.2,
        "wacc_pct": 10.2,
        "z_score": 5.2,
        "m_score": -2.6,
        "upside_pct": 26.5,
        "thesis": "Лидер в автономното шофиране (FSD v13+), съхранението на енергия (Megapack +120% YoY) и хуманоидната роботика (Optimus). Справедлива стойност $260.00 (+18% MoS), Таргет $290.00. Ров: Narrow, ROIC: 14.2%, Z-Score: 5.2.",
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers & Energy Storage",
        "model_type": "DCF Multi-Division SOTP (Auto, Energy, AI)",
        "price": 229.0,
        "shares": 3180000000,
        "mcap_b": 728.0,
        "beta": 2.2,
        "revenue_b": 97.0,
        "ebit_b": 9.2,
        "nopat_b": 7.8,
        "tata": -0.02,
        "entry_price": 220.0,
        "action": "BUY",
        "solvency_type": "Altman Z-Score (Safe Zone)",
    },
    "PLTR": {
        "name": "Palantir Technologies",
        "verdict": "BUY",
        "target_price": 75.0,
        "fair_value": 65.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "roic_pct": 22.0,
        "wacc_pct": 9.0,
        "z_score": 6.8,
        "m_score": -2.9,
        "upside_pct": 24.0,
        "thesis": "Доминантна операционна система за предприятиен изкуствен интелект (AIP). Експоненциален растеж в US Commercial сектора (+54% YoY) и непоклатими правителствени договори. Справедлива стойност $65.00, Таргет $75.00.",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "model_type": "High-Growth Software DCF & Rule of 40",
        "price": 60.5,
        "shares": 2240000000,
        "mcap_b": 135.5,
        "beta": 1.8,
        "revenue_b": 2.8,
        "ebit_b": 0.65,
        "nopat_b": 0.58,
        "tata": -0.05,
        "entry_price": 58.0,
        "action": "BUY",
        "solvency_type": "Altman Z-Score (Safe Zone)",
    },
    # 🪙 Bitcoin-Native Holding & Treasury Companies
    "NAKA": {
        "name": "Nakamoto Inc.",
        "verdict": "STRONG BUY",
        "target_price": 18.50,
        "fair_value": 16.00,
        "mos_pct": 37.5,
        "moat": "Narrow",
        "roic_pct": 18.0,
        "wacc_pct": 10.5,
        "z_score": 3.5,
        "upside_pct": 84.1,
        "thesis": "Bitcoin-native трежъри холдинг на Дейвид Бейли (NASDAQ: NAKA) с 4,467 BTC в баланса. Търгува се с екстремна отстъпка от ~37% под нетната стойност на биткойните си (NAV $16.00). Притежава Bitcoin Magazine, най-голямата глобална Bitcoin конференция и UTXO Management. Справедлива стойност $16.00 (+59% MoS), Таргет $18.50.",
        "sector": "Financial Services",
        "industry": "Bitcoin Treasury & Holding",
        "model_type": "Look-Through Bitcoin NAV & Treasury Valuation",
        "price": 10.05,
        "shares": 17900000.0,
        "mcap_b": 0.18,
        "beta": 2.85,
        "revenue_b": 0.035,
        "ebit_b": 0.005,
        "nopat_b": 0.004,
        "tata": -0.02,
        "entry_price": 10.05,
        "action": "BUY",
        "solvency_type": "Spot Bitcoin Treasury (Safe Zone)",
    },
}



class QuantamentalRegistry:
    """Singleton registry caching fundamental verdicts and metrics."""

    _instance: Optional["QuantamentalRegistry"] = None

    def __init__(self, verdicts_path: Optional[str] = None):
        self.profiles: Dict[str, FundamentalProfile] = {}
        self.verdicts_path = verdicts_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "research",
            "verdicts.json",
        )
        self.load_profiles()

    @classmethod
    def get_instance(cls, verdicts_path: Optional[str] = None) -> "QuantamentalRegistry":
        if cls._instance is None:
            cls._instance = cls(verdicts_path)
        return cls._instance

    def load_profiles(self) -> int:
        """Loads equity verdicts from verdicts.json and multi-asset research profiles."""
        count = 0
        # 1. Load multi-asset profiles first (Crypto, Commodities, Macro)
        for ticker, data in _MULTI_ASSET_PROFILES.items():
            prof = FundamentalProfile(
                ticker=ticker,
                name=data.get("name", ticker),
                verdict=data.get("verdict", "NEUTRAL"),
                target_price=data.get("target_price"),
                fair_value=data.get("fair_value"),
                mos_pct=data.get("mos_pct"),
                moat=data.get("moat", "None"),
                roic_pct=data.get("roic_pct"),
                wacc_pct=data.get("wacc_pct"),
                z_score=data.get("z_score"),
                m_score=data.get("m_score"),
                upside_pct=data.get("upside_pct"),
                thesis=data.get("thesis", ""),
                sector=data.get("sector") or ("Крипто активи" if "USDT" in ticker else ("Суровини" if "=F" in ticker else "Макро индекси")),
                industry=data.get("industry") or ("Layer 1 / DeFi" if "USDT" in ticker else ("Индустриални & Благородни метали" if "=F" in ticker else "Борсови индекси")),
                model_type=data.get("model_type") or "Макро ончейн оценка & Себестойност",
                price=data.get("price"),
                shares=data.get("shares"),
                mcap_b=data.get("mcap_b"),
                beta=data.get("beta"),
                revenue_b=data.get("revenue_b"),
                ebit_b=data.get("ebit_b"),
                nopat_b=data.get("nopat_b"),
                tata=data.get("tata"),
                entry_price=data.get("entry_price"),
                action=data.get("action") or ("BUY" if "BUY" in data.get("verdict", "") else ("HOLD" if "HOLD" in data.get("verdict", "") else "REDUCE")),
                solvency_type=data.get("solvency_type") or "Altman Z-Score",
                production_cost=data.get("production_cost") or (62000.0 if ticker == "BTCUSDT" else None),
                mvrv_ratio=data.get("mvrv_ratio") or (1.95 if ticker == "BTCUSDT" else None),
            )
            self.profiles[ticker.upper()] = prof
            if ticker.endswith("USDT"):
                base_sym = ticker[:-4].upper()
                self.profiles[base_sym] = prof
            count += 1

        # 2. Load equity verdicts from research/verdicts.json
        if os.path.exists(self.verdicts_path):
            try:
                with open(self.verdicts_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for item in data.get("verdicts", []):
                    ticker = item.get("ticker")
                    if not ticker:
                        continue

                    # Upside calculation fallback
                    price = _clean_float(item.get("price"))
                    target = _clean_float(item.get("target_price") or item.get("fair_value_base"))
                    upside = _clean_float(item.get("upside_pct"))
                    if upside is None and price and target and price > 0:
                        upside = round(((target - price) / price) * 100, 1)

                    verdict_val = item.get("verdict", "HOLD").upper()
                    target_val = target
                    fair_val = _clean_float(item.get("fair_value_base")) or target
                    mos_val = _clean_float(item.get("mos_pct"))
                    roic_val = _clean_float(item.get("roic_pct"))
                    wacc_val = _clean_float(item.get("wacc_pct"))
                    z_val = _clean_float(item.get("z_score"))
                    m_val = _clean_float(item.get("m_score"))

                    target_str = f"${target_val:,.2f}" if target_val is not None else "N/A"
                    upside_str = f"{upside:+.1f}%" if upside is not None else "N/A"
                    roic_str = f"{roic_val:.1f}%" if roic_val is not None else "N/A"
                    z_str = f"{z_val:.2f}" if z_val is not None else "N/A"

                    profile = FundamentalProfile(
                        ticker=ticker,
                        name=item.get("name", ticker),
                        verdict=verdict_val,
                        target_price=target_val,
                        fair_value=fair_val,
                        mos_pct=mos_val,
                        moat=item.get("moat", "None"),
                        roic_pct=roic_val,
                        wacc_pct=wacc_val,
                        z_score=z_val,
                        m_score=m_val,
                        upside_pct=upside,
                        thesis=f"Справедлива стойност {target_str} ({upside_str}). Ров: {item.get('moat', 'None')}, ROIC: {roic_str}, Z-Score: {z_str}.",
                        sector=item.get("sector"),
                        industry=item.get("industry"),
                        model_type=item.get("model_type"),
                        price=price,
                        shares=_clean_float(item.get("shares")),
                        mcap_b=_clean_float(item.get("mcap_b")),
                        beta=_clean_float(item.get("beta")),
                        revenue_b=_clean_float(item.get("revenue_b")),
                        ebit_b=_clean_float(item.get("ebit_b")),
                        nopat_b=_clean_float(item.get("nopat_b")),
                        tata=_clean_float(item.get("tata")),
                        entry_price=_clean_float(item.get("entry_price")),
                        action=item.get("action"),
                        solvency_type=item.get("solvency_type"),
                    )
                    self.profiles[ticker.upper()] = profile
                    count += 1

                logger.info(f"Loaded {len(self.profiles)} fundamental profiles (including {len(data.get('verdicts', []))} equities).")
            except Exception as e:
                logger.error(f"Failed to load fundamental verdicts from {self.verdicts_path}: {e}")
        else:
            logger.warning(f"Fundamental verdicts file not found at {self.verdicts_path}.")

        return count

    def get_profile(self, ticker: str) -> Optional[FundamentalProfile]:
        """
        Retrieves fundamental profile for a ticker.
        Handles exchange suffixes (e.g. 'NASDAQ:AAPL' -> 'AAPL').
        """
        if not ticker:
            return None

        clean_ticker = ticker.split(":")[-1].strip().upper()
        if clean_ticker in self.profiles:
            return self.profiles[clean_ticker]

        # Check unstripped
        raw_upper = ticker.strip().upper()
        if raw_upper in self.profiles:
            return self.profiles[raw_upper]

        return None


def get_fundamental_profile(ticker: str) -> Optional[FundamentalProfile]:
    """Helper function to fetch profile from global registry."""
    return QuantamentalRegistry.get_instance().get_profile(ticker)
