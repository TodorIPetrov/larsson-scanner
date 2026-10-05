"""
Tests for src/engine/correlation.py

Covers:
- Pairwise Pearson correlation calculation
- Portfolio average correlation
- Concentration warning threshold (> 0.75)
- HHI (Herfindahl-Hirschman Index) calculation
- Diversification suggestions from universe
- Edge case: single asset or insufficient history
- Telegram formatter formatting check
"""

import pandas as pd
import numpy as np
import pytest

from src.engine.correlation import (
    compute_correlation_matrix,
    suggest_diversification,
    format_correlation_telegram,
    cluster_transition_signals,
    format_cluster_alerts_telegram,
    SignalCluster,
    CONCENTRATION_WARNING_THRESHOLD,
)


def _make_prices(n: int = 50, trend: float = 1.0, noise: float = 0.5, seed: int = 42):
    rng = np.random.default_rng(seed)
    rets = rng.normal(trend / 100.0, noise / 100.0, n)
    prices = 100.0 * np.cumprod(1.0 + rets)
    return pd.Series(prices)


def test_correlation_matrix_highly_correlated():
    # Asset A and Asset B move almost identically
    s_a = _make_prices(50, seed=1)
    s_b = s_a * 1.5 + np.random.normal(0, 0.01, 50)  # ~1.0 corr
    price_data = {"BTC": s_a, "ETH": s_b}

    res = compute_correlation_matrix(["BTC", "ETH"], price_data, window=30)
    assert "BTC" in res["matrix"]
    assert "ETH" in res["matrix"]
    assert res["matrix"]["BTC"]["ETH"] is not None
    assert res["matrix"]["BTC"]["ETH"] > 0.8
    assert res["portfolio_avg_correlation"] > 0.8
    assert res["concentration_warning"] is True
    assert res["hhi"] == 0.5  # Equal weight of 2 assets = 0.5


def test_correlation_matrix_uncorrelated():
    s_a = _make_prices(50, trend=1.0, noise=2.0, seed=10)
    s_b = _make_prices(50, trend=-0.5, noise=2.0, seed=99)
    price_data = {"BTC": s_a, "GOLD": s_b}

    res = compute_correlation_matrix(["BTC", "GOLD"], price_data, window=30)
    assert res["matrix"]["BTC"]["GOLD"] is not None
    assert abs(res["matrix"]["BTC"]["GOLD"]) < CONCENTRATION_WARNING_THRESHOLD
    assert res["concentration_warning"] is False


def test_diversification_suggestions():
    s_a = _make_prices(50, seed=1)
    s_b = s_a * 1.2
    s_c = _make_prices(50, trend=-1.0, noise=3.0, seed=888)  # uncorrelated candidate

    price_data = {"BTC": s_a, "ETH": s_b, "PAXG": s_c}

    suggestions = suggest_diversification(
        portfolio_symbols=["BTC", "ETH"],
        universe_symbols=["PAXG"],
        price_data=price_data,
        window=30,
    )

    assert len(suggestions) == 1
    assert suggestions[0]["ticker"] == "PAXG"
    assert suggestions[0]["would_reduce_hhi"] is True


def test_single_symbol_edge_case():
    s_a = _make_prices(50, seed=1)
    price_data = {"BTC": s_a}

    res = compute_correlation_matrix(["BTC"], price_data, window=30)
    assert res["portfolio_avg_correlation"] == 0.0
    assert res["concentration_warning"] is False
    assert res["hhi"] == 1.0


def test_telegram_formatter():
    corr_res = {
        "portfolio_avg_correlation": 0.85,
        "concentration_warning": True,
        "hhi": 0.5,
        "matrix": {"BTC": {"ETH": 0.92}, "ETH": {"BTC": 0.92}},
        "uncorrelated_candidates": ["PAXG", "USO"],
    }
    msg = format_correlation_telegram(corr_res, ["BTC", "ETH"])
    assert "Корелационна Матрица" in msg
    assert "0.85" in msg
    assert "PAXG" in msg


def test_cluster_transition_signals():
    # 3 crypto assets: BTC and ETH are highly correlated (~0.99), SOL is independent/noisy
    s_btc = _make_prices(50, seed=1)
    s_eth = s_btc * 1.5 + np.random.normal(0, 0.01, 50)
    s_sol = _make_prices(50, trend=-0.5, noise=3.0, seed=777)

    price_data = {
        "BTCUSDT": s_btc,
        "ETHUSDT": s_eth,
        "SOLUSDT": s_sol,
    }

    transitions = [
        {"ticker": "BTCUSDT", "asset_class": "crypto", "transition_type": "NEUTRAL_TO_GOLD"},
        {"ticker": "ETHUSDT", "asset_class": "crypto", "transition_type": "NEUTRAL_TO_GOLD"},
        {"ticker": "SOLUSDT", "asset_class": "crypto", "transition_type": "NEUTRAL_TO_GOLD"},
    ]

    clusters = cluster_transition_signals(
        transitions=transitions,
        price_data=price_data,
        correlation_threshold=0.70,
        benchmark_symbol="BTCUSDT",
    )

    assert len(clusters) == 2
    # One cluster has 2 symbols (BTC + ETH), the other has 1 (SOL)
    sizes = sorted([len(c.member_symbols) for c in clusters])
    assert sizes == [1, 2]

    # Find the multi-asset cluster
    macro_cluster = next(c for c in clusters if len(c.member_symbols) == 2)
    assert "BTCUSDT" in macro_cluster.member_symbols
    assert "ETHUSDT" in macro_cluster.member_symbols
    assert macro_cluster.avg_correlation > 0.8
    assert macro_cluster.is_solo is False

    # Find the solo cluster
    solo_cluster = next(c for c in clusters if len(c.member_symbols) == 1)
    assert solo_cluster.leader_symbol == "SOLUSDT"
    assert solo_cluster.is_solo is True

    # Test Telegram alert formatting
    tg_msg = format_cluster_alerts_telegram(clusters)
    assert "Клъстеризирани пазарни преходи" in tg_msg
    assert "BTCUSDT" in tg_msg
    assert "SOLUSDT" in tg_msg
    assert "Внимание" in tg_msg

