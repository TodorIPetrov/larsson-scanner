"""
Tests for Options Flow Integration (US Equities).
Verifies PCR, unusual call sweep detection, sentiment classification,
max pain, gamma wall calculation, caching, and confluence boost logic.
"""

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from src.engine.options_flow import (
    clear_options_cache,
    get_options_flow,
    is_crypto_or_non_equity,
)
from src.trading.paper_trader import PaperTrader


@pytest.fixture(autouse=True)
def reset_cache():
    clear_options_cache()
    yield
    clear_options_cache()


def _build_mock_chain(
    call_records,
    put_records,
):
    chain = MagicMock()
    chain.calls = pd.DataFrame(call_records)
    chain.puts = pd.DataFrame(put_records)
    return chain


def test_crypto_and_non_equity_returns_none():
    """Crypto symbols, indices, and forex should immediately return None without API calls."""
    crypto_symbols = ["BTCUSDT", "ETHUSDC", "SOL-USD", "GC=F", "^GSPC", "BTC/USDT", "BTC"]
    for sym in crypto_symbols:
        assert is_crypto_or_non_equity(sym) is True
        assert get_options_flow(sym) is None


def test_symbol_without_options_returns_none():
    """If symbol has no options available, get_options_flow returns None."""
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ()
        mock_ticker_cls.return_value = mock_instance

        flow = get_options_flow("NO_OPTIONS_CORP", use_cache=False)
        assert flow is None


def test_bullish_unusual_call_sweep():
    """
    Test detection of unusual call sweep (call vol / call OI > 2.0)
    and bullish sentiment with low put/call ratio.
    """
    calls_data = [
        {"strike": 180.0, "openInterest": 1000, "volume": 3000, "impliedVolatility": 0.25},
        {"strike": 185.0, "openInterest": 1000, "volume": 2000, "impliedVolatility": 0.28},
    ]
    puts_data = [
        {"strike": 175.0, "openInterest": 500, "volume": 100, "impliedVolatility": 0.30},
        {"strike": 180.0, "openInterest": 700, "volume": 200, "impliedVolatility": 0.26},
    ]
    # Total call OI = 2000, call vol = 5000 -> ratio = 2.5 (> 2.0) -> unusual call sweep = True
    # Total put OI = 1200 -> PCR = 1200 / 2000 = 0.60 (< 0.70) -> net_sentiment = 'BULLISH'

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16", "2026-11-20")
        mock_instance.option_chain.return_value = _build_mock_chain(calls_data, puts_data)
        mock_instance.fast_info.last_price = 182.50
        mock_ticker_cls.return_value = mock_instance

        flow = get_options_flow("AAPL", ribbon_state="GOLD", use_cache=False)

        assert flow is not None
        assert flow["put_call_ratio"] == 0.60
        assert flow["unusual_call_sweep"] is True
        assert flow["net_sentiment"] == "BULLISH"
        assert flow["confluence_boost"] is True
        assert flow["max_pain"] in (180.0, 185.0)


def test_bearish_high_put_call_ratio():
    """High put/call ratio (> 1.3) and normal volume results in BEARISH sentiment."""
    calls_data = [
        {"strike": 100.0, "openInterest": 1000, "volume": 300, "impliedVolatility": 0.30},
    ]
    puts_data = [
        {"strike": 95.0, "openInterest": 1000, "volume": 200, "impliedVolatility": 0.32},
        {"strike": 90.0, "openInterest": 1000, "volume": 300, "impliedVolatility": 0.35},
    ]
    # Total call OI = 1000, put OI = 2000 -> PCR = 2.0 (> 1.3)
    # Call vol / OI = 300 / 1000 = 0.3 (< 2.0) -> unusual_call_sweep = False

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16",)
        mock_instance.option_chain.return_value = _build_mock_chain(calls_data, puts_data)
        mock_instance.fast_info.last_price = 98.0
        mock_ticker_cls.return_value = mock_instance

        flow = get_options_flow("BEAR_CO", ribbon_state="BLUE", use_cache=False)

        assert flow is not None
        assert flow["put_call_ratio"] == 2.0
        assert flow["unusual_call_sweep"] is False
        assert flow["net_sentiment"] == "BEARISH"
        assert flow["confluence_boost"] is True


def test_neutral_sentiment():
    """PCR between 0.7 and 1.3 with normal call volume results in NEUTRAL sentiment."""
    calls_data = [
        {"strike": 50.0, "openInterest": 1000, "volume": 500, "impliedVolatility": 0.20},
    ]
    puts_data = [
        {"strike": 50.0, "openInterest": 1000, "volume": 400, "impliedVolatility": 0.20},
    ]
    # PCR = 1.0, call vol/OI = 0.5

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16",)
        mock_instance.option_chain.return_value = _build_mock_chain(calls_data, puts_data)
        mock_instance.fast_info.last_price = 50.0
        mock_ticker_cls.return_value = mock_instance

        flow = get_options_flow("NEUT_CO", ribbon_state="GOLD", use_cache=False)

        assert flow is not None
        assert flow["put_call_ratio"] == 1.0
        assert flow["unusual_call_sweep"] is False
        assert flow["net_sentiment"] == "NEUTRAL"
        assert flow["confluence_boost"] is False


