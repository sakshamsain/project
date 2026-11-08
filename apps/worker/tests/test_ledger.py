from finn.pull.fiscal import Period
from finn.pull.ledger import Promise, check, quarters_of
from finn.push.results_math import StatementLines


def lines(
    revenue: float,
    pbeit: float,
    other: float = 0.0,
    finance: float = 0.0,
    dep: float = 0.0,
    pat: float = 0.0,
) -> StatementLines:
    return StatementLines(
        revenue_from_operations=revenue,
        other_income=other,
        finance_costs=0.0,
        depreciation=0.0,
        profit_before_exceptional_and_tax=pbeit,
        exceptional_items=0.0,
        profit_before_tax=pbeit,
        tax_expense=0.0,
        profit_after_tax=pat or pbeit,
    )


SERIES = {
    "Q1 FY26": lines(1000, 200, other=20),
    "Q2 FY26": lines(1000, 200, other=20),
    "Q3 FY26": lines(1000, 200, other=20),
    "Q4 FY26": lines(1000, 200, other=20),
    "Q1 FY27": lines(1100, 240, other=20),  # EBIT 220 on 1100 = 20%
    "Q2 FY27": lines(1150, 250, other=20),  # EBIT 230 on 1150
}


def margin(lo: float | None, hi: float | None, period: Period) -> Promise:
    return Promise("ebit_margin", "margin", "inr", lo, hi, "%", period)


def test_quarters_of_periods() -> None:
    assert [q.label for q in quarters_of(Period(27, "H2"))] == ["Q3 FY27", "Q4 FY27"]
    assert len(quarters_of(Period(27, "FY"))) == 4


def test_margin_on_track_mid_year_and_delivered_for_a_full_year() -> None:
    c = check(margin(20, 22, Period(27, "FY")), SERIES)
    assert c.status == "on_track" and (c.reported, c.needed) == (2, 4)
    assert abs(c.actual - (450 / 2250 * 100)) < 1e-9  # 20.0%
    full = check(margin(17, 19, Period(26, "FY")), SERIES)
    assert full.status == "delivered" and abs(full.actual - 18.0) < 1e-9
    assert check(margin(19, 20, Period(26, "FY")), SERIES).status == "missed"
    assert check(margin(21, 22, Period(27, "FY")), SERIES).status == "off_track"


def test_growth_needs_the_base_year() -> None:
    g = Promise("revenue_growth", "growth", "inr", 10, 14, "%", Period(27, "H1"))
    c = check(g, SERIES)
    assert c.status == "delivered" and abs(c.actual - 12.5) < 1e-9
    no_base = Promise("revenue_growth", "growth", "inr", 10, 14, "%", Period(26, "H1"))
    assert check(no_base, SERIES).status == "not_measurable"


def test_what_filings_cannot_measure() -> None:
    cc = Promise("revenue_growth", "growth", "constant_currency", 1, 2, "%", Period(27, "FY"))
    assert check(cc, SERIES).status == "not_measurable"
    words = Promise("ebit_margin", "qualitative", "inr", None, None, "%", Period(27, "FY"))
    assert check(words, SERIES).status == "not_measurable"
    later = margin(20, 22, Period(28, "FY"))
    assert check(later, SERIES).status == "too_early"
    order = Promise("order_inflow", "growth", "inr", 10, 12, "%", Period(27, "FY"))
    assert check(order, SERIES).status == "not_measurable"


def test_levels_compare_only_complete_periods() -> None:
    rev = Promise("revenue", "level", "inr", 4000, None, "crore", Period(26, "FY"))
    assert check(rev, SERIES).status == "delivered"
    partial = Promise("revenue", "level", "inr", 5000, None, "crore", Period(27, "FY"))
    c = check(partial, SERIES)
    assert c.status == "too_early" and c.actual == 2250


def test_margin_change_in_bps() -> None:
    bps = Promise("ebit_margin", "margin", "inr", 100, None, "bps", Period(27, "H1"))
    c = check(bps, SERIES)
    assert c.status == "delivered" and abs(c.actual - 200.0) < 1e-6  # 20.0% against 18.0%


def test_segment_and_adjusted_targets_are_not_checked_against_the_company() -> None:
    seg = Promise(
        "revenue", "level", "inr", 1500, None, "crore", Period(26, "FY"), "segment", "telecom"
    )
    c = check(seg, SERIES)
    assert c.status == "not_measurable" and "telecom" in c.note
    adj = Promise(
        "revenue_growth",
        "growth",
        "inr",
        15,
        17,
        "%",
        Period(27, "H1"),
        "adjusted",
        "excluding the JV",
    )
    assert check(adj, SERIES).status == "not_measurable"
