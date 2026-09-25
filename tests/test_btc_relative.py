import pytest
import pandas as pd
import numpy as np

from src.engine.btc_relative import BTCRelativeStrengthAnalyzer, BTCRelativeAnalysis
from src.engine.trade_suggestions import generate_trade_suggestion, TradeSuggestion
from src.storage.database import Database


def generate_dummy_candles(n_bars=60, start_price=100.0, trend=0.01):
    dates = pd.date_range(start="2026-01-01", periods=n_bars, freq="D")
    prices = [start_price]
    for _ in range(1, n_bars):
        next_p = prices[-1] * (1.0 + trend)
        prices.append(next_p)
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000] * n_bars
    })
    return df


class TestBTCRelativeStrength:
    def test_analyzer_returns_none_on_insufficient_bars(self):
        analyzer = BTCRelativeStrengthAnalyzer()
        asset_df = generate_dummy_candles(n_bars=15)
        btc_df = generate_dummy_candles(n_bars=15)
        res = analyzer.compute_relative_strength(
            "ETHUSDT", "crypto",
            asset_df["high"].values, asset_df["low"].values, asset_df["close"].values,
            btc_df["high"].values, btc_df["low"].values, btc_df["close"].values
        )
        assert res is None

    def test_outperforming_asset_gets_gold_and_leverage(self):
        analyzer = BTCRelativeStrengthAnalyzer()
        # Asset growing at +2% per day, BTC flat
        asset_df = generate_dummy_candles(n_bars=80, start_price=10.0, trend=0.02)
        btc_df = generate_dummy_candles(n_bars=80, start_price=60000.0, trend=0.0001)

        res = analyzer.compute_relative_strength(
            "SOLUSDT", "crypto",
            asset_df["high"].values, asset_df["low"].values, asset_df["close"].values,
            btc_df["high"].values, btc_df["low"].values, btc_df["close"].values
        )
        assert res is not None
        assert isinstance(res, BTCRelativeAnalysis)
        assert res.ticker == "SOLUSDT"
        assert res.ratio_state == "GOLD"
        assert res.alpha_30d_pct > 0
        assert res.leverage_allowed is True
        assert "vs BTC" in res.badge_bg
        assert "ALPHA" in res.verdict

    def test_underperforming_asset_gets_blue_and_blocks_leverage(self):
        analyzer = BTCRelativeStrengthAnalyzer()
        # Asset crashing -2% per day, BTC pumping +1% per day
        asset_df = generate_dummy_candles(n_bars=80, start_price=100.0, trend=-0.02)
        btc_df = generate_dummy_candles(n_bars=80, start_price=60000.0, trend=0.01)

        res = analyzer.compute_relative_strength(
            "WEAKUSDT", "crypto",
            asset_df["high"].values, asset_df["low"].values, asset_df["close"].values,
            btc_df["high"].values, btc_df["low"].values, btc_df["close"].values
        )
        assert res is not None
        assert res.ratio_state == "BLUE"
        assert res.alpha_30d_pct < 0
        assert res.leverage_allowed is False
        assert "vs BTC" in res.badge_bg
        assert "UNDERPERFORMER" in res.verdict

    def test_leverage_gating_in_trade_suggestions(self):
        # When BTC relative allows leverage
        btc_bullish = BTCRelativeAnalysis(
            ticker="MSTR",
            asset_class="crypto_stocks",
            current_ratio=0.0025,
            ratio_state="GOLD",
            ratio_spread_pct=4.5,
            ratio_v1=0.0026,
            ratio_v2=0.0024,
            alpha_30d_pct=25.0,
            alpha_7d_pct=8.0,
            asset_perf_30d_pct=30.0,
            btc_perf_30d_pct=5.0,
            verdict="STRONG_ALPHA",
            leverage_allowed=True,
            badge_bg="⚡ ₿ Alpha (+25.0%)",
            label_bg="🟢 НАДМИНАВА BTC",
            thesis_bg="Лидер спрямо BTC"
        )
        
        ts_bullish = generate_trade_suggestion(
            current_price=141.0,
            state="GOLD",
            v1=145.0,
            m1=143.0,
            m2=141.0,
            v2=139.0,
            spread_pct=3.5,
            atr=5.0,
            s1=140.0,
            s1_lower=139.0,
            s1_touches=3,
            r1=170.0,
            context_flag="NEAR_SUPPORT",
            timeframe="1D",
            ticker="MSTR",
            asset_class="crypto_stocks",
            btc_relative=btc_bullish
        )
        assert ts_bullish.recommended_leverage >= 2
        assert ts_bullish.max_leverage >= 2
        assert ts_bullish.btc_leverage_allowed is True
        assert ts_bullish.btc_ratio_state == "GOLD"

        # When BTC relative bleeds, leverage MUST be capped strictly to 1x Spot
        btc_bleeding = BTCRelativeAnalysis(
            ticker="MSTR",
            asset_class="crypto_stocks",
            current_ratio=0.0018,
            ratio_state="BLUE",
            ratio_spread_pct=-3.0,
            ratio_v1=0.0017,
            ratio_v2=0.0019,
            alpha_30d_pct=-15.0,
            alpha_7d_pct=-4.0,
            asset_perf_30d_pct=-10.0,
            btc_perf_30d_pct=5.0,
            verdict="UNDERPERFORMER",
            leverage_allowed=False,
            badge_bg="⚠️ ₿ Bleeding (-15.0%)",
            label_bg="🔴 ПОД BTC",
            thesis_bg="Губи от BTC"
        )
        
        ts_bleeding = generate_trade_suggestion(
            current_price=141.0,
            state="GOLD",
            v1=145.0,
            m1=143.0,
            m2=141.0,
            v2=139.0,
            spread_pct=3.5,
            atr=5.0,
            s1=140.0,
            s1_lower=139.0,
            s1_touches=3,
            r1=170.0,
            context_flag="NEAR_SUPPORT",
            timeframe="1D",
            ticker="MSTR",
            asset_class="crypto_stocks",
            btc_relative=btc_bleeding
        )
        assert ts_bleeding.recommended_leverage == 1
        assert ts_bleeding.max_leverage == 1
        assert ts_bleeding.btc_leverage_allowed is False
        assert ts_bleeding.btc_ratio_state == "BLUE"
        assert ts_bleeding.score < ts_bullish.score

    def test_database_persistence_and_retrieval(self, tmp_path):
        db_path = str(tmp_path / "test_market_scanner.db")
        db = Database(db_path)

        btc_rel = BTCRelativeAnalysis(
            ticker="NAKA",
            asset_class="crypto_stocks",
            current_ratio=0.000035,
            ratio_state="GOLD",
            ratio_spread_pct=2.8,
            ratio_v1=0.000036,
            ratio_v2=0.000034,
            alpha_30d_pct=18.5,
            alpha_7d_pct=5.2,
            asset_perf_30d_pct=25.0,
            btc_perf_30d_pct=6.5,
            verdict="ALPHA_OUTPERFORMER",
            leverage_allowed=True,
            badge_bg="⚡ ₿ Alpha (+18.5%)",
            label_bg="🟢 НАДМИНАВА BTC",
            thesis_bg="Тестов анализ"
        )

        db.upsert_symbols([("NAKA", "crypto_stocks", "NAKA")])
        from src.engine.smma import LarssonState
        db.update_state("NAKA", "1D", 2.40, 2.35, 2.30, 2.25, LarssonState.GOLD, 2.50)

        suggestion = generate_trade_suggestion(
            current_price=2.50,
            state="GOLD",
            v1=2.40,
            m1=2.35,
            m2=2.30,
            v2=2.25,
            spread_pct=2.1,
            atr=0.15,
            s1=2.30,
            r1=3.10,
            timeframe="1D",
            ticker="NAKA",
            asset_class="crypto_stocks",
            btc_relative=btc_rel
        )

        db.upsert_trade_suggestion(
            ticker="NAKA",
            timeframe="1D",
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
            btc_ratio_state=suggestion.btc_ratio_state,
            btc_alpha_30d=suggestion.btc_alpha_30d,
            btc_alpha_7d=suggestion.btc_alpha_7d,
            btc_ratio_spread=suggestion.btc_ratio_spread,
            btc_verdict=suggestion.btc_verdict,
            btc_badge_bg=suggestion.btc_badge_bg,
            btc_thesis_bg=suggestion.btc_thesis_bg,
            btc_leverage_allowed=1 if suggestion.btc_leverage_allowed else 0,
        )

        # Retrieve through get_all_states
        states = db.get_all_states()
        assert len(states) >= 1
        naka_row = next((r for r in states if r["ticker"] == "NAKA"), None)
        assert naka_row is not None
        assert naka_row["ts_btc_ratio_state"] == "GOLD"
        assert naka_row["ts_btc_alpha_30d"] == pytest.approx(18.5)
        assert naka_row["ts_btc_leverage_allowed"] == 1
        assert "Alpha" in naka_row["ts_btc_badge_bg"]

    def test_tradingview_ratio_symbols_and_links(self):
        from src.engine.btc_relative import get_tradingview_ratio_symbol, get_tradingview_ratio_link

        # Native pairs
        assert get_tradingview_ratio_symbol("ETHUSDT", "crypto") == "BINANCE:ETHBTC"
        assert get_tradingview_ratio_symbol("SOLUSDT", "crypto") == "BINANCE:SOLBTC"

        # Synthetic crypto pairs
        assert get_tradingview_ratio_symbol("SUIUSDT", "crypto") == "BINANCE:SUIUSDT/BINANCE:BTCUSDT"

        # Crypto stocks / equities
        assert get_tradingview_ratio_symbol("MSTR", "crypto_stocks") == "NASDAQ:MSTR/BINANCE:BTCUSDT"
        assert get_tradingview_ratio_symbol("NVDA", "us_stocks") == "NASDAQ:NVDA/BINANCE:BTCUSDT"

        # Direct URLs
        link_eth = get_tradingview_ratio_link("ETHUSDT", "crypto", "1D")
        assert "https://www.tradingview.com/chart/?symbol=" in link_eth
        assert "interval=1D" in link_eth
        assert "ETHBTC" in link_eth

        link_sui_4h = get_tradingview_ratio_link("SUIUSDT", "crypto", "4H")
        assert "interval=240" in link_sui_4h
        assert "SUIUSDT" in link_sui_4h
        assert "BTCUSDT" in link_sui_4h

