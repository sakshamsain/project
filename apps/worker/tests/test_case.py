from __future__ import annotations

from annual_helpers import recorded, recorded_llm

from finn.pull.annual import cash_facts, crore, numbered_facts, pct
from finn.pull.case import Fact, verify_points, write_case

FACTS = {
    "F1": Fact(
        "F1",
        "FY26 revenue from operations was ₹1,78,650 crore, up 9.6% on the year before.",
        "computed",
    ),
    "F2": Fact(
        "F2",
        "FY26 free cash flow was ₹31,259 crore: operating cash flow less ₹2,727 crore"
        " of capital expenditure.",
        "computed",
    ),
    "F3": Fact(
        "F3",
        'Management names a risk (AI): "AI is shifting discretionary spending."',
        "quote",
        7,
        76,
    ),
}


def test_points_keep_only_figures_their_facts_contain() -> None:
    kept, dropped = verify_points(
        [
            {
                "point": "₹1,78,650 crore of FY26 revenue was up 9.6% on the year before.",
                "facts": ["F1"],
            },
            {"point": "₹31,259 crore of FY26 free cash flow was 12% above FY25.", "facts": ["F2"]},
            {"point": "AI is shifting discretionary spending away from services.", "facts": ["F9"]},
        ],
        FACTS,
        "bull",
    )
    assert [p.text[:10] for p in kept] == ["₹1,78,650 "]
    assert dropped == ["bull: figure 12 is not in its facts", "bull: cites no known fact"]


def test_fact_ids_written_into_a_point_are_removed() -> None:
    kept, dropped = verify_points(
        [{"point": "FY26 revenue of ₹1,78,650 crore rose 9.6% (F1).", "facts": ["F1"]}],
        FACTS,
        "bull",
    )
    assert not dropped and kept[0].text == "FY26 revenue of ₹1,78,650 crore rose 9.6%."


def test_advice_is_dropped() -> None:
    kept, dropped = verify_points(
        [{"point": "Revenue grew 9.6% in FY26, so buy the shares.", "facts": ["F1"]}], FACTS, "bull"
    )
    assert not kept and dropped and dropped[0].startswith("bull: ")


def test_recorded_case_verifies() -> None:
    llm, _ = recorded_llm()
    facts = [
        Fact(f"F{i}", f"fact {i}", "computed") for i in range(1, 17)
    ]  # ids only: the recorded answer cites F1-F16
    case, model = write_case(llm, facts, "Infosys Limited")
    raw = recorded("case")
    assert model is not None
    assert len(case.bull) + len(case.bear) + len(case.dropped) >= 1
    assert len(raw["bull"]) <= 3 and len(raw["bear"]) <= 3


def test_too_few_facts_writes_no_case() -> None:
    llm, transport = recorded_llm()
    case, model = write_case(llm, list(FACTS.values())[:2], "X")
    assert model is None and transport.tasks == [] and case.dropped == ["too few checked facts"]


def test_cash_facts_are_written_by_code() -> None:
    cash = {
        "lender": False,
        "years": [
            {
                "fiscal_year": "FY26",
                "revenue": 178650.0,
                "revenue_growth_pct": 9.6,
                "pat": 29474.0,
                "pat_growth_pct": 10.2,
                "cfo": 33986.0,
                "capex": 2727.0,
                "fcf": 31259.0,
                "cash_conversion_pct": 115.3,
                "failures": [],
                "pages": {"revenue": 288, "cfo": 295},
                "document_id": 3,
            },
            {"fiscal_year": "FY25", "failures": ["cash_flows_do_not_add_up"]},
        ],
        "totals": {},
    }
    facts = numbered_facts([cash_facts(cash)])
    assert [f.id for f in facts] == ["F1", "F2", "F3", "F4"]
    assert (
        facts[0].text
        == "FY26 revenue from operations was ₹1,78,650 crore, up 9.6% on the year before."
    )
    assert facts[0].page == 288 and facts[0].document_id == 3
    assert "115.3% of profit" in facts[2].text
    assert all("FY25" not in f.text for f in facts)  # a year that does not add up says nothing


def test_formats() -> None:
    assert crore(178650) == "1,78,650"
    assert crore(-65789.8) == "−65,790"
    assert crore(3.04) == "3.0"
    assert pct(0.12) == "0.12" and pct(115.34) == "115.3" and pct(9.0) == "9"
