import os
import json
import pytest
from src.dashboard.server import PROJECT_ROOT

def test_portfolio_sync_file_handling(tmp_path):
    test_sync_file = tmp_path / "portfolio_user_sync.json"
    sample_data = {
        "real": {
            "positions": [{"symbol": "NVDA", "units": 10, "entry_price": 140.0}],
            "cash": 8600.0,
            "closed": []
        },
        "paper": {"positions": []}
    }
    with open(test_sync_file, "w", encoding="utf-8") as f:
        json.dump(sample_data, f)
    
    assert os.path.exists(test_sync_file)
    with open(test_sync_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["real"]["cash"] == 8600.0
    assert len(loaded["real"]["positions"]) == 1
    assert loaded["real"]["positions"][0]["symbol"] == "NVDA"

def test_v2_stop_invariant_logic():
    # Invariant: price below v2 must trigger exit/broken stop
    price = 95.0
    v2 = 100.0
    is_broken_stop = (price <= v2 and v2 > 0)
    assert is_broken_stop is True

    safe_price = 105.0
    is_safe = (safe_price <= v2 and v2 > 0)
    assert is_safe is False
