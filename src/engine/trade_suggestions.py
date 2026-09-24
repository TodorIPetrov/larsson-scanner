"""
Institutional Trade Suggestions Engine.
Translates Larsson Ribbon trend states, ATR volatility buffers, and quantitative S/R clusters
into actionable, risk-managed trade suggestions tailored for Spot investing and light leverage (up to 2x).
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import numpy as np

from src.engine.asset_profiles import get_max_allowed_leverage

if TYPE_CHECKING:
    from src.engine.quantamental import FundamentalProfile


@dataclass
class TradeSuggestion:
    action: str  # 'SPOT_BUY', 'TAKE_PROFIT', 'EXIT_PROTECT', 'SHORT_2X_OPTIONAL', 'WAIT'
    direction: str  # 'LONG', 'SHORT', 'NEUTRAL'
    setup_type: str  # 'QUANTAMENTAL_ALPHA_BUY', 'PULLBACK_VALUE_BUY', 'BREAKOUT_BUY', 'SPECULATIVE_BUY', 'VALUE_TRAP_WARNING', 'QUALITY_HOLD_ACCUMULATION', etc.
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    rr_ratio: Optional[float] = None
    score: int = 0  # 0 - 100 confluence score
    tier: str = "NONE"  # 'A+', 'A', 'B', 'NONE'
    reason_bg: str = ""
    reason_en: str = ""
    fund_verdict: Optional[str] = None
    fair_value: Optional[float] = None
    mos_pct: Optional[float] = None
    moat: Optional[str] = None
    z_score: Optional[float] = None
    quantamental_tag: Optional[str] = None
    dca_plan: Optional[str] = None
    # Leverage support (1x - 3x)
    max_leverage: int = 1  # 1, 2, 3
    recommended_leverage: int = 1
    # Explicit Technical vs Fundamental separation
    tech_action: str = "WAIT"  # 'BUY', 'HOLD', 'EXIT', 'TAKE_PROFIT', 'SHORT', 'WAIT'
    tech_label_bg: str = "⏳ ИЗЧАКАЙ"
    tech_thesis_bg: str = ""
    fund_action: str = "SPECULATIVE_NA"  # 'STRONG_BUY', 'BUY', 'HOLD', 'REDUCE', 'SPECULATIVE_NA'
    fund_label_bg: str = "⚪ МАКРО / СПЕКУЛАТИВЕН"
    fund_thesis_bg: str = ""
    synthesis_badge_bg: str = "⏳ WAIT"
    synthesis_label_bg: str = ""
    # BTC Relative Strength fields
    btc_ratio_state: str = "NA"  # 'GOLD', 'BLUE', 'NEUTRAL', 'NA'
    btc_alpha_30d: Optional[float] = None
    btc_alpha_7d: Optional[float] = None
    btc_ratio_spread: Optional[float] = None
    btc_verdict: Optional[str] = None
    btc_badge_bg: Optional[str] = None
    btc_thesis_bg: Optional[str] = None
    btc_leverage_allowed: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_leverage_matrix(
    entry_price: float,
    stop_loss: Optional[float],
    position_size_usd: float = 300.0,
    max_leverage: int = 3,
    direction: str = "LONG",
) -> list:
    """
    Computes comparative parameters (margin, risk, estimated liquidation)
    for each allowed leverage level from 1 to max_leverage.
    """
    if entry_price <= 0 or position_size_usd <= 0:
        return []

    max_lev = max(1, min(3, max_leverage))
    matrix = []
    is_long = direction.upper() != "SHORT"

    for lev in range(1, max_lev + 1):
        margin_usd = round(position_size_usd / lev, 2)
        if stop_loss and stop_loss > 0:
            sl_loss_usd = round(abs(entry_price - stop_loss) / entry_price * position_size_usd, 2)
            sl_pct_margin = round((sl_loss_usd / margin_usd) * 100.0, 1) if margin_usd > 0 else 0.0
        else:
            sl_loss_usd = 0.0
            sl_pct_margin = 0.0

        if lev > 1:
            # 0.5% maintenance margin buffer
            if is_long:
                liq_price = round(entry_price * (1.0 - (1.0 / lev) + 0.005), 4)
            else:
                liq_price = round(entry_price * (1.0 + (1.0 / lev) - 0.005), 4)
            dist_to_liq_pct = round(abs(entry_price - liq_price) / entry_price * 100.0, 1)
        else:
            liq_price = None
            dist_to_liq_pct = None

        if lev == 1:
            label = "Spot (1x)" if is_long else "Hedge 1x"
        elif lev == 2:
            label = "Long 2x" if is_long else "Short 2x"
        else:
            label = "Long 3x" if is_long else "Short 3x"

        matrix.append({
            "leverage": lev,
            "label": label,
            "margin_usd": margin_usd,
            "notional_usd": round(position_size_usd, 2),
            "sl_loss_usd": sl_loss_usd,
            "sl_pct_margin": sl_pct_margin,
            "liquidation_price": liq_price,
            "dist_to_liq_pct": dist_to_liq_pct,
        })

    return matrix



def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    account_size: float = 10000.0,
    risk_pct: float = 1.0,
    tp1: Optional[float] = None,
    tp2: Optional[float] = None,
    leverage: int = 1,
) -> dict:
    """
    Calculates institutional position sizing based on risk-per-trade.
    Formula: Risk USD = account_size * (risk_pct / 100)
             Risk Per Unit = abs(entry_price - stop_loss)
             Position Units = Risk USD / Risk Per Unit
    """
    if entry_price <= 0 or stop_loss <= 0 or account_size <= 0 or risk_pct <= 0:
        return {
            "units": 0.0,
            "position_value": 0.0,
            "margin_usd": 0.0,
            "risk_usd": 0.0,
            "risk_per_unit": 0.0,
            "risk_pct_price": 0.0,
            "profit_tp1_usd": 0.0,
            "profit_tp2_usd": 0.0,
            "leverage": leverage,
            "liquidation_price": None,
        }

    risk_per_unit = abs(entry_price - stop_loss)
    if risk_per_unit <= 1e-8:
        return {
            "units": 0.0,
            "position_value": 0.0,
            "margin_usd": 0.0,
            "risk_usd": 0.0,
            "risk_per_unit": 0.0,
            "risk_pct_price": 0.0,
            "profit_tp1_usd": 0.0,
            "profit_tp2_usd": 0.0,
            "leverage": leverage,
            "liquidation_price": None,
        }

    risk_usd = round(account_size * (risk_pct / 100.0), 2)
    units_raw = risk_usd / risk_per_unit

    units = round(units_raw, 4 if entry_price < 100 else 2)
    position_value = round(units * entry_price, 2)
    risk_pct_price = round((risk_per_unit / entry_price) * 100.0, 2)

    profit_tp1_usd = round(units * abs(tp1 - entry_price), 2) if tp1 else None
    profit_tp2_usd = round(units * abs(tp2 - entry_price), 2) if tp2 else None

    lev = max(1, min(3, leverage))
    margin_usd = round(position_value / lev, 2)
    liq_price = round(entry_price * (1.0 - (1.0 / lev) + 0.005), 4) if lev > 1 else None

    return {
        "units": units,
        "position_value": position_value,
        "margin_usd": margin_usd,
        "risk_usd": risk_usd,
        "risk_per_unit": round(risk_per_unit, 4),
        "risk_pct_price": risk_pct_price,
        "profit_tp1_usd": profit_tp1_usd,
        "profit_tp2_usd": profit_tp2_usd,
        "leverage": lev,
        "liquidation_price": liq_price,
    }



def calculate_confluence_score(
    is_mtf_aligned: bool,
    near_support: bool,
    s1_touches: int,
    spread_expanding: bool,
    rr_ratio: Optional[float],
    fund_profile: Optional[object] = None,
    btc_relative: Optional[object] = None,
) -> Tuple[int, str]:
    """
    Calculates institutional confluence score (0 - 100) and assigns a quality tier.
    Enriched with fundamental valuation metrics (MoS, Moat, Altman Z) and BTC Relative Alpha.
    """
    score = 40  # baseline for valid directional setup

    if is_mtf_aligned:
        score += 20
    if near_support:
        score += 20
    if s1_touches >= 3:
        score += 10
    elif s1_touches >= 2:
        score += 5
    if spread_expanding:
        score += 10
    if rr_ratio is not None:
        if rr_ratio >= 2.5:
            score += 10
        elif rr_ratio >= 2.0:
            score += 5
        elif rr_ratio < 1.8:
            score -= 20

    # Fundamental Confluence adjustments
    if fund_profile:
        is_bullish = getattr(fund_profile, "is_bullish", False)
        is_bearish = getattr(fund_profile, "is_bearish_or_distressed", False)
        moat = getattr(fund_profile, "moat", "None")

        if is_bullish:
            score += 15
            if moat == "Wide":
                score += 5
            elif moat == "Narrow":
                score += 2
        elif is_bearish:
            score -= 25

    # BTC Relative Strength adjustments (Alpha vs Bitcoin Benchmark)
    if btc_relative:
        r_state = getattr(btc_relative, "ratio_state", "NA")
        alpha_30 = getattr(btc_relative, "alpha_30d_pct", 0.0)
        if r_state == "GOLD":
            score += 15 if alpha_30 >= 5.0 else 8
        elif r_state == "BLUE":
            score -= 20 if alpha_30 <= -5.0 else 10

    score = max(0, min(100, score))

    if score >= 85:
        tier = "A+"
    elif score >= 70:
        tier = "A"
    elif score >= 55:
        tier = "B"
    else:
        tier = "NONE"

    return score, tier


def _enrich_trade_suggestion(
    s: TradeSuggestion,
    state: str,
    spread_pct: float,
    s1: Optional[float],
    r1: Optional[float],
    current_price: float,
    fund_profile: Optional[object],
    btc_relative: Optional[object] = None,
) -> TradeSuggestion:
    """Enriches a TradeSuggestion with clear, distinct technical, fundamental, and BTC relative fields."""
    # 1. Technical Analysis Recommendation & Details
    if state == "GOLD":
        if s.action == "SPOT_BUY":
            s.tech_action = "BUY"
            if s.setup_type in ["PULLBACK_VALUE_BUY", "QUALITY_HOLD_ACCUMULATION", "SPECULATIVE_PULLBACK_BUY"]:
                s.tech_label_bg = "🟢 BUY (Pullback S1)"
                s.tech_thesis_bg = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с успешен тест на S1 подкрепа."
            elif s.setup_type in ["BREAKOUT_BUY", "SPECULATIVE_MOMENTUM_BUY"]:
                s.tech_label_bg = "🟢 BUY (Пробив / Momentum)"
                s.tech_thesis_bg = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с пробив в Price Discovery над R1."
            else:
                s.tech_label_bg = "🟢 BUY (Бича лента)"
                s.tech_thesis_bg = f"Бичи възходящ тренд на Larsson лентата (spread {spread_pct:+.1f}%)."
        elif s.action == "TAKE_PROFIT":
            s.tech_action = "TAKE_PROFIT"
            s.tech_label_bg = "💰 TAKE PROFIT (Тест на R1)"
            s.tech_thesis_bg = "Бичи тренд, но цената достига ключова макро съпротива R1. Препоръчва се прибиране на печалба."
        else:
            s.tech_action = "HOLD"
            s.tech_label_bg = "🟡 HOLD (Възходящ тренд)"
            s.tech_thesis_bg = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%). Задръжте или изчакайте корекция до S1 за нов вход."
    elif state == "BLUE":
        if s.action == "SHORT_2X_OPTIONAL":
            s.tech_action = "SHORT"
            s.tech_label_bg = "🔴 SHORT (Меча панделка)"
            s.tech_thesis_bg = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%) с отхвърляне от съпротива."
        else:
            s.tech_action = "EXIT"
            s.tech_label_bg = "🔴 EXIT / STOP (Мечи тренд)"
            s.tech_thesis_bg = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%) и/или загуба на ключова подкрепа S1."
    else:  # NEUTRAL
        s.tech_action = "WAIT"
        s.tech_label_bg = "⏳ WAIT (Консолидация)"
        s.tech_thesis_bg = "Панделката е преплетена без ясна посока. Изчакайте разширяване и формиране на тренд."

    # 2. Fundamental Analysis Recommendation & Details
    fund_verdict = getattr(fund_profile, "verdict", None) if fund_profile else s.fund_verdict
    fair_value = getattr(fund_profile, "fair_value", None) if fund_profile else s.fair_value
    mos_pct = getattr(fund_profile, "mos_pct", None) if fund_profile else s.mos_pct
    moat = getattr(fund_profile, "moat", None) if fund_profile else s.moat
    thesis = getattr(fund_profile, "thesis", "") if fund_profile else ""

    if fund_verdict:
        fv_txt = f"${fair_value:,.2f}" if fair_value else "N/A"
        mos_txt = f"{mos_pct:+.0f}%" if mos_pct is not None else "N/A"
        moat_txt = f", {moat} Moat" if moat and moat != "None" else ""

        if "STRONG BUY" in fund_verdict.upper():
            s.fund_action = "STRONG_BUY"
            s.fund_label_bg = f"🟢 СИЛНО ПОДЦЕНЕН ({mos_txt} MoS)"
            s.fund_thesis_bg = f"DCF Справедлива стойност: {fv_txt} (Margin of Safety: {mos_txt}{moat_txt}). {thesis}".strip()
        elif "BUY" in fund_verdict.upper() or "OVERWEIGHT" in fund_verdict.upper():
            s.fund_action = "BUY"
            s.fund_label_bg = f"🟢 ПОДЦЕНЕН ({mos_txt} MoS)"
            s.fund_thesis_bg = f"DCF Справедлива стойност: {fv_txt} (Margin of Safety: {mos_txt}{moat_txt}). {thesis}".strip()
        elif "HOLD" in fund_verdict.upper() or "NEUTRAL" in fund_verdict.upper():
            s.fund_action = "HOLD"
            s.fund_label_bg = "🟡 СПРАВЕДЛИВА ЦЕНА (Hold)"
            s.fund_thesis_bg = f"Търгува се близо до DCF оценка {fv_txt}{moat_txt}. Балансиран риск/доходност.".strip()
        elif "REDUCE" in fund_verdict.upper() or "AVOID" in fund_verdict.upper() or "UNDERPERFORM" in fund_verdict.upper():
            s.fund_action = "REDUCE"
            s.fund_label_bg = "🔴 НАДЦЕНЕН (Reduce)"
            s.fund_thesis_bg = f"Надценен спрямо паричните потоци или влошаващи се финансови показатели (DCF {fv_txt}). {thesis}".strip()
        else:
            s.fund_action = "HOLD"
            s.fund_label_bg = f"⚪ {fund_verdict}"
            s.fund_thesis_bg = f"DCF: {fv_txt}{moat_txt}. {thesis}".strip()
    else:
        s.fund_action = "SPECULATIVE_NA"
        s.fund_label_bg = "⚪ МАКРО / СПЕКУЛАТИВЕН"
        s.fund_thesis_bg = "Крипто/суровинен инструмент без класически корпоративен DCF модел. Движи се от мрежови ефекти, ликвидност и технически моментум."

    # 3. Quantamental Synthesis & Confluence
    if s.setup_type == "QUANTAMENTAL_ALPHA_BUY":
        s.synthesis_badge_bg = "⭐ ALPHA BUY"
        s.synthesis_label_bg = "Пълен консенсус (Бича техника + Подценен фундамент)"
    elif s.setup_type == "VALUE_TRAP_WARNING":
        s.synthesis_badge_bg = "⏳ VALUE TRAP RISK"
        s.synthesis_label_bg = "Конфликт: Евтин фундамент, но меча техника (Не купувай преди обръщане!)"
    elif s.setup_type in ["SPECULATIVE_MOMENTUM_BUY", "SPECULATIVE_PULLBACK_BUY"]:
        s.synthesis_badge_bg = "⚠️ СПЕКУЛАТИВЕН ВХОД"
        s.synthesis_label_bg = "Конфликт: Бича техника, но слаб/надценен фундамент (Търгувай само с къс SL)"
    elif s.setup_type == "QUALITY_HOLD_ACCUMULATION":
        s.synthesis_badge_bg = "🧱 QUALITY ACCUMULATE"
        s.synthesis_label_bg = "Качествена компания за дългосрочно натрупване (DCA) на ключови нива"
    elif s.action == "SPOT_BUY":
        s.synthesis_badge_bg = "🟢 SPOT BUY"
        s.synthesis_label_bg = "Чист технически вход в бичи тренд"
    elif s.action == "TAKE_PROFIT":
        s.synthesis_badge_bg = "💰 TAKE PROFIT"
        s.synthesis_label_bg = "Прибиране на печалби при тест на съпротива"
    elif s.action == "EXIT_PROTECT":
        s.synthesis_badge_bg = "🛑 CAPITAL PROTECT"
        s.synthesis_label_bg = "Защита на капитала при пробив на структурата"
    elif s.action == "SHORT_2X_OPTIONAL":
        s.synthesis_badge_bg = "🔴 SHORT 2X"
        s.synthesis_label_bg = "Мечи трендов шорт с ограничен левъридж"
    else:
        s.synthesis_badge_bg = "⏳ WAIT"
        s.synthesis_label_bg = "Изчакване на качествена структура за вход"

    # 4. BTC Relative Strength Enrichment & Leverage Gating
    if btc_relative:
        s.btc_ratio_state = getattr(btc_relative, "ratio_state", "NA")
        s.btc_alpha_30d = getattr(btc_relative, "alpha_30d_pct", None)
        s.btc_alpha_7d = getattr(btc_relative, "alpha_7d_pct", None)
        s.btc_ratio_spread = getattr(btc_relative, "ratio_spread_pct", None)
        s.btc_verdict = getattr(btc_relative, "verdict", None)
        s.btc_badge_bg = getattr(btc_relative, "badge_bg", None)
        s.btc_thesis_bg = getattr(btc_relative, "thesis_bg", None)
        s.btc_leverage_allowed = getattr(btc_relative, "leverage_allowed", True)

        if not s.btc_leverage_allowed:
            s.max_leverage = 1
            s.recommended_leverage = 1
            if "Изостава от BTC" not in s.reason_bg and s.btc_alpha_30d is not None:
                s.reason_bg = f"{s.reason_bg} ⚠️ Изостава от BTC ({s.btc_alpha_30d:+.1f}% за 30д): Левъриджът е блокиран на 1x Spot."
        elif s.btc_ratio_state == "GOLD":
            if "Водещ актив спрямо BTC" not in s.reason_bg and s.btc_alpha_30d is not None:
                s.reason_bg = f"{s.reason_bg} 🚀 Водещ актив спрямо BTC (+{s.btc_alpha_30d:.1f}% Alpha): Потвърден възходящ тренд."

    return s


def _raw_generate_trade_suggestion(
    current_price: float,
    state: str,  # 'GOLD', 'BLUE', 'NEUTRAL'
    v1: float,
    m1: float,
    m2: float,
    v2: float,
    spread_pct: float,
    atr: float,
    s1: Optional[float] = None,
    s1_lower: Optional[float] = None,
    s1_touches: int = 0,
    s2: Optional[float] = None,
    r1: Optional[float] = None,
    r1_lower: Optional[float] = None,
    r1_upper: Optional[float] = None,
    r1_touches: int = 0,
    r2: Optional[float] = None,
    context_flag: str = "IN_VALUE_RANGE",
    timeframe: str = "1D",
    macro_1d_state: Optional[str] = None,
    min_rr_threshold: float = 1.8,
    fund_profile: Optional[object] = None,
    ticker: Optional[str] = None,
    asset_class: str = "crypto",
    btc_relative: Optional[object] = None,
) -> TradeSuggestion:
    """
    Evaluates market conditions and returns an institutional TradeSuggestion.
    Fuses technical momentum/structure with institutional fundamental valuation.
    """
    atr = max(atr, current_price * 0.005)
    atr_pct = (atr / current_price) * 100.0 if current_price > 0 else 0.0
    is_mtf_aligned = (macro_1d_state == "GOLD") if (macro_1d_state and timeframe != "1D") else (state == "GOLD")
    spread_expanding = spread_pct > 0.25

    # Extract fundamental metadata if present
    fund_verdict = getattr(fund_profile, "verdict", None) if fund_profile else None
    fair_value = getattr(fund_profile, "fair_value", None) if fund_profile else None
    mos_pct = getattr(fund_profile, "mos_pct", None) if fund_profile else None
    moat = getattr(fund_profile, "moat", None) if fund_profile else None
    z_score = getattr(fund_profile, "z_score", None) if fund_profile else None
    is_bullish = getattr(fund_profile, "is_bullish", False) if fund_profile else False
    is_bearish = getattr(fund_profile, "is_bearish_or_distressed", False) if fund_profile else False
    is_hold = getattr(fund_profile, "is_hold", False) if fund_profile else False
    fund_name = getattr(fund_profile, "name", "") if fund_profile else ""

    # -------------------------------------------------------------------------
    # 0. VALUE TRAP GUARD (Fundamental Buy in active Technical Downtrend)
    # -------------------------------------------------------------------------
    if is_bullish and (state == "BLUE" or context_flag == "BREAKDOWN_BELOW" or (s1 is not None and current_price < s1)):
        fv_str = f"${fair_value:,.2f}" if fair_value else "N/A"
        return TradeSuggestion(
            action="WAIT",
            direction="NEUTRAL",
            setup_type="VALUE_TRAP_WARNING",
            entry_price=round(current_price, 4),
            stop_loss=None,
            tp1=None,
            tp2=None,
            rr_ratio=None,
            score=45,
            tier="NONE",
            reason_bg=f"⏳ ВАЛУАЦИОНЕН КАПАН: Фундаментално подценен актив ({fund_verdict}, Fair Value {fv_str}), но в активен низходящ тренд (BLUE/под S1). Изчакайте бичо обръщане в GOLD и тест на подкрепа преди вход!",
            reason_en=f"Value trap risk: Undervalued asset ({fund_verdict}, Fair Value {fv_str}), but in active downtrend. Wait for bullish GOLD reversal before entry.",
            fund_verdict=fund_verdict,
            fair_value=fair_value,
            mos_pct=mos_pct,
            moat=moat,
            z_score=z_score,
            quantamental_tag="VALUE_TRAP_RISK",
        )

    # -------------------------------------------------------------------------
    # 1. STRUCTURAL EXIT / CAPITAL PROTECTION (Spot Protect)
    # -------------------------------------------------------------------------
    if state == "BLUE" or context_flag == "BREAKDOWN_BELOW":
        # Lost trend or broke key support
        if s1 is not None and current_price < s1:
            tag = "SHORT_FUNDAMENTAL_ALIGNMENT" if is_bearish else "STRUCTURAL_EXIT"
            return TradeSuggestion(
                action="EXIT_PROTECT",
                direction="EXIT",
                setup_type="STRUCTURAL_EXIT",
                entry_price=round(current_price, 4),
                stop_loss=None,
                tp1=None,
                tp2=None,
                rr_ratio=None,
                score=85 if is_bearish else 80,
                tier="A+" if is_bearish else "A",
                reason_bg=f"Загуба на макро подкрепа S1 (${s1:,.2f}) и мечи тренд." + (f" Потвърдено от слаб фундамент ({fund_verdict})." if is_bearish else "") + " Защити капитала / излез от спот позиции.",
                reason_en=f"Breakdown below macro support S1 (${s1:,.2f}) and bearish ribbon." + (f" Confirmed by weak fundamentals ({fund_verdict})." if is_bearish else "") + " Exit/protect spot capital.",
                fund_verdict=fund_verdict,
                fair_value=fair_value,
                mos_pct=mos_pct,
                moat=moat,
                z_score=z_score,
                quantamental_tag=tag,
            )

    # -------------------------------------------------------------------------
    # 2. TAKE PROFIT / TRIM (Spot Profit Realization)
    # -------------------------------------------------------------------------
    if state == "GOLD" and context_flag == "NEAR_RESISTANCE":
        r1_price_str = f"${r1:,.2f}" if r1 else "съпротива"
        dist_str = f"{(r1 - current_price) / current_price * 100:.1f}%" if r1 else "0%"
        extra_bg = f" Фундаменталната оценка е {fund_verdict} (надценен) – затвори до 100% от позицията." if is_bearish else " Прибери 50-100% печалба на спот."
        extra_en = f" Fundamentals show {fund_verdict} (overvalued) – trim up to 100%." if is_bearish else " Trim 50-100% of spot position."
        return TradeSuggestion(
            action="TAKE_PROFIT",
            direction="NEUTRAL",
            setup_type="TAKE_PROFIT_SELL",
            entry_price=round(current_price, 4),
            stop_loss=None,
            tp1=round(r1, 4) if r1 else round(current_price, 4),
            tp2=round(r2, 4) if r2 else None,
            rr_ratio=None,
            score=90 if is_bearish else 85,
            tier="A+",
            reason_bg=f"Цената тества макро съпротива R1 ({r1_price_str}, само +{dist_str}).{extra_bg}",
            reason_en=f"Price testing macro resistance R1 ({r1_price_str}, only +{dist_str}).{extra_en}",
            fund_verdict=fund_verdict,
            fair_value=fair_value,
            mos_pct=mos_pct,
            moat=moat,
            z_score=z_score,
            quantamental_tag="PROFIT_REALIZATION",
        )

    # -------------------------------------------------------------------------
    # 3. BREAKOUT BUY (Spot Long Momentum)
    # -------------------------------------------------------------------------
    if state == "GOLD" and (context_flag == "BREAKOUT_ABOVE" or r1 is None):
        # In price discovery or breaking above R1
        sl_base = s1 if s1 is not None else v2
        sl = round(sl_base - (0.5 * atr), 4)
        risk = current_price - sl

        if risk > 0:
            tp1 = round(current_price + (1.8 * risk), 4)
            tp2 = round(current_price + (3.5 * risk), 4)
            rr = round((tp1 - current_price) / risk, 2)
            score, tier = calculate_confluence_score(
                is_mtf_aligned=is_mtf_aligned,
                near_support=False,
                s1_touches=s1_touches,
                spread_expanding=spread_expanding,
                rr_ratio=rr,
                fund_profile=fund_profile,
                btc_relative=btc_relative,
            )

            if is_bearish:
                tier = "B"
                setup_type = "SPECULATIVE_MOMENTUM_BUY"
                quant_tag = "SPECULATIVE_MOMENTUM"
                reason_bg = f"Пробив в Price Discovery, но с фундаментален рейтинг {fund_verdict} (слаб баланс). Търгувайте само със свит стоп!"
                reason_en = f"Breakout into Price Discovery, but with weak fundamentals ({fund_verdict}). Strict trailing SL required."
            elif is_bullish:
                setup_type = "QUANTAMENTAL_ALPHA_BUY"
                quant_tag = "INSTITUTIONAL_ALPHA"
                if fair_value and fair_value > tp2:
                    tp2 = round(fair_value, 4)
                reason_bg = f"Пробив в Price Discovery в синергия с институционален {fund_verdict} (Fair Value ${fair_value:,.2f}, Ров: {moat}). Трендов моментум."
                reason_en = f"Breakout into Price Discovery aligned with institutional {fund_verdict} (Fair Value ${fair_value:,.2f}, Moat: {moat}). Momentum continuation."
            else:
                setup_type = "BREAKOUT_BUY"
                quant_tag = "TECHNICAL_MOMENTUM"
                reason_bg = "Пробив над всички съпротиви (Price Discovery) със силна бича лента. Трендов моментум."
                reason_en = "Breakout into Price Discovery with strong bullish ribbon. Momentum continuation."

            max_lev = get_max_allowed_leverage(
                ticker=ticker or "",
                asset_class=asset_class,
                score=score,
                tier=tier,
                atr_pct=atr_pct,
                direction="LONG",
            )
            return TradeSuggestion(
                action="SPOT_BUY",
                direction="LONG",
                setup_type=setup_type,
                entry_price=round(current_price, 4),
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                rr_ratio=rr,
                score=score,
                tier=tier,
                reason_bg=reason_bg,
                reason_en=reason_en,
                fund_verdict=fund_verdict,
                fair_value=fair_value,
                mos_pct=mos_pct,
                moat=moat,
                z_score=z_score,
                quantamental_tag=quant_tag,
                max_leverage=max_lev,
                recommended_leverage=min(2, max_lev),
            )

    # -------------------------------------------------------------------------
    # 4. PULLBACK VALUE BUY (Primary Institutional Spot Long)
    # -------------------------------------------------------------------------
    is_pullback_location = (
        context_flag == "NEAR_SUPPORT"
        or (s1 is not None and (current_price - s1) <= 1.2 * atr)
        or (current_price <= v1 and current_price >= (v2 - 0.2 * atr))  # retesting ribbon
    )

    if (state == "GOLD" or (timeframe != "1D" and macro_1d_state == "GOLD")) and is_pullback_location:
        # Invalidation SL: Below S1 lower bound (or S1 core) and beneath ribbon v2, with 0.5 ATR buffer
        s1_anchor = s1_lower if s1_lower is not None else (s1 if s1 is not None else v2)
        structural_floor = min(s1_anchor, v2)
        sl = round(structural_floor - (0.5 * atr), 4)
        risk = current_price - sl

        if risk > 0:
            # Targets: TP1 at R1 lower (or 1.8R), TP2 at R2
            if r1 is not None and r1 > current_price:
                tp1 = round(r1_lower if r1_lower is not None else r1, 4)
                reward1 = tp1 - current_price
                rr = round(reward1 / risk, 2)
                tp2 = round(r2 if r2 is not None else (current_price + (2.5 * risk)), 4)
            else:
                tp1 = round(current_price + (2.0 * risk), 4)
                tp2 = round(current_price + (3.5 * risk), 4)
                rr = 2.0

            if rr >= min_rr_threshold:
                score, tier = calculate_confluence_score(
                    is_mtf_aligned=is_mtf_aligned,
                    near_support=True,
                    s1_touches=s1_touches,
                    spread_expanding=spread_expanding,
                    rr_ratio=rr,
                    fund_profile=fund_profile,
                    btc_relative=btc_relative,
                )

                s1_desc = f"${s1:,.2f}" if s1 else "лентата"
                r1_desc = f"${tp1:,.2f}" if tp1 else "R1"

                if is_bullish:
                    setup_type = "QUANTAMENTAL_ALPHA_BUY"
                    quant_tag = "INSTITUTIONAL_ALPHA"
                    if fair_value and fair_value > tp2:
                        tp2 = round(fair_value, 4)
                    reason_bg = f"💎 ИНСТИТУЦИОНАЛЕН АЛФА ВХОД: Корекция до S1 ({s1_desc}) с институционален {fund_verdict} (Fair Value ${fair_value:,.2f}, Ров: {moat}). R:R 1:{rr:.1f} с таван до R1 ({r1_desc}) и макро цел ${tp2:,.2f}."
                    reason_en = f"Quantamental Alpha: Pullback to S1 ({s1_desc}) aligned with institutional {fund_verdict} (Fair Value ${fair_value:,.2f}, Moat: {moat}). R:R 1:{rr:.1f} targeting R1 ({r1_desc}) and macro target ${tp2:,.2f}."
                elif is_hold:
                    setup_type = "QUALITY_HOLD_ACCUMULATION"
                    quant_tag = "CORE_QUALITY_HOLD"
                    reason_bg = f"🏰 ЕЛИТЕН ЛИДЕР: Корекция до S1 ({s1_desc}) за качествен лидер ({fund_name or 'Емитент'}, {fund_verdict}). R:R 1:{rr:.1f} до R1 ({r1_desc})."
                    reason_en = f"Quality Leader: Pullback to S1 ({s1_desc}) for high-quality core hold ({fund_name or 'Asset'}, {fund_verdict}). R:R 1:{rr:.1f} targeting R1 ({r1_desc})."
                elif is_bearish:
                    tier = "B"
                    setup_type = "SPECULATIVE_PULLBACK_BUY"
                    quant_tag = "SPECULATIVE_MOMENTUM"
                    reason_bg = f"⚠️ СПЕКУЛАТИВЕН ВХОД: Технически отскок от S1 ({s1_desc}), но със слаб фундаментален профил ({fund_verdict}). Търгувайте само със свит стоп!"
                    reason_en = f"Speculative Bounce: Technical bounce at S1 ({s1_desc}), but weak fundamental profile ({fund_verdict}). Strict stop required!"
                else:
                    setup_type = "PULLBACK_VALUE_BUY"
                    quant_tag = "TECHNICAL_VALUE"
                    reason_bg = f"Корекция до подкрепа S1 ({s1_desc}) в бичи тренд. Отличен Risk/Reward (1:{rr:.1f}) с таван до R1 ({r1_desc})."
                    reason_en = f"Pullback to support S1 ({s1_desc}) in bullish trend. Solid R:R (1:{rr:.1f}) targeting R1 ({r1_desc})."

                dca = f"50% Market (${current_price:,.2f}) + 50% Limit S1 (${s1:,.2f})" if (s1 and s1 < current_price) else None

                max_lev = get_max_allowed_leverage(
                    ticker=ticker or "",
                    asset_class=asset_class,
                    score=score,
                    tier=tier,
                    atr_pct=atr_pct,
                    direction="LONG",
                )
                return TradeSuggestion(
                    action="SPOT_BUY",
                    direction="LONG",
                    setup_type=setup_type,
                    entry_price=round(current_price, 4),
                    stop_loss=sl,
                    tp1=tp1,
                    tp2=tp2,
                    rr_ratio=rr,
                    score=score,
                    tier=tier,
                    reason_bg=reason_bg,
                    reason_en=reason_en,
                    fund_verdict=fund_verdict,
                    fair_value=fair_value,
                    mos_pct=mos_pct,
                    moat=moat,
                    z_score=z_score,
                    quantamental_tag=quant_tag,
                    dca_plan=dca,
                    max_leverage=max_lev,
                    recommended_leverage=min(2, max_lev),
                )

    # -------------------------------------------------------------------------
    # 5. HEDGE SHORT 2X (Optional Light Futures Short on Breakdown)
    # -------------------------------------------------------------------------
    if state == "BLUE":
        overhead_res = r1 if (r1 is not None and r1 > current_price) else v2
        if current_price < overhead_res:
            # Bearish trend retesting overhead resistance/ribbon (v1 lower, v2 upper)
            retesting_overhead = (
                (current_price >= (v1 - 0.2 * atr) and current_price <= (v2 + 0.3 * atr))
                or (r1 is not None and abs(current_price - r1) <= 0.8 * atr)
            )

            if retesting_overhead:
                sl_anchor = max(r1_upper if r1_upper is not None else overhead_res, v2)
                sl = round(sl_anchor + (0.5 * atr), 4)
                risk = sl - current_price

                if risk > 0:
                    tp1 = round(s1 if s1 is not None else (current_price - 1.8 * risk), 4)
                    tp2 = round(s2 if s2 is not None else (current_price - 3.0 * risk), 4)
                    reward = current_price - tp1
                    rr = round(reward / risk, 2)

                    if rr >= min_rr_threshold and current_price > tp1:
                        score, tier = calculate_confluence_score(
                            is_mtf_aligned=True,
                            near_support=False,
                            s1_touches=r1_touches,
                            spread_expanding=spread_pct < -0.2,
                            rr_ratio=rr,
                            fund_profile=fund_profile,
                        )
                        tag = "SHORT_FUNDAMENTAL_ALIGNMENT" if is_bearish else "TECHNICAL_SHORT"
                        extra_reason = f" Потвърдено от слаб фундаментален рейтинг ({fund_verdict})." if is_bearish else ""
                        max_lev = get_max_allowed_leverage(
                            ticker=ticker or "",
                            asset_class=asset_class,
                            score=score,
                            tier=tier,
                            atr_pct=atr_pct,
                            direction="SHORT",
                        )
                        lev_label = f"макс {max_lev}x левъридж" if max_lev > 1 else "1x (без левъридж)"
                        lev_label_en = f"max {max_lev}x leverage" if max_lev > 1 else "1x (spot/no leverage)"
                        return TradeSuggestion(
                            action="SHORT_2X_OPTIONAL",
                            direction="SHORT",
                            setup_type="HEDGE_SHORT_2X",
                            entry_price=round(current_price, 4),
                            stop_loss=sl,
                            tp1=tp1,
                            tp2=tp2,
                            rr_ratio=rr,
                            score=score,
                            tier=tier,
                            reason_bg=f"Отхвърляне от съпротива/меча панделка с потенциал до подкрепа S1 (${tp1:,.2f}).{extra_reason} Лек short с {lev_label}.",
                            reason_en=f"Rejection at resistance/bearish ribbon with room to S1 (${tp1:,.2f}).{extra_reason} Light hedge short ({lev_label_en}).",
                            fund_verdict=fund_verdict,
                            fair_value=fair_value,
                            mos_pct=mos_pct,
                            moat=moat,
                            z_score=z_score,
                            quantamental_tag=tag,
                            max_leverage=max_lev,
                            recommended_leverage=min(2, max_lev),
                        )

    # -------------------------------------------------------------------------
    # 6. DEFAULT: WAIT FOR HIGH CONVICTION SETUP
    # -------------------------------------------------------------------------
    wait_bg = "Цената е в междинна зона или съотношението Риск/Печалба е под 1:1.8. Изчакай тест на ключово ниво."
    wait_en = "Price in mid-range or R:R below 1:1.8. Wait for key structural level test."
    if is_bullish:
        wait_bg += f" Фундаментален {fund_verdict} (Fair Value ${fair_value:,.2f}) – изчакайте корекция до S1 за вход!"
        wait_en += f" Fundamentally {fund_verdict} (Fair Value ${fair_value:,.2f}) – wait for pullback to S1 for entry!"

    return TradeSuggestion(
        action="WAIT",
        direction="NEUTRAL",
        setup_type="WAIT_FOR_SETUP",
        entry_price=round(current_price, 4),
        stop_loss=None,
        tp1=None,
        tp2=None,
        rr_ratio=None,
        score=40,
        tier="NONE",
        reason_bg=wait_bg,
        reason_en=wait_en,
        fund_verdict=fund_verdict,
        fair_value=fair_value,
        mos_pct=mos_pct,
        moat=moat,
        z_score=z_score,
        quantamental_tag="WAIT_FOR_DIP" if is_bullish else "WAIT_FOR_STRUCTURE",
    )


def generate_trade_suggestion(
    current_price: float,
    state: str,
    v1: float,
    m1: float,
    m2: float,
    v2: float,
    spread_pct: float,
    atr: float,
    s1: Optional[float] = None,
    s1_lower: Optional[float] = None,
    s1_touches: int = 0,
    s2: Optional[float] = None,
    r1: Optional[float] = None,
    r1_lower: Optional[float] = None,
    r1_upper: Optional[float] = None,
    r1_touches: int = 0,
    r2: Optional[float] = None,
    context_flag: str = "IN_VALUE_RANGE",
    timeframe: str = "1D",
    macro_1d_state: Optional[str] = None,
    min_rr_threshold: float = 1.8,
    fund_profile: Optional[object] = None,
    ticker: Optional[str] = None,
    asset_class: str = "crypto",
    btc_relative: Optional[object] = None,
) -> TradeSuggestion:
    """
    Evaluates market conditions and returns an institutional TradeSuggestion,
    enriched with distinct Technical vs Fundamental recommendations and Quantamental synthesis.
    """
    raw_s = _raw_generate_trade_suggestion(
        current_price=current_price,
        state=state,
        v1=v1,
        m1=m1,
        m2=m2,
        v2=v2,
        spread_pct=spread_pct,
        atr=atr,
        s1=s1,
        s1_lower=s1_lower,
        s1_touches=s1_touches,
        s2=s2,
        r1=r1,
        r1_lower=r1_lower,
        r1_upper=r1_upper,
        r1_touches=r1_touches,
        r2=r2,
        context_flag=context_flag,
        timeframe=timeframe,
        macro_1d_state=macro_1d_state,
        min_rr_threshold=min_rr_threshold,
        fund_profile=fund_profile,
        ticker=ticker,
        asset_class=asset_class,
        btc_relative=btc_relative,
    )
    return _enrich_trade_suggestion(
        raw_s,
        state=state,
        spread_pct=spread_pct,
        s1=s1,
        r1=r1,
        current_price=current_price,
        fund_profile=fund_profile,
        btc_relative=btc_relative,
    )


