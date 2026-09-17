"""
Interactive Telegram Bot Command Listener.
Listens for incoming commands (/status, /gold, /blue, /help) via long-polling (getUpdates)
and replies with instant market summaries and asset lists.
Requires no open ports, webhooks, or public IP.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Optional
import requests

from src.alerts.formatter import get_tradingview_link
from src.alerts.telegram import TelegramNotifier
from src.storage.database import Database

logger = logging.getLogger(__name__)


def normalize_timeframe(tf: Optional[str]) -> Optional[str]:
    if not tf:
        return None
    cleaned = tf.upper().strip()
    if cleaned in ["1D", "D", "DAILY"]:
        return "1D"
    elif cleaned in ["4H", "4"]:
        return "4H"
    elif cleaned in ["1W", "W", "WEEKLY"]:
        return "1W"
    return None


class TelegramCommandListener:
    def __init__(
        self,
        notifier: Optional[TelegramNotifier] = None,
        db: Optional[Database] = None,
        paper_trader=None,
        config: Optional[dict] = None,
    ):
        self.notifier = notifier or TelegramNotifier()
        self.db = db or Database()
        self.config = config or {}
        if paper_trader is not None:
            self.paper_trader = paper_trader
        else:
            from src.trading.paper_trader import PaperTrader
            self.paper_trader = PaperTrader(db=self.db, notifier=self.notifier, config=self.config)
        self.last_update_id = 0
        self.session = requests.Session()
        self.running = False

    def handle_status(self, timeframe: Optional[str] = None) -> str:
        """Generates overview summary message, optionally filtered by timeframe."""
        states = self.db.get_all_states()
        if not states:
            return "📊 Няма записани активи в базата данни."

        norm_tf = normalize_timeframe(timeframe)
        if norm_tf:
            states = [s for s in states if s["timeframe"] == norm_tf]
            tf_badge = f" [{norm_tf}]"
        else:
            tf_badge = ""

        if not states:
            return f"📊 Няма намерени активи за таймфрейм <b>{timeframe}</b>."

        total = len(states)
        gold = [s for s in states if s["current_state"] == "GOLD"]
        blue = [s for s in states if s["current_state"] == "BLUE"]
        neutral = [s for s in states if s["current_state"] == "NEUTRAL"]

        gold_pct = round(len(gold) / total * 100, 1) if total > 0 else 0.0
        blue_pct = round(len(blue) / total * 100, 1) if total > 0 else 0.0
        neutral_pct = round(len(neutral) / total * 100, 1) if total > 0 else 0.0

        msg = (
            f"📊 <b>Larsson Line Пазарен Баланс{tf_badge}</b>\n\n"
            f"• Общо наблюдавани: <b>{total}</b>\n"
            f"• 🟡 <b>Gold (Бичи):</b> {len(gold)} ({gold_pct}%)\n"
            f"• 🔵 <b>Blue (Мечи):</b> {len(blue)} ({blue_pct}%)\n"
            f"• ⚪ <b>Neutral:</b> {len(neutral)} ({neutral_pct}%)\n\n"
            f"<i>За списък на активните инструменти: /gold или /blue</i>"
        )
        return msg

    def handle_state_list(self, target_state: str, emoji: str, timeframe: Optional[str] = None) -> str:
        """Generates list of symbols in a given state, optionally filtered by timeframe."""
        states = self.db.get_all_states()
        norm_tf = normalize_timeframe(timeframe)
        if norm_tf:
            matches = [s for s in states if s["current_state"] == target_state and s["timeframe"] == norm_tf]
            tf_badge = f" [{norm_tf}]"
        else:
            matches = [s for s in states if s["current_state"] == target_state]
            tf_badge = ""

        if not matches:
            return f"{emoji} В момента няма активи в състояние <b>{target_state}</b>{tf_badge}."

        header = f"{emoji} <b>Активи в състояние {target_state}{tf_badge} ({len(matches)}):</b>\n\n"
        lines = []
        # Group or list top 25
        for s in matches[:25]:
            ticker = s["ticker"]
            tf = s["timeframe"]
            price = s["last_price"]
            tv_sym = s["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)

            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): <code>{p_str}</code>")

        body = "\n".join(lines)
        if len(matches) > 25:
            body += f"\n\n<i>... и още {len(matches) - 25} инструмента. Виж всички в уеб дашборда: http://localhost:8080</i>"

        return header + body

    def handle_watch(self, ticker: str) -> str:
        """Adds symbol to watchlist."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/watch NVDA</code> или <code>/watch BTCUSDT</code>"
        ticker = ticker.upper()
        added = self.db.add_to_watchlist(ticker)
        if added:
            return f"✅ Добавен <b>{ticker}</b> към твоя личен Watchlist!"
        else:
            return f"ℹ️ <b>{ticker}</b> вече е в твоя Watchlist."

    def handle_unwatch(self, ticker: str) -> str:
        """Removes symbol from watchlist."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/unwatch NVDA</code>"
        ticker = ticker.upper()
        removed = self.db.remove_from_watchlist(ticker)
        if removed:
            return f"🗑️ Премахнат <b>{ticker}</b> от твоя Watchlist."
        else:
            return f"ℹ️ <b>{ticker}</b> не беше намерен в твоя Watchlist."

    def handle_watchlist(self) -> str:
        """Displays all symbols in personal watchlist."""
        rows = self.db.get_watchlist_states()
        tickers = self.db.get_watchlist()
        if not tickers:
            return "📋 Твоят Watchlist е празен. Добави символ с: <code>/watch AAPL</code>"

        header = f"⭐ <b>Твоят Watchlist ({len(tickers)} актива):</b>\n\n"
        if not rows:
            return header + f"Активи: {', '.join(tickers)}\n<i>(Ще се обновят при следващото сканиране)</i>"

        lines = []
        for s in rows:
            ticker = s["ticker"]
            tf = s["timeframe"]
            state = s["current_state"]
            price = s["last_price"]
            tv_sym = s["tv_symbol"]
            url = get_tradingview_link(tv_sym, tf)

            emoji = "🟡" if state == "GOLD" else ("🔵" if state == "BLUE" else "⚪")
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): {emoji} <b>{state}</b> @ <code>{p_str}</code>")

        return header + "\n".join(lines)

    def handle_analyze(self, ticker: str, timeframe: Optional[str] = None) -> str:
        """Generates comprehensive Quantamental & Technical analysis card for a ticker."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/a NVDA</code> или <code>/analyze BTCUSDT</code>"

        clean_ticker = ticker.upper().split(":")[-1].strip()
        norm_tf = normalize_timeframe(timeframe)

        # Query states from DB
        states = [dict(r) for r in self.db.get_all_states()]
        matching = [s for s in states if s["ticker"].upper() == clean_ticker]

        if not matching:
            return f"🔍 Символът <b>{clean_ticker}</b> не е намерен в текущата база данни. Уверете се, че е сканиран или добавен в конфигурацията."

        # Select timeframe: prefer requested, then 1D, then 4H, then first
        selected = None
        if norm_tf:
            selected = next((s for s in matching if s["timeframe"] == norm_tf), None)
        if not selected:
            selected = next((s for s in matching if s["timeframe"] == "1D"), matching[0])

        tf = selected["timeframe"]
        price = selected["last_price"]
        state = selected["current_state"]
        emoji = "🟡" if state == "GOLD" else ("🔵" if state == "BLUE" else "⚪")
        tv_sym = selected["tv_symbol"]
        url = get_tradingview_link(tv_sym, tf)

        v1 = selected.get("v1", 0.0)
        v2 = selected.get("v2", 0.0)
        spread_pct = round(((v1 - v2) / v2) * 100, 2) if v2 > 0 else 0.0
        spread_sign = "+" if spread_pct > 0 else ""

        p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")

        # 1. 📐 ТЕХНИЧЕСКИ АНАЛИЗ (Larsson Ribbon & S/R)
        tech_label = selected.get("ts_tech_label_bg")
        if not tech_label:
            tech_label = f"🟢 {state} Бичи Тренд" if state == "GOLD" else (f"🔴 {state} Мечи Тренд" if state == "BLUE" else "⚪ Консолидация")
        tech_thesis = selected.get("ts_tech_thesis_bg") or ("Възходящо разширяване на лентата." if state == "GOLD" else ("Низходящо разширяване на лентата." if state == "BLUE" else "Панделката е сплескана без ясен тренд."))

        s1 = selected.get("s1")
        r1 = selected.get("r1")
        s1_touches = selected.get("s1_touches", 0)
        r1_touches = selected.get("r1_touches", 0)
        s1_dist = selected.get("s1_dist_pct")
        r1_dist = selected.get("r1_dist_pct")

        s1_str = (f"${s1:,.2f}" if s1 >= 1 else f"${s1:.5f}") if s1 is not None else None
        dist_txt_s1 = f" (-{s1_dist}%)" if s1_dist is not None else ""
        r1_str = (f"${r1:,.2f}" if r1 >= 1 else f"${r1:.5f}") if r1 is not None else None
        dist_txt_r1 = f" (+{r1_dist}%)" if r1_dist is not None else ""

        tech_block = (
            f"\n📐 <b>ТЕХНИЧЕСКИ АНАЛИЗ (Larsson Ribbon):</b>\n"
            f"• Сигнал: <b>{tech_label}</b>\n"
            f"• Лента: {emoji} <b>{state}</b> (Spread: <code>{spread_sign}{spread_pct}%</code>)\n"
        )
        if s1 is not None:
            tech_block += f"• 🟢 Подкрепа S1: <b>{s1_str}</b>{dist_txt_s1} [{s1_touches} теста]\n"
        if r1 is not None:
            tech_block += f"• 🔴 Съпротива R1: <b>{r1_str}</b>{dist_txt_r1} [{r1_touches} теста]\n"
        tech_block += f"• Теза: <i>{tech_thesis}</i>\n"

        # 2. 🏢 ФУНДАМЕНТАЛЕН АНАЛИЗ (DCF & Valuation)
        is_crypto = (selected.get("asset_class") == "crypto") or clean_ticker.endswith("USDT")
        try:
            from src.engine.quantamental import get_fundamental_profile
            fund = get_fundamental_profile(clean_ticker)
        except Exception:
            fund = None

        fund_label = selected.get("ts_fund_label_bg")
        fund_thesis = selected.get("ts_fund_thesis_bg")
        if not fund_label:
            if fund:
                fund_label = f"🟢 {fund.verdict}"
                fund_thesis = fund.thesis
            elif is_crypto:
                fund_label = "⚪ МАКРО / СПЕКУЛАТИВЕН"
                fund_thesis = "Крипто актив без DCF модел. Движи се от ликвидност и мрежови ефекти."
            else:
                fund_label = "⚪ Неоценен"
                fund_thesis = "Няма наличен фундаментален DCF модел."

        fund_block = f"\n🏢 <b>ФУНДАМЕНТАЛЕН АНАЛИЗ (DCF & Valuation):</b>\n• Оценка: <b>{fund_label}</b>\n"
        if fund and fund.fair_value is not None:
            upside_str = f" (+{round(fund.upside_pct)}%)" if fund.upside_pct is not None else ""
            fund_block += f"• DCF Справедлива стойност: <b>${fund.fair_value:,.2f}</b>{upside_str} (MoS: {fund.mos_pct:.0f}%)\n"
            if fund.moat:
                fund_block += f"• Икономически ров: <b>{fund.moat}</b> | Z-Score: <b>{fund.z_score:.2f}</b>\n"
        elif selected.get("ts_fair_value") or (selected.get("ts_fund_verdict") and selected.get("ts_fund_verdict") != "SPECULATIVE_NA"):
            fv = selected.get("ts_fair_value")
            fv_str = f"${fv:,.2f}" if fv else "N/A"
            fund_block += f"• DCF Справедлива стойност: <b>{fv_str}</b> | Ров: <b>{selected.get('ts_moat', 'None')}</b>\n"
        if fund_thesis:
            fund_block += f"• Теза: <i>{fund_thesis}</i>\n"

        # 3. 🎯 СИНТЕЗИРАНА СТРАТЕГИЯ (Quantamental Confluence)
        action = selected.get("ts_action", "WAIT")
        tier = selected.get("ts_tier", "NONE")
        score = selected.get("ts_score", 0)
        setup_type = selected.get("ts_setup_type", "WAIT_FOR_SETUP")
        entry = selected.get("ts_entry")
        sl = selected.get("ts_sl")
        tp1 = selected.get("ts_tp1")
        tp2 = selected.get("ts_tp2")
        rr = selected.get("ts_rr")
        reason_bg = selected.get("ts_reason_bg", "")

        synth_badge = selected.get("ts_synthesis_badge_bg")
        if not synth_badge:
            synth_badge = f"⭐ {action}" if action != "WAIT" else "⏳ WAIT"

        synth_block = f"\n🎯 <b>СИНТЕЗИРАНА СТРАТЕГИЯ (Quantamental):</b>\n• Статус: <b>{synth_badge}</b>\n"
        if action != "WAIT":
            entry_str = f"${entry:,.2f}" if entry and entry >= 1 else (f"${entry:.5f}" if entry else "N/A")
            sl_str = f"${sl:,.2f}" if sl and sl >= 1 else (f"${sl:.5f}" if sl else "N/A")
            tp1_str = f"${tp1:,.2f}" if tp1 and tp1 >= 1 else (f"${tp1:.5f}" if tp1 else "N/A")
            tp2_str = f"${tp2:,.2f}" if tp2 and tp2 >= 1 else (f"${tp2:.5f}" if tp2 else "N/A")
            rr_str = f"1 : {rr}" if rr else "N/A"
            synth_block += (
                f"• Ранг: <b>⭐ Tier {tier}</b> (Score: {score}/100 | R:R: <b>{rr_str}</b>)\n"
                f"• Вход: <code>{entry_str}</code> | SL: <code>{sl_str}</code>\n"
                f"• TP1: <code>{tp1_str}</code>" + (f" | TP2: <code>{tp2_str}</code>\n" if tp2 else "\n")
            )
            if s1 and entry and s1 < entry:
                synth_block += f"• 🧱 <b>DCA Натрупване:</b> 50% пазарен вход + 50% лимит на S1 (${s1:,.2f})\n"
        else:
            if setup_type == "VALUE_TRAP_WARNING":
                synth_block += "• Предупреждение: ⏳ <b>VALUE TRAP RISK</b> (Подценен фундамент, но мечи тренд. Изчакай GOLD!)\n"
            else:
                synth_block += "• Препоръка: ⏳ <b>Изчакай</b> по-благоприятна консолидация или тест на ключова подкрепа.\n"

        if reason_bg:
            synth_block += f"• Обосновка: <i>{reason_bg}</i>\n"

        header = f"📊 <b>Анализ на {clean_ticker} [{tf}]</b>\n"
        header += f"💵 Цена: <code>{p_str}</code>\n━━━━━━━━━━━━━━━━━━━━\n"
        tv_footer = f"\n━━━━━━━━━━━━━━━━━━━━\n🔗 <a href=\"{url}\">Отвори интерактивната графика в TradingView ↗</a>"

        return header + tech_block + fund_block + synth_block + tv_footer

    def handle_alpha(self, timeframe: Optional[str] = None) -> str:
        """Lists active high-conviction Tier A+ and Tier A institutional setups separated into Crypto & Equities."""
        states = [dict(r) for r in self.db.get_all_states()]
        norm_tf = normalize_timeframe(timeframe)
        if norm_tf:
            states = [s for s in states if s["timeframe"] == norm_tf]
            tf_badge = f" [{norm_tf}]"
        else:
            tf_badge = ""

        # Filter active BUY setups with Tier A+ or A, or QUANTAMENTAL_ALPHA_BUY
        matches = [
            s for s in states
            if s.get("ts_action") == "SPOT_BUY" and (s.get("ts_tier") in ["A+", "A"] or s.get("ts_setup_type") == "QUANTAMENTAL_ALPHA_BUY")
        ]

        if not matches:
            return f"💎 В момента няма намерени активни <b>Institutional Alpha (Tier A/A+)</b> входове{tf_badge}."

        crypto_matches = [
            s for s in matches
            if s.get("asset_class") == "crypto" or s.get("ticker", "").endswith("USDT")
        ]
        equity_matches = [s for s in matches if s not in crypto_matches]

        header = f"💎 <b>Институционални Alpha Входове (Tier A / A+){tf_badge} ({len(matches)}):</b>\n"
        sections = [header]

        if crypto_matches:
            crypto_lines = [f"\n🪙 <b>Крипто Сетъпи ({len(crypto_matches)}):</b>"]
            for s in crypto_matches[:15]:
                ticker = s["ticker"]
                tf = s["timeframe"]
                tier = s.get("ts_tier", "A")
                score = s.get("ts_score", 0)
                entry = s.get("ts_entry", s["last_price"])
                rr = s.get("ts_rr")
                url = get_tradingview_link(s["tv_symbol"], tf)
                rr_txt = f" | R:R 1:{rr}" if rr else ""
                crypto_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): 🪙 <b>Tier {tier}</b> ({score}/100) @ <code>${entry:,.2f}</code>{rr_txt}")
            sections.append("\n".join(crypto_lines))

        if equity_matches:
            eq_lines = [f"\n🏛️ <b>Акции & Суровини ({len(equity_matches)}):</b>"]
            for s in equity_matches[:15]:
                ticker = s["ticker"]
                tf = s["timeframe"]
                tier = s.get("ts_tier", "A")
                score = s.get("ts_score", 0)
                entry = s.get("ts_entry", s["last_price"])
                rr = s.get("ts_rr")
                moat = s.get("ts_moat", "")
                moat_tag = f" [💎 {moat} Moat]" if moat and moat != "None" else ""
                url = get_tradingview_link(s["tv_symbol"], tf)
                rr_txt = f" | R:R 1:{rr}" if rr else ""
                eq_lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): 🏛️ <b>Tier {tier}</b>{moat_tag} ({score}/100) @ <code>${entry:,.2f}</code>{rr_txt}")
            sections.append("\n".join(eq_lines))

        if len(matches) > 30:
            sections.append(f"\n<i>... и още {len(matches) - 30} инструмента в уеб таблото.</i>")

        return "\n".join(sections)

    def handle_traps(self) -> str:
        """Lists assets currently flagged as Value Trap Risk."""
        states = [dict(r) for r in self.db.get_all_states()]
        traps = [
            s for s in states
            if s.get("ts_setup_type") == "VALUE_TRAP_WARNING" or s.get("ts_quantamental_tag") == "VALUE_TRAP_RISK"
        ]

        if not traps:
            return "✅ В момента няма активи, маркирани като <b>Валуационен Капан</b>."

        header = f"⏳ <b>Предупреждения за Валуационни Капани ({len(traps)}):</b>\n"
        header += "<i>(Фундаментално подценени, но в низходящ тренд – НЕ купувайте преди GOLD обръщане!)</i>\n\n"
        lines = []
        for s in traps[:20]:
            ticker = s["ticker"]
            tf = s["timeframe"]
            price = s["last_price"]
            fv = s.get("ts_fair_value")
            fv_txt = f" | DCF Fair Value: <b>${fv:,.2f}</b>" if fv else ""
            url = get_tradingview_link(s["tv_symbol"], tf)
            lines.append(f"• <a href=\"{url}\"><b>{ticker}</b></a> ({tf}): <code>${price:,.2f}</code>{fv_txt}")

        return header + "\n".join(lines)

    def handle_calc(self, args: list) -> str:
        """
        Calculates position size based on risk-per-trade.
        Usage: /calc [ticker] [capital] [risk_pct]
        """
        if not args:
            return "⚠️ Употреба: <code>/calc [тикер] [капитал] [риск_%]</code>\nПример: <code>/calc NVDA 10000 1</code> (риск 1% при $10,000 капитал)"

        ticker = args[0].upper().split(":")[-1].strip()
        capital = float(args[1]) if len(args) > 1 else 10000.0
        risk_pct = float(args[2]) if len(args) > 2 else 1.0

        states = [dict(r) for r in self.db.get_all_states()]
        matching = [s for s in states if s["ticker"].upper() == ticker]
        if not matching:
            return f"🔍 Символът <b>{ticker}</b> не е намерен в базата данни."

        selected = next((s for s in matching if s["timeframe"] == "1D"), matching[0])
        entry = selected.get("ts_entry") or selected["last_price"]
        sl = selected.get("ts_sl")
        tp1 = selected.get("ts_tp1")
        tp2 = selected.get("ts_tp2")

        if not sl or sl >= entry:
            sl = round(entry * 0.95, 4)

        from src.engine.trade_suggestions import calculate_position_size
        calc = calculate_position_size(
            entry_price=entry,
            stop_loss=sl,
            account_size=capital,
            risk_pct=risk_pct,
            tp1=tp1,
            tp2=tp2,
        )

        is_crypto = (selected.get("asset_class") == "crypto") or ticker.endswith("USDT")
        type_str = "🪙 Крипто актив" if is_crypto else "🏛️ Акция / Суровина"
        units_label = "бр. монети" if is_crypto else "бр. акции"

        p1_txt = f"\n• Очаквана печалба при TP1: <b>+${calc['profit_tp1_usd']:,.2f}</b>" if calc['profit_tp1_usd'] else ""
        p2_txt = f"\n• Очаквана печалба при TP2: <b>+${calc['profit_tp2_usd']:,.2f}</b>" if calc['profit_tp2_usd'] else ""

        msg = (
            f"🧮 <b>Калкулатор за Размер на Позицията: {ticker} [{type_str}]</b>\n\n"
            f"• Капитал: <b>${capital:,.2f}</b> | Риск на сделка: <b>{risk_pct:.1f}%</b> (${calc['risk_usd']:,.2f})\n"
            f"• Вход: <code>${entry:,.2f}</code> | Стоп-лос (SL): <code>${sl:,.2f}</code> (-{calc['risk_pct_price']}%)\n\n"
            f"👉 <b>Препоръчителен брой: <code>{calc['units']}</code> {units_label}</b>\n"
            f"• Стойност на позицията: <b>${calc['position_value']:,.2f}</b> (от общо ${capital:,.2f})\n"
            f"• Максимална загуба при удряне на SL: <b>-${calc['risk_usd']:,.2f}</b>{p1_txt}{p2_txt}"
        )
        if selected.get("s1") and entry and selected["s1"] < entry:
            msg += f"\n\n🧱 <b>DCA Натрупване:</b> 50% пазарно (${entry:,.2f}) + 50% лимит на S1 (${selected['s1']:,.2f})"

        return msg

    def handle_digest(self) -> str:
        """Generates the full daily market digest."""
        from src.alerts.digest import generate_digest_data
        digest = generate_digest_data(self.db)
        return digest["message"]

    def handle_help(self) -> str:
        return (
            "🤖 <b>Larsson Line Бот Команди:</b>\n\n"
            "<b>Пазарни Справки:</b>\n"
            "/status [4h|1d|1w] - Общ пазарен баланс (Gold/Blue съотношение)\n"
            "/digest - Изпраща подробен бюлетин (топ трендове, Ribbon Spread, 24ч промени)\n"
            "/gold [4h|1d|1w] - Списък на всички бичи активи (Gold 🟡)\n"
            "/blue [4h|1d|1w] - Списък на всички мечи активи (Blue 🔵)\n\n"
            "<b>Институционални Анализи & Сигнали:</b>\n"
            "/analyze [символ] (или /a) - Пълен фундаментален + технически анализ на актив (напр. /a NVDA или /a BTC)\n"
            "/alpha [4h|1d|1w] (или /setups) - Топ институционални Alpha входове (Tier A / A+)\n"
            "/traps - Предупреждения за валуационни капани (подценени, но в низходящ тренд)\n"
            "/calc [символ] [капитал] [риск_%] - Калкулатор за точен размер на позицията\n\n"
            "<b>Личен Watchlist:</b>\n"
            "/watchlist - Показва активите в твоя личен списък ⭐\n"
            "/watch [символ] - Добавя актив в Watchlist (напр. /watch NVDA)\n"
            "/unwatch [символ] - Премахва актив от Watchlist\n\n"
            "<b>📈 Симулирана Spot Търговия (Paper Trading):</b>\n"
            "/portfolio (или /positions) - Виртуален баланс, активни позиции и PnL\n"
            "/trades (или /history) - История на приключилите сделки и Win Rate\n"
            "/close [тикер] - Ръчно затваряне на активна позиция (напр. /close SOLUSDT)\n\n"
            "/help - Показва това съобщение"
        )

    def process_callback_query(self, cq: dict):
        """Handles inline keyboard button callbacks for trade proposals."""
        cq_id = cq.get("id")
        from_user = cq.get("from", {})
        user_id = str(from_user.get("id", ""))
        message = cq.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        authorized_chat = str(self.notifier.chat_id)
        if user_id != authorized_chat and chat_id != authorized_chat:
            logger.warning(f"Unauthorized callback query from user {user_id} (expected {authorized_chat})")
            self.notifier.answer_callback_query(
                cq_id,
                text="⚠️ Нямате права за потвърждаване на сделки!",
                show_alert=True,
            )
            return

        data = cq.get("data", "")
        logger.info(f"Received Telegram callback_query: {data} from {user_id}")

        if data.startswith("trade:approve:"):
            proposal_id = data[len("trade:approve:"):]
            res = self.paper_trader.approve_proposal(proposal_id, chat_id=chat_id)
            if res.get("success"):
                self.notifier.answer_callback_query(
                    cq_id,
                    text=f"✅ Покупката на {res.get('ticker')} е потвърдена в симулатора!",
                    show_alert=False,
                )
            else:
                self.notifier.answer_callback_query(
                    cq_id,
                    text=f"⚠️ {res.get('error', 'Грешка при одобрение')}",
                    show_alert=True,
                )
        elif data.startswith("trade:reject:"):
            proposal_id = data[len("trade:reject:"):]
            res = self.paper_trader.reject_proposal(proposal_id, chat_id=chat_id)
            if res.get("success"):
                self.notifier.answer_callback_query(
                    cq_id,
                    text=f"❌ Предложението за {res.get('ticker')} е отхвърлено.",
                    show_alert=False,
                )
            else:
                self.notifier.answer_callback_query(
                    cq_id,
                    text=f"⚠️ {res.get('error', 'Грешка при отказ')}",
                    show_alert=True,
                )
        else:
            self.notifier.answer_callback_query(cq_id, text="Неизвестно действие.")

    def process_update(self, update: dict):
        """Processes a single incoming message or callback query from Telegram."""
        callback_query = update.get("callback_query")
        if callback_query:
            self.process_callback_query(callback_query)
            return

        message = update.get("message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        # Only allow authorized user to interact
        if chat_id != str(self.notifier.chat_id):
            logger.warning(f"Ignored message from unauthorized chat_id: {chat_id}")
            return

        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"Received Telegram command: {text}")
        parts = text.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/status":
            reply = self.handle_status(arg)
        elif cmd == "/digest":
            reply = self.handle_digest()
        elif cmd == "/gold":
            reply = self.handle_state_list("GOLD", "🟡", arg)
        elif cmd == "/blue":
            reply = self.handle_state_list("BLUE", "🔵", arg)
        elif cmd in ["/analyze", "/a", "/ticker"]:
            reply = self.handle_analyze(arg, parts[2] if len(parts) > 2 else None)
        elif cmd in ["/alpha", "/setups"]:
            reply = self.handle_alpha(arg)
        elif cmd == "/traps":
            reply = self.handle_traps()
        elif cmd == "/calc":
            reply = self.handle_calc(parts[1:])
        elif cmd in ["/portfolio", "/positions"]:
            reply = self.paper_trader.get_portfolio_summary()
        elif cmd in ["/trades", "/history"]:
            reply = self.paper_trader.get_trade_history_summary()
        elif cmd == "/close":
            if not arg:
                reply = "⚠️ Моля посочи тикер за затваряне. Пример: <code>/close SOLUSDT</code>"
            else:
                ok, msg = self.paper_trader.close_manually(arg)
                reply = msg
        elif cmd == "/watchlist":
            reply = self.handle_watchlist()
        elif cmd == "/watch":
            reply = self.handle_watch(arg)
        elif cmd == "/unwatch":
            reply = self.handle_unwatch(arg)
        elif cmd in ["/start", "/help"]:
            reply = self.handle_help()
        else:
            reply = "Непозната команда. Напиши /help за списък с наличните команди."

        self.notifier.send_raw_message(reply)

    def run_poll_loop(self):
        """Continuously polls for Telegram updates."""
        if not self.notifier.is_configured:
            logger.warning("Telegram not configured. Command listener stopped.")
            return

        self.running = True
        logger.info("Telegram Command Listener polling loop started.")
        url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getUpdates"

        while self.running:
            try:
                params = {"timeout": 20, "offset": self.last_update_id + 1}
                resp = self.session.get(url, params=params, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        self.process_update(update)
                else:
                    logger.warning(f"Telegram polling error {resp.status_code}: {resp.text}")
                    time.sleep(2)
            except requests.exceptions.Timeout:
                # Normal timeout from long-polling
                continue
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(3)
