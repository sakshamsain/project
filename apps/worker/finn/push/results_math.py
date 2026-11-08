"""Headline numbers for a results card, computed in code from statement lines.

All amounts are INR crore. EBITDA is not a line in the statutory format, so it is
derived here and labelled "EBITDA (excl. other income)". Banks and NBFCs show
operating profit before provisions (PPOP) instead.

`consistency_failures` runs before anything is shown: a card with failures renders
"Numbers need a look" and the filing link, never a possibly wrong figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CRORE_PER_UNIT: dict[str, float] = {
    "crore": 1.0,
    "crores": 1.0,
    "cr": 1.0,
    "lakh": 0.01,
    "lakhs": 0.01,
    "lacs": 0.01,
    "million": 0.1,
    "millions": 0.1,
    "mn": 0.1,
    "billion": 100.0,
    "bn": 100.0,
    "thousand": 1e-4,
    "thousands": 1e-4,
    "rupees": 1e-7,
}


def to_crore(value: float, unit: str) -> float:
    try:
        return value * CRORE_PER_UNIT[unit.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unknown unit: {unit!r}") from exc


@dataclass(frozen=True, slots=True)
class StatementLines:
    """One period, one basis (consolidated or standalone), in INR crore."""

    revenue_from_operations: float
    other_income: float
    finance_costs: float
    depreciation: float
    profit_before_exceptional_and_tax: float
    exceptional_items: float  # signed as reported: gains positive, losses negative
    profit_before_tax: float
    tax_expense: float
    profit_after_tax: float  # total profit for the period, before minority split
    share_of_associates_jv: float = 0.0
    net_interest_income: float | None = None  # banks and NBFCs
    operating_profit_before_provisions: float | None = None  # banks and NBFCs


def ebitda_excl_other_income(s: StatementLines) -> float:
    return s.profit_before_exceptional_and_tax + s.finance_costs + s.depreciation - s.other_income


def pct_change(current: float, previous: float | None) -> float | None:
    """Percent change against |previous|, so a smaller loss reads as an improvement.
    Returns None when there is no meaningful base."""
    if previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def margin_pct(value: float, revenue: float) -> float | None:
    return None if revenue == 0 else value / revenue * 100.0


@dataclass(frozen=True, slots=True)
class MetricRow:
    name: str
    value: float
    qoq_pct: float | None
    yoy_pct: float | None


@dataclass(frozen=True, slots=True)
class ResultsCard:
    rows: list[MetricRow]
    margin_label: str
    margin_pct: float | None
    margin_qoq_bps: float | None
    margin_yoy_bps: float | None
    flags: list[str] = field(default_factory=list)


def _operating_line(s: StatementLines, bank_like: bool) -> float:
    if bank_like:
        if s.operating_profit_before_provisions is None:
            raise ValueError("bank-like statement needs operating_profit_before_provisions")
        return s.operating_profit_before_provisions
    return ebitda_excl_other_income(s)


def _bps(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round((a - b) * 100.0, 1)


def build_card(
    current: StatementLines,
    previous_quarter: StatementLines | None,
    same_quarter_last_year: StatementLines | None,
    bank_like: bool = False,
) -> ResultsCard:
    op_name = "PPOP" if bank_like else "EBITDA (excl. other income)"
    lender_nii = bank_like and current.net_interest_income is not None
    rev_name, rev_attr = (
        ("NII", "net_interest_income") if lender_nii else ("Revenue", "revenue_from_operations")
    )

    def line(s: StatementLines | None, attr: str) -> float | None:
        if s is None:
            return None
        if attr == "operating":
            return _operating_line(s, bank_like)
        value: float | None = getattr(s, attr)
        return value

    rows = []
    for name, attr in (
        (rev_name, rev_attr),
        (op_name, "operating"),
        ("PBT", "profit_before_tax"),
        ("PAT", "profit_after_tax"),
    ):
        cur = line(current, attr)
        assert cur is not None
        rows.append(
            MetricRow(
                name,
                round(cur, 2),
                _round(pct_change(cur, line(previous_quarter, attr))),
                _round(pct_change(cur, line(same_quarter_last_year, attr))),
            )
        )

    def op_margin(s: StatementLines | None) -> float | None:
        if s is None or bank_like:  # a lender's PPOP over income is not a margin anyone reads
            return None
        return margin_pct(_operating_line(s, bank_like), s.revenue_from_operations)

    m_cur = op_margin(current)
    flags = []
    pbt = current.profit_before_tax
    if current.exceptional_items and pbt and abs(current.exceptional_items) > 0.05 * abs(pbt):
        sign = "gain" if current.exceptional_items > 0 else "charge"
        flags.append(f"PBT includes a one-off {sign} of ₹{abs(current.exceptional_items):,.0f} Cr")
    for label, prev in (("QoQ", previous_quarter), ("YoY", same_quarter_last_year)):
        if prev is not None and prev.profit_after_tax < 0 <= current.profit_after_tax:
            flags.append(f"Back to profit {label}")
        if prev is not None and prev.profit_after_tax >= 0 > current.profit_after_tax:
            flags.append(f"Swung to a loss {label}")

    return ResultsCard(
        rows=rows,
        margin_label=f"{op_name} margin",
        margin_pct=_round(m_cur),
        margin_qoq_bps=_bps(m_cur, op_margin(previous_quarter)),
        margin_yoy_bps=_bps(m_cur, op_margin(same_quarter_last_year)),
        flags=flags,
    )


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def consistency_failures(s: StatementLines, tolerance_pct: float = 1.0) -> list[str]:
    """Accounting identities that must hold before a card is shown."""
    scale = max(abs(s.revenue_from_operations), abs(s.profit_before_tax), 1.0)
    tol = max(0.5, scale * tolerance_pct / 100.0)
    failures = []
    if s.revenue_from_operations <= 0:
        failures.append("revenue_not_positive")
    pbt_candidates = (
        s.profit_before_exceptional_and_tax + s.exceptional_items,
        s.profit_before_exceptional_and_tax + s.exceptional_items + s.share_of_associates_jv,
    )
    if all(abs(s.profit_before_tax - c) > tol for c in pbt_candidates):
        failures.append("pbt_does_not_reconcile")
    pat_candidates = (
        s.profit_before_tax - s.tax_expense,
        s.profit_before_tax - s.tax_expense + s.share_of_associates_jv,
    )
    if all(abs(s.profit_after_tax - c) > tol for c in pat_candidates):
        failures.append("pat_does_not_reconcile")
    return failures
