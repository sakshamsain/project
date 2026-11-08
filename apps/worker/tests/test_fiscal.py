from datetime import date

import pytest

from finn.pull.fiscal import (
    Period,
    fiscal_year,
    parse_period,
    previous_quarter,
    quarter_of,
    same_quarter_last_year,
)


def test_fiscal_year_turns_in_april() -> None:
    assert fiscal_year(date(2026, 3, 31)) == 26
    assert fiscal_year(date(2026, 4, 1)) == 27
    assert fiscal_year(date(2026, 11, 8)) == 27


def test_quarters_and_labels() -> None:
    q = quarter_of(date(2026, 8, 15))
    assert q == Period(27, "Q2")
    assert q.label == "Q2 FY27"
    assert q.months_label() == "Jul–Sep 2026"
    assert quarter_of(date(2027, 2, 1)) == Period(27, "Q4")
    assert Period(27, "Q4").months_label() == "Jan–Mar 2027"
    assert Period(27, "FY").months_label() == "Apr 2026–Mar 2027"


def test_comparison_quarters() -> None:
    assert previous_quarter(Period(27, "Q1")) == Period(26, "Q4")
    assert previous_quarter(Period(27, "Q3")) == Period(27, "Q2")
    assert same_quarter_last_year(Period(27, "Q2")) == Period(26, "Q2")


@pytest.mark.parametrize(
    ("phrase", "said_on", "expected"),
    [
        ("we expect FY27 revenue growth of 12-14%", date(2026, 5, 10), Period(27, "FY")),
        ("for FY2027", date(2026, 5, 10), Period(27, "FY")),
        ("in 2026-27", date(2026, 5, 10), Period(27, "FY")),
        ("by Q4 FY27", date(2026, 5, 10), Period(27, "Q4")),
        ("H2FY27 margins", date(2026, 8, 1), Period(27, "H2")),
        ("next year", date(2026, 8, 1), Period(28, "FY")),
        ("this fiscal", date(2026, 8, 1), Period(27, "FY")),
        ("next quarter", date(2027, 2, 10), Period(28, "Q1")),
        ("in the second half", date(2026, 8, 1), Period(27, "H2")),
    ],
)
def test_parse_period(phrase: str, said_on: date, expected: Period) -> None:
    assert parse_period(phrase, said_on) == expected


def test_vague_horizon_is_not_measurable() -> None:
    assert parse_period("over the medium term", date(2026, 8, 1)) is None
