"""Indian fiscal calendar: FY27 runs 1 Apr 2026 to 31 Mar 2027; Q1 is Apr-Jun.

Used to normalise guidance periods ("FY27", "H2", "next year") against the call date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True, slots=True, order=True)
class Period:
    fy: int  # two-digit fiscal year label, e.g. 27 for FY27
    kind: str  # "FY", "H1", "H2", "Q1".."Q4"

    @property
    def label(self) -> str:
        return f"FY{self.fy:02d}" if self.kind == "FY" else f"{self.kind} FY{self.fy:02d}"

    def bounds(self) -> tuple[date, date]:
        start_year = 2000 + self.fy - 1  # FY27 starts in April 2026
        if self.kind == "FY":
            return date(start_year, 4, 1), date(start_year + 1, 3, 31)
        if self.kind == "H1":
            return date(start_year, 4, 1), date(start_year, 9, 30)
        if self.kind == "H2":
            return date(start_year, 10, 1), date(start_year + 1, 3, 31)
        q = int(self.kind[1])
        first_month = 4 + 3 * (q - 1)  # 4, 7, 10, 13
        y, m = (
            (start_year, first_month) if first_month <= 12 else (start_year + 1, first_month - 12)
        )
        end_m = m + 2
        end_day = 31 if end_m in (1, 3, 5, 7, 8, 10, 12) else 30
        return date(y, m, 1), date(y, end_m, end_day)

    def months_label(self) -> str:
        """Calendar months, e.g. "Jul-Sep 2026" for Q2 FY27."""
        start, end = self.bounds()
        first, last = MONTHS[start.month - 1], MONTHS[end.month - 1]
        if start.year == end.year:
            return f"{first}–{last} {end.year}"
        return f"{first} {start.year}–{last} {end.year}"


def fiscal_year(d: date) -> int:
    return (d.year + 1 if d.month >= 4 else d.year) % 100


def quarter_of(d: date) -> Period:
    q = ((d.month - 4) % 12) // 3 + 1
    return Period(fiscal_year(d), f"Q{q}")


def previous_quarter(p: Period) -> Period:
    q = int(p.kind[1])
    return Period(p.fy, f"Q{q - 1}") if q > 1 else Period(p.fy - 1, "Q4")


def same_quarter_last_year(p: Period) -> Period:
    return Period(p.fy - 1, p.kind)


# Four-digit years first, so "FY2027" is not read as FY20.
_FY = r"(?:fy|f\.y\.|fiscal(?: year)?)\s*'?(\d{4}|\d{2})"
_RANGE = r"(?:fy\s*)?(\d{4})\s*[-–/]\s*(\d{4}|\d{2})"


def parse_period(text: str, said_on: date) -> Period | None:
    """Parse a period phrase from a transcript, relative to the call date.
    Returns None for phrases that name no measurable period ("medium term")."""
    t = text.strip().lower()
    current_fy = fiscal_year(said_on)

    m = re.search(r"\b(q[1-4]|h[12])\s*'?\s*" + _FY, t) or re.search(
        r"\b(q[1-4]|h[12])\s*fy\s*'?(\d{4}|\d{2})", t
    )
    if m:
        return Period(_two_digit(m.group(2)), m.group(1).upper())
    m = re.search(r"\b" + _RANGE + r"\b", t)
    if m:
        return Period(_two_digit(m.group(2)), "FY")
    m = re.search(_FY, t)
    if m:
        return Period(_two_digit(m.group(1)), "FY")
    if re.search(r"\b(next|coming) (fiscal|financial year|year)\b", t):
        return Period(current_fy + 1, "FY")
    if re.search(r"\b(this|current) (fiscal|financial year|year)\b", t):
        return Period(current_fy, "FY")
    if re.search(r"\bnext quarter\b", t):
        q = quarter_of(said_on)
        n = int(q.kind[1])
        return Period(q.fy, f"Q{n + 1}") if n < 4 else Period(q.fy + 1, "Q1")
    m = re.search(r"\b(second half|h2)\b", t)
    if m:
        return Period(current_fy, "H2")
    return None


def _two_digit(y: str) -> int:
    return int(y) % 100
