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
    verdict: str  # 'STRONG BUY', 'BUY', 'HOLD', 'REDUCE', 'OVERWEIGHT', 'NEUTRAL', 'AVOID'
    target_price: Optional[float] = None
    fair_value: Optional[float] = None
    mos_pct: Optional[float] = None
    required_mos_pct: Optional[float] = None
    actual_discount_pct: Optional[float] = None
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
        if any(k in self.verdict.upper() for k in ["REDUCE", "AVOID", "UNDERPERFORM", "DISTRESSED"]):
            return True
        # Standardized Universal Altman Z''-Score distress threshold: Z'' < 1.10
        if self.z_score is not None and self.z_score < 1.10:
            return True
        return False

    @property
    def is_hold(self) -> bool:
        return any(k in self.verdict.upper() for k in ["HOLD", "NEUTRAL", "FAIRLY VALUED"])


# Pure Multi-asset registry for Commodities, Crypto, and Macro Indices.
# All corporate equities are strictly dynamically evaluated and loaded from verdicts.json.
_MULTI_ASSET_PROFILES: Dict[str, dict] = {
    # 🪙 Digital Assets (On-chain, Network Dynamics, Halving Cycles)
    "BTCUSDT": {
        "name": "Bitcoin",
        "verdict": "STRONG BUY",
        "target_price": 120000.0,
        "fair_value": 110000.0,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 45.0,
        "thesis": "Mayer Multiple консолидация; базова себестойност на миньорите $58k-$64k; нетни институционални ETF притоци.",
        "production_cost": 62000.0,
        "mvrv_ratio": 1.95,
    },
    "ETHUSDT": {
        "name": "Ethereum",
        "verdict": "HOLD",
        "target_price": 2800.0,
        "fair_value": 2600.0,
        "mos_pct": 10.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 8.0,
        "thesis": "L2 канибализация на такси срещу 3.2% стейкинг доходност; акумулиране при корекции.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "SOLUSDT": {
        "name": "Solana",
        "verdict": "BUY",
        "target_price": 150.0,
        "fair_value": 135.0,
        "mos_pct": 28.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 39.0,
        "thesis": "Лидер по DEX скорост на капитал; акумулиране в зоната на подкрепа.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "PAXGUSDT": {
        "name": "Pax Gold",
        "verdict": "STRONG BUY",
        "target_price": 4800.0,
        "fair_value": 4650.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 11.0,
        "thesis": "1:1 физическо обезпечение със злато в LBMA трезори; монетарен хедж срещу де-доларизация.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "LINKUSDT": {
        "name": "Chainlink",
        "verdict": "STRONG BUY",
        "target_price": 22.0,
        "fair_value": 19.5,
        "mos_pct": 45.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 81.0,
        "thesis": "Стандарт при оракулите и CCIP протокол за токенизация на реални активи (RWA).",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "BNBUSDT": {
        "name": "BNB",
        "verdict": "HOLD",
        "target_price": 750.0,
        "fair_value": 720.0,
        "mos_pct": 5.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 2.0,
        "thesis": "Launchpool ликвидност и борсова полезност; консолидация в широк рейндж.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "XRPUSDT": {
        "name": "Ripple",
        "verdict": "HOLD",
        "target_price": 1.35,
        "fair_value": 1.25,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": None,
        "upside_pct": 0.0,
        "thesis": "Трансгранични междубанкови разплащания след регулаторно изчистване.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "SUIUSDT": {
        "name": "Sui Network",
        "verdict": "BUY",
        "target_price": 1.20,
        "fair_value": 1.05,
        "mos_pct": 30.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 47.0,
        "thesis": "Високоскоростен обектно-ориентиран Move L1 с експоненциален растеж на ликвидността.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "DOGEUSDT": {
        "name": "Dogecoin",
        "verdict": "REDUCE",
        "target_price": 0.06,
        "fair_value": 0.05,
        "mos_pct": -37.0,
        "moat": "None",
        "z_score": None,
        "upside_pct": -37.0,
        "thesis": "Спекулативен мем актив без паричен поток, подложен на инфлационен натиск.",
        "production_cost": None,
        "mvrv_ratio": None,
    },
    "ADAUSDT": {
        "name": "Cardano",
        "verdict": "REDUCE",
        "target_price": 0.16,
        "fair_value": 0.15,
        "mos_pct": -25.0,
        "moat": "None",
        "z_score": None,
        "upside_pct": -25.0,
        "thesis": "Изоставаща DeFi ликвидност и ниска скорост на он-чейн капитал.",
        "production_cost": None,
        "mvrv_ratio": None,
    },

    # 🥇 Commodities & Energy
    "GC=F": {
        "name": "Gold Futures",
        "verdict": "STRONG BUY",
        "target_price": 4900.0,
        "fair_value": 4750.0,
        "mos_pct": 15.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 11.0,
        "thesis": "Секуларен монетарен суперцикъл; покупки на централни банки (>1,000 тона/год); де-доларизация.",
    },
    "SI=F": {
        "name": "Silver Futures",
        "verdict": "BUY",
        "target_price": 75.0,
        "fair_value": 72.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 12.0,
        "thesis": "Структурен индустриален дефицит; соларно (N-type) и AI хардуерно търсене.",
    },
    "HG=F": {
        "name": "Copper Futures",
        "verdict": "STRONG BUY",
        "target_price": 8.50,
        "fair_value": 8.20,
        "mos_pct": 25.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 27.0,
        "thesis": "Електропреносен дефицит и ключов ресурс за AI дата центрове (25-40 тона/MW).",
    },
    "URA": {
        "name": "Global X Uranium ETF",
        "verdict": "STRONG BUY",
        "target_price": 58.0,
        "fair_value": 55.0,
        "mos_pct": 28.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 32.0,
        "thesis": "Ядрен ренесанс; дългосрочни 20-годишни договори за захранване на хиперскейлъри.",
    },
    "URNM": {
        "name": "Sprott Uranium Miners ETF",
        "verdict": "STRONG BUY",
        "target_price": 70.0,
        "fair_value": 66.0,
        "mos_pct": 28.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": 35.0,
        "thesis": "Чиста експозиция към първични производители при структурен дефицит на рудници.",
    },
    "CL=F": {
        "name": "Crude Oil WTI",
        "verdict": "BUY",
        "target_price": 88.0,
        "fair_value": 85.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 18.0,
        "thesis": "Търгува се над US shale break-even ($72/bbl); OPEC+ дисциплина на предлагането.",
    },
    "BZ=F": {
        "name": "Brent Crude Oil",
        "verdict": "BUY",
        "target_price": 92.0,
        "fair_value": 89.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 16.0,
        "thesis": "Глобален бенчмарк с геополитическа премия.",
    },
    "NG=F": {
        "name": "Natural Gas",
        "verdict": "BUY",
        "target_price": 4.20,
        "fair_value": 3.90,
        "mos_pct": 30.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 32.0,
        "thesis": "Търгува се близо до базовата себестойност $2.60; LNG експортен капацитет.",
    },
    "PL=F": {
        "name": "Platinum Futures",
        "verdict": "BUY",
        "target_price": 2100.0,
        "fair_value": 2000.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 12.0,
        "thesis": "Зелен водород и заместител на паладия в автокатализаторите.",
    },

    # 🌐 Macro Indices
    "^GSPC": {
        "name": "S&P 500",
        "verdict": "HOLD",
        "target_price": 7000.0,
        "fair_value": 6800.0,
        "mos_pct": -10.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": -10.0,
        "thesis": "Forward P/E компресирана рискова премия; препоръчва се селективен подбор.",
    },
    "^IXIC": {
        "name": "Nasdaq Composite",
        "verdict": "HOLD",
        "target_price": 23500.0,
        "fair_value": 22000.0,
        "mos_pct": -15.0,
        "moat": "Wide",
        "z_score": None,
        "upside_pct": -15.0,
        "thesis": "Висока концентрация в технологични лидери.",
    },
    "^HSI": {
        "name": "Hang Seng Index",
        "verdict": "BUY",
        "target_price": 29000.0,
        "fair_value": 28000.0,
        "mos_pct": 15.0,
        "moat": "Narrow",
        "z_score": None,
        "upside_pct": 12.0,
        "thesis": "P/E 10.4x; подценен спрямо глобалните пазари с китайски фискални стимули.",
    },
    "^RUT": {
        "name": "Russell 2000",
        "verdict": "BUY",
        "target_price": 3200.0,
        "fair_value": 3100.0,
        "mos_pct": 10.0,
        "moat": "None",
        "z_score": None,
        "upside_pct": 8.0,
        "thesis": "Лихвена компресия и ротация към по-малки компании.",
    },
    "DX-Y.NYB": {
        "name": "US Dollar Index",
        "verdict": "REDUCE",
        "target_price": 96.0,
        "fair_value": 95.0,
        "mos_pct": 0.0,
        "moat": "None",
        "z_score": None,
        "upside_pct": -4.0,
        "thesis": "Спадът под 100 сигнализира глобална ликвидна експанзия за суровини и рискови активи.",
    },
}


class QuantamentalRegistry:
    """Singleton registry caching fundamental verdicts and metrics."""

    _instance: Optional["QuantamentalRegistry"] = None

    def __init__(self, verdicts_path: Optional[str] = None):
        self.profiles: Dict[str, FundamentalProfile] = {}
        if not verdicts_path:
            v_dashboard = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "dashboard",
                "fundamental_verdicts.json",
            )
            v_research = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "research",
                "verdicts.json",
            )
            self.verdicts_path = v_dashboard if os.path.exists(v_dashboard) else v_research
        else:
            self.verdicts_path = verdicts_path

        self.load_profiles()

    @classmethod
    def get_instance(cls, verdicts_path: Optional[str] = None) -> "QuantamentalRegistry":
        if cls._instance is None:
            cls._instance = cls(verdicts_path)
        return cls._instance

    def load_profiles(self) -> int:
        """Loads multi-asset research profiles and merges with dynamic verdicts.json."""
        count = 0
        # 1. Load pure multi-asset profiles (Crypto, Commodities, Macro)
        for ticker, data in _MULTI_ASSET_PROFILES.items():
            prof = FundamentalProfile(
                ticker=ticker,
                name=data.get("name", ticker),
                verdict=data.get("verdict", "NEUTRAL"),
                target_price=data.get("target_price"),
                fair_value=data.get("fair_value"),
                mos_pct=data.get("mos_pct"),
                required_mos_pct=data.get("required_mos_pct", 20.0),
                actual_discount_pct=data.get("actual_discount_pct", data.get("mos_pct")),
                moat=data.get("moat", "None"),
                roic_pct=data.get("roic_pct"),
                wacc_pct=data.get("wacc_pct"),
                z_score=data.get("z_score"),
                m_score=data.get("m_score"),
                upside_pct=data.get("upside_pct"),
                thesis=data.get("thesis", ""),
                sector=data.get("sector") or ("Крипто активи" if "USDT" in ticker else ("Суровини" if "=F" in ticker else "Макро индекси")),
                industry=data.get("industry") or ("Layer 1 / DeFi" if "USDT" in ticker else ("Индустриални & Благородни метали" if "=F" in ticker else "Борсови индекси")),
                model_type=data.get("model_type") or ("Он-чейн пазарен модел" if "USDT" in ticker else "Макро себестоен модел"),
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
                solvency_type=data.get("solvency_type") or "Multi-Asset Evaluation",
                production_cost=data.get("production_cost"),
                mvrv_ratio=data.get("mvrv_ratio"),
            )
            self.profiles[ticker.upper()] = prof
            if ticker.endswith("USDT"):
                base_sym = ticker[:-4].upper()
                self.profiles[base_sym] = prof
            count += 1

        # 2. Load dynamic equity verdicts from verdicts.json
        if os.path.exists(self.verdicts_path):
            try:
                with open(self.verdicts_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for item in data.get("verdicts", []):
                    ticker = item.get("ticker")
                    if not ticker:
                        continue

                    price = _clean_float(item.get("price"))
                    target = _clean_float(item.get("target_price") or item.get("fair_value_base"))
                    upside = _clean_float(item.get("upside_pct"))
                    if upside is None and price and target and price > 0:
                        upside = round(((target - price) / price) * 100, 1)

                    verdict_val = item.get("verdict", "HOLD").upper()
                    target_val = target
                    fair_val = _clean_float(item.get("fair_value_base")) or target
                    # Genuine actual discount vs hurdle required MoS
                    actual_disc = _clean_float(item.get("actual_discount_pct"))
                    if actual_disc is None and price and fair_val and fair_val > 0:
                        actual_disc = round(((fair_val - price) / fair_val) * 100.0, 1)

                    req_mos = _clean_float(item.get("required_mos_pct")) or 20.0
                    mos_val = actual_disc if actual_disc is not None else _clean_float(item.get("mos_pct"))

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
                        required_mos_pct=req_mos,
                        actual_discount_pct=actual_disc,
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

        raw_upper = ticker.strip().upper()
        if raw_upper in self.profiles:
            return self.profiles[raw_upper]

        return None


def get_fundamental_profile(ticker: str) -> Optional[FundamentalProfile]:
    """Helper function to fetch profile from global registry."""
    return QuantamentalRegistry.get_instance().get_profile(ticker)
