"""
Institutional Trade Suggestions Engine.
Translates Larsson Ribbon trend states, ATR volatility buffers, and quantitative S/R clusters
into actionable, risk-managed trade suggestions tailored for Spot investing and light leverage (up to 2x).
"""

from dataclasses import asdict, dataclass
from typing import Dict, Optional, Tuple, TYPE_CHECKING
import numpy as np

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

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_confluence_score(
    is_mtf_aligned: bool,
    near_support: bool,
    s1_touches: int,
    spread_expanding: bool,
    rr_ratio: Optional[float],
    fund_profile: Optional[object] = None,
) -> Tuple[int, str]:
    """
    Calculates institutional confluence score (0 - 100) and assigns a quality tier.
    Enriched with fundamental valuation metrics (MoS, Moat, Altman Z).
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


def generate_trade_suggestion(
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
) -> TradeSuggestion:
    """
    Evaluates market conditions and returns an institutional TradeSuggestion.
    Fuses technical momentum/structure with institutional fundamental valuation.
    """
    atr = max(atr, current_price * 0.005)
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
                )

    # -------------------------------------------------------------------------
    # 5. HEDGE SHORT 2X (Optional Light Futures Short on Breakdown)
    # -------------------------------------------------------------------------
    if state == "BLUE" and r1 is not None and current_price < r1:
        # Bearish trend retesting overhead resistance/ribbon
        retesting_overhead = (current_price >= v2 and current_price <= (v1 + 0.3 * atr)) or (
            abs(current_price - r1) <= 0.8 * atr
        )

        if retesting_overhead:
            sl_anchor = max(r1_upper if r1_upper is not None else r1, v1)
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
                        reason_bg=f"Отхвърляне от съпротива/меча панделка с потенциал до подкрепа S1 (${tp1:,.2f}).{extra_reason} Лек short с макс 2x левъридж.",
                        reason_en=f"Rejection at resistance/bearish ribbon with room to S1 (${tp1:,.2f}).{extra_reason} Light hedge short (max 2x leverage).",
                        fund_verdict=fund_verdict,
                        fair_value=fair_value,
                        mos_pct=mos_pct,
                        moat=moat,
                        z_score=z_score,
                        quantamental_tag=tag,
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
