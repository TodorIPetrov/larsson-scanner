import pytest
from src.engine.ai_company_map import (
    AI_COMPANY_MAP_SPEC,
    get_ticker_ai_scenarios,
    build_ai_company_map_payload,
)


def test_ai_company_map_structure():
    assert isinstance(AI_COMPANY_MAP_SPEC, list)
    assert len(AI_COMPANY_MAP_SPEC) == 3

    scenario_codes = [s["code"] for s in AI_COMPANY_MAP_SPEC]
    assert scenario_codes == ["S01", "S02", "S03"]

    scenario_ids = [s["id"] for s in AI_COMPANY_MAP_SPEC]
    assert scenario_ids == ["scenario_01", "scenario_02", "scenario_03"]

    for sc in AI_COMPANY_MAP_SPEC:
        assert "id" in sc
        assert "code" in sc
        assert "title" in sc
        assert "title_bg" in sc
        assert "categories" in sc
        assert len(sc["categories"]) > 0
        for cat in sc["categories"]:
            assert "name" in cat
            assert "name_bg" in cat
            assert "benefit" in cat
            assert "benefit_bg" in cat
            assert "companies" in cat
            assert len(cat["companies"]) > 0


def test_get_ticker_ai_scenarios():
    nvda_scenarios = get_ticker_ai_scenarios("NVDA")
    assert "S01" in nvda_scenarios
    assert "S02" in nvda_scenarios
    assert "S03" in nvda_scenarios

    googl_scenarios = get_ticker_ai_scenarios("GOOGL")
    assert "S01" in googl_scenarios
    assert "S02" in googl_scenarios
    assert "S03" in googl_scenarios

    tsm_scenarios = get_ticker_ai_scenarios("TSM")
    assert "S01" in tsm_scenarios
    assert "S02" in tsm_scenarios
    assert "S03" in tsm_scenarios

    asml_scenarios = get_ticker_ai_scenarios("ASML")
    assert "S01" in asml_scenarios
    assert "S02" in asml_scenarios
    assert "S03" in asml_scenarios

    tsla_scenarios = get_ticker_ai_scenarios("TSLA")
    assert "S01" in tsla_scenarios
    assert "S03" in tsla_scenarios

    msft_scenarios = get_ticker_ai_scenarios("MSFT")
    assert "S01" in msft_scenarios
    assert "S02" in msft_scenarios

    crwv_scenarios = get_ticker_ai_scenarios("CRWV")
    assert crwv_scenarios == ["S01"]

    unknown = get_ticker_ai_scenarios("RANDOM_TICKER_XYZ")
    assert unknown == []


def test_build_ai_company_map_payload():
    mock_items = [
        {"ticker": "NVDA", "state": "GOLD", "price": 210.0, "rs_rating": 85, "empirical_tier": "A", "mos_pct": -8.0, "moat": "Wide"},
        {"ticker": "GOOGL", "state": "BLUE", "price": 280.0, "rs_rating": 50, "empirical_tier": "A", "mos_pct": 17.0, "moat": "Wide"},
        {"ticker": "TSM", "state": "GOLD", "price": 418.0, "rs_rating": 75, "empirical_tier": "A", "mos_pct": None, "moat": "Wide"},
        {"ticker": "CRWV", "state": "BLUE", "price": 53.0, "rs_rating": 45, "empirical_tier": "B", "mos_pct": None, "moat": None},
        {"ticker": "TSLA", "state": "GOLD", "price": 250.0, "rs_rating": 80, "empirical_tier": "A", "mos_pct": -15.0, "moat": "Narrow"},
        {"ticker": "MSFT", "state": "GOLD", "price": 520.0, "rs_rating": 75, "empirical_tier": "B", "mos_pct": -10.0, "moat": "Wide"},
    ]

    payload = build_ai_company_map_payload(mock_items)
    assert "title" in payload
    assert "scenarios" in payload
    assert "all_weather_leaders" in payload
    assert "scenarios_breadth" in payload

    assert len(payload["scenarios"]) == 3
    assert len(payload["all_weather_leaders"]) >= 4

    # Check that NVDA, GOOGL, TSM are in all-weather leaders
    aw_tickers = [x["ticker"] for x in payload["all_weather_leaders"]]
    assert "NVDA" in aw_tickers
    assert "GOOGL" in aw_tickers
    assert "TSM" in aw_tickers
    assert "TSLA" in aw_tickers
    assert "MSFT" in aw_tickers

    # Check breadth computation
    s01_breadth = payload["scenarios_breadth"]["S01"]
    assert "total_listed" in s01_breadth
    assert "gold_pct" in s01_breadth
    assert "top_leader" in s01_breadth
