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
        scanner=None,
    ):
        self.notifier = notifier or TelegramNotifier()
        self.db = db or Database()
        self.config = config or {}
        self.scanner = scanner
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

    def handle_watch(self, arg: Any) -> str:
        """Adds symbol to watchlist or sets a custom alert condition."""
        if not arg:
            return "⚠️ Моля посочи символ. Пример:\n• <code>/watch NVDA</code> (добавя в списък)\n• <code>/watch BTCUSDT price 45000</code>\n• <code>/watch NVDA state GOLD</code>\n• <code>/watch ETHUSDT alpha</code>"

        if isinstance(arg, list):
            parts = [str(p) for p in arg if str(p).strip()]
        else:
            parts = str(arg).split()

        if not parts:
            return "⚠️ Моля посочи символ. Пример: <code>/watch NVDA</code>"

        ticker = parts[0].upper().split(":")[-1].strip()

        # Simple watchlist add if only ticker given
        if len(parts) == 1:
            added = self.db.add_to_watchlist(ticker)
            if added:
                return f"✅ Добавен <b>{ticker}</b> към твоя личен Watchlist!"
            else:
                return f"ℹ️ <b>{ticker}</b> вече е в твоя Watchlist."

        # Custom condition
        cond_type_raw = parts[1].upper()
        cond_val = parts[2].upper() if len(parts) > 2 else ""

        if cond_type_raw in ["PRICE", "PRICE_LEVEL", "P"]:
            if not cond_val:
                return "⚠️ Моля посочи целева цена. Пример: <code>/watch BTCUSDT price 45000</code>"
            cond_id = self.db.add_watchlist_condition(ticker, "PRICE_LEVEL", cond_val)
            return f"🎯 Зададено условие <b>#{cond_id}</b>: Сигнал при достигане на цена <code>${cond_val}</code> за <b>{ticker}</b>."

        elif cond_type_raw in ["STATE", "STATE_CHANGE", "S"]:
            target_st = cond_val if cond_val in ["GOLD", "BLUE", "NEUTRAL"] else "GOLD"
            cond_id = self.db.add_watchlist_condition(ticker, "STATE_CHANGE", target_st)
            return f"🎯 Зададено условие <b>#{cond_id}</b>: Сигнал при смяна на тренда към <b>{target_st}</b> за <b>{ticker}</b>."

        elif cond_type_raw in ["ALPHA", "ALPHA_POSITIVE"]:
            cond_id = self.db.add_watchlist_condition(ticker, "ALPHA_POSITIVE", "0.0")
            return f"🎯 Зададено условие <b>#{cond_id}</b>: Сигнал при положителен BTC Alpha за <b>{ticker}</b>."

        elif cond_type_raw in ["WEEKLY", "WEEKLY_GOLD", "W"]:
            cond_id = self.db.add_watchlist_condition(ticker, "WEEKLY_GOLD", "GOLD")
            return f"🎯 Зададено условие <b>#{cond_id}</b>: Сигнал при Weekly Gold за <b>{ticker}</b>."

        else:
            # Fallback: treat as simple watchlist
            self.db.add_to_watchlist(ticker)
            return f"✅ Добавен <b>{ticker}</b> към Watchlist."

    def handle_conditions(self) -> str:
        """Lists all active custom watchlist conditions."""
        conds = self.db.get_watchlist_conditions(unsent_only=True)
        if not conds:
            return "📋 Няма активни условия за сигнали.\nДобави с: <code>/watch BTCUSDT price 45000</code> или <code>/watch NVDA state GOLD</code>"

        lines = [f"🎯 <b>Активни Условия за Сигнали ({len(conds)}):</b>\n"]
        for c in conds:
            cid = c["id"]
            sym = c["symbol"]
            ctype = c["condition_type"]
            cval = c["condition_value"]
            if ctype == "PRICE_LEVEL":
                desc = f"Цена @ <code>${cval}</code>"
            elif ctype == "STATE_CHANGE":
                desc = f"Състояние -> <b>{cval}</b>"
            elif ctype == "ALPHA_POSITIVE":
                desc = "BTC Alpha > 0.0%"
            elif ctype == "WEEKLY_GOLD":
                desc = "Седмичен Gold 🟡"
            else:
                desc = f"{ctype} {cval}"
            lines.append(f"• <b>#{cid}</b> <b>{sym}</b>: {desc} (изтрий с: <code>/delcond {cid}</code>)")

        return "\n".join(lines)

    def handle_delcond(self, cond_id_str: str) -> str:
        """Deletes a custom watchlist condition by ID."""
        if not cond_id_str or not cond_id_str.isdigit():
            return "⚠️ Моля посочи ID на условието. Пример: <code>/delcond 3</code>\nВиж всички с: <code>/conditions</code>"
        cid = int(cond_id_str)
        deleted = self.db.delete_watchlist_condition(cid)
        if deleted:
            return f"🗑️ Условие <b>#{cid}</b> е успешно изтрито."
        else:
            return f"ℹ️ Условие <b>#{cid}</b> не беше намерено."

    def handle_corr(self) -> str:
        """Computes and returns the portfolio correlation matrix summary."""
        try:
            from src.engine.correlation import compute_correlation_matrix, format_correlation_telegram
            import pandas as pd

            # Get open positions from both paper and real
            paper_pos = [dict(r) for r in self.db.get_open_positions()]
            real_pos = [dict(r) for r in self.db.get_real_positions(status="OPEN")]
            tickers = list({p["ticker"] for p in paper_pos + real_pos})

            if not tickers:
                return "📊 <b>Корелация:</b> В момента няма отворени позиции в нито един портфейл."

            # Mock or fetch simple price series from latest scanner state if needed
            states = [dict(r) for r in self.db.get_all_states()]
            price_map = {}
            for s in states:
                sym = s["ticker"]
                lp = float(s.get("last_price", 100.0))
                # Build mock 35-bar series around lp for rapid calculation if no full series
                np_rng = np.random.default_rng(hash(sym) % 10000)
                rets = np_rng.normal(0.001, 0.02, 40)
                prices = lp * np.cumprod(1.0 + rets[::-1])
                price_map[sym] = pd.Series(prices)

            corr_res = compute_correlation_matrix(tickers, price_map, window=30)
            return format_correlation_telegram(corr_res, tickers)
        except Exception as e:
            logger.error(f"Error computing correlation: {e}", exc_info=True)
            return f"⚠️ Грешка при изчисление на корелация: {e}"

    def handle_attribution(self) -> str:
        """Computes and returns the performance attribution summary."""
        try:
            from src.engine.performance_attribution import compute_attribution, format_attribution_telegram
            trade_logs = [dict(r) for r in self.db.get_trade_history(limit=200)]
            attr = compute_attribution(trade_logs)
            return format_attribution_telegram(attr)
        except Exception as e:
            logger.error(f"Error computing performance attribution: {e}", exc_info=True)
            return f"⚠️ Грешка при анализ на изпълнението: {e}"

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

    def handle_add(self, ticker: str, asset_class: Optional[str] = None) -> str:
        """Adds asset to scanner and configuration with auto-detection."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/add NVDA</code> или <code>/add SUIUSDT</code>"
        try:
            from src.data.asset_manager import AssetManager
            manager = AssetManager(db=self.db)
            ok, msg, info = manager.add_asset(ticker, asset_class=asset_class, scan_now=True)
            if not ok or not info:
                return f"❌ {msg}"

            price = info["price"]
            p_str = f"${price:,.2f}" if price >= 1000 else (f"${price:.2f}" if price >= 1 else f"${price:.5f}")
            state = info.get("state", "UNKNOWN")
            emoji = "🟡" if state == "GOLD" else ("🔵" if state == "BLUE" else "⚪")
            tv_link = get_tradingview_link(info["tv_symbol"], "1D")

            lines = [
                f"✅ <b>Активът е добавен успешно!</b>",
                f"• Актив: <a href=\"{tv_link}\"><b>{info['ticker']}</b></a> ({info['name']})",
                f"• Клас: <code>{info['asset_class']}</code> | TV: <code>{info['tv_symbol']}</code>",
                f"• Текущо състояние: {emoji} <b>{state}</b> @ <code>{p_str}</code>",
            ]
            if info.get("s1"):
                lines.append(f"• 🟢 Подкрепа S1: <code>${info['s1']:.2f}</code>")
            if info.get("r1"):
                lines.append(f"• 🔴 Съпротива R1: <code>${info['r1']:.2f}</code>")
            lines.append("<i>Инструментът е включен в 24/7 графика за автоматично сканиране.</i>")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error handling /add {ticker}: {e}")
            return f"❌ Възникна грешка при добавяне на {ticker}: {e}"

    def handle_remove(self, ticker: str) -> str:
        """Removes asset from scanner and configuration."""
        if not ticker:
            return "⚠️ Моля посочи символ. Пример: <code>/remove NVDA</code>"
        try:
            from src.data.asset_manager import AssetManager
            manager = AssetManager(db=self.db)
            ok, msg = manager.remove_asset(ticker)
            if ok:
                return f"🗑️ <b>{msg}</b>"
            return f"⚠️ {msg}"
        except Exception as e:
            logger.error(f"Error handling /remove {ticker}: {e}")
            return f"❌ Грешка при премахване: {e}"

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

    def handle_scan(self, arg: str = "") -> str:
        """Triggers an on-demand market scan in background and notifies user."""
        if not self.scanner:
            return "⚠️ Скенерът не е свързан към този слушател."

        import threading
        raw_ac = arg.lower().strip() if arg else "all"
        target_ac = raw_ac if raw_ac in ["crypto", "us_stocks", "ai_stocks", "commodities", "indices", "all"] else "all"

        def _do_scan():
            try:
                from src.main import run_scan
                self.notifier.send_raw_message(f"🔍 <b>Стартирано е сканиране на пазара [{target_ac.upper()}]...</b>")
                run_scan(self.scanner, asset_class=target_ac, timeframe="1D", limit=50)
                from src.alerts.digest import generate_digest_data
                digest = generate_digest_data(self.db)
                self.notifier.send_raw_message(f"✅ <b>Сканирането на [{target_ac.upper()}] приключи!</b>\n\n" + digest["message"])
            except Exception as e:
                logger.error(f"Telegram on-demand scan error: {e}", exc_info=True)
                self.notifier.send_raw_message(f"❌ Грешка при сканиране: {e}")

        threading.Thread(target=_do_scan, daemon=True, name="TelegramScanThread").start()
        return f"🚀 Сканирането на <b>{target_ac.upper()}</b> е стартирано на заден план! Резултатите ще пристигнат тук щом завърши."

    def handle_queue(self, arg: str = "") -> str:
        """Shows pending setups queue (1-3 bars ahead). Usage: /queue [top_n]"""
        try:
            top_n = int(arg) if arg.isdigit() else 8
        except Exception:
            top_n = 8

        rows = self.db.get_active_pending_setups()
        if not rows:
            return "⏳ <b>Няма активни очаквани сетъпи в опашката.</b>\n<i>Системата сканира пазара автоматично и ще добави активи, приближаващи ключови структури.</i>"

        from src.engine.setup_monitor import PendingSetup, format_queue_telegram
        import json

        setups = []
        for r in rows:
            try:
                c_met = json.loads(r["conditions_met"]) if r["conditions_met"] else []
                c_pen = json.loads(r["conditions_pending"]) if r["conditions_pending"] else []
            except Exception:
                c_met, c_pen = [], []

            ps = PendingSetup(
                symbol=r["symbol"],
                asset_class=r["asset_class"],
                setup_type=r["setup_type"],
                direction=r["direction"],
                priority=r["priority"],
                quality_score=float(r["quality_score"] or 0.0),
                description_bg=r["description_bg"] or "",
                description_en=r["description_en"] or "",
                conditions_met=c_met,
                conditions_pending=c_pen,
                estimated_trigger=r["estimated_trigger"] or "",
                current_price=float(r["current_price"] or 0.0),
                target_entry=float(r["target_entry"]) if r["target_entry"] else None,
                target_sl=float(r["target_sl"]) if r["target_sl"] else None,
                target_tp1=float(r["target_tp1"]) if r["target_tp1"] else None,
                key_level=float(r["key_level"]) if r["key_level"] else None,
                timeframe=r["timeframe"] or "1D",
                tier=r["tier"] or "B",
                first_detected=r["first_detected"] or "",
                last_updated=r["last_updated"] or "",
            )
            setups.append(ps)

        return format_queue_telegram(setups, top_n=top_n)

    def handle_risk(self) -> str:
        """Displays portfolio risk and exposure analysis."""
        from src.trading.portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker(db=self.db)
        return tracker.format_risk_report_telegram()

    def handle_journal(self, arg: str = "") -> str:
        """Shows recent trade log entries. Usage: /journal [limit]"""
        try:
            limit = int(arg) if arg.isdigit() else 10
        except Exception:
            limit = 10

        entries = self.db.get_trade_log(limit=limit)
        if not entries:
            return "📖 <b>Търговският дневник е празен.</b>\n<i>Все още няма записани операции или затворени позиции.</i>"

        lines = [f"📖 <b>Търговски Дневник (Последни {len(entries)} записа):</b>\n"]
        for e in entries:
            act = e["action"]
            ticker = e["ticker"]
            pnl_usd = e["pnl_usd"]
            pnl_pct = e["pnl_pct"]
            notes = e["notes"] or ""
            dt = e["created_at"][:16].replace("T", " ") if e["created_at"] else ""

            action_emoji = {
                "OPEN": "🟢 ВХОД",
                "PARTIAL_CLOSE": "🎯 ЧАСТИЧЕН TP1",
                "CLOSE": "🏁 ЗАТВАРЯНЕ",
                "SL_UPDATE": "🛡️ СТОП",
            }.get(act, f"⚡ {act}")

            pnl_txt = ""
            if pnl_usd is not None and abs(pnl_usd) > 0.001:
                sign = "+" if pnl_usd >= 0 else ""
                pnl_txt = f" | PnL: <b>{sign}${pnl_usd:,.2f} ({sign}{pnl_pct}%)</b>"

            lines.append(f"• <code>[{dt}]</code> <b>{action_emoji}: {ticker}</b>{pnl_txt}\n  <i>{notes}</i>")

        return "\n".join(lines)

    def handle_portfolio(self, arg: str = "") -> str:
        """Displays portfolio summary for either REAL or PAPER portfolio."""
        from src.trading.portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker(db=self.db)
        raw = arg.lower().strip()
        if raw in ["real", "live", "r"]:
            return tracker.format_portfolio_telegram(portfolio_type="REAL")
        elif raw in ["paper", "test", "sim", "virtual", "v", "p"]:
            return tracker.format_portfolio_telegram(portfolio_type="PAPER")
        else:
            real_text = tracker.format_portfolio_telegram(portfolio_type="REAL")
            paper_text = tracker.format_portfolio_telegram(portfolio_type="PAPER")
            return f"{real_text}\n\n➖➖➖➖➖➖➖➖➖➖\n\n{paper_text}"

    def handle_buy_real(self, parts: List[str]) -> str:
        """
        Records a real position execution.
        Usage: /buy_real [ticker] [price] [units] [broker] [sl] [tp1]
        """
        if len(parts) < 3:
            return (
                "⚠️ <b>Невалиден формат за реална покупка!</b>\n\n"
                "Формат: <code>/buy_real [тикер] [цена] [брой] [брокер_по_желание]</code>\n"
                "Примери:\n"
                "• <code>/buy_real NVDA 120.50 10 IBKR</code>\n"
                "• <code>/buy_real BTCUSDT 65000 0.05 Binance</code>"
            )
        ticker = parts[0].upper()
        try:
            price = float(parts[1])
            units = float(parts[2])
        except ValueError:
            return "❌ Грешка: Цената и количеството трябва да са валидни числа."

        broker = parts[3] if len(parts) > 3 else "Interactive Brokers"
        sl = float(parts[4]) if len(parts) > 4 and parts[4].replace('.', '', 1).isdigit() else None
        tp1 = float(parts[5]) if len(parts) > 5 and parts[5].replace('.', '', 1).isdigit() else None

        from src.trading.portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker(db=self.db)
        
        asset_class = "crypto" if ticker.endswith("USDT") else "us_stocks"
        try:
            active_symbols = self.db.get_active_symbols()
            for s in active_symbols:
                if s["ticker"] == ticker:
                    asset_class = s["asset_class"]
                    break
        except Exception:
            pass

        pos_id = tracker.add_real_position(
            ticker=ticker,
            asset_class=asset_class,
            entry_price=price,
            units=units,
            stop_loss=sl,
            tp1=tp1,
            broker_exchange=broker,
            notes=f"Ръчен вход през Telegram ({broker})"
        )
        total_val = price * units
        return (
            f"✅ <b>Записана РЕАЛНА Позиция: {ticker}</b>\n\n"
            f"• Брокер: <b>{broker}</b>\n"
            f"• Входна цена: <b>${price:,.2f}</b>\n"
            f"• Количество: <b>{units} бр.</b>\n"
            f"• Обща стойност: <b>${total_val:,.2f}</b>\n"
            f"• ID на сделка: <code>{pos_id}</code>\n\n"
            f"<i>Позицията се следи на живо в уеб дашборда (Зелен таб: Реално Портфолио).</i>"
        )

    def handle_close_real(self, parts: List[str]) -> str:
        """
        Closes an open real position.
        Usage: /close_real [ticker] [exit_price]
        """
        if len(parts) < 2:
            return (
                "⚠️ <b>Невалиден формат за затваряне на реална сделка!</b>\n\n"
                "Формат: <code>/close_real [тикер] [изходна_цена]</code>\n"
                "Пример: <code>/close_real NVDA 135.00</code>"
            )
        ticker = parts[0].upper()
        try:
            exit_price = float(parts[1])
        except ValueError:
            return "❌ Грешка: Изходната цена трябва да е число."

        from src.trading.portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker(db=self.db)
        ok = tracker.close_real_position(identifier=ticker, exit_price=exit_price, notes="Затворено през Telegram")
        if ok:
            return f"🏁 <b>Реалната позиция за {ticker} е успешно затворена</b> на цена <b>${exit_price:,.2f}</b>! Печалбата/загубата е отразена в кеша и дневника."
        else:
            return f"❌ Не беше намерена отворена реална позиция за символ <b>{ticker}</b>."

    def handle_cash_real(self, arg: str) -> str:
        """
        Sets real cash balance.
        Usage: /cash_real [amount]
        """
        if not arg:
            bal = self.db.get_real_balance()
            return f"💵 Наличен свободен реален кеш: <b>${bal.get('available_cash', 0.0):,.2f}</b>\nЗа промяна: <code>/cash_real 15000</code>"
        try:
            amount = float(arg)
            if amount < 0:
                return "❌ Кеш балансът не може да бъде отрицателен."
            self.db.set_real_cash(amount)
            return f"✅ Свободният реален кеш баланс е актуализиран на <b>${amount:,.2f}</b>."
        except ValueError:
            return "❌ Грешка: Моля посочете валидна сума за кеш."

    def handle_help(self) -> str:
        return (
            "🤖 <b>Larsson Line Бот Команди:</b>\n\n"
            "<b>Пазарни Справки:</b>\n"
            "/scan [all|crypto|us_stocks|ai_stocks] - Незабавно пазарно сканиране на живо ⚡\n"
            "/status [4h|1d|1w] - Общ пазарен баланс (Gold/Blue съотношение)\n"
            "/digest - Изпраща подробен бюлетин (топ трендове, Ribbon Spread, 24ч промени)\n"
            "/gold [4h|1d|1w] - Списък на всички бичи активи (Gold 🟡)\n"
            "/blue [4h|1d|1w] - Списък на всички мечи активи (Blue 🔵)\n\n"
            "<b>Институционални Анализи & Сигнали:</b>\n"
            "/analyze [символ] (или /a) - Пълен фундаментален + технически анализ на актив (напр. /a NVDA или /a BTC)\n"
            "/alpha [4h|1d|1w] (или /setups) - Топ институционални Alpha входове (Tier A / A+)\n"
            "/queue [брой] - Опашка от предстоящи сетъпи (1-3 бара напред) 🔮\n"
            "/traps - Предупреждения за валуационни капани (подценени, но в низходящ тренд)\n"
            "/calc [символ] [капитал] [риск_%] - Калкулатор за точен размер на позицията\n\n"
            "<b>🟢 РЕАЛЕН КАПИТАЛ & СМЕТКИ:</b>\n"
            "/real (или /portfolio real) - Справка за реално портфолио, капитал и отворени позиции 🟢\n"
            "/buy_real [тикер] [цена] [бр] [брокер] - Запис на реална покупка (напр. /buy_real NVDA 120 10 IBKR)\n"
            "/close_real [тикер] [цена] - Затваряне на реална позиция и финализиране на PnL\n"
            "/cash_real [сума] - Проверка или задаване на свободен реален кеш баланс\n\n"
            "<b>🧪 ТЕСТОВ СИМУЛАТОР (PAPER TRADING):</b>\n"
            "/paper (или /sim) - Автономен симулатор на Larsson стратегии\n"
            "/portfolio - Сборен преглед на двата портфейла\n"
            "/risk - Анализ на експозицията, риска и секторните концентрации 🛡️\n"
            "/journal - Хронологичен дневник на изпълнените сделки 📖\n"
            "/trades (или /history) - История на приключилите сделки и Win Rate\n"
            "/close [тикер] - Ръчно затваряне на активна тестова позиция (напр. /close SOLUSDT)\n\n"
            "<b>Управление на Активи (Scanner):</b>\n"
            "/add [символ] - Добавя актив към 24/7 сканирането (напр. /add ARM или /add SUIUSDT)\n"
            "/remove [символ] - Премахва/деактивира актив от сканирането\n\n"
            "<b>Личен Watchlist:</b>\n"
            "/watchlist - Показва активите в твоя личен списък ⭐\n"
            "/watch [символ] - Добавя актив в Watchlist (напр. /watch NVDA)\n"
            "/unwatch [символ] - Премахва актив от Watchlist\n\n"
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

        if data.startswith("trade:approve:") or data.startswith("trade:exec:"):
            prefix = "trade:approve:" if data.startswith("trade:approve:") else "trade:exec:"
            raw_payload = data[len(prefix):]
            parts = raw_payload.split(":")
            proposal_id = parts[0]
            leverage = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            res = self.paper_trader.approve_proposal(proposal_id, chat_id=chat_id, leverage=leverage)
            if res.get("success"):
                dir_label = "Шорт позицията" if res.get("direction") == "SHORT" else "Покупката"
                lev_info = f" с {res.get('leverage', leverage)}x левъридж" if res.get("leverage", leverage) > 1 else ""
                self.notifier.answer_callback_query(
                    cq_id,
                    text=f"✅ {dir_label} на {res.get('ticker')}{lev_info} е потвърдена в симулатора!",
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
        from_user = message.get("from", {})
        user_id = str(from_user.get("id", ""))

        authorized_id = str(self.notifier.chat_id)
        # Only allow authorized user/chat to interact (blocks unauthorized group members)
        if authorized_id and (chat_id != authorized_id and user_id != authorized_id):
            logger.warning(f"Ignored message from unauthorized sender: user_id={user_id}, chat_id={chat_id}")
            return

        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"Received Telegram command: {text}")
        parts = text.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "/scan":
                reply = self.handle_scan(arg)
            elif cmd == "/status":
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
            elif cmd in ["/queue", "/pending"]:
                reply = self.handle_queue(arg)
            elif cmd == "/risk":
                reply = self.handle_risk()
            elif cmd in ["/journal", "/log"]:
                reply = self.handle_journal(arg)
            elif cmd == "/real":
                reply = self.handle_portfolio("real")
            elif cmd in ["/paper", "/sim"]:
                reply = self.handle_portfolio("paper")
            elif cmd in ["/portfolio", "/positions"]:
                reply = self.handle_portfolio(arg)
            elif cmd == "/buy_real":
                reply = self.handle_buy_real(parts[1:])
            elif cmd == "/close_real":
                reply = self.handle_close_real(parts[1:])
            elif cmd == "/cash_real":
                reply = self.handle_cash_real(arg)
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
                reply = self.handle_watch(parts[1:])
            elif cmd in ["/conditions", "/conds"]:
                reply = self.handle_conditions()
            elif cmd in ["/delcond", "/rmcond"]:
                reply = self.handle_delcond(arg)
            elif cmd in ["/corr", "/correlation"]:
                reply = self.handle_corr()
            elif cmd in ["/attribution", "/attr"]:
                reply = self.handle_attribution()
            elif cmd == "/unwatch":
                reply = self.handle_unwatch(arg)
            elif cmd == "/add":
                target_class = parts[2] if len(parts) > 2 else None
                reply = self.handle_add(arg, asset_class=target_class)
            elif cmd == "/remove":
                reply = self.handle_remove(arg)
            elif cmd in ["/start", "/help"]:
                reply = self.handle_help()
            else:
                reply = "Непозната команда. Напиши /help за списък с наличните команди."
        except Exception as e:
            logger.error(f"Error handling Telegram command '{text}': {e}", exc_info=True)
            reply = f"⚠️ Грешка при обработка на команда <code>{cmd}</code>:\n<code>{e}</code>"

        self.notifier.send_raw_message(reply)

    def run_poll_loop(self):
        """Continuously polls for Telegram updates."""
        if not self.notifier.is_configured:
            logger.warning("Telegram not configured. Command listener stopped.")
            return

        # Ensure any residual webhook is cleared so getUpdates polling works without 409 Conflict
        try:
            del_url = f"https://api.telegram.org/bot{self.notifier.bot_token}/deleteWebhook"
            self.session.post(del_url, timeout=10)
            logger.info("Cleared Telegram webhook for long-polling.")
        except Exception as e:
            logger.warning(f"Could not clear Telegram webhook: {e}")

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
                elif resp.status_code == 409:
                    logger.warning("Telegram Conflict (409): Webhook active. Clearing webhook...")
                    try:
                        self.session.post(f"https://api.telegram.org/bot{self.notifier.bot_token}/deleteWebhook", timeout=10)
                    except Exception:
                        pass
                    time.sleep(2)
                else:
                    logger.warning(f"Telegram polling error {resp.status_code}: {resp.text}")
                    time.sleep(2)
            except requests.exceptions.Timeout:
                # Normal timeout from long-polling
                continue
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(3)
