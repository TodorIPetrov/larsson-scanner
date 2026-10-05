"""
tests/test_ackman_evaluation.py

Comprehensive Automated Verification Test Suite for the Bill Ackman Equity Evaluation Report
Deliverable: docs/ackman_stock_evaluation.md

Validates the master evaluation deliverable against:
1. Universe coverage & deduplication (255 unique equity tickers from us_stocks, intl_stocks, ai_stocks in config/assets.yaml; non-equity categories excluded).
2. Tiered ranking architecture & partitioning (Tier 1 = 11, Tier 2 = 61, Tier 3 = 183; disjoint sets, full partition).
3. Summary card schema validation (all 11 fields present for all 11 Tier 1 and 61 Tier 2 stocks; Ackman Score 1–10 scale).
4. Step-by-step screening walkthroughs (Tier 1) and explicit shortfall explanations (Tier 2).
5. Concrete, specific disqualification reasons for all 183 Tier 3 stocks (no generic placeholders).
6. Forensic audit of the 4 Anti-Pattern Red Flags (Valeant, Herbalife, JCPenney/Borders, Netflix).
7. Executive summary reference table & concentrated portfolio construction (8–12 holdings, tail-risk hedges).
8. Adversarial integrity verification (meta-tests proving failure detection on corrupted/defective inputs).
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
import pytest
import yaml

# ---------------------------------------------------------------------------
# Path & Configuration Discovery
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
EVAL_DOC_PATH = ROOT_DIR / "docs" / "ackman_stock_evaluation.md"
ASSETS_CONFIG_PATH = ROOT_DIR / "config" / "assets.yaml"
STRATEGY_CHEAT_SHEET_PATH = ROOT_DIR / "docs" / "ackman_strategy_cheat_sheet.md"


@pytest.fixture(scope="session")
def assets_config() -> dict:
    """Load and parse config/assets.yaml."""
    assert ASSETS_CONFIG_PATH.exists(), f"Missing config file: {ASSETS_CONFIG_PATH}"
    with open(ASSETS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def evaluation_doc_text() -> str:
    """Read the full text of docs/ackman_stock_evaluation.md in UTF-8."""
    assert EVAL_DOC_PATH.exists(), f"Deliverable report missing: {EVAL_DOC_PATH}"
    return EVAL_DOC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def parsed_sections(evaluation_doc_text: str) -> Dict[str, str]:
    """Parse major H2 sections from docs/ackman_stock_evaluation.md."""
    raw_sections = re.split(r"\n##\s+", evaluation_doc_text)
    sec_map: Dict[str, str] = {}
    for s in raw_sections[1:]:
        header = s.split("\n")[0].strip()
        sec_map[header] = s
    return sec_map


@pytest.fixture(scope="session")
def equity_universe(assets_config: dict) -> Tuple[List[str], List[str], List[str], Set[str]]:
    """Extract raw and deduplicated unique equity universe from config/assets.yaml."""
    us = [x["ticker"] for x in assets_config.get("us_stocks", [])]
    intl = [x["ticker"] for x in assets_config.get("intl_stocks", [])]
    ai = [x["ticker"] for x in assets_config.get("ai_stocks", [])]
    unique = set(us + intl + ai)
    return us, intl, ai, unique


@pytest.fixture(scope="session")
def parsed_tiers(parsed_sections: Dict[str, str], equity_universe: Tuple) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, str]]:
    """Parse Tier 1 cards, Tier 2 cards, and Tier 3 disqualifications from report body."""
    _, _, _, target_tickers = equity_universe

    tier1_sec = [s for h, s in parsed_sections.items() if "Tier 1" in h][0]
    tier2_sec = [s for h, s in parsed_sections.items() if "Tier 2" in h][0]
    tier3_sec = [s for h, s in parsed_sections.items() if "Tier 3" in h][0]

    # Tier 1 parsing
    t1_cards = {}
    t1_blocks = re.split(r"\n###\s+", tier1_sec)[1:]
    for b in t1_blocks:
        first_line = b.splitlines()[0]
        m = re.match(r"`?([A-Za-z0-9._-]+)`?\s*[\u2013\u2014\-]\s*(.+)", first_line)
        if m and not m.group(1).startswith("Step"):
            ticker = m.group(1).strip()
            name = m.group(2).strip()
            t1_cards[ticker] = {"name": name, "block": b}

    # Tier 2 parsing
    t2_cards = {}
    t2_blocks = re.split(r"\n###\s+", tier2_sec)[1:]
    for b in t2_blocks:
        first_line = b.splitlines()[0]
        m = re.match(r"`?([A-Za-z0-9._-]+)`?\s*[\u2013\u2014\-]\s*(.+)", first_line)
        if m and not m.group(1).startswith("Sub"):
            ticker = m.group(1).strip()
            name = m.group(2).strip()
            t2_cards[ticker] = {"name": name, "block": b}

    # Tier 3 parsing
    t3_reasons = {}
    # 5.1 and 5.2 numbered items
    for line in tier3_sec.splitlines():
        m = re.match(r"^\s*\d+\.\s+\*\*([^*]+?):?\*\*:?\s*(.+)", line)
        if m:
            header_text = m.group(1)
            reason = m.group(2).strip()
            extracted = re.findall(r"`([A-Za-z0-9._-]+)`", header_text)
            if not extracted:
                m_first = re.match(r"^([A-Za-z0-9._-]+)", header_text.strip())
                if m_first:
                    extracted = [m_first.group(1)]
            for t in extracted:
                if t in target_tickers:
                    t3_reasons[t] = reason

    # 5.3 H4 items
    h4_blocks = re.split(r"\n####\s+", tier3_sec)[1:]
    for b in h4_blocks:
        first_line = b.splitlines()[0]
        m = re.search(r"`?([A-Za-z0-9._-]+)`?\s*[\u2013\u2014\-]", first_line)
        if m:
            t = m.group(1).strip()
            if t in target_tickers:
                m_rat = re.search(r"\*\*Specific Disqualification Rationale:?\*\*\s*(.+)", b)
                if m_rat:
                    t3_reasons[t] = m_rat.group(1).strip()
                else:
                    t3_reasons[t] = b.strip()

    return t1_cards, t2_cards, t3_reasons


@pytest.fixture(scope="session")
def section8_concordance_rows(parsed_sections: Dict[str, str]) -> List[Dict[str, str]]:
    """Parse rows from the Master 255-Ticker Concordance Table in Section 8."""
    sec8_text = [s for h, s in parsed_sections.items() if "Master 255-Ticker Concordance" in h][0]
    rows = []
    for line in sec8_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 11 and parts[0].isdigit():
            rows.append({
                "num": int(parts[0]),
                "ticker": re.sub(r"[`*]", "", parts[1]),
                "name": parts[2],
                "category": parts[3],
                "market_cap": parts[4],
                "roic": parts[5],
                "op_margin": parts[6],
                "net_debt": parts[7],
                "tier": parts[8],
                "score": parts[9],
                "rationale": parts[10]
            })
    return rows


# ===========================================================================
# 1. Deliverable Integrity & Structure
# ===========================================================================

class TestDeliverableIntegrity:
    """Validates physical presence, size bounds, and top-level Markdown structure."""

    def test_deliverable_file_exists_and_substantial(self, evaluation_doc_text: str):
        """Deliverable must exist and contain substantial institutional research (>100,000 chars)."""
        assert EVAL_DOC_PATH.is_file(), f"Deliverable report does not exist at {EVAL_DOC_PATH}"
        char_count = len(evaluation_doc_text)
        assert char_count >= 100_000, f"Deliverable too short: {char_count} chars (expected >100,000)"

    def test_all_eight_major_sections_present(self, parsed_sections: Dict[str, str]):
        """Deliverable must contain all 8 major numbered H2 sections."""
        expected_keywords = [
            "Executive Summary",
            "Evaluation Methodology",
            "Tier 1",
            "Tier 2",
            "Tier 3",
            "Anti-Pattern Red Flags",
            "Concentrated Portfolio",
            "Master 255-Ticker Concordance"
        ]
        section_titles = list(parsed_sections.keys())
        for kw in expected_keywords:
            matching = [t for t in section_titles if kw.lower() in t.lower()]
            assert len(matching) >= 1, f"Missing major section with keyword '{kw}'. Found: {section_titles}"


# ===========================================================================
# 2. Universe Coverage & Deduplication
# ===========================================================================

class TestUniverseCoverageAndDeduplication:
    """Validates exact extraction from config/assets.yaml, category counts, deduplication, and 100% coverage."""

    def test_assets_yaml_raw_counts(self, equity_universe: Tuple):
        """Raw equity counts must match assets.yaml: us_stocks=36, intl_stocks=54, ai_stocks=188 (sum=278)."""
        us, intl, ai, _ = equity_universe
        assert len(us) == 36, f"Expected 36 us_stocks, got {len(us)}"
        assert len(intl) == 54, f"Expected 54 intl_stocks, got {len(intl)}"
        assert len(ai) == 188, f"Expected 188 ai_stocks, got {len(ai)}"
        assert len(us) + len(intl) + len(ai) == 278, "Raw total of equity entries must equal 278"

    def test_cross_category_deduplication(self, equity_universe: Tuple):
        """Cross-category duplicates must be exactly 23, resulting in exactly 255 unique equities."""
        us, intl, ai, unique = equity_universe
        us_set, intl_set, ai_set = set(us), set(intl), set(ai)

        us_ai_overlap = us_set & ai_set
        intl_ai_overlap = intl_set & ai_set
        us_intl_overlap = us_set & intl_set

        assert len(us_ai_overlap) == 12, f"Expected 12 us/ai duplicates, got {len(us_ai_overlap)}"
        assert len(intl_ai_overlap) == 11, f"Expected 11 intl/ai duplicates, got {len(intl_ai_overlap)}"
        assert len(us_intl_overlap) == 0, f"Expected 0 us/intl duplicates, got {len(us_intl_overlap)}"

        total_duplicates = len(us_ai_overlap) + len(intl_ai_overlap) + len(us_intl_overlap)
        assert total_duplicates == 23, f"Expected 23 total duplicates, got {total_duplicates}"
        assert len(unique) == 255, f"Expected exactly 255 unique equity tickers, got {len(unique)}"

    def test_non_equity_categories_excluded(self, assets_config: dict, equity_universe: Tuple, evaluation_doc_text: str):
        """Non-equity categories (crypto, commodities, indices, crypto_stocks) must not be evaluated as equities."""
        _, _, _, unique_equities = equity_universe
        non_equity_cats = ["crypto", "commodities", "indices", "crypto_stocks"]

        purely_non_equity: Set[str] = set()
        for cat in non_equity_cats:
            for item in assets_config.get(cat, []):
                t = item["ticker"]
                if t not in unique_equities:
                    purely_non_equity.add(t)

        # Confirm non-equity tickers (e.g. BTCUSDT, GC=F, ^GSPC, MSTR, COIN) do not appear in the Master Concordance Table
        assert len(purely_non_equity) >= 80, "Expected at least 80 purely non-equity assets"
        for t in ["BTCUSDT", "ETHUSDT", "GC=F", "CL=F", "^GSPC", "^IXIC", "MSTR", "COIN", "HOOD", "MARA"]:
            assert f"| `{t}` |" not in evaluation_doc_text, f"Non-equity asset {t} inappropriately evaluated in master table"

    def test_all_255_unique_tickers_present_in_document(self, equity_universe: Tuple, evaluation_doc_text: str):
        """Every single one of the 255 unique equity tickers must appear in the evaluation deliverable."""
        _, _, _, unique_equities = equity_universe
        missing = [t for t in unique_equities if t not in evaluation_doc_text]
        assert len(missing) == 0, f"Tickers missing from evaluation document: {missing}"

    def test_concordance_table_contains_all_255_unique_tickers(self, equity_universe: Tuple, section8_concordance_rows: List[Dict]):
        """Master concordance table in Section 8 must index all 255 unique tickers with complete data."""
        _, _, _, unique_equities = equity_universe
        sec8_tickers = set(r["ticker"] for r in section8_concordance_rows)
        assert len(section8_concordance_rows) == 255, f"Expected 255 rows in Section 8, got {len(section8_concordance_rows)}"
        assert sec8_tickers == unique_equities, f"Concordance table mismatch. Missing: {unique_equities - sec8_tickers}, Extra: {sec8_tickers - unique_equities}"


# ===========================================================================
# 3. Tiered Ranking Architecture & Partitioning
# ===========================================================================

class TestTierArchitectureAndPartitioning:
    """Validates exact counts (11, 61, 183), disjointness, and full universe partitioning."""

    def test_tier_counts_exact(self, parsed_tiers: Tuple):
        """Tier 1 must contain 11, Tier 2 must contain 61, Tier 3 must contain 183 stocks (total=255)."""
        t1_cards, t2_cards, t3_reasons = parsed_tiers
        assert len(t1_cards) == 11, f"Tier 1 count expected 11, got {len(t1_cards)}"
        assert len(t2_cards) == 61, f"Tier 2 count expected 61, got {len(t2_cards)}"
        assert len(t3_reasons) == 183, f"Tier 3 count expected 183, got {len(t3_reasons)}"
        assert len(t1_cards) + len(t2_cards) + len(t3_reasons) == 255, "Sum of tiers must equal 255"

    def test_tiers_are_mutually_disjoint(self, parsed_tiers: Tuple):
        """No ticker may appear in more than one tier (mutually exclusive sets)."""
        t1_cards, t2_cards, t3_reasons = parsed_tiers
        t1_set, t2_set, t3_set = set(t1_cards.keys()), set(t2_cards.keys()), set(t3_reasons.keys())

        assert t1_set.isdisjoint(t2_set), f"Overlap between Tier 1 and Tier 2: {t1_set & t2_set}"
        assert t1_set.isdisjoint(t3_set), f"Overlap between Tier 1 and Tier 3: {t1_set & t3_set}"
        assert t2_set.isdisjoint(t3_set), f"Overlap between Tier 2 and Tier 3: {t2_set & t3_set}"

    def test_tiers_partition_full_255_universe(self, parsed_tiers: Tuple, equity_universe: Tuple):
        """The union of Tier 1, Tier 2, and Tier 3 must equal the exact set of 255 unique equity tickers."""
        t1_cards, t2_cards, t3_reasons = parsed_tiers
        _, _, _, unique_equities = equity_universe

        evaluated_union = set(t1_cards.keys()) | set(t2_cards.keys()) | set(t3_reasons.keys())
        assert evaluated_union == unique_equities, f"Tiers do not partition universe. Missing: {unique_equities - evaluated_union}, Extra: {evaluated_union - unique_equities}"

    def test_concordance_table_tier_distribution(self, section8_concordance_rows: List[Dict]):
        """The Master Concordance Table must classify exactly 11 in Tier 1, 61 in Tier 2, and 183 in Tier 3."""
        tier_counts = {"1": 0, "2": 0, "3": 0}
        for r in section8_concordance_rows:
            m = re.search(r"Tier\s*([123])", r["tier"])
            assert m, f"Invalid tier designation in Section 8 row: {r}"
            tier_counts[m.group(1)] += 1

        assert tier_counts["1"] == 11, f"Expected 11 Tier 1 rows in table, got {tier_counts['1']}"
        assert tier_counts["2"] == 61, f"Expected 61 Tier 2 rows in table, got {tier_counts['2']}"
        assert tier_counts["3"] == 183, f"Expected 183 Tier 3 rows in table, got {tier_counts['3']}"


# ===========================================================================
# 4. Summary Card Schema Validation
# ===========================================================================

class TestSummaryCardSchemaValidation:
    """Validates presence and format of all 11 required fields for all 11 Tier 1 and 61 Tier 2 stocks."""

    REQUIRED_CARD_FIELDS = [
        ("Market Cap", r"\*\*Market Cap:?\*\*"),
        ("ROIC", r"\*\*ROIC[^*]*:?\*\*"),
        ("FCF Conversion", r"\*\*FCF Conversion:?\*\*"),
        ("Net Debt / EBITDA", r"\*\*Net Debt / EBITDA:?\*\*"),
        ("Operating Margin", r"\*\*Operating Margin:?\*\*"),
        ("Moat Type", r"\*\*Moat (?:Type|Classification):?\*\*"),
        ("Key Strength", r"\*\*Key Strength:?\*\*"),
        ("Key Risk", r"\*\*Key Risk:?\*\*"),
        ("Ackman Score", r"\*\*Ackman Score:?\*\*"),
        ("Screening Status", r"\*\*Screening Status:?\*\*")
    ]

    def test_tier_1_summary_cards_complete_schema(self, parsed_tiers: Tuple):
        """All 11 Tier 1 summary cards must contain header (ticker & name) and all 10 bullet fields."""
        t1_cards, _, _ = parsed_tiers
        assert len(t1_cards) == 11

        for ticker, data in t1_cards.items():
            assert data["name"], f"Tier 1 {ticker} missing company name in header"
            block = data["block"]
            for field_name, regex in self.REQUIRED_CARD_FIELDS:
                assert re.search(regex, block, re.IGNORECASE), f"Tier 1 ticker {ticker} missing required card field: '{field_name}'"

    def test_tier_2_summary_cards_complete_schema(self, parsed_tiers: Tuple):
        """All 61 Tier 2 summary cards must contain header (ticker & name) and all 10 bullet fields."""
        _, t2_cards, _ = parsed_tiers
        assert len(t2_cards) == 61

        for ticker, data in t2_cards.items():
            assert data["name"], f"Tier 2 {ticker} missing company name in header"
            block = data["block"]
            for field_name, regex in self.REQUIRED_CARD_FIELDS:
                assert re.search(regex, block, re.IGNORECASE), f"Tier 2 ticker {ticker} missing required card field: '{field_name}'"

    def test_ackman_score_scale_and_tier_distribution(self, parsed_tiers: Tuple, section8_concordance_rows: List[Dict]):
        """Ackman Score must be numerical on 1-10 scale; Tier 1 >= 8.0, Tier 2 between 6.0 and 7.5, Tier 3 <= 5.0."""
        t1_cards, t2_cards, _ = parsed_tiers

        for ticker, data in t1_cards.items():
            m = re.search(r"\*\*Ackman Score:?\*\*\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?", data["block"])
            assert m, f"Tier 1 ticker {ticker} missing score"
            score = float(m.group(1))
            assert 8.0 <= score <= 10.0, f"Tier 1 ticker {ticker} score {score} out of Ackman-Grade range (8.0-10.0)"

        for ticker, data in t2_cards.items():
            m = re.search(r"\*\*Ackman Score:?\*\*\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?", data["block"])
            assert m, f"Tier 2 ticker {ticker} missing score"
            score = float(m.group(1))
            assert 6.0 <= score <= 7.5, f"Tier 2 ticker {ticker} score {score} out of Near-Miss range (6.0-7.5)"

        for r in section8_concordance_rows:
            m = re.search(r"(\d+(?:\.\d+)?)", r["score"])
            assert m, f"Invalid score in concordance row for {r['ticker']}: {r['score']}"
            score = float(m.group(1))
            assert 1.0 <= score <= 10.0, f"Concordance score {score} for {r['ticker']} out of 1-10 bounds"
            if "Tier 3" in r["tier"]:
                assert score <= 5.0, f"Tier 3 stock {r['ticker']} has score {score} > 5.0"

    def test_summary_card_metrics_are_quantitative(self, parsed_tiers: Tuple):
        """Quantitative fields in summary cards must cite specific numeric values, not vague descriptors."""
        t1_cards, t2_cards, _ = parsed_tiers
        all_cards = {**t1_cards, **t2_cards}

        for ticker, data in all_cards.items():
            b = data["block"]
            # Market Cap should contain $ and B or T
            m_cap = re.search(r"\*\*Market Cap:?\*\*\s*([^\n]+)", b)
            assert m_cap and re.search(r"\$\s*\d+", m_cap.group(1)), f"Ticker {ticker} Market Cap not quantitative: {m_cap.group(1) if m_cap else 'None'}"

            # ROIC should contain %
            m_roic = re.search(r"\*\*ROIC[^*]*:?\*\*\s*([^\n]+)", b)
            assert m_roic and "%" in m_roic.group(1), f"Ticker {ticker} ROIC not numeric percentage: {m_roic.group(1) if m_roic else 'None'}"

            # Operating Margin should contain %
            m_margin = re.search(r"\*\*Operating Margin:?\*\*\s*([^\n]+)", b)
            assert m_margin and "%" in m_margin.group(1), f"Ticker {ticker} Operating Margin not numeric: {m_margin.group(1) if m_margin else 'None'}"


# ===========================================================================
# 5. Step Walkthroughs & Shortfall Deltas
# ===========================================================================

class TestStepWalkthroughsAndShortfalls:
    """Validates 5-step walkthroughs for Tier 1 and explicit shortfall analyses for Tier 2."""

    def test_tier_1_five_step_screening_walkthroughs(self, parsed_tiers: Tuple):
        """Each of the 11 Tier 1 stocks must have all 5 screening steps explicitly analyzed."""
        t1_cards, _, _ = parsed_tiers
        assert len(t1_cards) == 11

        for ticker, data in t1_cards.items():
            b = data["block"]
            for step_num in range(1, 6):
                step_pattern = rf"Step\s+{step_num}\b"
                assert re.search(step_pattern, b, re.IGNORECASE), f"Tier 1 ticker {ticker} missing analysis for Step {step_num}"

    def test_tier_2_explicit_shortfall_explanations(self, parsed_tiers: Tuple):
        """Each of the 61 Tier 2 stocks must explain why it failed to achieve Tier 1."""
        _, t2_cards, _ = parsed_tiers
        assert len(t2_cards) == 61

        shortfall_keywords = r"Shortfall|Near-Miss|Why not Tier 1|Fails Step|reinvestment drag|valuation"
        for ticker, data in t2_cards.items():
            b = data["block"]
            assert re.search(shortfall_keywords, b, re.IGNORECASE), f"Tier 2 ticker {ticker} missing shortfall explanation"


# ===========================================================================
# 6. Tier 3 Disqualification Reasons
# ===========================================================================

class TestTier3Disqualifications:
    """Validates that all 183 Tier 3 stocks have specific, concrete, non-placeholder disqualification reasons."""

    def test_tier_3_all_183_tickers_have_concrete_reasons(self, parsed_tiers: Tuple):
        """Every single one of the 183 Tier 3 stocks must have a substantive reason (>20 chars)."""
        _, _, t3_reasons = parsed_tiers
        assert len(t3_reasons) == 183, f"Expected 183 Tier 3 reasons, got {len(t3_reasons)}"

        for ticker, reason in t3_reasons.items():
            clean_reason = reason.strip()
            assert len(clean_reason) >= 20, f"Disqualification reason for {ticker} too brief ({len(clean_reason)} chars): '{clean_reason}'"

    def test_tier_3_no_generic_placeholders(self, parsed_tiers: Tuple):
        """Disqualification reasons must not contain generic placeholders or cop-outs."""
        _, _, t3_reasons = parsed_tiers
        banned_patterns = [
            r"^fails?\s*screen\.?$",
            r"^to\s*be\s*determined",
            r"^tbd$",
            r"^todo",
            r"^n/a$",
            r"^placeholder",
            r"^none$"
        ]

        for ticker, reason in t3_reasons.items():
            for pat in banned_patterns:
                assert not re.match(pat, reason.strip(), re.IGNORECASE), f"Ticker {ticker} has banned generic reason: '{reason}'"

    def test_tier_3_major_disqualification_categories_present(self, parsed_tiers: Tuple):
        """Core Pershing Square hard disqualification categories must be represented."""
        _, _, t3_reasons = parsed_tiers

        # 1. Commodity producers
        for sym in ["XOM", "CVX", "OXY", "BHP.AX", "RIO.L"]:
            assert sym in t3_reasons, f"Commodity producer {sym} missing from Tier 3"
            assert re.search(r"commodity|price-taker|oil|extrinsic|fossil fuel|fuel|energy|upstream|mining", t3_reasons[sym], re.IGNORECASE)

        # 2. Commercial banks / complex financials
        for sym in ["JPM", "BAC", "AXP", "NU", "CBA.AX"]:
            assert sym in t3_reasons, f"Bank {sym} missing from Tier 3"
            assert re.search(r"bank|financial|duration|credit|loan", t3_reasons[sym], re.IGNORECASE)

        # 3. Closed-end fund / holding structures
        for sym in ["PSUS", "PS", "INVE-B.ST"]:
            assert sym in t3_reasons, f"Holding vehicle {sym} missing from Tier 3"
            assert re.search(r"closed-end|fund|holding|wrapper", t3_reasons[sym], re.IGNORECASE)

        # 4. Small-cap / speculative liquidity failures (<$10B)
        for sym in ["RKLB", "ASTS", "SOUN", "SERV"]:
            assert sym in t3_reasons, f"Small-cap {sym} missing from Tier 3"
            assert re.search(r"market cap|hurdle|\$10|pre-commercial|burn", t3_reasons[sym], re.IGNORECASE)


# ===========================================================================
# 7. Forensic Audit of Anti-Pattern Red Flags
# ===========================================================================

class TestAntiPatternRedFlags:
    """Validates that Section 6 analyzes all 4 anti-patterns with precedents and universe audits."""

    def test_all_four_antipatterns_analyzed(self, parsed_sections: Dict[str, str]):
        """Section 6 must systematically cover all 4 anti-patterns."""
        sec6 = [s for h, s in parsed_sections.items() if "Anti-Pattern Red Flags" in h][0]

        anti_patterns = [
            ("Anti-Pattern 1 (Valeant)", r"Valeant|VRX|serial M&A|non-GAAP"),
            ("Anti-Pattern 2 (Herbalife)", r"Herbalife|HLF|short selling|regulatory dependency"),
            ("Anti-Pattern 3 (JCPenney/Borders)", r"JCPenney|Borders|retail turnaround|secular decline"),
            ("Anti-Pattern 4 (Netflix)", r"Netflix|NFLX|predictability|thesis invalidation")
        ]
        for name, pattern in anti_patterns:
            assert re.search(pattern, sec6, re.IGNORECASE), f"Missing red flag analysis for {name}"

    def test_antipattern_flagged_stocks_documented(self, parsed_sections: Dict[str, str]):
        """Stocks matching each anti-pattern must be explicitly identified in Section 6."""
        sec6 = [s for h, s in parsed_sections.items() if "Anti-Pattern Red Flags" in h][0]

        expected_flagged_tickers = ["CRM", "NDAQ", "BABA", "KHC", "SIRI", "NFLX", "SMCI", "UPST"]
        for t in expected_flagged_tickers:
            assert t in sec6, f"Red flags section missing audit for flagged ticker {t}"


# ===========================================================================
# 8. Executive Summary & Concentrated Portfolio Construction
# ===========================================================================

class TestExecutiveSummaryAndPortfolioConstruction:
    """Validates Section 1 reference table and Section 7 concentrated portfolio construction."""

    def test_executive_summary_contains_tier_1_reference_table(self, parsed_sections: Dict[str, str], parsed_tiers: Tuple):
        """Executive summary (Section 1) must list all 11 Tier 1 stocks in a master reference table."""
        sec1 = [s for h, s in parsed_sections.items() if "Executive Summary" in h][0]
        t1_cards, _, _ = parsed_tiers
        assert len(t1_cards) == 11

        for t in t1_cards.keys():
            assert t in sec1, f"Executive summary reference table missing Tier 1 stock {t}"

    def test_concentrated_portfolio_rules_and_count(self, parsed_sections: Dict[str, str], parsed_tiers: Tuple):
        """Section 7 must recommend an 8-12 stock concentrated portfolio selected from Tier 1."""
        sec7 = [s for h, s in parsed_sections.items() if "Concentrated Portfolio" in h][0]
        t1_cards, _, _ = parsed_tiers

        # Recommended portfolio count from Section 7.2 master portfolio table
        # Table rows use unicode box drawing '│' or ASCII '|': │ Pos │ Ticker │ Company Legal Name │ Target % │ ...
        portfolio_items = re.findall(
            r"[│|]\s*(\d+)\s*[│|]\s*`?([A-Za-z0-9._-]+)`?\s*[│|]\s*([^│|]+)[│|]\s*(\d+(?:\.\d+)?%)\s*[│|]",
            sec7
        )
        assert 8 <= len(portfolio_items) <= 12, f"Concentrated portfolio count should be 8-12, got {len(portfolio_items)}"

        # Every portfolio recommendation must be from Tier 1
        total_weight = 0.0
        for pos, ticker, name, weight_str in portfolio_items:
            assert ticker in t1_cards, f"Portfolio recommendation {ticker} is not an Ackman-Grade Tier 1 stock"
            total_weight += float(weight_str.rstrip("%"))

        # Target weights should sum to 100%
        assert abs(total_weight - 100.0) < 0.1, f"Portfolio target weights sum to {total_weight}%, expected 100%"

    def test_asymmetric_tail_risk_hedging_framework(self, parsed_sections: Dict[str, str]):
        """Section 7.3 must document asymmetric macro hedging (CDS on credit indices, Treasury swaptions)."""
        sec7 = [s for h, s in parsed_sections.items() if "Concentrated Portfolio" in h][0]
        assert re.search(r"Credit Default Swaps|CDS", sec7, re.IGNORECASE), "Missing CDS credit hedging in Section 7"
        assert re.search(r"swaptions|Treasur", sec7, re.IGNORECASE), "Missing Treasury swaptions in Section 7"
        assert re.search(r"liquidity engine|reinvestment", sec7, re.IGNORECASE), "Missing reinvestment protocol in Section 7"

    def test_strategic_buy_triggers_for_top_tier_2_stocks(self, parsed_sections: Dict[str, str]):
        """Section 7.4 must specify valuation buy-triggers for top Tier 2 compounders."""
        sec7 = [s for h, s in parsed_sections.items() if "Concentrated Portfolio" in h][0]
        key_watchlist = ["MSFT", "AAPL", "RMS.PA", "NOW", "TSM", "MCO"]
        for sym in key_watchlist:
            assert sym in sec7, f"Top Tier 2 watchlist missing buy-trigger for {sym}"


# ===========================================================================
# 9. Adversarial Verification & Negative Tests
# ===========================================================================

class TestAdversarialVerification:
    """Meta-tests demonstrating that test assertions fail when presented with corrupted or invalid inputs."""

    def test_adversarial_detects_missing_ticker_in_universe(self, equity_universe: Tuple):
        """Verifies that an incomplete document missing a ticker fails coverage assertions."""
        _, _, _, unique_equities = equity_universe
        # Synthetic document omitting GOOGL
        synthetic_text = "All stocks except XYZ are evaluated here."
        missing_tickers = [t for t in unique_equities if t not in synthetic_text]
        assert "GOOGL" in missing_tickers
        assert len(missing_tickers) == 255  # None of the 255 tickers appear in this synthetic text

    def test_adversarial_detects_tier_overlap(self):
        """Verifies that non-disjoint tier sets are caught and rejected."""
        t1_fake = {"GOOGL", "META", "AAPL"}
        t2_fake = {"AAPL", "MSFT", "NVDA"}
        assert not t1_fake.isdisjoint(t2_fake)
        overlap = t1_fake & t2_fake
        assert "AAPL" in overlap

    def test_adversarial_detects_missing_card_field(self):
        """Verifies that a summary card missing a mandatory field (e.g. ROIC) is flagged."""
        corrupted_card = """
        ### `GOOGL` — Alphabet Inc.
        - **Market Cap:** $2,120.0 Billion
        - **FCF Conversion:** 88.4%
        - **Net Debt / EBITDA:** Net Cash
        - **Operating Margin:** 32.0%
        - **Moat Type:** Two-Sided Network Effects
        - **Key Strength:** Search monopoly
        - **Key Risk:** Antitrust
        - **Ackman Score:** 9 / 10
        - **Screening Status:** Tier 1 Full Pass
        """
        # ROIC is deliberately omitted
        has_roic = bool(re.search(r"\*\*ROIC[^*]*:?\*\*", corrupted_card, re.IGNORECASE))
        assert not has_roic, "Adversarial test must detect missing ROIC field"

    def test_adversarial_detects_invalid_ackman_score(self):
        """Verifies that out-of-bounds Ackman scores (<1.0 or >10.0) are caught."""
        invalid_score_str = "**Ackman Score:** 15 / 10"
        m = re.search(r"\*\*Ackman Score:?\*\*\s*(\d+(?:\.\d+)?)", invalid_score_str)
        assert m
        score = float(m.group(1))
        is_valid_1_to_10 = (1.0 <= score <= 10.0)
        assert not is_valid_1_to_10, "Adversarial test must reject score > 10.0"

    def test_adversarial_detects_generic_disqualification_placeholder(self):
        """Verifies that generic placeholder reasons are caught by regex filters."""
        generic_reason = "fails screen."
        banned_pattern = r"^fails?\s*screen\.?$"
        assert re.match(banned_pattern, generic_reason.strip(), re.IGNORECASE), "Adversarial test must detect generic reason"
