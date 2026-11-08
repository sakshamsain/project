import pytest

from finn.push.classify import classify, load_rules

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
    (
        "Intimation of Board Meeting to consider Financial Results for the quarter ended "
        "September 30, 2026",
        "results",
        "results_intimation",
    ),
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
    ("Credit Rating reaffirmed by CRISIL for bank facilities", "credit_rating", "credit_rating"),
    (
        "Appointment of Mr. Rajesh Kumar as Chief Financial Officer",
        "management_change",
        "kmp_change",
    ),
    (
        "Disclosure of reasons for encumbrance under Regulation 31(1)",
        "pledging",
        "pledge",
    ),
    ("Allotment of shares under ESOP Scheme 2021", "unclassified", "esop_allotment"),
    (
        "Board approves Qualified Institutions Placement of up to Rs 2,000 crore",
        "fund_raise",
        "fund_raise",
    ),
    ("Record date for Interim Dividend", "dividend", "dividend"),
    ("Acquisition of 100% stake in XYZ Private Limited", "M&A", "m_and_a"),
    ("Commencement of commercial production at the new plant", "capex", "capex"),
    ("Receipt of show cause notice from GST authorities", "litigation", "litigation"),
    ("Company bags order worth Rs 1,200 crore", "press_release", "press_release"),
    ("Certificate under Regulation 74(5) of SEBI (DP) Regulations", "unclassified", "routine"),
]


@pytest.mark.parametrize(("subject", "category", "rule_id"), CASES)
def test_rules_classify_common_subjects(subject: str, category: str, rule_id: str) -> None:
    c = classify(subject)
    assert c is not None, subject
    assert (c.category, c.rule_id) == (category, rule_id)


def test_ambiguous_board_outcome_goes_to_the_model() -> None:
    assert classify("Outcome of Board Meeting") is None


def test_body_text_breaks_ties_for_vague_subjects() -> None:
    c = classify("Outcome of Board Meeting", body="The Board declared an interim dividend of Rs 5")
    assert c is not None and c.category == "dividend"


def test_auditor_rule_sets_floor_attributes() -> None:
    c = classify("Resignation of Statutory Auditor")
    assert c is not None
    assert c.attributes == {"role": "auditor", "action": "resign"}


def test_rule_ids_are_unique() -> None:
    ids = [r.id for r in load_rules()]
    assert len(ids) == len(set(ids))
