"""Promise against delivery: what code can say about one piece of guidance.

Every figure here is computed from quarterly statements the company filed as XBRL; the
model only reported what was promised. A promise is

    delivered       its period is fully reported and the figure is inside the range
    missed          its period is fully reported and the figure is outside it
    on_track        part of the period is reported and the figure so far is inside it
    off_track       part of the period is reported and the figure so far is outside it
    too_early       nothing of its period is reported yet
    not_measurable  filed statements cannot measure it: constant currency, order inflow,
                    a promise in words, or a base period that is not on file
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from finn.pull.fiscal import Period, same_quarter_last_year
from finn.push.results_math import StatementLines, ebitda_excl_other_income

GROWTH = {"revenue_growth": "revenue", "pat_growth": "pat", "ebitda_growth": "ebitda"}
MARGINS = {"ebitda_margin", "ebit_margin", "operating_margin", "pat_margin"}
LEVELS = {"revenue", "ebitda", "pat"}
COMPUTABLE = set(GROWTH) | MARGINS | LEVELS
EPS = 1e-9

NAMES = {
    "revenue": "Revenue",
    "ebitda": "EBITDA",
    "pat": "PAT",
    "ebitda_margin": "EBITDA margin",
    "ebit_margin": "Operating (EBIT) margin",
    "operating_margin": "Operating (EBIT) margin",
    "pat_margin": "PAT margin",
}


@dataclass(frozen=True, slots=True)
class Promise:
    metric_key: str
    kind: str  # growth | margin | level | qualitative
    basis: str  # inr | constant_currency | usd | other
    value_low: float | None
    value_high: float | None
    unit: str  # % | bps | crore | other
    period: Period | None
    scope: str = "company"  # company | segment | adjusted
    scope_note: str | None = None


@dataclass(frozen=True, slots=True)
class Check:
    status: str
    actual: float | None
    note: str
    reported: int = 0
    needed: int = 0


def quarters_of(p: Period) -> list[Period]:
    if p.kind == "FY":
        return [Period(p.fy, f"Q{i}") for i in range(1, 5)]
    if p.kind == "H1":
        return [Period(p.fy, "Q1"), Period(p.fy, "Q2")]
    if p.kind == "H2":
        return [Period(p.fy, "Q3"), Period(p.fy, "Q4")]
    return [p]


def _operating(s: StatementLines) -> float:
    """EBIT excluding other income: profit before exceptional items and tax, plus
    finance costs, less other income."""
    return s.profit_before_exceptional_and_tax + s.finance_costs - s.other_income


LINE: dict[str, Callable[[StatementLines], float]] = {
    "revenue": lambda s: s.revenue_from_operations,
    "ebitda": ebitda_excl_other_income,
    "pat": lambda s: s.profit_after_tax,
    "operating": _operating,
}
MARGIN_LINE = {
    "ebitda_margin": "ebitda",
    "ebit_margin": "operating",
    "operating_margin": "operating",
    "pat_margin": "pat",
}


def _total(series: Mapping[str, StatementLines], qs: list[Period], line: str) -> float:
    return sum(LINE[line](series[q.label]) for q in qs)


def _margin(series: Mapping[str, StatementLines], qs: list[Period], key: str) -> float:
    return _total(series, qs, MARGIN_LINE[key]) / _total(series, qs, "revenue") * 100.0


def _fmt(x: float, unit: str) -> str:
    if unit == "crore":
        return f"₹{x:,.0f} Cr"
    if unit == "bps":
        return f"{x:+.0f} bps"
    return f"{x:.1f}%"


def _range(p: Promise) -> str:
    lo, hi = p.value_low, p.value_high
    if lo is not None and hi is not None and lo != hi:
        return f"{_fmt(lo, p.unit)} to {_fmt(hi, p.unit)}"
    if lo is not None and hi is not None:
        return _fmt(lo, p.unit)
    if lo is not None:
        return f"at least {_fmt(lo, p.unit)}"
    if hi is not None:
        return f"at most {_fmt(hi, p.unit)}"
    return "no figure"


def check(p: Promise, series: Mapping[str, StatementLines]) -> Check:
    if p.kind == "qualitative" or p.metric_key not in COMPUTABLE:
        return Check("not_measurable", None, "Filed statements do not report this measure.")
    if p.scope == "segment":
        what = f" ({p.scope_note})" if p.scope_note else ""
        return Check(
            "not_measurable",
            None,
            f"A target for one part of the business{what}; filed statements cover the company.",
        )
    if p.scope == "adjusted":
        what = f" ({p.scope_note})" if p.scope_note else ""
        return Check(
            "not_measurable", None, f"An adjusted figure{what}; filed statements are unadjusted."
        )
    if p.period is None:
        return Check("not_measurable", None, "No period was given.")
    if p.value_low is None and p.value_high is None:
        return Check("not_measurable", None, "No figure was given.")
    if p.basis not in ("inr", ""):
        return Check(
            "not_measurable",
            None,
            f"Guided in {p.basis.replace('_', ' ')}; filed statements are in rupees.",
        )

    qs = quarters_of(p.period)
    reported = [q for q in qs if q.label in series]
    if not reported:
        return Check(
            "too_early", None, f"No quarter of {p.period.label} is reported yet.", 0, len(qs)
        )
    span = (
        p.period.label
        if len(reported) == len(qs)
        else f"{', '.join(q.label for q in reported)} ({len(reported)} of {len(qs)} quarters)"
    )

    if p.metric_key in GROWTH or (p.metric_key in MARGINS and p.unit == "bps"):
        base = [same_quarter_last_year(q) for q in reported]
        missing = [b.label for b in base if b.label not in series]
        if missing:
            return Check(
                "not_measurable",
                None,
                f"The comparison quarters ({', '.join(missing)}) are not on file.",
                len(reported),
                len(qs),
            )
        if p.metric_key in GROWTH:
            line = GROWTH[p.metric_key]
            now, then = _total(series, reported, line), _total(series, base, line)
            if then <= 0:
                return Check(
                    "not_measurable", None, "The base period was a loss.", len(reported), len(qs)
                )
            actual = (now / then - 1.0) * 100.0
            what = f"{NAMES[line]} growth for {span}: {_fmt(actual, '%')} year on year"
        else:
            actual = (
                _margin(series, reported, p.metric_key) - _margin(series, base, p.metric_key)
            ) * 100
            what = f"{NAMES[p.metric_key]} change for {span}: {_fmt(actual, 'bps')} year on year"
    elif p.metric_key in MARGINS:
        actual = _margin(series, reported, p.metric_key)
        what = f"{NAMES[p.metric_key]} for {span}: {_fmt(actual, '%')}"
    else:  # a level in crore: only a full period can be compared
        actual = _total(series, reported, p.metric_key)
        if len(reported) < len(qs):
            return Check(
                "too_early",
                actual,
                f"{NAMES[p.metric_key]} so far: {_fmt(actual, 'crore')} in {span}.",
                len(reported),
                len(qs),
            )
        what = f"{NAMES[p.metric_key]} for {span}: {_fmt(actual, 'crore')}"

    inside = (p.value_low is None or actual >= p.value_low - EPS) and (
        p.value_high is None or actual <= p.value_high + EPS
    )
    complete = len(reported) == len(qs)
    status = (
        ("delivered" if inside else "missed")
        if complete
        else ("on_track" if inside else "off_track")
    )
    return Check(status, round(actual, 4), f"{what}; promised {_range(p)}.", len(reported), len(qs))
