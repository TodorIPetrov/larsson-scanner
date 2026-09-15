import numpy as np
import pytest
from src.engine.smma import (
    compute_hl2,
    compute_smma,
    evaluate_larsson_state,
    LarssonState,
    update_incremental_smma,
)


def test_hl2():
    high = np.array([10.0, 20.0, 30.0])
    low = np.array([6.0, 10.0, 20.0])
    hl2 = compute_hl2(high, low)
    np.testing.assert_array_almost_equal(hl2, [8.0, 15.0, 25.0])


def test_smma_calculation():
    # Sequence of 5 numbers, SMMA period 3
    src = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float64)
    res = compute_smma(src, 3)

    assert np.isnan(res[0])
    assert np.isnan(res[1])
    # SMA of first 3 items: (10 + 20 + 30) / 3 = 20.0
    assert pytest.approx(res[2]) == 20.0

    # Index 3: (20.0 * 2 + 40.0) / 3 = 80 / 3 = 26.666666...
    assert pytest.approx(res[3]) == (20.0 * 2 + 40.0) / 3.0

    # Index 4: (26.666666... * 2 + 50.0) / 3 = 34.444444...
    assert pytest.approx(res[4]) == (res[3] * 2 + 50.0) / 3.0


def test_incremental_smma():
    prev = 20.0
    new_val = 40.0
    inc = update_incremental_smma(prev, new_val, 3)
    assert pytest.approx(inc) == (20.0 * 2 + 40.0) / 3.0


def test_larsson_state_gold():
    # Bullish ordering: v1 (15) > m1 (19) > m2 (25) > v2 (29)
    # v1 = 100, m1 = 90, m2 = 80, v2 = 70
    state = evaluate_larsson_state(100.0, 90.0, 80.0, 70.0)
    assert state == LarssonState.GOLD


def test_larsson_state_blue():
    # Bearish ordering: v1 (15) < m1 (19) < m2 (25) < v2 (29)
    # v1 = 70, m1 = 80, m2 = 90, v2 = 100
    state = evaluate_larsson_state(70.0, 80.0, 90.0, 100.0)
    assert state == LarssonState.BLUE


def test_larsson_state_neutral():
    # Mixed: v1 > v2 but v1 < m1
    # v1 = 85, m1 = 90, m2 = 75, v2 = 70
    state = evaluate_larsson_state(85.0, 90.0, 75.0, 70.0)
    assert state == LarssonState.NEUTRAL

    # Another mixed: NaN present
    state_nan = evaluate_larsson_state(np.nan, 90.0, 75.0, 70.0)
    assert state_nan == LarssonState.NEUTRAL
