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
