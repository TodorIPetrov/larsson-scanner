"""
Larsson Line Market Scanner Core.
Orchestrates data fetching, SMMA indicator calculations, database state updates,
and alert dispatching across Crypto, US Stocks, International Stocks, Commodities, and Indices.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional
import yaml

from src.alerts.telegram import TelegramNotifier
from src.data.binance_fetch import BinanceFetcher
from src.data.sp500_loader import load_sp500_tickers
from src.data.yfinance_fetch import YFinanceFetcher
from src.engine.smma import compute_larsson_series, LarssonState
from src.engine.sr_levels import analyze_sr_levels
from src.storage.database import Database
from src.trading.paper_trader import PaperTrader

logger = logging.getLogger(__name__)


class LarssonScanner:
    def __init__(
        self,
        db: Optional[Database] = None,
        binance_fetcher: Optional[BinanceFetcher] = None,
        yf_fetcher: Optional[YFinanceFetcher] = None,
        notifier: Optional[TelegramNotifier] = None,
        paper_trader: Optional[PaperTrader] = None,
        config_path: str = "config/settings.yaml",
        assets_path: str = "config/assets.yaml",
        tv_mapping_path: str = "config/tv_mapping.json",
    ):
        self.db = db or Database()
        self.binance_fetcher = binance_fetcher or BinanceFetcher()
        self.yf_fetcher = yf_fetcher or YFinanceFetcher()
        self.notifier = notifier or TelegramNotifier()
        self.config = self._load_yaml(config_path)
        self.assets = self._load_yaml(assets_path)
        self.tv_mapping = self._load_json(tv_mapping_path)
        self.paper_trader = paper_trader or PaperTrader(db=self.db, notifier=self.notifier, config=self.config)

    def _load_yaml(self, path: str) -> dict:
        data = {}
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            # Check for settings.local.yaml override
            if "settings.yaml" in path:
                local_path = path.replace("settings.yaml", "settings.local.yaml")
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as f:
                        local_data = yaml.safe_load(f) or {}
                        for k, v in local_data.items():
                            if isinstance(v, dict) and isinstance(data.get(k), dict):
                                data[k].update(v)
                            else:
                                data[k] = v
        except Exception as e:
            logger.warning(f"Could not load YAML config from {path}: {e}")
        return data

    def _load_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load JSON mapping from {path}: {e}")
            return {}

    def get_tv_symbol(self, ticker: str, asset_class: str) -> str:
        """Resolves the TradingView deep-link symbol for a given ticker."""
        if ticker in self.tv_mapping:
            return self.tv_mapping[ticker]
        if asset_class == "crypto":
            return f"BINANCE:{ticker}"
        elif asset_class in ["us_stocks", "intl_stocks", "ai_stocks"]:
            return f"NASDAQ:{ticker}"
        return ticker

    def _resolve_sr_analysis(
        self,
        ticker: str,
        timeframe: str,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        latest_price: float,
        asset_class: str,
    ) -> Optional[dict]:
        """
        Resolves Support and Resistance analysis adhering to the Multi-Timeframe hierarchy.
        For 1D and 1W: Computes S/R directly on the timeframe candles.
        For 4H: Prioritizes 1D macro S/R levels. If not yet cached, fetches 1D klines.
        """
        try:
            if timeframe == "4H" and asset_class == "crypto":
                # Check if 1D S/R already exists in database
                row = self.db.get_sr_levels(ticker, "1D")
                if row and row["atr"]:
                    s1 = row["s1"]
                    r1 = row["r1"]
                    atr = row["atr"]
                    s1_dist = round(((latest_price - s1) / latest_price) * 100.0, 2) if s1 is not None else None
                    r1_dist = round(((r1 - latest_price) / latest_price) * 100.0, 2) if r1 is not None else None

                    context_flag = "IN_VALUE_RANGE"
                    if r1 is not None and (r1_dist is not None and r1_dist <= 1.5 or (r1 - latest_price) <= atr * 0.75):
                        context_flag = "NEAR_RESISTANCE"
                    elif s1 is not None and (s1_dist is not None and s1_dist <= 1.5 or (latest_price - s1) <= atr * 0.75):
                        context_flag = "NEAR_SUPPORT"
                    elif r1 is None:
                        context_flag = "BREAKOUT_ABOVE"
                    elif s1 is None:
                        context_flag = "BREAKDOWN_BELOW"

                    return {
                        "current_price": float(latest_price),
                        "atr": atr,
                        "s1": s1,
                        "s1_touches": row["s1_touches"],
                        "s1_dist_pct": s1_dist,
                        "r1": r1,
                        "r1_touches": row["r1_touches"],
                        "r1_dist_pct": r1_dist,
                        "context_flag": context_flag,
                    }

                # If not cached, fetch 1D klines to establish macro levels
                if self.binance_fetcher:
                    k1d = self.binance_fetcher.fetch_klines(ticker, "1D", limit=160)
                    if k1d:
                        h1d, l1d, c1d, _ = k1d
                        sr_1d = analyze_sr_levels(h1d, l1d, c1d, current_price=float(latest_price))
                        self._persist_sr_analysis(ticker, "1D", sr_1d)
                        return sr_1d.to_dict()

            # Default: compute on current timeframe candles
            sr_analysis = analyze_sr_levels(highs, lows, closes, current_price=float(latest_price))
            self._persist_sr_analysis(ticker, timeframe, sr_analysis)
            return sr_analysis.to_dict()
        except Exception as e:
            logger.warning(f"Failed to calculate S/R levels for {ticker} [{timeframe}]: {e}")
            return None

    def _persist_sr_analysis(self, ticker: str, timeframe: str, sr_analysis):
        self.db.upsert_sr_levels(
            ticker=ticker,
            timeframe=timeframe,
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

    def _evaluate_and_persist_trade_suggestion(
        self,
        ticker: str,
        timeframe: str,
        current_price: float,
        state: LarssonState,
        v1: float,
        m1: float,
        m2: float,
        v2: float,
        sr_data: Optional[dict],
    ) -> Optional[dict]:
        try:
            from src.engine.trade_suggestions import generate_trade_suggestion
            from src.engine.quantamental import get_fundamental_profile

            v2_val = v2 if v2 > 0 else 1e-6
            spread_pct = ((v1 - v2_val) / v2_val) * 100.0

            atr = sr_data.get("atr", current_price * 0.02) if sr_data else (current_price * 0.02)
            s1 = sr_data.get("s1") if sr_data else None
            s1_touches = sr_data.get("s1_touches", 0) if sr_data else 0
            s2 = sr_data.get("s2") if sr_data else None
            r1 = sr_data.get("r1") if sr_data else None
            r1_touches = sr_data.get("r1_touches", 0) if sr_data else 0
            r2 = sr_data.get("r2") if sr_data else None
            context_flag = sr_data.get("context_flag", "IN_VALUE_RANGE") if sr_data else "IN_VALUE_RANGE"

            # Check macro 1D state if scanning 4H or other lower timeframes
            macro_1d_state = None
            if timeframe != "1D":
                st_1d = self.db.get_current_state(ticker, "1D")
                if st_1d:
                    macro_1d_state = st_1d["current_state"]

            fund_profile = get_fundamental_profile(ticker)

            suggestion = generate_trade_suggestion(
                current_price=current_price,
                state=state.value,
                v1=v1,
                m1=m1,
                m2=m2,
                v2=v2,
                spread_pct=spread_pct,
                atr=atr,
                s1=s1,
                s1_touches=s1_touches,
                s2=s2,
                r1=r1,
                r1_touches=r1_touches,
                r2=r2,
                context_flag=context_flag,
                timeframe=timeframe,
                macro_1d_state=macro_1d_state,
                fund_profile=fund_profile,
            )

            self.db.upsert_trade_suggestion(
                ticker=ticker,
                timeframe=timeframe,
                action=suggestion.action,
                direction=suggestion.direction,
                setup_type=suggestion.setup_type,
                entry_price=suggestion.entry_price,
                stop_loss=suggestion.stop_loss,
                tp1=suggestion.tp1,
                tp2=suggestion.tp2,
                rr_ratio=suggestion.rr_ratio,
                score=suggestion.score,
                tier=suggestion.tier,
                reason_bg=suggestion.reason_bg,
                reason_en=suggestion.reason_en,
                fund_verdict=suggestion.fund_verdict,
                fair_value=suggestion.fair_value,
                mos_pct=suggestion.mos_pct,
                moat=suggestion.moat,
                z_score=suggestion.z_score,
                quantamental_tag=suggestion.quantamental_tag,
                tech_action=suggestion.tech_action,
                tech_label_bg=suggestion.tech_label_bg,
                tech_thesis_bg=suggestion.tech_thesis_bg,
                fund_action=suggestion.fund_action,
                fund_label_bg=suggestion.fund_label_bg,
                fund_thesis_bg=suggestion.fund_thesis_bg,
                synthesis_badge_bg=suggestion.synthesis_badge_bg,
                synthesis_label_bg=suggestion.synthesis_label_bg,
            )
            return suggestion.to_dict()
        except Exception as e:
            logger.warning(f"Failed to generate trade suggestion for {ticker} [{timeframe}]: {e}")
            return None

    def scan_crypto_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1D",
        delay_s: float = 0.05,
    ) -> Dict:
        """
        Scans a list of crypto symbols on Binance for Larsson Line state transitions.
        """
        results = {
            "asset_class": "crypto",
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
        }

        min_warmup = self.config.get("scanner", {}).get("min_warmup_candles", 160)

        for sym in symbols:
            tv_symbol = self.get_tv_symbol(sym, "crypto")
            kline_data = self.binance_fetcher.fetch_klines(sym, timeframe, limit=min_warmup)
            if not kline_data:
                results["failed_count"] += 1
                continue

            highs, lows, closes, latest_price = kline_data
            v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
            current_state = states[-1]

            # Resolve Support and Resistance levels
            sr_data = self._resolve_sr_analysis(
                ticker=sym,
                timeframe=timeframe,
                highs=highs,
                lows=lows,
                closes=closes,
                latest_price=float(latest_price),
                asset_class="crypto",
            )

            results["total_scanned"] += 1
            if current_state == LarssonState.GOLD:
                results["gold_count"] += 1
            elif current_state == LarssonState.BLUE:
                results["blue_count"] += 1
            else:
                results["neutral_count"] += 1

            # Update database and check for transition
            state_changed, old_state = self.db.update_state(
                ticker=sym,
                timeframe=timeframe,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                new_state=current_state,
                price=float(latest_price),
            )

            # Evaluate and record Trade Suggestion
            trade_suggestion = self._evaluate_and_persist_trade_suggestion(
                ticker=sym,
                timeframe=timeframe,
                current_price=float(latest_price),
                state=current_state,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                sr_data=sr_data,
            )

            self.db.upsert_symbols([(sym, "crypto", tv_symbol)])

            # Evaluate open paper positions for this ticker (SL/TP/Blue exit)
            try:
                self.paper_trader.evaluate_open_positions(
                    prices={sym: float(latest_price)},
                    states={sym: current_state.value},
                )
            except Exception as e:
                logger.warning(f"Error evaluating paper positions for {sym}: {e}")

            if state_changed and old_state is not None:
                change_event = {
                    "ticker": sym,
                    "timeframe": timeframe,
                    "old_state": old_state,
                    "new_state": current_state,
                    "price": latest_price,
                    "tv_symbol": tv_symbol,
                    "sr_data": sr_data,
                    "trade_suggestion": trade_suggestion,
                }
                results["state_changes"].append(change_event)
                self.db.log_alert(
                    ticker=sym,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=current_state,
                    price=latest_price,
                    tv_symbol=tv_symbol,
                )

                # Trigger interactive trade proposal if transitioning to GOLD
                if current_state == LarssonState.GOLD and trade_suggestion:
                    try:
                        self.paper_trader.handle_new_signal(
                            ticker=sym,
                            timeframe=timeframe,
                            trade_suggestion=trade_suggestion,
                            current_price=float(latest_price),
                            tv_symbol=tv_symbol,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to generate trade proposal for {sym}: {e}")

            if delay_s > 0:
                time.sleep(delay_s)

        if results["state_changes"]:
            self._dispatch_state_changes(results["state_changes"])

        return results

    def _dispatch_state_changes(self, state_changes: List[dict]):
        if not state_changes:
            return
        include_sr = self.config.get("telegram", {}).get("include_sr_in_alerts", False)
        dispatched = []
        for ev in state_changes:
            item = dict(ev)
            if not include_sr:
                item.pop("sr_data", None)
            dispatched.append(item)
        self.notifier.dispatch_alerts(dispatched)

    def scan_yfinance_assets(
        self,
        asset_class: str,
        tickers: Optional[List[str]] = None,
        timeframe: str = "1D",
    ) -> Dict:
        """
        Scans stocks, commodities, or indices using yfinance batch download.
        """
        if not tickers:
            configured = self.assets.get(asset_class, [])
            tickers = [item["ticker"] for item in configured if isinstance(item, dict) and "ticker" in item]

        results = {
            "asset_class": asset_class,
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
        }

        if not tickers:
            return results

        batch_data = self.yf_fetcher.fetch_batch(tickers, timeframe=timeframe)

        for sym in tickers:
            if sym not in batch_data:
                results["failed_count"] += 1
                continue

            highs, lows, closes, latest_price = batch_data[sym]
            v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
            current_state = states[-1]

            # Resolve Support and Resistance levels
            sr_data = self._resolve_sr_analysis(
                ticker=sym,
                timeframe=timeframe,
                highs=highs,
                lows=lows,
                closes=closes,
                latest_price=float(latest_price),
                asset_class=asset_class,
            )

            results["total_scanned"] += 1
            if current_state == LarssonState.GOLD:
                results["gold_count"] += 1
            elif current_state == LarssonState.BLUE:
                results["blue_count"] += 1
            else:
                results["neutral_count"] += 1

            tv_symbol = self.get_tv_symbol(sym, asset_class)

            state_changed, old_state = self.db.update_state(
                ticker=sym,
                timeframe=timeframe,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                new_state=current_state,
                price=float(latest_price),
            )

            # Evaluate and record Trade Suggestion
            trade_suggestion = self._evaluate_and_persist_trade_suggestion(
                ticker=sym,
                timeframe=timeframe,
                current_price=float(latest_price),
                state=current_state,
                v1=float(v1[-1]),
                m1=float(m1[-1]),
                m2=float(m2[-1]),
                v2=float(v2[-1]),
                sr_data=sr_data,
            )

            self.db.upsert_symbols([(sym, asset_class, tv_symbol)])

            # Evaluate open paper positions for this symbol (SL/TP/Blue exit)
            try:
                self.paper_trader.evaluate_open_positions(
                    prices={sym: float(latest_price)},
                    states={sym: current_state.value},
                )
            except Exception as e:
                logger.warning(f"Error evaluating paper positions for {sym}: {e}")

            if state_changed and old_state is not None:
                change_event = {
                    "ticker": sym,
                    "timeframe": timeframe,
                    "old_state": old_state,
                    "new_state": current_state,
                    "price": latest_price,
                    "tv_symbol": tv_symbol,
                    "sr_data": sr_data,
                    "trade_suggestion": trade_suggestion,
                }
                results["state_changes"].append(change_event)
                self.db.log_alert(
                    ticker=sym,
                    timeframe=timeframe,
                    old_state=old_state,
                    new_state=current_state,
                    price=latest_price,
                    tv_symbol=tv_symbol,
                )

                # Trigger interactive trade proposal if transitioning to GOLD
                if current_state == LarssonState.GOLD and trade_suggestion:
                    try:
                        self.paper_trader.handle_new_signal(
                            ticker=sym,
                            timeframe=timeframe,
                            trade_suggestion=trade_suggestion,
                            current_price=float(latest_price),
                            tv_symbol=tv_symbol,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to generate trade proposal for {sym}: {e}")

        if results["state_changes"]:
            self._dispatch_state_changes(results["state_changes"])

        return results

    def scan_sp500(self, limit: Optional[int] = None, timeframe: str = "1D") -> Dict:
        """Loads all S&P 500 constituents and scans them using batch download."""
        tickers = load_sp500_tickers(limit=limit)
        return self.scan_yfinance_assets(asset_class="us_stocks", tickers=tickers, timeframe=timeframe)

    def scan_all_assets(self, timeframe: str = "1D", crypto_limit: int = 50) -> Dict:
        """
        Runs comprehensive scan across all asset classes for a given timeframe.
        """
        combined = {
            "timeframe": timeframe,
            "total_scanned": 0,
            "gold_count": 0,
            "blue_count": 0,
            "neutral_count": 0,
            "failed_count": 0,
            "state_changes": [],
            "classes": {},
        }

        # 1. Crypto (always scanned on 1D, 4H, 1W)
        crypto_res = self.scan_top_crypto(limit=crypto_limit, timeframe=timeframe)
        combined["classes"]["crypto"] = crypto_res
        self._aggregate_stats(combined, crypto_res)

        # 2. Stocks, Commodities, Indices (only on 1D and 1W)
        if timeframe in ["1D", "1W"]:
            for a_class in ["us_stocks", "crypto_stocks", "intl_stocks", "ai_stocks", "commodities", "indices"]:
                res = self.scan_yfinance_assets(asset_class=a_class, timeframe=timeframe)
                combined["classes"][a_class] = res
                self._aggregate_stats(combined, res)

        return combined

    def scan_top_crypto(self, limit: int = 50, timeframe: str = "1D") -> Dict:
        """Fetches top N USDT pairs by 24h volume and scans them."""
        symbols = self.binance_fetcher.get_top_usdt_pairs(limit=limit)
        return self.scan_crypto_symbols(symbols, timeframe=timeframe)

    @staticmethod
    def _aggregate_stats(combined: dict, part: dict):
        combined["total_scanned"] += part["total_scanned"]
        combined["gold_count"] += part["gold_count"]
        combined["blue_count"] += part["blue_count"]
        combined["neutral_count"] += part["neutral_count"]
        combined["failed_count"] += part["failed_count"]
        combined["state_changes"].extend(part["state_changes"])

    def handle_candle_close_event(
        self,
        symbol: str,
        timeframe: str,
        high: float,
        low: float,
        close: float,
    ) -> Optional[Dict]:
        """
        Handles an instant candle close event from Binance WebSocket.
        Recalculates SMMA ribbon and triggers alerts/dashboard sync if state transitioned.
        """
        logger.info(f"⚡ [WebSocket Trigger] Processing candle close for {symbol} [{timeframe}] @ ${close:,.2f}")
        res = self.scan_crypto_symbols([symbol], timeframe=timeframe, delay_s=0.0)
        if res.get("state_changes"):
            try:
                from src.dashboard.generator import export_dashboard_data
                from src.dashboard.git_sync import sync_dashboard_to_git

                export_dashboard_data(self.db)
                sync_dashboard_to_git()
            except Exception as e:
                logger.warning(f"Failed to sync dashboard after WS candle close: {e}")
        return res

