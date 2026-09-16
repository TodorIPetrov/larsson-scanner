import pytest
from src.engine.trade_suggestions import calculate_position_size


def test_calculate_position_size_standard_equity():
    # Account ,000, 1% risk ( risk)
    # Entry: .0, SL: .0 -> Risk per share = .0
    # Expected units =  /  = 20 shares
    res = calculate_position_size(
        entry_price=100.0,
        stop_loss=95.0,
        account_size=10000.0,
        risk_pct=1.0,
        tp1=110.0,
        tp2=125.0,
    )
    assert res['risk_usd'] == 100.0
    assert res['risk_per_unit'] == 5.0
    assert res['units'] == 20.0
    assert res['position_value'] == 2000.0
    assert res['profit_tp1_usd'] == 200.0
    assert res['profit_tp2_usd'] == 500.0


def test_calculate_position_size_crypto_decimals():
    # BTC trade: Entry ,000, SL ,500 (,500 risk per BTC)
    # Account ,000, 2% risk (,000 risk)
    # Expected units = 1000 / 3500 = 0.2857 BTC
    res = calculate_position_size(
        entry_price=70000.0,
        stop_loss=66500.0,
        account_size=50000.0,
        risk_pct=2.0,
        tp1=77000.0,
    )
    assert res['risk_usd'] == 1000.0
    assert res['risk_per_unit'] == 3500.0
    assert abs(res['units'] - 0.29) < 0.05
    assert res['profit_tp1_usd'] > 1800.0


def test_calculate_position_size_zero_or_invalid():
    res = calculate_position_size(entry_price=0.0, stop_loss=0.0)
    assert res['units'] == 0.0
    assert res['risk_usd'] == 0.0

    # Entry == SL
    res2 = calculate_position_size(entry_price=100.0, stop_loss=100.0)
    assert res2['units'] == 0.0
