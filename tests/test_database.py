import os
import tempfile
import pytest
from src.engine.smma import LarssonState
from src.storage.database import Database


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    db = Database(temp_path)
    yield db
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_symbols_upsert_and_retrieve(temp_db):
    temp_db.upsert_symbols([
        ("BTCUSDT", "crypto", "BINANCE:BTCUSDT"),
        ("ETHUSDT", "crypto", "BINANCE:ETHUSDT"),
    ])
    rows = temp_db.get_active_symbols("crypto")
    assert len(rows) == 2
    assert rows[0]["ticker"] == "BTCUSDT"
    assert rows[1]["tv_symbol"] == "BINANCE:ETHUSDT"


def test_state_change_detection(temp_db):
    temp_db.upsert_symbols([("BTCUSDT", "crypto", "BINANCE:BTCUSDT")])

    # Initial state insert (Cold start -> no alert triggered on cold start)
    changed, old = temp_db.update_state("BTCUSDT", "1D", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 50000.0)
    assert changed is False
    assert old is None

    # Update with same state -> changed is False
    changed, old = temp_db.update_state("BTCUSDT", "1D", 10.1, 9.1, 8.1, 7.1, LarssonState.GOLD, 50500.0)
    assert changed is False
    assert old == LarssonState.GOLD

    # Update with new state -> changed is True
    changed, old = temp_db.update_state("BTCUSDT", "1D", 9.0, 10.0, 8.0, 7.0, LarssonState.NEUTRAL, 49000.0)
    assert changed is True
    assert old == LarssonState.GOLD


def test_sr_levels_upsert_and_retrieve(temp_db):
    temp_db.upsert_sr_levels(
        ticker="BTCUSDT",
        timeframe="1D",
        current_price=68000.0,
        atr=1500.0,
        s1=64000.0,
        s1_touches=3,
        s1_dist_pct=5.88,
        r1=70000.0,
        r1_touches=4,
        r1_dist_pct=2.94,
        context_flag="IN_VALUE_RANGE",
        context_desc="Range test",
    )

    row = temp_db.get_sr_levels("BTCUSDT", "1D")
    assert row is not None
    assert row["ticker"] == "BTCUSDT"
    assert row["s1"] == 64000.0
    assert row["s1_touches"] == 3
    assert row["r1"] == 70000.0
    assert row["r1_touches"] == 4
    assert row["context_flag"] == "IN_VALUE_RANGE"


def test_trade_suggestions_upsert_and_retrieve(temp_db):
    temp_db.upsert_symbols([("BTCUSDT", "crypto", "BINANCE:BTCUSDT")])
    temp_db.update_state("BTCUSDT", "1D", 10.0, 9.0, 8.0, 7.0, LarssonState.GOLD, 68000.0)

    temp_db.upsert_trade_suggestion(
        ticker="BTCUSDT",
        timeframe="1D",
        action="SPOT_BUY",
        direction="LONG",
        setup_type="PULLBACK_VALUE_BUY",
        entry_price=68000.0,
        stop_loss=64000.0,
        tp1=76000.0,
        tp2=82000.0,
        rr_ratio=2.0,
        score=90,
        tier="A+",
        reason_bg="Тестово описание",
        reason_en="Test description",
    )

    row = temp_db.get_trade_suggestion("BTCUSDT", "1D")
    assert row is not None
    assert row["ticker"] == "BTCUSDT"
    assert row["action"] == "SPOT_BUY"
    assert row["tier"] == "A+"
    assert row["rr_ratio"] == 2.0

    all_states = temp_db.get_all_states()
    assert len(all_states) == 1
    assert all_states[0]["ts_action"] == "SPOT_BUY"
    assert all_states[0]["ts_tier"] == "A+"
    assert all_states[0]["ts_rr"] == 2.0