def test_max_pain_and_gamma_wall():
    """Max pain correctly identifies strike with maximum options open interest."""
    calls_data = [
        {"strike": 170.0, "openInterest": 500, "volume": 100, "impliedVolatility": 0.30},
        {"strike": 180.0, "openInterest": 8000, "volume": 200, "impliedVolatility": 0.25},
        {"strike": 190.0, "openInterest": 1200, "volume": 50, "impliedVolatility": 0.28},
    ]
    puts_data = [
        {"strike": 170.0, "openInterest": 1000, "volume": 50, "impliedVolatility": 0.30},
        {"strike": 180.0, "openInterest": 4000, "volume": 100, "impliedVolatility": 0.25},
        {"strike": 190.0, "openInterest": 300, "volume": 20, "impliedVolatility": 0.28},
    ]
    # Total OI per strike:
    # 170: 500 + 1000 = 1500
    # 180: 8000 + 4000 = 12000 (Maximum!)
    # 190: 1200 + 300 = 1500

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16",)
        mock_instance.option_chain.return_value = _build_mock_chain(calls_data, puts_data)
        mock_instance.fast_info.last_price = 180.0
        mock_ticker_cls.return_value = mock_instance

        flow = get_options_flow("MP_STOCK", use_cache=False)

        assert flow is not None
        assert flow["max_pain"] == 180.0
        assert flow["gamma_wall"] is not None
        assert isinstance(flow["gamma_wall"], float)


def test_confluence_boost_confirmation():
    """Confluence boost confirms when ribbon matches options sentiment."""
    calls_bull = [{"strike": 100.0, "openInterest": 2000, "volume": 6000, "impliedVolatility": 0.25}]
    puts_bull = [{"strike": 100.0, "openInterest": 800, "volume": 100, "impliedVolatility": 0.25}]

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16",)
        mock_instance.option_chain.return_value = _build_mock_chain(calls_bull, puts_bull)
        mock_instance.fast_info.last_price = 100.0
        mock_ticker_cls.return_value = mock_instance

        # Bullish flow + GOLD ribbon -> True
        flow_gold = get_options_flow("CONF_CO", ribbon_state="GOLD", use_cache=False)
        assert flow_gold["confluence_boost"] is True

        # Bullish flow + BLUE ribbon -> False (mismatch)
        flow_blue = get_options_flow("CONF_CO", ribbon_state="BLUE", use_cache=False)
        assert flow_blue["confluence_boost"] is False


def test_options_flow_caching():
    """Repeated calls within 1h reuse the cache without re-fetching yfinance."""
    calls_data = [{"strike": 50.0, "openInterest": 1000, "volume": 500, "impliedVolatility": 0.2}]
    puts_data = [{"strike": 50.0, "openInterest": 500, "volume": 100, "impliedVolatility": 0.2}]

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.options = ("2026-10-16",)
        mock_instance.option_chain.return_value = _build_mock_chain(calls_data, puts_data)
        mock_instance.fast_info.last_price = 50.0
        mock_ticker_cls.return_value = mock_instance

        # First call fetches from yfinance
        flow1 = get_options_flow("CACHE_TEST", use_cache=True)
        assert flow1 is not None
        assert mock_instance.option_chain.call_count == 1

        # Second call uses cache
        flow2 = get_options_flow("CACHE_TEST", use_cache=True)
        assert flow2 is not None
        assert mock_instance.option_chain.call_count == 1  # No additional API call!


def test_trade_proposal_format_with_options():
    """PaperTrader formats proposal message with Options flow line."""
    mock_db = MagicMock()
    mock_db.get_pending_proposals.return_value = []
    mock_db.get_open_paper_positions.return_value = []
    mock_db.get_paper_balance.return_value = {"available_cash": 10000.0, "balance": 10000.0}
    mock_db.create_trade_proposal.return_value = True

    mock_notifier = MagicMock()
    mock_notifier.send_message_with_markup.return_value = 12345

    pt = PaperTrader(db=mock_db, notifier=mock_notifier)

    opt_flow = {
        "put_call_ratio": 0.72,
        "unusual_call_sweep": True,
        "net_sentiment": "BULLISH",
        "max_pain": 185.0,
        "gamma_wall": 190.0,
        "confluence_boost": True,
    }

    trade_suggestion = {
        "action": "SPOT_BUY",
        "direction": "LONG",
        "setup_type": "QUANTAMENTAL_ALPHA_BUY",
        "entry_price": 185.0,
        "stop_loss": 178.0,
        "tp1": 200.0,
        "tp2": 215.0,
        "score": 90,
        "tier": "A+",
        "reason_bg": "Силен технически и фундаментален сигнал",
        "max_leverage": 2,
        "recommended_leverage": 1,
        "options_flow": opt_flow,
    }

    msg_text, markup = pt.format_proposal_message(
        proposal_id="prop_AAPL_123",
        ticker="AAPL",
        timeframe="1D",
        entry_price=185.0,
        stop_loss=178.0,
        tp1=200.0,
        tp2=215.0,
        position_size_usd=1000.0,
        units=5.4,
        tier="A+",
        score=90,
        reason="Силен технически сигнал",
        expires_minutes=60,
        tv_symbol="NASDAQ:AAPL",
        trade_suggestion=trade_suggestion,
    )

    assert "📈 Options: Unusual call sweep detected | PCR: 0.72 (BULLISH)" in msg_text
