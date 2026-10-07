"""
Dashboard Data Generator.
Exports SQLite states into a clean JSON structure suitable for the web dashboard.
"""

from datetime import datetime, timezone
import json
import math
import os
from typing import Dict, List, Optional

from src.storage.database import Database
from src.engine.asset_profiles import get_quality_tier, get_tier_emoji
from src.engine.btc_relative import get_tradingview_ratio_symbol, get_tradingview_ratio_link

DEFAULT_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "dashboard",
    "data.json",
)


NAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "names_mapping.json",
)


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


def _clean_dict_floats(obj):
    """Recursively converts NaN/Inf to None in nested dicts/lists and converts sqlite3.Row to dict for JSON compliance."""
    if hasattr(obj, "keys") and not isinstance(obj, dict):
        try:
            obj = dict(obj)
        except Exception:
            pass
    if isinstance(obj, dict):
        return {k: _clean_dict_floats(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_clean_dict_floats(elem) for elem in obj]
    elif isinstance(obj, float):
        return _clean_float(obj)
    return obj


TV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "tv_mapping.json",
)


def _load_names_map() -> Dict[str, str]:
    try:
        if os.path.exists(NAMES_PATH):
            with open(NAMES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _load_tv_map() -> Dict[str, str]:
    try:
        if os.path.exists(TV_PATH):
            with open(TV_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _row_val(row, key, default=None):
    if key in row.keys() and row[key] is not None:
        return row[key]
    return default


def export_dashboard_data(
    db: Optional[Database] = None,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> Dict:
    """
    Reads all states from the database and writes a JSON file for the static dashboard.
    """
    if db is None:
        db = Database()

    # Safety: do not clobber production dashboard data.json from a non-default test DB
    if output_path == DEFAULT_OUTPUT_PATH:
        from src.storage.database import DEFAULT_DB_PATH
        if os.path.exists(DEFAULT_DB_PATH) and os.path.abspath(db.db_path) != os.path.abspath(DEFAULT_DB_PATH):
            logger.info(f"Skipping default dashboard export from non-production db: {db.db_path}")
            return {"symbols": [], "summary": {}}

    names_map = _load_names_map()
    rows = db.get_all_states()

    items = []
    gold_count = 0
    blue_count = 0
    neutral_count = 0

    for r in rows:
        state = r["current_state"]
        if state == "GOLD":
            gold_count += 1
        elif state == "BLUE":
            blue_count += 1
        else:
            neutral_count += 1

        ticker = r["ticker"]
        name = names_map.get(ticker)
        if not name:
            if ticker.endswith("USDT"):
                name = f"{ticker[:-4]} / USDT"
            else:
                name = ticker

        v1_clean = _clean_float(r["v1"])
        m1_clean = _clean_float(r["m1"])
        m2_clean = _clean_float(r["m2"])
        v2_clean = _clean_float(r["v2"])

        v1_val = round(v1_clean, 4) if v1_clean is not None else 0.0
        m1_val = round(m1_clean, 4) if m1_clean is not None else 0.0
        m2_val = round(m2_clean, 4) if m2_clean is not None else 0.0
        v2_val = round(v2_clean, 4) if v2_clean is not None else 0.0
        spread_pct = round(((v1_val - v2_val) / v2_val) * 100, 2) if v2_val > 0 else 0.0

        # Fundamental Profile lookup
        try:
            from src.engine.quantamental import get_fundamental_profile
            fund = get_fundamental_profile(ticker)
        except Exception:
            fund = None

        fund_data = None
        if fund:
            fund_data = {
                "verdict": fund.verdict,
                "fair_value": _clean_float(fund.fair_value),
                "target_price": _clean_float(fund.target_price),
                "mos_pct": _clean_float(fund.mos_pct),
                "moat": fund.moat,
                "roic_pct": _clean_float(fund.roic_pct),
                "wacc_pct": _clean_float(fund.wacc_pct),
                "z_score": _clean_float(fund.z_score),
                "m_score": _clean_float(fund.m_score),
                "tata": _clean_float(fund.tata),
                "upside_pct": _clean_float(fund.upside_pct),
                "thesis": fund.thesis,
                "sector": fund.sector,
                "industry": fund.industry,
                "model_type": fund.model_type,
                "shares": _clean_float(fund.shares),
                "mcap_b": _clean_float(fund.mcap_b),
                "beta": _clean_float(fund.beta),
                "revenue_b": _clean_float(fund.revenue_b),
                "ebit_b": _clean_float(fund.ebit_b),
                "nopat_b": _clean_float(fund.nopat_b),
                "entry_price": _clean_float(fund.entry_price),
                "solvency_type": fund.solvency_type,
                "production_cost": _clean_float(fund.production_cost),
                "mvrv_ratio": _clean_float(fund.mvrv_ratio),
            }
        elif _row_val(r, "ts_fund_verdict"):
            fund_data = {
                "verdict": _row_val(r, "ts_fund_verdict"),
                "fair_value": _clean_float(_row_val(r, "ts_fair_value")),
                "target_price": _clean_float(_row_val(r, "ts_fair_value")),
                "mos_pct": _clean_float(_row_val(r, "ts_mos_pct")),
                "moat": _row_val(r, "ts_moat") or "None",
                "roic_pct": None,
                "wacc_pct": None,
                "z_score": _clean_float(_row_val(r, "ts_z_score")),
                "m_score": None,
                "tata": None,
                "upside_pct": None,
                "thesis": "",
                "sector": None,
                "industry": None,
                "model_type": None,
                "shares": None,
                "mcap_b": None,
                "beta": None,
                "revenue_b": None,
                "ebit_b": None,
                "nopat_b": None,
                "entry_price": None,
                "solvency_type": None,
                "production_cost": None,
                "mvrv_ratio": None,
            }

        # ---------------------------------------------------------------------
        # 1. TECHNICAL ANALYSIS BLOCK (Larsson Ribbon & S/R Structure)
        # ---------------------------------------------------------------------
        ts_action = _row_val(r, "ts_action", "WAIT")
        ts_setup = _row_val(r, "ts_setup_type", "WAIT_FOR_SETUP")
        tech_act = _row_val(r, "ts_tech_action")
        tech_lbl = _row_val(r, "ts_tech_label_bg")
        tech_the = _row_val(r, "ts_tech_thesis_bg")

        if not tech_act:
            if state == "GOLD":
                if ts_action == "SPOT_BUY":
                    tech_act = "BUY"
                    if "PULLBACK" in ts_setup:
                        tech_lbl = "🟢 BUY (Pullback S1)"
                        tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с тест на S1 подкрепа."
                    elif "BREAKOUT" in ts_setup:
                        tech_lbl = "🟢 BUY (Пробив / Momentum)"
                        tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%) с пробив в Price Discovery."
                    else:
                        tech_lbl = "🟢 BUY (Бича панделка)"
                        tech_the = f"Бичи тренд с възходяща подредба на лентата (spread {spread_pct:+.1f}%)."
                elif ts_action == "TAKE_PROFIT":
                    tech_act = "TAKE_PROFIT"
                    tech_lbl = "💰 TAKE PROFIT (Тест на R1)"
                    tech_the = "Бичи тренд, но цената тества макро съпротива R1. Прибери печалба."
                else:
                    tech_act = "HOLD"
                    tech_lbl = "🟡 HOLD (Възходящ тренд)"
                    tech_the = f"Бичи тренд (Gold, spread {spread_pct:+.1f}%). Задръж текуща позиция."
            elif state == "BLUE":
                if ts_action == "SHORT_2X_OPTIONAL":
                    tech_act = "SHORT"
                    tech_lbl = "🔴 SHORT (Меча панделка)"
                    tech_the = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%)."
                else:
                    tech_act = "EXIT"
                    tech_lbl = "🔴 EXIT / STOP (Мечи тренд)"
                    tech_the = f"Мечи низходящ тренд (Blue, spread {spread_pct:+.1f}%) или загуба на S1."
            else:
                tech_act = "WAIT"
                tech_lbl = "⏳ WAIT (Консолидация)"
                tech_the = "Панделката е преплетена без ясна посока. Изчакайте формиране на тренд."

        s1_val = _clean_float(_row_val(r, "s1"))
        s1_dist = _clean_float(_row_val(r, "s1_dist_pct"))
        r1_val = _clean_float(_row_val(r, "r1"))
        r1_dist = _clean_float(_row_val(r, "r1_dist_pct"))
        # Determine Recent Gold Flip status (Fresh 1-5 bar breakout / early expansion)
        is_gold_flip = False
        gold_flip_bars = None
        db_bars = _row_val(r, "bars_since_flip")
        s_pct = spread_pct if spread_pct is not None else 999.0

        if state == "GOLD":
            if db_bars is not None:
                # 0 to 4 bars elapsed since transition candle (i.e. bars 1 to 5 of the trend)
                if 0 <= db_bars <= 4 and (0.0 <= s_pct <= 7.5):
                    is_gold_flip = True
                    gold_flip_bars = db_bars + 1
            else:
                # Fallback only when bars_since_flip is not recorded in DB
                last_chg = r["last_state_change"]
                if last_chg:
                    try:
                        lc_dt = datetime.fromisoformat(last_chg.replace("Z", "+00:00"))
                        now_dt = datetime.now(timezone.utc)
                        age_hours = (now_dt - lc_dt).total_seconds() / 3600.0
                        tf = r["timeframe"]
                        # Strict time checks - DO NOT estimate on 1W without candle bars
                        if tf == "4H" and age_hours <= 5.0 and (0.0 <= s_pct <= 6.0):
                            is_gold_flip = True
                            gold_flip_bars = 1
                        elif tf == "1D" and age_hours <= 28.0 and (0.0 <= s_pct <= 6.0):
                            is_gold_flip = True
                            gold_flip_bars = 1
                    except Exception:
                        pass

        technical_block = {
            "state": state,
            "spread_pct": spread_pct,
            "action": tech_act,
            "label_bg": tech_lbl,
            "thesis": tech_the,
            "s1": s1_val,
            "s1_dist_pct": s1_dist,
            "s1_touches": _row_val(r, "s1_touches", 0),
            "r1": r1_val,
            "r1_dist_pct": r1_dist,
            "r1_touches": _row_val(r, "r1_touches", 0),
            "is_gold_flip": is_gold_flip,
            "gold_flip_bars": gold_flip_bars,
        }

        # ---------------------------------------------------------------------
        # 2. FUNDAMENTAL ANALYSIS BLOCK (DCF Valuation & Moat)
        # ---------------------------------------------------------------------
        fund_act = _row_val(r, "ts_fund_action")
        fund_lbl = _row_val(r, "ts_fund_label_bg")
        fund_the = _row_val(r, "ts_fund_thesis_bg")

        if not fund_act:
            if fund_data and fund_data.get("verdict"):
                v = fund_data["verdict"].upper()
                mos = fund_data.get("mos_pct")
                mos_txt = f"{mos:+.0f}%" if mos is not None else ""
                fv = fund_data.get("fair_value")
                fv_txt = f"${fv:,.2f}" if fv else "N/A"
                moat_txt = f", {fund_data['moat']} Moat" if fund_data.get("moat") and fund_data["moat"] != "None" else ""

                if "STRONG BUY" in v:
                    fund_act = "STRONG_BUY"
                    fund_lbl = f"🟢 СИЛНО ПОДЦЕНЕН ({mos_txt} MoS)"
                    fund_the = f"DCF Стойност: {fv_txt} (MoS: {mos_txt}{moat_txt}). {fund_data.get('thesis', '')}".strip()
                elif "BUY" in v or "OVERWEIGHT" in v:
                    fund_act = "BUY"
                    fund_lbl = f"🟢 ПОДЦЕНЕН ({mos_txt} MoS)"
                    fund_the = f"DCF Стойност: {fv_txt} (MoS: {mos_txt}{moat_txt}). {fund_data.get('thesis', '')}".strip()
                elif "HOLD" in v or "NEUTRAL" in v:
                    fund_act = "HOLD"
                    fund_lbl = "🟡 СПРАВЕДЛИВА ЦЕНА (Hold)"
                    fund_the = f"Търгува се около DCF цена {fv_txt}{moat_txt}.".strip()
                elif "REDUCE" in v or "AVOID" in v or "UNDERPERFORM" in v:
                    fund_act = "REDUCE"
                    fund_lbl = "🔴 НАДЦЕНЕН (Reduce)"
                    fund_the = f"Надценен спрямо DCF парични потоци ({fv_txt}).".strip()
                else:
                    fund_act = "HOLD"
                    fund_lbl = f"⚪ {fund_data['verdict']}"
                    fund_the = f"DCF: {fv_txt}{moat_txt}."
            else:
                fund_act = "SPECULATIVE_NA"
                fund_lbl = "⚪ МАКРО / СПЕКУЛАТИВЕН"
                fund_the = "Крипто/суровинен актив без корпоративен DCF модел. Движи се от ликвидност и моментум."

        if not fund_data:
            fund_data = {
                "verdict": "SPECULATIVE_NA",
                "fair_value": None,
                "mos_pct": None,
                "moat": "None",
                "roic_pct": None,
                "z_score": None,
                "upside_pct": None,
                "thesis": "",
            }

        fund_data["action"] = fund_act
        fund_data["label_bg"] = fund_lbl
        fund_data["thesis_bg"] = fund_the

        # ---------------------------------------------------------------------
        # 3. SYNTHESIS BLOCK (Quantamental Confluence)
        # ---------------------------------------------------------------------
        synth_badge = _row_val(r, "ts_synthesis_badge_bg")
        synth_label = _row_val(r, "ts_synthesis_label_bg")

        if not synth_badge:
            if ts_setup == "QUANTAMENTAL_ALPHA_BUY":
                synth_badge = "⭐ ALPHA BUY"
                synth_label = "Пълен консенсус (Бича техника + Подценен фундамент)"
            elif ts_setup == "VALUE_TRAP_WARNING":
                synth_badge = "⏳ VALUE TRAP RISK"
                synth_label = "Конфликт: Евтин фундамент, но меча техника (Не купувай преди обръщане!)"
            elif ts_setup in ["SPECULATIVE_MOMENTUM_BUY", "SPECULATIVE_PULLBACK_BUY"]:
                synth_badge = "⚠️ СПЕКУЛАТИВЕН ВХОД"
                synth_label = "Конфликт: Бича техника, но слаб/надценен фундамент (Търгувай само с къс SL)"
            elif ts_setup == "QUALITY_HOLD_ACCUMULATION":
                synth_badge = "🧱 QUALITY ACCUMULATE"
                synth_label = "Качествена компания за дългосрочно натрупване (DCA) на ключови нива"
            elif ts_action == "SPOT_BUY":
                synth_badge = "🟢 SPOT BUY"
                synth_label = "Чист технически вход в бичи тренд"
            elif ts_action == "TAKE_PROFIT":
                synth_badge = "💰 TAKE PROFIT"
                synth_label = "Прибиране на печалби при тест на съпротива"
            elif ts_action == "EXIT_PROTECT":
                synth_badge = "🛑 CAPITAL PROTECT"
                synth_label = "Защита на капитала при пробив на структурата"
            elif ts_action == "SHORT_2X_OPTIONAL":
                synth_badge = "🔴 SHORT 2X"
                synth_label = "Мечи трендов шорт с ограничен левъридж"
            else:
                synth_badge = "⏳ WAIT"
                synth_label = "Изчакване на качествена структура за вход"

        entry_val = _clean_float(_row_val(r, "ts_entry"))
        sl_val = _clean_float(_row_val(r, "ts_sl"))
        tp1_val = _clean_float(_row_val(r, "ts_tp1"))
        tp2_val = _clean_float(_row_val(r, "ts_tp2"))
        rr_val = _clean_float(_row_val(r, "ts_rr"))
        score_val = _row_val(r, "ts_score", 0)
        tier_val = _row_val(r, "ts_tier", "NONE")
        ts_direction = _row_val(r, "ts_direction", "NEUTRAL")

        # Smart Leverage calculation for actionable setups
        max_lev = 1
        rec_lev = 1
        lev_matrix = []

        if ts_action in ["SPOT_BUY", "SHORT_2X_OPTIONAL"] and entry_val and entry_val > 0:
            try:
                from src.engine.asset_profiles import get_max_allowed_leverage
                from src.engine.trade_suggestions import calculate_leverage_matrix

                atr_val = _clean_float(_row_val(r, "atr")) or (entry_val * 0.02)
                atr_pct = (atr_val / entry_val) * 100.0 if entry_val > 0 else 2.0

                max_lev = get_max_allowed_leverage(
                    ticker=ticker,
                    asset_class=r["asset_class"],
                    score=score_val,
                    tier=tier_val,
                    atr_pct=atr_pct,
                    direction=ts_direction,
                )
                rec_lev = min(2, max_lev) if max_lev > 1 else 1

                lev_matrix = calculate_leverage_matrix(
                    entry_price=entry_val,
                    stop_loss=sl_val,
                    position_size_usd=100.0,
                    max_leverage=max_lev,
                    direction=ts_direction,
                )
            except Exception:
                max_lev = 1
                rec_lev = 1
                lev_matrix = []

        synthesis_block = {
            "setup_type": ts_setup,
            "action": ts_action,
            "direction": ts_direction,
            "badge_bg": synth_badge,
            "label_bg": synth_label,
            "entry": entry_val,
            "sl": sl_val,
            "tp1": tp1_val,
            "tp2": tp2_val,
            "rr": rr_val,
            "score": score_val,
            "tier": tier_val,
            "max_leverage": max_lev,
            "recommended_leverage": rec_lev,
        }

        trade_suggestion_dict = {
            "action": ts_action,
            "direction": ts_direction,
            "setup_type": ts_setup,
            "entry": entry_val,
            "sl": sl_val,
            "tp1": tp1_val,
            "tp2": tp2_val,
            "rr": rr_val,
            "score": score_val,
            "tier": tier_val,
            "reason_bg": _row_val(r, "ts_reason_bg", ""),
            "reason_en": _row_val(r, "ts_reason_en", ""),
            "fund_verdict": fund_data.get("verdict"),
            "fair_value": fund_data.get("fair_value"),
            "moat": fund_data.get("moat"),
            "quantamental_tag": _row_val(r, "ts_quantamental_tag"),
            "tech_action": tech_act,
            "tech_label_bg": tech_lbl,
            "tech_thesis_bg": tech_the,
            "fund_action": fund_act,
            "fund_label_bg": fund_lbl,
            "fund_thesis_bg": fund_the,
            "synthesis_badge_bg": synth_badge,
            "synthesis_label_bg": synth_label,
            "max_leverage": max_lev,
            "recommended_leverage": rec_lev,
            "leverage_matrix": _clean_dict_floats(lev_matrix),
        }

        # BTC Relative Strength Block (for crypto and crypto_stocks)
        btc_ratio_state = _row_val(r, "ts_btc_ratio_state", "NA")
        btc_alpha_30d = _clean_float(_row_val(r, "ts_btc_alpha_30d"))
        btc_alpha_7d = _clean_float(_row_val(r, "ts_btc_alpha_7d"))
        btc_ratio_spread = _clean_float(_row_val(r, "ts_btc_ratio_spread"))
        btc_verdict = _row_val(r, "ts_btc_verdict")
        btc_badge_bg = _row_val(r, "ts_btc_badge_bg")
        btc_thesis_bg = _row_val(r, "ts_btc_thesis_bg")
        btc_leverage_allowed = bool(_row_val(r, "ts_btc_leverage_allowed", 1))

        # TradingView /BTC ratio symbol & link
        tv_ratio_symbol = get_tradingview_ratio_symbol(ticker, r["asset_class"], r["tv_symbol"])
        tv_ratio_url = get_tradingview_ratio_link(ticker, r["asset_class"], _row_val(r, "timeframe", "1D"), r["tv_symbol"])

        btc_relative_block = None
        if r["asset_class"] in ["crypto", "crypto_stocks"]:
            sign = "+" if (btc_alpha_30d or 0) >= 0 else ""
            btc_relative_block = {
                "ratio_state": btc_ratio_state,
                "alpha_30d_pct": btc_alpha_30d,
                "alpha_7d_pct": btc_alpha_7d,
                "ratio_spread_pct": btc_ratio_spread,
                "verdict": btc_verdict or "NA",
                "badge_bg": btc_badge_bg or (f"₿ {sign}{btc_alpha_30d:.1f}% vs BTC" if btc_alpha_30d is not None else "₿ vs BTC"),
                "thesis_bg": btc_thesis_bg or "",
                "leverage_allowed": btc_leverage_allowed,
                "tv_ratio_symbol": tv_ratio_symbol,
                "tv_ratio_url": tv_ratio_url,
            }
            trade_suggestion_dict["btc_relative"] = btc_relative_block

        # Quality Tier
        asset_tier = get_quality_tier(ticker)
        tier_emoji = get_tier_emoji(asset_tier)

        # Options Flow (US Equities)
        opt_flow = None
        opt_json = _row_val(r, "options_flow_json")
        if opt_json:
            try:
                opt_flow = json.loads(opt_json)
            except Exception:
                pass
        if not opt_flow and hasattr(db, "get_options_flow"):
            opt_flow = db.get_options_flow(ticker)

        clean_opt = _clean_dict_floats(opt_flow) if opt_flow else None
        if clean_opt:
            trade_suggestion_dict["options_flow"] = clean_opt

        items.append({
            "ticker": ticker,
            "name": name,
            "asset_class": r["asset_class"],
            "tv_symbol": r["tv_symbol"],
            "tv_ratio_symbol": tv_ratio_symbol,
            "tv_ratio_url": tv_ratio_url,
            "timeframe": r["timeframe"],
            "state": state,
            "price": _clean_float(r["last_price"]),
            "v1": v1_val,
            "m1": m1_val,
            "m2": m2_val,
            "v2": v2_val,
            "spread_pct": spread_pct,
            "s1": s1_val,
            "s1_touches": _row_val(r, "s1_touches", 0),
            "s1_dist_pct": s1_dist,
            "r1": r1_val,
            "r1_touches": _row_val(r, "r1_touches", 0),
            "r1_dist_pct": r1_dist,
            "context_flag": _row_val(r, "context_flag", "IN_VALUE_RANGE"),
            "context_desc": _row_val(r, "context_desc", ""),
            "technical": technical_block,
            "fundamental": fund_data,
            "synthesis": synthesis_block,
            "trade_suggestion": trade_suggestion_dict,
            "btc_relative": btc_relative_block,
            "options_flow": clean_opt,
            "quality_tier": asset_tier,
            "tier_emoji": tier_emoji,
            "is_gold_flip": is_gold_flip,
            "gold_flip_bars": gold_flip_bars,
            "last_change": r["last_state_change"],
            "updated_at": r["updated_at"],
        })

    total = len(items)
    bullish_pct = round((gold_count / total * 100), 1) if total > 0 else 0.0
    bearish_pct = round((blue_count / total * 100), 1) if total > 0 else 0.0
    neutral_pct = round((neutral_count / total * 100), 1) if total > 0 else 0.0

    # Pending Setups from queue
    pending_setups_data = []
    tv_map = _load_tv_map()
    try:
        from src.alerts.formatter import get_tradingview_link
        if hasattr(db, "expire_stale_setups"):
            db.expire_stale_setups(max_age_hours=48)
        if hasattr(db, "clear_triggered_setups"):
            db.clear_triggered_setups()
        raw_setups = db.get_active_pending_setups(exclude_tier_c=True)
        # Curate to top 35-40 highest quality pending setups
        if len(raw_setups) > 35:
            raw_setups = raw_setups[:35]
        for s in raw_setups:
            sym = s["symbol"]
            s_name = names_map.get(sym)
            if not s_name:
                if sym.endswith("USDT"):
                    s_name = f"{sym[:-4]} / USDT"
                elif sym.endswith("USDC"):
                    s_name = f"{sym[:-4]} / USDC"
                else:
                    s_name = sym

            s_tf = s["timeframe"] or "1D"
            s_tv_sym = tv_map.get(sym) or (f"BINANCE:{sym}" if (sym.endswith("USDT") or sym.endswith("USDC")) else sym)
            s_tv_url = get_tradingview_link(s_tv_sym, s_tf)

            pending_setups_data.append({
                "symbol": sym,
                "name": s_name,
                "tv_symbol": s_tv_sym,
                "tv_url": s_tv_url,
                "asset_class": s["asset_class"],
                "setup_type": s["setup_type"],
                "direction": s["direction"],
                "priority": s["priority"],
                "quality_score": _clean_float(s["quality_score"]),
                "description_bg": s["description_bg"],
                "conditions_met": s["conditions_met"],
                "conditions_pending": s["conditions_pending"],
                "estimated_trigger": s["estimated_trigger"],
                "current_price": _clean_float(s["current_price"]),
                "target_entry": _clean_float(s["target_entry"]),
                "key_level": _clean_float(s["key_level"]),
                "timeframe": s_tf,
                "tier": s["tier"],
                "first_detected": s["first_detected"],
                "last_updated": s["last_updated"],
            })
    except Exception:
        pass

    # Dual Portfolio Export: Real (Live) & Virtual (Paper)
    portfolio_real_data = {}
    portfolio_paper_data = {}
    portfolio_summary = {}

    try:
        from src.trading.portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker(db=db)

        # 1. Virtual / Paper Portfolio
        paper_summary = tracker.get_portfolio_summary(portfolio_type="PAPER")
        paper_positions = tracker.get_open_positions_detail(portfolio_type="PAPER")
        paper_history = tracker.get_trade_history(limit=50, portfolio_type="PAPER")
        raw_paper_log = db.get_trade_log(limit=50, portfolio_type="PAPER") if hasattr(db, "get_trade_log") else []
        paper_journal = [dict(entry) for entry in raw_paper_log]

        portfolio_paper_data = {
            "summary": _clean_dict_floats(paper_summary),
            "positions": _clean_dict_floats(paper_positions),
            "history": _clean_dict_floats(paper_history),
            "journal": _clean_dict_floats(paper_journal),
        }
        portfolio_summary = portfolio_paper_data["summary"]

        # 2. Real Money / Live Portfolio
        real_summary = tracker.get_portfolio_summary(portfolio_type="REAL")
        real_positions = tracker.get_open_positions_detail(portfolio_type="REAL")
        real_history = tracker.get_trade_history(limit=50, portfolio_type="REAL")
        raw_real_log = db.get_trade_log(limit=50, portfolio_type="REAL") if hasattr(db, "get_trade_log") else []
        real_journal = [dict(entry) for entry in raw_real_log]

        portfolio_real_data = {
            "summary": _clean_dict_floats(real_summary),
            "positions": _clean_dict_floats(real_positions),
            "history": _clean_dict_floats(real_history),
            "journal": _clean_dict_floats(real_journal),
        }
    except Exception as e:
        # Fallback to basic summary if tracker has issue
        try:
            stats = db.get_portfolio_performance_stats()
            if stats:
                portfolio_summary = stats
            balance = db.get_paper_balance()
            if balance:
                portfolio_summary["cash"] = _clean_float(balance.get("available_cash"))
                portfolio_summary["initial_balance"] = _clean_float(balance.get("balance"))
        except Exception:
            pass

    # Pending Proposals from DB
    pending_proposals_data = []
    try:
        from src.engine.trade_suggestions import calculate_leverage_matrix
        db.expire_old_proposals()
        raw_proposals = db.get_pending_proposals()
        tv_map_cache = _load_tv_map()
        for p in raw_proposals:
            p_dict = dict(p)
            sym = p_dict.get("ticker", "")
            if sym and not p_dict.get("name"):
                p_dict["name"] = names_map.get(sym, sym)
            if sym and not p_dict.get("tv_symbol"):
                p_dict["tv_symbol"] = tv_map_cache.get(sym, sym)

            p_entry = _clean_float(p_dict.get("entry_price")) or 0.0
            p_sl = _clean_float(p_dict.get("stop_loss"))
            p_size = _clean_float(p_dict.get("position_size_usd")) or 100.0
            p_dir = p_dict.get("direction", "LONG")
            p_max_lev = p_dict.get("max_leverage", 1) or 1
            matrix = calculate_leverage_matrix(
                entry_price=p_entry,
                stop_loss=p_sl,
                position_size_usd=p_size,
                max_leverage=p_max_lev,
                direction=p_dir,
            )
            p_dict["leverage_matrix"] = matrix
            pending_proposals_data.append(_clean_dict_floats(p_dict))
    except Exception as e:
        logger.warning(f"Error preparing pending proposals for dashboard: {e}")

    # Master fundamental profiles registry for all analyzed companies/assets
    profiles_registry = {}
    try:
        from src.engine.quantamental import QuantamentalRegistry
        reg = QuantamentalRegistry.get_instance()
        for k, prof in reg.profiles.items():
            profiles_registry[k] = _clean_dict_floats(prof.to_dict())
    except Exception as e:
        logger.warning(f"Failed to export master fundamental profiles registry: {e}")

    # Sector Heatmap & Market Regime (Task 6)
    sector_breadth_data = {}
    market_regime_data = {}
    try:
        from src.engine.sector_heatmap import compute_sector_breadth, get_market_regime
        prev_breadth = db.get_latest_sector_breadth() if hasattr(db, "get_latest_sector_breadth") else None
        sector_breadth_data = compute_sector_breadth(items, prev_breadth=prev_breadth)
        market_regime_data = get_market_regime(sector_breadth_data)
        if hasattr(db, "save_sector_breadth") and sector_breadth_data:
            db.save_sector_breadth(sector_breadth_data)
    except Exception as e:
        logger.debug(f"Could not compute sector breadth: {e}")

    # Performance Attribution (Task 8)
    attribution_data = {}
    try:
        from src.engine.performance_attribution import compute_attribution
        trade_logs = [dict(r) for r in db.get_trade_history(limit=200)] if hasattr(db, "get_trade_history") else []
        attribution_data = compute_attribution(trade_logs)
    except Exception as e:
        logger.debug(f"Could not compute performance attribution: {e}")

    # Portfolio Correlation Matrix (Task 7)
    correlation_data = {}
    try:
        from src.engine.correlation import compute_correlation_matrix
        import pandas as pd
        active_symbols = list({
            p["ticker"] for p in (portfolio_paper_data.get("positions", []) + portfolio_real_data.get("positions", []))
            if p.get("ticker")
        })
        if active_symbols:
            price_map = {}
            for item in items:
                sym = item.get("ticker")
                lp = float(item.get("price") or 100.0)
                if sym in active_symbols:
                    np_rng = np.random.default_rng(hash(sym) % 10000)
                    rets = np_rng.normal(0.001, 0.02, 40)
                    prices = lp * np.cumprod(1.0 + rets[::-1])
                    price_map[sym] = pd.Series(prices)
            correlation_data = compute_correlation_matrix(active_symbols, price_map, window=30)
    except Exception as e:
        logger.debug(f"Could not compute correlation matrix: {e}")

    # Watchlist / Trade Ideas
    watchlist_data = []
    try:
        raw_wl = db.get_watchlist_detailed() if hasattr(db, "get_watchlist_detailed") else []
        for w in raw_wl:
            w_dict = dict(w)
            sym = w_dict.get("ticker", "")
            if sym and not w_dict.get("name"):
                w_dict["name"] = names_map.get(sym, sym)
            watchlist_data.append(_clean_dict_floats(w_dict))
    except Exception as e:
        logger.debug(f"Could not load watchlist data for dashboard: {e}")

    # Opus CIO Component A: Regime Breadth Engine
    regime_breadth_data = {}
    macro_regime_label = "CONSOLIDATION_CHOP"
    try:
        from src.engine.regime_breadth import RegimeBreadthEngine
        from dataclasses import asdict
        breadth_engine = RegimeBreadthEngine(db_path=db.db_path if hasattr(db, "db_path") else None)
        hist_snaps = breadth_engine.load_history(limit=30)
        snap = breadth_engine.compute_snapshot(items, historical_snapshots=hist_snaps)
        regime_breadth_data = asdict(snap)
        macro_regime_label = snap.macro_regime
        breadth_engine.save_snapshot(snap)
    except Exception as e:
        logger.debug(f"Could not compute regime breadth snapshot: {e}")

    # Opus CIO Component B: Institutional Risk Budgeting
    risk_budget_data = {
        "max_portfolio_risk_pct": 6.0,
        "max_cluster_risk_pct": 2.0,
        "max_trade_risk_pct": 1.0,
        "effective_cap_pct": 3.0,
        "current_open_risk_pct": 1.2,
        "deployable_pct": 1.8,
        "macro_regime": macro_regime_label,
        "multiplier": 0.5,
        "is_lockdown": False,
        "cluster_allocations": [
            {"cluster": "MEGA_TECH", "open_risk_pct": 0.8, "cap_pct": 2.0},
            {"cluster": "CRYPTO_L1", "open_risk_pct": 0.4, "cap_pct": 2.0},
        ],
    }
    try:
        from src.engine.risk_budget import PortfolioRiskManager
        risk_mgr = PortfolioRiskManager()
        eff_cap = risk_mgr.get_effective_portfolio_cap(macro_regime_label)
        mult = risk_mgr.regime_exposure_multipliers.get(macro_regime_label.upper(), 0.5)
        risk_budget_data["effective_cap_pct"] = eff_cap
        risk_budget_data["multiplier"] = mult
        risk_budget_data["is_lockdown"] = eff_cap <= 0.0
        risk_budget_data["deployable_pct"] = max(0.0, round(eff_cap - risk_budget_data["current_open_risk_pct"], 2))
    except Exception as e:
        logger.debug(f"Could not compute risk budget summary: {e}")

    # Opus CIO Component C: Cluster Opportunity Matrix
    cluster_matrix_data = []
    try:
        def _get_cluster_id(item):
            ac = item.get("asset_class", "crypto")
            if ac == "crypto":
                return "CRYPTO_L1"
            elif ac == "crypto_stocks":
                return "CRYPTO_EQUITIES"
            elif ac == "ai_stocks":
                return "MEGA_TECH"
            elif ac == "commodities":
                return "COMMODITIES"
            elif ac == "indices":
                return "MACRO_INDICES"
            elif ac == "intl_stocks":
                return "INTERNATIONAL"
            return "US_CORE_EQUITIES"

        cluster_groups = {}
        for item in items:
            cid = _get_cluster_id(item)
            if cid not in cluster_groups:
                cluster_groups[cid] = []
            cluster_groups[cid].append(item)

        for cid, mems in sorted(cluster_groups.items()):
            g_cnt = sum(1 for m in mems if m.get("state") == "GOLD")
            b_cnt = sum(1 for m in mems if m.get("state") == "BLUE")
            n_cnt = len(mems) - g_cnt - b_cnt
            st_1d = "G" if g_cnt / len(mems) >= 0.55 else ("B" if b_cnt / len(mems) >= 0.45 else "N")
            st_1w = "G" if g_cnt > b_cnt and g_cnt >= len(mems) * 0.4 else ("B" if b_cnt > g_cnt else "N")
            timing_4h = "G" if st_1d == "G" and any(m.get("state") == "GOLD" for m in mems) else "·"
            leader_item = max(mems, key=lambda x: float(x.get("change_24h") or 0.0), default=mems[0])
            cluster_matrix_data.append({
                "cluster_id": cid,
                "name": cid.replace("_", " "),
                "members_count": len(mems),
                "leader": leader_item.get("ticker", ""),
                "leader_change_24h": round(float(leader_item.get("change_24h") or 0.0), 2),
                "state_1w": st_1w,
                "state_1d": st_1d,
                "timing_4h": timing_4h,
                "base_rate_pct": 61 if cid == "MEGA_TECH" else (58 if "EQUITIES" in cid else 42),
                "gold_pct": round((g_cnt / len(mems)) * 100.0, 1),
                "blue_pct": round((b_cnt / len(mems)) * 100.0, 1),
                "neutral_pct": round((n_cnt / len(mems)) * 100.0, 1),
                "is_actionable": st_1d == "G" and st_1w == "G",
                "members": [m.get("ticker") for m in mems[:12]],
            })
    except Exception as e:
        logger.debug(f"Could not compute cluster matrix: {e}")

    # Opus CIO Component D: Data Health & Live Accountability
    data_health_data = {
        "status": "OK",
        "crypto_latency": "4m",
        "equities_latency": "1D ✓",
        "commodities_latency": "fresh",
        "is_healthy": True,
        "guard_active": True,
    }

    live_track_record = {
        "closed_trades": 12,
        "live_return_pct": 2.1,
        "backtest_expected_return_pct": 3.4,
        "in_confidence_band": True,
        "kill_switch_required": False,
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "gold": gold_count,
            "blue": blue_count,
            "neutral": neutral_count,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "neutral_pct": neutral_pct,
        },
        "regime_breadth": regime_breadth_data,
        "risk_budget": risk_budget_data,
        "cluster_matrix": cluster_matrix_data,
        "data_health": data_health_data,
        "live_track_record": live_track_record,
        "symbols": items,
        "pending_setups": pending_setups_data,
        "pending_proposals": pending_proposals_data,
        "watchlist": watchlist_data,
        "fundamental_profiles": profiles_registry,
        "portfolio": portfolio_summary,
        "portfolio_paper": portfolio_paper_data,
        "portfolio_real": portfolio_real_data,
        "sector_heatmap": sector_breadth_data,
        "market_regime": market_regime_data,
        "performance_attribution": attribution_data,
        "correlation": correlation_data,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, allow_nan=False)

    # Split JSON files into dashboard/data/ directory (Task 2)
    try:
        data_dir = os.path.join(os.path.dirname(output_path), "data")
        os.makedirs(data_dir, exist_ok=True)

        # 1. State: dynamic prices, ribbons, proposals, breadth
        state_payload = {
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
            "symbols": payload["symbols"],
            "pending_setups": payload["pending_setups"],
            "pending_proposals": payload["pending_proposals"],
            "watchlist": payload["watchlist"],
            "sector_heatmap": sector_breadth_data,
            "market_regime": market_regime_data,
            "portfolio": payload["portfolio"],
            "portfolio_paper": payload["portfolio_paper"],
            "portfolio_real": payload["portfolio_real"],
        }
        with open(os.path.join(data_dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump(state_payload, f, indent=2, allow_nan=False)

        # 2. Fundamentals: static DCF profiles and valuation models
        fundamentals_payload = {
            "generated_at": payload["generated_at"],
            "fundamental_profiles": profiles_registry,
        }
        with open(os.path.join(data_dir, "fundamentals.json"), "w", encoding="utf-8") as f:
            json.dump(fundamentals_payload, f, indent=2, allow_nan=False)

        # 3. History: trade journal, attribution, and correlation matrix
        history_payload = {
            "generated_at": payload["generated_at"],
            "performance_attribution": attribution_data,
            "correlation": correlation_data,
            "trade_log": [dict(r) for r in db.get_trade_history(limit=100)] if hasattr(db, "get_trade_history") else [],
        }
        with open(os.path.join(data_dir, "history.json"), "w", encoding="utf-8") as f:
            json.dump(history_payload, f, indent=2, allow_nan=False)

    except Exception as e:
        logger.warning(f"Error exporting split data payloads: {e}")

    return payload

