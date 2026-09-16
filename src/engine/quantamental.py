"""
Quantamental Engine: Ingestion and evaluation of institutional fundamental research.
Merges deep equity valuation (DCF, MoS, Moat, Altman Z, ROIC) and multi-asset memos
with technical trade signals.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


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
            self.profiles[ticker.upper()] = FundamentalProfile(
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
            )
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
                    price = item.get("price")
                    target = item.get("target_price") or item.get("fair_value_base")
                    upside = item.get("upside_pct")
                    if upside is None and price and target and price > 0:
                        upside = round(((target - price) / price) * 100, 1)

                    verdict_val = item.get("verdict", "HOLD").upper()
                    profile = FundamentalProfile(
                        ticker=ticker,
                        name=item.get("name", ticker),
                        verdict=verdict_val,
                        target_price=target,
                        fair_value=item.get("fair_value_base") or target,
                        mos_pct=item.get("mos_pct"),
                        moat=item.get("moat", "None"),
                        roic_pct=item.get("roic_pct"),
                        wacc_pct=item.get("wacc_pct"),
                        z_score=item.get("z_score"),
                        m_score=item.get("m_score"),
                        upside_pct=upside,
                        thesis=f"Справедлива стойност ${target:,.2f} ({upside:+.1f}%). Ров: {item.get('moat', 'None')}, ROIC: {item.get('roic_pct', 0):.1f}%, Z-Score: {item.get('z_score', 0):.2f}.",
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
