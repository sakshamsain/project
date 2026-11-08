import json
from pathlib import Path

import pytest

from finn.push.classify import classify, is_generic, load_rules

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "nse"

CASES = [
    # subject, expected category, expected rule
    (
        "Closure of Trading Window till 48 hours after declaration of financial results",
        "unclassified",
        "trading_window",
    ),
    (
        "Resignation of Statutory Auditors of the Company",
        "management_change",
        "auditor_resignation",
    ),
    ("Board Meeting Intimation", "results", "results_intimation"),
    (
        "Copy of Newspaper Publication of Unaudited Financial Results",
        "results",
        "results_newspaper",
    ),
    (
        "Transcript of the Earnings Conference Call held on November 6, 2026",
        "earnings_call",
        "transcript",
    ),
    ("Audio Recording of Earnings Call for Q2 FY27", "earnings_call", "call_recording"),
    (
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        "investor_meetings",
        "investor_meet",
    ),
    (
        "Unaudited Standalone and Consolidated Financial Results for the quarter ended "
        "September 30, 2026",
        "results",
        "results_filing",
    ),
    ("Credit Rating", "credit_rating", "credit_rating"),
    ("Appointment", "management_change", "kmp_change"),
    ("Resignation of Director/KMP/SMP", "management_change", "kmp_change"),
    ("Disclosure of reasons for encumbrance under Regulation 31(1)", "pledging", "pledge"),
    ("ESOP/ESOS/ESPS", "unclassified", "esop_allotment"),
    ("Monitoring Agency Report", "unclassified", "fund_use"),
    (
        "Board approves Qualified Institutions Placement of up to Rs 2,000 crore",
        "fund_raise",
        "fund_raise",
    ),
    ("Record date for Interim Dividend", "dividend", "dividend"),
    ("Acquisition", "M&A", "m_and_a"),
    ("Commencement of commercial production at the new plant", "capex", "capex"),
    ("Pendency of any litigation(s) or dispute(s)-(Sub-para 8-Para B)", "litigation", "litigation"),
    ("Bagging/Receiving of orders/contracts", "press_release", "order_win"),
    ("Disruption of Operations", "press_release", "disruption"),
    ("Shareholders meeting", "agm_egm", "agm_egm"),
    ("Certificate under Regulation 74(5) of SEBI (DP) Regulations", "unclassified", "routine"),
    ("Declaration of NAV", "unclassified", "non_equity"),
]


@pytest.mark.parametrize(("subject", "category", "rule_id"), CASES)
def test_rules_classify_common_subjects(subject: str, category: str, rule_id: str) -> None:
    c = classify(subject)
    assert c is not None, subject
    assert (c.category, c.rule_id) == (category, rule_id)


def test_generic_subjects_defer_to_the_filing_text() -> None:
    assert is_generic("General Updates")
    assert is_generic("Analyst/Investor Meet Para A-XBRL")
    c = classify(
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        body="X Limited has informed the Exchange about Transcript",
    )
    assert c is not None and c.rule_id == "transcript"
    c = classify(
        "Outcome of Board Meeting",
        body="X has submitted to the Exchange, the financial results for the period ended "
        "September 30, 2026.",
    )
    assert c is not None and (c.category, c.attributes["stage"]) == ("results", "filing")


def test_ambiguous_board_outcome_goes_to_the_model() -> None:
    assert classify("Outcome of Board Meeting") is None


def test_management_change_attributes() -> None:
    c = classify(
        "Change in Director(s)",
        body="Resignation of Mr A as Chief Financial Officer of the Company with effect from today",
    )
    assert c is not None
    assert c.attributes == {"role": "cfo", "action": "resign"}


def test_rating_direction() -> None:
    c = classify("Credit Rating", body="ICRA has downgraded the long-term rating to [ICRA]A")
    assert c is not None and c.attributes == {"direction": "downgrade"}


def test_auditor_rule_sets_floor_attributes() -> None:
    c = classify("Resignation of Statutory Auditor")
    assert c is not None
    assert c.attributes == {"role": "auditor", "action": "resign"}


def test_rule_ids_are_unique() -> None:
    ids = [r.id for r in load_rules()]
    assert len(ids) == len(set(ids))


def test_coverage_on_recorded_nse_filings() -> None:
    rows = json.loads((FIXTURES / "announcements_market_1d_sample.json").read_text())
    rows += json.loads((FIXTURES / "announcements_TATAPOWER_30d.json").read_text())
    classified = 0
    for r in rows:
        if classify(r["desc"], r["desc"], r.get("attchmntText"), summary=r.get("voiceSummary")):
            classified += 1
    assert classified / len(rows) >= 0.9


@pytest.mark.parametrize(
    ("body", "category", "stage"),
    [
        (
            "X Limited has informed the Exchange regarding a press release dated "
            'November 06, 2026, titled "Tata Steel reports Consolidated EBITDA of Rs 10,665 '
            'crores for the quarter".',
            "results",
            "press_release",
        ),
        (
            'titled "Denta Water Reports Q2 FY27 Performance; Order Book Stands at 7,824 Million"',
            "results",
            "press_release",
        ),
        ('titled  Achieve 19% PAT Growth in H1-FY27 ".', "results", "press_release"),
        (
            'titled "Tata Power Renewables Records over 130% YoY Growth in Utility-Scale '
            'Execution in Q2 FY27"',
            "press_release",
            None,
        ),
        (
            'titled "Tata Power Signs MoU with BPCL to Develop 110 kV Power Infrastructure"',
            "press_release",
            None,
        ),
    ],
)
def test_a_press_release_title_can_be_more_specific(
    body: str, category: str, stage: str | None
) -> None:
    c = classify("Press Release", "Press Release", body)
    assert c is not None
    assert c.category == category
    assert c.attributes.get("stage") == stage


def test_internal_restructuring_is_marked() -> None:
    c = classify(
        "Scheme of Arrangement",
        "Scheme of Arrangement",
        "Effective Date of the Scheme of Amalgamation amongst Tata Steel Limited and Rujuvalika "
        "Investments Limited, wholly owned subsidiary",
    )
    assert c is not None and c.category == "M&A" and c.attributes.get("kind") == "internal"


def test_a_release_is_not_reclassified_by_what_its_summary_mentions() -> None:
    c = classify(
        "Press Release",
        "Press Release",
        "Tata Steel Limited has informed the Exchange regarding a press release dated November "
        '07, 2026, titled "Tata Steel reports Consolidated EBITDA of Rs 10,665 crores for the '
        'quarter".',
        summary="Tata Steel submitted a press release and investor presentation to BSE and NSE.",
    )
    assert c is not None and c.rule_id == "results_press_release"


def test_summary_decides_only_when_nothing_else_matched() -> None:
    c = classify(
        "General Updates",
        "General Updates",
        "Tata Power Company Limited has informed the Exchange about General Updates",
        summary="Tata Power filed a notice of appeal before the Singapore Court of Appeal.",
    )
    assert c is not None and c.category == "litigation"
