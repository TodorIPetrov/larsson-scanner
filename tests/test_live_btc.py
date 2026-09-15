from src.data.binance_fetch import BinanceFetcher
from src.engine.smma import compute_larsson_series


def test_btc_current_state():
    fetcher = BinanceFetcher()
    res = fetcher.fetch_klines("BTCUSDT", "1D", limit=180)
    assert res is not None
    highs, lows, closes, latest_price = res
    v1, m1, m2, v2, states = compute_larsson_series(highs, lows)

    latest_state = states[-1]
    print(f"\n[BTCUSDT 1D] Price: {latest_price:.2f}")
    print(f"SMMA(15) v1: {v1[-1]:.2f}")
    print(f"SMMA(19) m1: {m1[-1]:.2f}")
    print(f"SMMA(25) m2: {m2[-1]:.2f}")
    print(f"SMMA(29) v2: {v2[-1]:.2f}")
    print(f"Current Larsson State: {latest_state.value}")
    assert latest_state in ["GOLD", "BLUE", "NEUTRAL"]
