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
        body = " ".join(x for x in (r.get("attchmntText"), r.get("voiceSummary")) if x)
        if classify(r["desc"], r["desc"], body) is not None:
            classified += 1
    assert classified / len(rows) >= 0.9
