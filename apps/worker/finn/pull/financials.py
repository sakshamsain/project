"""Quarterly figures for research, from the company's own Integrated Filing XBRL.

The ledger checks promises against these figures only. Each quarter is read from the
filing for that quarter, checked for internal consistency, and stored in `financials`;
a quarter that does not add up is left out rather than used.
"""

from __future__ import annotations

from typing import Any

from finn.core.db import Conn, copy_upsert
from finn.pull.fiscal import Period, previous_quarter, quarter_of
from finn.push.results import ResultsSource, _load, financial_rows, quarter_end
from finn.push.results_math import StatementLines, consistency_failures
from finn.sources.nse import parse_integrated_filings, pick_filing
from finn.sources.xbrl import QuarterResults


def quarterly_results(
    src: ResultsSource, symbol: str, quarters: int = 10
) -> tuple[str | None, dict[str, QuarterResults]]:
    """(basis, {"Q2 FY27": results, ...}) for the latest `quarters` quarters on file."""
    filings = parse_integrated_filings(src.integrated_filings(symbol))
    if not filings:
        return None, {}
    latest = filings[0].quarter_end
    basis = "Consolidated" if pick_filing(filings, latest, "Consolidated") else "Standalone"
    out: dict[str, QuarterResults] = {}
    q: Period = quarter_of(latest)
    for _ in range(quarters):
        f = pick_filing(filings, quarter_end(q), basis)
        if f is not None:
            r, _err = _load(src, f)
            if r is not None and not consistency_failures(r.lines):
                out[q.label] = r
        q = previous_quarter(q)
    return basis, out


def store_quarters(conn: Conn, isin: str, basis: str, series: dict[str, QuarterResults]) -> int:
    rows: list[tuple[Any, ...]] = []
    for label, r in series.items():
        rows += financial_rows(isin, basis, label, r.lines)
    copy_upsert(
        conn,
        "financials",
        ["isin", "period", "period_type", "basis", "metric", "value_cr", "source"],
        rows,
        conflict=["isin", "period", "basis", "metric", "source"],
        update=["value_cr"],
    )
    return len(series)


def lines_by_label(series: dict[str, QuarterResults]) -> dict[str, StatementLines]:
    return {k: v.lines for k, v in series.items()}
