import pytest

from finn.push.headline import MAX_CHARS, clean_description, headline_for, shorten

CASES = [
    (
        "Tata Power Company Limited has informed the Exchange regarding Cessation of Mr Sanjay "
        "Vijay Bhandarkar (DIN: 01260274) as Non- Executive Independent Director of the company "
        "w.e.f. October 13, 2026.",
        "Cessation of Mr Sanjay Vijay Bhandarkar as Non-Executive Independent Director "
        "w.e.f. October 13, 2026.",
    ),
    (
        "Tata Power Company Limited has informed the Exchange regarding a press release dated "
        'November 05, 2026, titled "Tata Power Renewables Commissions 300 MW Project for SECI '
        'in Karnataka".',
        "Tata Power Renewables Commissions 300 MW Project for SECI in Karnataka",
    ),
    (
        "D. P. Abhushan Limited has informed the Exchange regarding a press release dated "
        'November 06, 2026, titled  Achieve 19% PAT Growth in H1-FY27 ".',
        "Achieve 19% PAT Growth in H1-FY27",
    ),
    (
        "PAKKA LIMITED has informed regarding Sanction of the Scheme of Amalgamation",
        "Sanction of the Scheme of Amalgamation",
    ),
    (
        "Pursuant to Regulation 30 read with Clause 7 of Para A of Part A of Schedule III of the "
        "SEBI Listing Regulations, 2015, this is to inform you that the Members of the Company "
        "have approved the Special Resolution",
        "The Members have approved the Special Resolution",
    ),
    (
        "Zen Technologies Limited has informed the Exchange regarding Exercise of 350  Options.",
        "Exercise of 350 Options.",
    ),
    (
        "Gland Pharma Limited has submitted the Exchange a copy Srutinizers report of  Postal "
        "Ballot. Further, the company has informed the Exchange regarding voting results.",
        "A copy Srutinizers report of Postal Ballot; voting results.",
    ),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_clean_description(text: str, expected: str) -> None:
    assert clean_description(text) == expected


def test_says_nothing_falls_back_to_summary_then_subject() -> None:
    text = "Tata Power Company Limited has informed the Exchange about General Updates"
    summary = (
        "Tata Power Company Limited filed a notice of appeal before the Singapore Court of "
        "Appeal on September 7, 2026. The appeal is scheduled for hearing on January 19, 2027."
    )
    assert headline_for("General Updates", text, summary).startswith(
        "Tata Power Company Limited filed a notice of appeal"
    )
    assert "January" not in headline_for("General Updates", text, summary)
    assert headline_for(
        "Credit Rating", "X Limited has informed the Exchange about Credit Rating"
    ) == ("Credit Rating")


def test_headline_drops_trailing_period_and_respects_length() -> None:
    long = "Company has informed the Exchange regarding " + "a very long description " * 20
    h = headline_for("Updates", long)
    assert len(h) <= MAX_CHARS and h.endswith("…")
    assert not headline_for(
        "Appointment", "X has informed the Exchange regarding Appointment of Mr A."
    ).endswith(".")


def test_shorten_keeps_short_text() -> None:
    assert shorten("Short.") == "Short."
