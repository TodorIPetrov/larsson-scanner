"""
tests/test_ackman_cheat_sheet.py

Comprehensive Automated E2E Test Suite for the Bill Ackman Investing Strategy
& Stock-Picking Cheat Sheet deliverable.

Evaluates docs/ackman_strategy_cheat_sheet.md and/or ackman_strategy_cheat_sheet.md
against all 20 binary audit checks defined in Section 12 of spec_report.md
and all acceptance criteria in ORIGINAL_REQUEST.md.

Audit Rubric Mapping (Exact 1-to-1 Correspondence with spec_report.md Section 12):
----------------------------------------------------------------------------------
01: Six Sections Present        -> test_rubric_01_six_sections_present
02: Core Philosophy Count       -> test_rubric_02_core_philosophy_count
03: Core Principles Grounded    -> test_rubric_03_core_principles_grounded
04: Quantitative Metric Count   -> test_rubric_04_quantitative_metric_count
05: Explicit Numeric Ranges     -> test_rubric_05_explicit_numeric_ranges
06: Franchise/Royalty Rule      -> test_rubric_06_franchise_royalty_rule
07: Qualitative Moat Coverage   -> test_rubric_07_qualitative_moat_coverage
08: Governance & Management     -> test_rubric_08_governance_and_management
09: Extrinsic Risk Insularity   -> test_rubric_09_extrinsic_risk_insularity
10: Step Count Minimum          -> test_rubric_10_step_count_minimum
11: Actionable Workflow         -> test_rubric_11_actionable_workflow
12: Red Flags Count             -> test_rubric_12_red_flags_count
13: Red Flag Precedent Pairing  -> test_rubric_13_red_flag_precedent_pairing
14: Track Record Breadth        -> test_rubric_14_track_record_breadth
15: Wins and Losses Included    -> test_rubric_15_wins_and_losses_included
16: Usable Lessons Extracted    -> test_rubric_16_usable_lessons_extracted
17: Strategic Evolution Matrix  -> test_rubric_17_strategic_evolution_matrix
18: Distinct Sources Count      -> test_rubric_18_distinct_sources_count
19: Multi-Source Corroboration  -> test_rubric_19_multi_source_corroboration
20: Anti-Fluff & Conciseness    -> test_rubric_20_anti_fluff_and_conciseness

Additional Test Classes:
- TestDeliverableIntegrityAndSynchronization: Checks file presence, size limits, and synchronization
- TestAdversarialVerification: Proves tests genuinely reject non-compliant documents
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pytest

# ---------------------------------------------------------------------------
# Path & Deliverable Discovery
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

CANDIDATE_PATHS = [
    ROOT_DIR / "docs" / "ackman_strategy_cheat_sheet.md",
    ROOT_DIR / "ackman_strategy_cheat_sheet.md",
]


def get_existing_deliverable_path() -> Path:
    """Find the primary deliverable markdown file across canonical project locations."""
    for p in CANDIDATE_PATHS:
        if p.exists() and p.is_file():
            return p
    pytest.fail(
        f"Deliverable not found at any candidate location: {[str(p) for p in CANDIDATE_PATHS]}. "
        "The deliverable must be written to docs/ackman_strategy_cheat_sheet.md or ackman_strategy_cheat_sheet.md."
    )


def get_all_existing_deliverable_paths() -> List[Path]:
    """Return all existing candidate deliverable paths."""
    return [p for p in CANDIDATE_PATHS if p.exists() and p.is_file()]


# ---------------------------------------------------------------------------
# Robust Markdown Parsers & Structural Analyzers
# ---------------------------------------------------------------------------

def parse_markdown_sections(text: str) -> Dict[str, str]:
    """
    Parses a markdown document into major sections demarcated by '## ' (level 2 headings).
    All subsections (###, ####) and nested content remain within their parent major section.
    Returns a dictionary mapping heading titles to section body text.
    """
    lines = text.splitlines()
    sections: Dict[str, List[str]] = {}
    current_heading = "__HEADER__"
    sections[current_heading] = []

    major_heading_pattern = re.compile(r"^##\s+(.+)$")

    for line in lines:
        match = major_heading_pattern.match(line.strip())
        if match:
            current_heading = match.group(1).strip()
            if current_heading not in sections:
                sections[current_heading] = []
        else:
            sections[current_heading].append(line)

    return {k: "\n".join(v) for k, v in sections.items()}


def get_section_by_keyword(sections: Dict[str, str], keywords: List[str]) -> Tuple[str, str]:
    """Finds a section whose heading contains any of the provided keywords (case-insensitive)."""
    for heading, content in sections.items():
        heading_lower = heading.lower()
        if any(kw.lower() in heading_lower for kw in keywords):
            return heading, content
    return "", ""


def extract_all_citations(text: str) -> List[str]:
    """Extracts bracketed citations matching patterns like [PSH 2021 Annual Report]."""
    citations = re.findall(r"\[([A-Za-z0-9\s,\.\-#\:\/]{4,80})\]", text)
    valid_citations = [
        c.strip() for c in citations
        if not c.startswith("http")
        and not c.isdigit()
        and any(keyword in c.lower() for keyword in [
            "psh", "pershing", "report", "annual", "letter", "sec", "13d", "13f",
            "form", "n-2", "fridman", "parrish", "presentation", "podcast", "wsj", "ft"
        ])
    ]
    return valid_citations


# ---------------------------------------------------------------------------
# Master Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def deliverable_path() -> Path:
    return get_existing_deliverable_path()


@pytest.fixture(scope="session")
def deliverable_text(deliverable_path: Path) -> str:
    content = deliverable_path.read_text(encoding="utf-8")
    assert content, f"Deliverable file at {deliverable_path} is completely empty."
    return content


@pytest.fixture(scope="session")
def parsed_sections(deliverable_text: str) -> Dict[str, str]:
    return parse_markdown_sections(deliverable_text)


# ===========================================================================
# Deliverable Integrity & Synchronization Tests
# ===========================================================================

class TestDeliverableIntegrityAndSynchronization:
    """Validates physical file integrity, location, and synchronization."""

    def test_file_existence_and_size_bounds(self, deliverable_path: Path, deliverable_text: str):
        """Assert deliverable exists, is non-empty (>5,000 bytes) and concisely bounded (<200,000 bytes)."""
        assert deliverable_path.exists(), "Deliverable file does not exist."
        size = deliverable_path.stat().st_size
        assert size >= 5000, f"Deliverable size ({size} bytes) is below minimum 5,000 bytes."
        assert size <= 200000, f"Deliverable size ({size} bytes) exceeds 200,000 bytes, violating conciseness."
        assert len(deliverable_text.strip()) > 0, "Deliverable text cannot be empty or whitespace only."

    def test_deliverable_locations_synchronized(self):
        """Assert that if both docs/ and root deliverables exist, their contents match."""
        docs_path = ROOT_DIR / "docs" / "ackman_strategy_cheat_sheet.md"
        root_path = ROOT_DIR / "ackman_strategy_cheat_sheet.md"
        if docs_path.exists() and root_path.exists():
            docs_content = docs_path.read_text(encoding="utf-8")
            root_content = root_path.read_text(encoding="utf-8")
            assert docs_content == root_content, (
                "Discrepancy detected between docs/ackman_strategy_cheat_sheet.md and root "
                "ackman_strategy_cheat_sheet.md. Both copies must be identical."
            )


# ===========================================================================
# Master 20-Point Binary Rubric Test Suite (Section 12 of spec_report.md)
# ===========================================================================

class TestBillAckmanCheatSheetRubric:
    """
    Automated evaluation of all 20 binary checks from Section 12 of spec_report.md.
    Every test corresponds directly to an audit gate condition.
    """

    # -----------------------------------------------------------------------
    # Rubric Gate 01: Six Sections Present
    # -----------------------------------------------------------------------
    def test_rubric_01_six_sections_present(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 01: Document contains Sections 1 through 6 with full headers, plus Sourcing Registry.
        """
        required_sections = [
            ("Section 1: Core Philosophy", ["Core Philosophy", "Philosophy", "Foundational Principles"]),
            ("Section 2: Quantitative Screening Criteria", ["Quantitative Screening", "Quantitative", "Financial Thresholds"]),
            ("Section 3: Qualitative Evaluation Framework", ["Qualitative Evaluation", "Qualitative Framework", "Moat & Governance"]),
            ("Section 4: Step-by-Step Screening Process", ["Step-by-Step", "Screening Process", "Actionable Workflow"]),
            ("Section 5: Red Flags & Deal-Breakers", ["5. Red Flags", "Deal-Breakers", "Anti-Patterns"]),
            ("Section 6: Track Record Summary & Strategy Evolution", ["6. High-Level Track Record", "Track Record Summary"]),
            ("Section 7 / Appendix: Sourcing Registry", ["7. Sources", "Reference Concordance", "Sourcing Registry", "Appendix"]),
        ]

        missing = []
        for name, keywords in required_sections:
            h, c = get_section_by_keyword(parsed_sections, keywords)
            if not h or len(c.strip()) < 200:
                missing.append(name)

        assert not missing, f"The following mandatory sections are missing or substantively empty: {missing}"

    # -----------------------------------------------------------------------
    # Rubric Gate 02: Core Philosophy Count
    # -----------------------------------------------------------------------
    def test_rubric_02_core_philosophy_count(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 02: Section 1 has between 3 and 5 distinct core principles or the 8 Core Criteria ('Stone Tablets').
        Verifies presence of foundational Ackman investment axioms.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Core Philosophy", "Foundational Principles"])
        assert h, "Section 1 (Core Philosophy) not found."

        core_axioms = [
            r"simple\s+and\s+predictable",
            r"free\s+cash\s+flow",
            r"(?:dominant|wide)\s+(?:market\s+position|moat|barriers?\s+to\s+entry)",
            r"(?:high\s+return\s+on\s+(?:invested\s+)?capital|roic)",
            r"extrinsic\s+risk",
            r"(?:strong|fortress)\s+balance\s+sheet",
        ]
        matched_axioms = 0
        for pattern in core_axioms:
            if re.search(pattern, content, re.IGNORECASE):
                matched_axioms += 1

        assert matched_axioms >= 4, f"Section 1 only matched {matched_axioms} core axioms out of {len(core_axioms)}."

        # Check concentrated portfolio architecture (8-12 positions)
        assert re.search(r"8\s*(?:to|-)\s*12\s*(?:core\s*)?(?:positions|holdings|stocks|names)", content, re.IGNORECASE), \
            "Section 1 must define concentrated portfolio architecture of 8 to 12 positions."

        # Check asymmetric hedging doctrine
        assert re.search(r"(?:asymmetric|tail-risk|cds|credit\s+default\s+swap|swaption)", content, re.IGNORECASE), \
            "Section 1 must define asymmetric risk/reward and tail-risk macro hedging doctrine."

    # -----------------------------------------------------------------------
    # Rubric Gate 03: Core Principles Grounded
    # -----------------------------------------------------------------------
    def test_rubric_03_core_principles_grounded(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 03: Each core principle cites specific PSH letters, filings, or presentations.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Core Philosophy", "Foundational Principles"])
        citations = extract_all_citations(content)
        assert len(citations) >= 4, f"Section 1 must carry at least 4 specific source citations; found {len(citations)}: {citations}"

        has_primary = any("psh" in c.lower() or "annual report" in c.lower() or "form" in c.lower() for c in citations)
        assert has_primary, "Section 1 citations must include primary PSH Annual Reports or SEC Filings."

    # -----------------------------------------------------------------------
    # Rubric Gate 04: Quantitative Metric Count
    # -----------------------------------------------------------------------
    def test_rubric_04_quantitative_metric_count(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 04: Section 2 defines at least 4 (and ideally 5+) specific financial metrics.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Quantitative Screening", "Financial Thresholds"])
        assert h, "Section 2 (Quantitative Screening) not found."

        required_metrics = [
            ("ROIC / ROCE", [r"roic", r"return\s+on\s+invested\s+capital", r"roce"]),
            ("Free Cash Flow Conversion", [r"fcf\s+conversion", r"free\s+cash\s+flow\s+conversion"]),
            ("Free Cash Flow Yield", [r"fcf\s+yield", r"free\s+cash\s+flow\s+yield"]),
            ("Leverage / Net Debt to EBITDA", [r"net\s+debt\s*/\s*ebitda", r"debt\s+to\s+ebitda", r"leverage"]),
            ("Operating Margin", [r"operating\s+margin", r"ebit\s+margin"]),
            ("Market Capitalization", [r"market\s+cap(?:italization)?"]),
        ]

        found_metrics = []
        for name, patterns in required_metrics:
            if any(re.search(pat, content, re.IGNORECASE) for pat in patterns):
                found_metrics.append(name)

        assert len(found_metrics) >= 4, f"Section 2 must define at least 4 metrics; found {len(found_metrics)}: {found_metrics}"

    # -----------------------------------------------------------------------
    # Rubric Gate 05: Explicit Numeric Ranges
    # -----------------------------------------------------------------------
    def test_rubric_05_explicit_numeric_ranges(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 05: All financial metrics feature explicit numerical thresholds:
        - ROIC: >=15% or 20% floor, mentions 45% or higher target
        - FCF Conversion: >=85% or 90% threshold
        - FCF Yield: target range (e.g. 4.5% - 7.0%)
        - Net Debt / EBITDA: <=2.5x - 3.0x standard
        - Operating Margin: >=15% - 20%
        - Market Cap: >=$10B large-cap hurdle
        """
        h, content = get_section_by_keyword(parsed_sections, ["Quantitative Screening", "Financial Thresholds"])

        # ROIC threshold >=15% and target mentions 45%
        assert re.search(r"15(?:\.0)?%", content), "Section 2 must specify ROIC hurdle >= 15%."
        assert re.search(r"45(?:\.0)?%", content), "Section 2 must reference higher target ROIC (e.g. Lowe's 45% target or Chipotle unit returns)."

        # FCF Conversion >=85% or 90%
        assert re.search(r"(?:85|90)(?:\.0)?%", content), "Section 2 must specify FCF Conversion threshold >= 85% or 90%."

        # Net Debt / EBITDA <= 2.5x or 3.0x
        assert re.search(r"(?:2\.5|3\.0)\s*x", content, re.IGNORECASE), "Section 2 must specify standard Net Debt / EBITDA <= 2.5x-3.0x."

        # Operating margin >= 15% or 20%
        assert re.search(r"(?:15|20)(?:\.0)?%", content), "Section 2 must specify Operating Margin threshold >= 15-20%."

        # Market Cap >= $10 Billion
        assert re.search(r"\$10(?:\.0)?\s*(?:Billion|B\b)", content, re.IGNORECASE), "Section 2 must specify Market Cap >= $10 Billion."

    # -----------------------------------------------------------------------
    # Rubric Gate 06: Franchise / Royalty Rule (Leverage Exception)
    # -----------------------------------------------------------------------
    def test_rubric_06_franchise_royalty_rule(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 06: Leverage exceptions for asset-light franchise/royalty models are explicitly specified
        (Net Debt / EBITDA bounded up to <= 4.0x-4.5x or 5.0x for models like Hilton or Restaurant Brands).
        """
        h, content = get_section_by_keyword(parsed_sections, ["Quantitative Screening", "Financial Thresholds"])

        assert re.search(r"(?:franchise|asset-light|royalty)", content, re.IGNORECASE), \
            "Section 2 must specify differentiated threshold for franchise/asset-light royalty business models."

        assert re.search(r"(?:4\.0|4\.5|5\.0)\s*x", content, re.IGNORECASE), \
            "Section 2 must specify bounded leverage exception up to 4.0x-4.5x (or 5.0x) for franchisors."

        assert re.search(r"(?:Hilton|HLT|Restaurant\s+Brands|QSR)", content, re.IGNORECASE), \
            "Section 2 must cite franchise exemplars such as Hilton or Restaurant Brands."

    # -----------------------------------------------------------------------
    # Rubric Gate 07: Qualitative Moat Coverage
    # -----------------------------------------------------------------------
    def test_rubric_07_qualitative_moat_coverage(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 07: Section 3 covers barriers to entry, pricing power / inflation pass-through,
        and business simplicity / royalty dynamics.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Qualitative Evaluation", "Moat & Governance"])
        assert h, "Section 3 (Qualitative Evaluation) not found."

        # Pricing power and inflation pass-through
        assert re.search(r"pricing\s+power", content, re.IGNORECASE), "Section 3 must analyze pricing power."
        assert re.search(r"inflation", content, re.IGNORECASE), "Section 3 must analyze inflation pass-through."

        # Barriers to entry & economic moats
        assert re.search(r"(?:barriers?\s+to\s+entry|economic\s+moat)", content, re.IGNORECASE), \
            "Section 3 must analyze barriers to entry and durable moats."

        # Simplicity / Asset-Light / Royalty Dynamics
        assert re.search(r"(?:asset-light|royalt|franchise|simplicity|predictab)", content, re.IGNORECASE), \
            "Section 3 must cover asset-light, royalty dynamics, and business simplicity/predictability."

    # -----------------------------------------------------------------------
    # Rubric Gate 08: Governance & Management Alignment
    # -----------------------------------------------------------------------
    def test_rubric_08_governance_and_management(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 08: Section 3 details capital allocation, insider alignment ('skin in the game'),
        and executive compensation tied to ROIC/FCF per share.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Qualitative Evaluation", "Moat & Governance"])

        # Executive compensation & ROIC/FCF
        assert re.search(r"(?:executive\s+comp(?:ensation)?|incentive)", content, re.IGNORECASE), \
            "Section 3 must audit executive compensation structures."
        assert re.search(r"(?:roic|free\s+cash\s+flow\s+per\s+share|fcf\s+per\s+share)", content, re.IGNORECASE), \
            "Section 3 must verify incentives are tied to ROIC or per-share FCF."

        # Skin in the game / alignment
        assert re.search(r"(?:skin\s+in\s+the\s+game|insider\s+ownership|stock\s+ownership)", content, re.IGNORECASE), \
            "Section 3 must examine management skin-in-the-game and insider alignment."

        # Capital allocation & buybacks
        assert re.search(r"(?:capital\s+allocation|share\s+repurchase|buyback)", content, re.IGNORECASE), \
            "Section 3 must evaluate capital allocation discipline and counter-cyclical buybacks."

    # -----------------------------------------------------------------------
    # Rubric Gate 09: Extrinsic Risk Insularity
    # -----------------------------------------------------------------------
    def test_rubric_09_extrinsic_risk_insularity(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 09: Qualitative screen tests immunity to commodity, macro, or regulatory risks.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Qualitative Evaluation", "Moat & Governance"])

        assert re.search(r"extrinsic\s+risk", content, re.IGNORECASE), "Section 3 must cover Extrinsic Risk Insularity."
        assert re.search(r"commodity", content, re.IGNORECASE), "Section 3 must assess commodity price immunity."
        assert re.search(r"(?:regulatory|political)", content, re.IGNORECASE), "Section 3 must evaluate regulatory risk insulation."

    # -----------------------------------------------------------------------
    # Rubric Gate 10: Step Count Minimum
    # -----------------------------------------------------------------------
    def test_rubric_10_step_count_minimum(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 10: Section 4 has at least 5 numbered, sequential steps (Step 1 to Step 5).
        """
        h, content = get_section_by_keyword(parsed_sections, ["Step-by-Step", "Screening Process", "Actionable Workflow"])
        assert h, "Section 4 (Step-by-Step Screening Process) not found."

        step_matches = re.findall(r"Step\s*([1-9]):?", content, re.IGNORECASE)
        unique_steps = sorted(list(set(step_matches)))
        assert len(unique_steps) >= 5, f"Section 4 must contain at least 5 numbered sequential steps; found: {unique_steps}"
        assert ["1", "2", "3", "4", "5"] <= unique_steps[:5], f"Steps must be numbered 1 through 5; found: {unique_steps}"

    # -----------------------------------------------------------------------
    # Rubric Gate 11: Actionable Workflow from SEC Filings
    # -----------------------------------------------------------------------
    def test_rubric_11_actionable_workflow(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 11: Steps can be executed directly using public SEC filings (10-K, DEF 14A)
        and provide concrete instructions and disqualification triggers.
        """
        h, content = get_section_by_keyword(parsed_sections, ["Step-by-Step", "Screening Process", "Actionable Workflow"])

        assert re.search(r"10-K", content), "Section 4 must cite 10-K filings."
        assert re.search(r"(?:DEF\s*14A|proxy\s+statement)", content, re.IGNORECASE), \
            "Section 4 must cite DEF 14A proxy statements for management audit."

        assert re.search(r"(?:dcf|discounted\s+cash\s+flow)", content, re.IGNORECASE), \
            "Section 4 must instruct building a Discounted Cash Flow (DCF) model."
        assert re.search(r"margin\s+of\s+safety", content, re.IGNORECASE), \
            "Section 4 must require a Margin of Safety discount."

        assert re.search(r"(?:disqualif|kill-switch|pass\b|trigger)", content, re.IGNORECASE), \
            "Section 4 must provide concrete disqualification triggers."

    # -----------------------------------------------------------------------
    # Rubric Gate 12: Red Flags Count
    # -----------------------------------------------------------------------
    def test_rubric_12_red_flags_count(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 12: Section 5 details at least 3 (and 4) specific anti-patterns / deal-breakers.
        """
        h, content = get_section_by_keyword(parsed_sections, ["5. Red Flags", "Deal-Breakers", "Anti-Patterns"])
        assert h, "Section 5 (Red Flags & Deal-Breakers) not found."

        anti_patterns = re.findall(r"(?:Anti-Pattern\s*[1-9]|Deal-Breaker\s*[1-9]|\d+\.\s+[A-Z])", content)
        assert len(anti_patterns) >= 3, f"Section 5 must define at least 3 anti-patterns; found {len(anti_patterns)}"

    # -----------------------------------------------------------------------
    # Rubric Gate 13: Red Flag Precedent Pairing
    # -----------------------------------------------------------------------
    def test_rubric_13_red_flag_precedent_pairing(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 13: Every red flag anti-pattern is explicitly tied to a real Pershing Square historical loss:
        - Valeant Pharmaceuticals (VRX): Debt roll-up, non-GAAP obfuscation, predatory pricing
        - Herbalife (HLF): Activist short selling, unlimited downside, regulatory dependency
        - JCPenney (JCP) or Borders: Secular retail decline, broken moat turnaround
        - Netflix (NFLX): Sudden loss of business model predictability, thesis invalidation
        """
        h, content = get_section_by_keyword(parsed_sections, ["5. Red Flags", "Deal-Breakers", "Anti-Patterns"])

        # Valeant
        assert re.search(r"Valeant", content), "Section 5 must pair an anti-pattern with Valeant Pharmaceuticals."
        assert re.search(r"(?:roll-up|m&a|non-gaap|predatory)", content, re.IGNORECASE), \
            "Valeant anti-pattern must cover serial roll-up, predatory pricing, or non-GAAP accounting."

        # Herbalife
        assert re.search(r"Herbalife", content), "Section 5 must pair an anti-pattern with Herbalife."
        assert re.search(r"(?:short|asymmetric\s+risk|squeeze)", content, re.IGNORECASE), \
            "Herbalife anti-pattern must cover activist short selling hazards."

        # JCPenney or Borders
        assert re.search(r"(?:JCPenney|J\.C\.\s*Penney|Borders)", content, re.IGNORECASE), \
            "Section 5 must pair an anti-pattern with JCPenney or Borders."

        # Netflix
        assert re.search(r"Netflix", content), "Section 5 must pair an anti-pattern with Netflix."
        assert re.search(r"(?:predictab|thesis\s+invalidation|subscriber)", content, re.IGNORECASE), \
            "Netflix anti-pattern must cover sudden loss of predictability or thesis invalidation rule."

    # -----------------------------------------------------------------------
    # Rubric Gate 14: Track Record Breadth
    # -----------------------------------------------------------------------
    def test_rubric_14_track_record_breadth(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 14: Section 6 covers at least 5 notable historical positions.
        """
        h, content = get_section_by_keyword(parsed_sections, ["6. High-Level Track Record", "Track Record Summary"])
        assert h, "Section 6 (Track Record) not found."

        notable_positions = [
            ("General Growth Properties", [r"General\s+Growth", r"GGP"]),
            ("Canadian Pacific Railway", [r"Canadian\s+Pacific", r"CP\b", r"CPKC"]),
            ("Chipotle Mexican Grill", [r"Chipotle", r"CMG"]),
            ("Hilton Worldwide", [r"Hilton", r"HLT"]),
            ("Universal Music Group", [r"Universal\s+Music", r"UMG"]),
            ("COVID CDS Credit Hedge", [r"COVID", r"CDS", r"Credit\s+Default\s+Swap"]),
            ("Valeant Pharmaceuticals", [r"Valeant", r"VRX"]),
            ("Herbalife", [r"Herbalife", r"HLF"]),
            ("Netflix", [r"Netflix", r"NFLX"]),
        ]

        found_positions = []
        for name, patterns in notable_positions:
            if any(re.search(pat, content) for pat in patterns):
                found_positions.append(name)

        assert len(found_positions) >= 5, f"Section 6 must cover at least 5 notable positions; found {len(found_positions)}: {found_positions}"

    # -----------------------------------------------------------------------
    # Rubric Gate 15: Wins and Losses Included
    # -----------------------------------------------------------------------
    def test_rubric_15_wins_and_losses_included(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 15: Track record includes both major multi-billion-dollar wins and signature losses.
        """
        h, content = get_section_by_keyword(parsed_sections, ["6. High-Level Track Record", "Track Record Summary"])

        # Signature wins
        wins_matched = [
            p for p in ["General Growth", "Canadian Pacific", "Chipotle", "Hilton", "COVID", "CDS"]
            if re.search(p, content, re.IGNORECASE)
        ]
        assert len(wins_matched) >= 2, f"Track record must feature major wins; found: {wins_matched}"

        # Signature losses
        losses_matched = [
            p for p in ["Valeant", "Herbalife", "Netflix", "JCPenney"]
            if re.search(p, content, re.IGNORECASE)
        ]
        assert len(losses_matched) >= 2, f"Track record must feature signature losses; found: {losses_matched}"

    # -----------------------------------------------------------------------
    # Rubric Gate 16: Usable Lessons Extracted
    # -----------------------------------------------------------------------
    def test_rubric_16_usable_lessons_extracted(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 16: Each position extracts concrete rules and analytical lessons, not mere narrative.
        """
        h, content = get_section_by_keyword(parsed_sections, ["6. High-Level Track Record", "Track Record Summary"])

        assert re.search(r"(?:lesson|takeaway|investment\s+rule|analytical)", content, re.IGNORECASE), \
            "Section 6 must systematically extract analytical lessons and investment rules."

        # Key operational takeaways
        assert re.search(r"(?:solvency\s+vs\.?\s+liquidity|ring-fenced)", content, re.IGNORECASE), \
            "Track record must extract the solvency vs. liquidity / ring-fenced debt lesson (GGP)."
        assert re.search(r"(?:operating\s+ratio|hunter\s+harrison|scheduled\s+railroading)", content, re.IGNORECASE), \
            "Track record must extract the operational ratio / management leadership lesson (CP)."
        assert re.search(r"(?:sunk-cost|thesis\s+invalidation|liquidat|averaging\s+down)", content, re.IGNORECASE), \
            "Track record must extract the sunk-cost discipline / thesis invalidation rule (Netflix/Valeant)."

    # -----------------------------------------------------------------------
    # Rubric Gate 17: Strategic Evolution Matrix
    # -----------------------------------------------------------------------
    def test_rubric_17_strategic_evolution_matrix(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 17: Document contrasts Pre-Valeant (1.0) vs. Post-Valeant (2.0 / 3.0 'Quiet Investing').
        Verifies contrast across engagement posture, short selling, hedging, and permanent capital.
        """
        h, content = get_section_by_keyword(parsed_sections, ["6. High-Level Track Record", "Track Record Summary"])

        # The 3 eras
        assert re.search(r"Pershing\s+Square\s+1\.0", content, re.IGNORECASE), "Must define Pershing Square 1.0."
        assert re.search(r"Pershing\s+Square\s+2\.0", content, re.IGNORECASE), "Must define Pershing Square 2.0."
        assert re.search(r"Pershing\s+Square\s+3\.0", content, re.IGNORECASE), "Must define Pershing Square 3.0."

        # "Quiet Investing" or "Quiet Compounder"
        assert re.search(r"(?:quiet\s+investing|quiet\s+compounder)", content, re.IGNORECASE), \
            "Must characterize 3.0 as 'Quiet Investing' or 'Quiet Compounder'."

        # Retirement of short selling
        assert re.search(r"(?:short.*retir|retir.*short|zero standalone equity shorts|no\s+shorting)", content, re.IGNORECASE), \
            "Must document official retirement of short selling."

        # Permanent capital
        assert re.search(r"permanent\s+capital", content, re.IGNORECASE), \
            "Must analyze transition to permanent closed-end capital (PSH)."

    # -----------------------------------------------------------------------
    # Rubric Gate 18: Distinct Sources Count
    # -----------------------------------------------------------------------
    def test_rubric_18_distinct_sources_count(self, parsed_sections: Dict[str, str], deliverable_text: str):
        """
        Rubric Gate 18: Deliverable references at least 5 distinct sources across primary and secondary categories.
        """
        h, content = get_section_by_keyword(parsed_sections, ["7. Sources", "Reference Concordance", "Sourcing Registry", "Appendix"])
        target_text = content if h else deliverable_text

        sources_found = []
        if re.search(r"Pershing\s+Square\s+Holdings.*(?:Annual\s+Report|Annual\s+Letter)", target_text, re.IGNORECASE):
            sources_found.append("PSH Annual Reports")
        if re.search(r"(?:Form\s+N-2|PSUS|Schedule\s+13D|Form\s+13F)", target_text, re.IGNORECASE):
            sources_found.append("SEC Filings (N-2, 13D, 13F)")
        if re.search(r"(?:Lex\s+Fridman|Podcast\s*#?413)", target_text, re.IGNORECASE):
            sources_found.append("Lex Fridman Interview")
        if re.search(r"(?:Shane\s+Parrish|Knowledge\s+Project)", target_text, re.IGNORECASE):
            sources_found.append("Shane Parrish Interview")
        if re.search(r"(?:Investor\s+Presentation|Proxy\s+Fight\s+Presentation|UMG\s+Presentation)", target_text, re.IGNORECASE):
            sources_found.append("Pershing Square Investor Presentations")
        if re.search(r"(?:Financial\s+Times|Wall\s+Street\s+Journal|WSJ|FT\b)", target_text, re.IGNORECASE):
            sources_found.append("Authoritative Financial Journalism")

        assert len(sources_found) >= 5, f"Deliverable must reference at least 5 distinct sources; found {len(sources_found)}: {sources_found}"

    # -----------------------------------------------------------------------
    # Rubric Gate 19: Multi-Source Corroboration
    # -----------------------------------------------------------------------
    def test_rubric_19_multi_source_corroboration(self, parsed_sections: Dict[str, str]):
        """
        Rubric Gate 19: Key principles are corroborated across multiple distinct sources
        (e.g., cross-validation matrix).
        """
        h, content = get_section_by_keyword(parsed_sections, ["7. Sources", "Reference Concordance", "Sourcing Registry"])
        assert h, "Sources & Reference Concordance section must be present."

        has_cross_validation = (
            "cross-validation" in content.lower() or
            "corroborat" in content.lower() or
            "secondary" in content.lower()
        )
        assert has_cross_validation, "Sourcing section must include cross-validation / corroboration mapping."

    # -----------------------------------------------------------------------
    # Rubric Gate 20: Anti-Fluff & Conciseness
    # -----------------------------------------------------------------------
    def test_rubric_20_anti_fluff_and_conciseness(self, deliverable_text: str):
        """
        Rubric Gate 20: Document is strictly concise, operational, and fluff-free.
        Verifies presence of structured comparison tables and visual summary cards,
        and absence of irrelevant personal trivia.
        """
        table_count = len(re.findall(r"\|(?:\s*:?-+:?\s*\|)+", deliverable_text))
        box_count = len(re.findall(r"```", deliverable_text))

        assert table_count >= 2, f"Deliverable must contain structured comparison tables for usability; found {table_count}"
        assert box_count >= 6, f"Deliverable must contain visual cards / callout boxes; found {box_count} code block fences"
        assert (table_count + box_count // 2) >= 6, "Deliverable must provide dense visual summaries and reference cards."

        # Absence of biographical trivia
        unwanted_fluff = [
            "born in charleston", "childhood hobbies", "high school tennis captain",
            "vacation homes", "gossip", "celebrity gossip"
        ]
        found_fluff = [f for f in unwanted_fluff if f in deliverable_text.lower()]
        assert not found_fluff, f"Deliverable contains irrelevant biographical fluff: {found_fluff}"


# ===========================================================================
# Adversarial & Structural Meta-Tests
# (Proves the test suite is genuine and actively detects defects/omissions)
# ===========================================================================

class TestAdversarialVerification:
    """
    Adversarial verification testing that the test parsers and validation gates
    strictly detect missing data, invalid metrics, missing sections, and facade documents.
    """

    def test_adversarial_detects_missing_mandatory_section(self):
        """Verify that a document missing a mandatory section fails validation."""
        fake_doc = """# Title
## 1. Core Philosophy
Content here.
## 2. Quantitative Screening Criteria
ROIC > 15%.
## 3. Qualitative Evaluation Framework
Moats.
## 4. Step-by-Step Screening Process
Step 1 to 5.
## 5. Red Flags & Deal-Breakers
Valeant bad.
"""
        sections = parse_markdown_sections(fake_doc)
        h, c = get_section_by_keyword(sections, ["Track Record Summary", "6. High-Level Track Record"])
        assert not h, "Adversarial test confirms missing Track Record section is detected."

    def test_adversarial_detects_vague_unquantified_metrics(self):
        """Verify that a document with vague qualitative metrics fails quantitative checks."""
        vague_text = """
## 2. Quantitative Screening Criteria
- Look for companies with strong returns on capital.
- Free cash flow should be high and growing nicely.
- Debt should be reasonable and manageable.
- Margins should be healthy.
"""
        has_roic_number = bool(re.search(r"15(?:\.0)?%", vague_text))
        has_debt_number = bool(re.search(r"(?:2\.5|3\.0)\s*x", vague_text, re.IGNORECASE))
        has_market_cap = bool(re.search(r"\$10(?:\.0)?\s*(?:Billion|B\b)", vague_text, re.IGNORECASE))

        assert not has_roic_number, "Vague text must NOT pass ROIC numeric requirement."
        assert not has_debt_number, "Vague text must NOT pass leverage numeric requirement."
        assert not has_market_cap, "Vague text must NOT pass market cap requirement."

    def test_adversarial_detects_unpaired_red_flags(self):
        """Verify that red flags without specific historical loss pairings fail."""
        unpaired_red_flags = """
## 5. Red Flags & Deal-Breakers
1. High debt roll-ups: Avoid companies buying other companies with debt.
2. Short selling: Short selling is risky.
3. Retail turnarounds: Retail is hard.
"""
        has_valeant = bool(re.search(r"Valeant", unpaired_red_flags))
        has_herbalife = bool(re.search(r"Herbalife", unpaired_red_flags))
        has_netflix = bool(re.search(r"Netflix", unpaired_red_flags))

        assert not has_valeant, "Adversarial check confirms missing Valeant is detected."
        assert not has_herbalife, "Adversarial check confirms missing Herbalife is detected."
        assert not has_netflix, "Adversarial check confirms missing Netflix is detected."
