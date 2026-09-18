import json
import os
import tempfile
import pytest
import yaml

from src.data.asset_manager import AssetManager
from src.storage.database import Database


@pytest.fixture
def temp_environment():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        assets_path = os.path.join(tmpdir, "assets.yaml")
        tv_path = os.path.join(tmpdir, "tv_mapping.json")
        names_path = os.path.join(tmpdir, "names_mapping.json")

        # Initial assets.yaml
        with open(assets_path, "w", encoding="utf-8") as f:
            yaml.dump({"crypto": [], "us_stocks": [], "ai_stocks": []}, f)

        # Initial tv_mapping.json
        with open(tv_path, "w", encoding="utf-8") as f:
            json.dump({"BTCUSDT": "BINANCE:BTCUSDT"}, f)

        # Initial names_mapping.json
        with open(names_path, "w", encoding="utf-8") as f:
            json.dump({"BTCUSDT": "Bitcoin"}, f)

        db = Database(db_path)
        am = AssetManager(
            db=db,
            assets_yaml_path=assets_path,
            tv_mapping_path=tv_path,
            names_mapping_path=names_path,
        )
        yield am, db, assets_path, tv_path, names_path
        db.close()


def test_resolve_tv_symbol(temp_environment):
    am, _, _, _, _ = temp_environment

    # Crypto
    assert am._resolve_tv_symbol("BTCUSDT", "BINANCE", "crypto") == "BINANCE:BTCUSDT"

    # Indices
    assert am._resolve_tv_symbol("^GSPC", "", "indices") == "SP:SPX"
    assert am._resolve_tv_symbol("^IXIC", "", "indices") == "NASDAQ:IXIC"
    assert am._resolve_tv_symbol("^DJI", "", "indices") == "TVC:DJI"

    # Commodities
    assert am._resolve_tv_symbol("GC=F", "", "commodities") == "COMEX:GC1!"
    assert am._resolve_tv_symbol("CL=F", "", "commodities") == "NYMEX:CL1!"

    # Stocks with exchange suffixes
    assert am._resolve_tv_symbol("SAP.DE", "", "intl_stocks") == "XETR:SAP"
    assert am._resolve_tv_symbol("MC.PA", "", "intl_stocks") == "EURONEXT:MC"
    assert am._resolve_tv_symbol("VOD.L", "", "intl_stocks") == "LSE:VOD"

    # US Stocks
    assert am._resolve_tv_symbol("AAPL", "NMS", "us_stocks") == "NASDAQ:AAPL"
    assert am._resolve_tv_symbol("JPM", "NYQ", "us_stocks") == "NYSE:JPM"


def test_validate_and_enrich_invalid(temp_environment):
    am, _, _, _, _ = temp_environment
    res = am.validate_and_enrich("NONEXISTENT_TICKER_9999999")
    assert res is None


def test_add_and_remove_asset(temp_environment):
    am, db, assets_path, tv_path, names_path = temp_environment

    # Add a known liquid stock (AAPL)
    ok, msg, info = am.add_asset("AAPL", asset_class="us_stocks", scan_now=True)
    assert ok is True
    assert info is not None
    assert info["ticker"] == "AAPL"
    assert info["asset_class"] == "us_stocks"
    assert "Apple" in info["name"]
    assert info["state"] in ["GOLD", "BLUE", "NEUTRAL"]
    assert info["price"] > 0

    # Verify assets.yaml was updated
    with open(assets_path, "r", encoding="utf-8") as f:
        y_data = yaml.safe_load(f)
    assert any(item["ticker"] == "AAPL" for item in y_data.get("us_stocks", []))

    # Verify tv_mapping.json was updated
    with open(tv_path, "r", encoding="utf-8") as f:
        tv_data = json.load(f)
    assert "AAPL" in tv_data

    # Verify names_mapping.json was updated
    with open(names_path, "r", encoding="utf-8") as f:
        names_data = json.load(f)
    assert "AAPL" in names_data

    # Verify DB has active symbol
    symbols = db.get_active_symbols("us_stocks")
    assert any(s["ticker"] == "AAPL" for s in symbols)

    # Now remove asset
    rem_ok, rem_msg = am.remove_asset("AAPL")
    assert rem_ok is True

    # Verify assets.yaml no longer contains AAPL
    with open(assets_path, "r", encoding="utf-8") as f:
        y_data_after = yaml.safe_load(f)
    assert not any(item["ticker"] == "AAPL" for item in y_data_after.get("us_stocks", []))

    # Verify DB marks AAPL as inactive
    active_after = db.get_active_symbols("us_stocks")
    assert not any(s["ticker"] == "AAPL" for s in active_after)
