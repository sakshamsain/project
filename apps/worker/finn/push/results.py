"""Results cards: Revenue, EBITDA (excl. other income), PBT and PAT, QoQ and YoY.

The three quarters come from the company's own Integrated Filing XBRL on NSE; every
comparison and margin is computed by `results_math`. A quarter that fails the accounting
checks is never compared against; if the reported quarter itself fails, the card says
"Numbers need a look" and links the filing instead of showing a figure.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from finn.core.db import Conn, Jsonb, copy_upsert, fetch_all
from finn.pull.fiscal import Period, previous_quarter, quarter_of, same_quarter_last_year
from finn.push.pipeline import rescore_events
from finn.push.results_math import (
    StatementLines,
    build_card,
    consistency_failures,
    ebitda_excl_other_income,
)
from finn.sources.nse import IST, IntegratedFiling, parse_integrated_filings, pick_filing
from finn.sources.xbrl import QuarterResults, XbrlError, parse_results_xbrl

RETRY_AFTER = timedelta(minutes=30)


class ResultsSource(Protocol):
    def integrated_filings(self, symbol: str) -> Any: ...
    def fetch_text(self, url: str) -> str | None: ...


def quarter_end(p: Period) -> date:
    return p.bounds()[1]


def last_quarter_end_before(d: date) -> date:
    """The most recent quarter end strictly before `d`: results filed on 7 Nov 2026 are
    for the quarter ended 30 Sep 2026."""
    return quarter_end(previous_quarter(quarter_of(d)))


def _load(
    src: ResultsSource, f: IntegratedFiling | None
) -> tuple[QuarterResults | None, str | None]:
    if f is None:
        return None, "no filing"
    text = src.fetch_text(f.xbrl_url)
    if text is None:
        return None, "file missing"
    try:
        return parse_results_xbrl(text, f.quarter_end, f.taxonomy), None
    except XbrlError as exc:
        return None, str(exc)


def build_results_card(src: ResultsSource, symbol: str, quarter: date) -> dict[str, Any]:
    """The card for one company and quarter, as stored in the event's enrichment."""
    filings = parse_integrated_filings(src.integrated_filings(symbol))
    basis = "Consolidated" if pick_filing(filings, quarter, "Consolidated") else "Standalone"
    current_filing = pick_filing(filings, quarter, basis)
    period = quarter_of(quarter)
    base: dict[str, Any] = {
        "period": period.label,
        "months": period.months_label(),
        "quarter_end": quarter.isoformat(),
        "basis": basis,
    }
    if current_filing is None:
        return {**base, "status": "waiting", "reason": "XBRL not filed yet"}
    current, error = _load(src, current_filing)
    sources = {"current": current_filing.xbrl_url}
    if current is None:
        return {**base, "status": "needs_a_look", "reason": error, "sources": sources}
    failures = consistency_failures(current.lines)
    if failures:
        return {
            **base,
            "status": "needs_a_look",
            "consistency_failures": failures,
            "sources": sources,
        }

    def comparable(p: Period, key: str) -> QuarterResults | None:
        f = pick_filing(filings, quarter_end(p), basis)
        q, _ = _load(src, f)
        if q is None or consistency_failures(q.lines):
            return None
        if f is not None:
            sources[key] = f.xbrl_url
        return q

    prev = comparable(previous_quarter(period), "previous_quarter")
    year_ago = comparable(same_quarter_last_year(period), "year_ago")
    lender = current.lender
    if prev is not None and prev.lender != lender:
        prev = None
    if year_ago is not None and year_ago.lender != lender:
        year_ago = None
    card = build_card(
        current.lines,
        prev.lines if prev else None,
        year_ago.lines if year_ago else None,
        bank_like=lender,
    )
    return {
        **base,
        "status": "ok",
        "lender": lender,
        "audited": current.audited,
        "rows": [asdict(r) for r in card.rows],
        "margin_label": card.margin_label,
        "margin_pct": card.margin_pct,
        "margin_qoq_bps": card.margin_qoq_bps,
        "margin_yoy_bps": card.margin_yoy_bps,
        "flags": card.flags,
        "compared_with": {
            "previous_quarter": previous_quarter(period).label if prev else None,
            "year_ago": same_quarter_last_year(period).label if year_ago else None,
        },
        "sources": sources,
        "filed_at": current_filing.filed_at.isoformat() if current_filing.filed_at else None,
        "_lines": {
            period.label: asdict(current.lines),
            **({previous_quarter(period).label: asdict(prev.lines)} if prev else {}),
            **({same_quarter_last_year(period).label: asdict(year_ago.lines)} if year_ago else {}),
        },
    }


def financial_rows(isin: str, basis: str, label: str, s: StatementLines) -> list[tuple[Any, ...]]:
    period = label.replace(" ", "")
    metrics: dict[str, float] = {
        "revenue": s.revenue_from_operations,
        "ebitda": ebitda_excl_other_income(s),
        "pbt": s.profit_before_tax,
        "pat": s.profit_after_tax,
        "other_income": s.other_income,
        "finance_costs": s.finance_costs,
        "depreciation": s.depreciation,
        "exceptional": s.exceptional_items,
        "tax": s.tax_expense,
    }
    if s.net_interest_income is not None:
        metrics["nii"] = s.net_interest_income
    if s.operating_profit_before_provisions is not None:
        metrics["ppop"] = s.operating_profit_before_provisions
        del metrics["ebitda"]
    return [
        (isin, period, "Q", basis.lower(), name, round(value, 4), "xbrl")
        for name, value in metrics.items()
    ]


def store_card(conn: Conn, isin: str, event_id: int, card: dict[str, Any]) -> None:
    lines = card.pop("_lines", {})
    rows: list[tuple[Any, ...]] = []
    for label, values in lines.items():
        rows += financial_rows(isin, card["basis"], label, StatementLines(**values))
    if rows:
        copy_upsert(
            conn,
            "financials",
            ["isin", "period", "period_type", "basis", "metric", "value_cr", "source"],
            rows,
            conflict=["isin", "period", "basis", "metric", "source"],
            update=["value_cr"],
        )
    card["attempted_at"] = datetime.now(IST).isoformat()
    fetch_all(
        conn,
        "update events set enrichment = jsonb_set(enrichment, '{results_card}', %s) where id = %s",
        [Jsonb(card), event_id],
    )
    rescore_events(conn, [event_id])  # the headline can now lead with the numbers


def pending_results_events(
    conn: Conn, days: int = 10, limit: int = 8, force: bool = False
) -> list[dict[str, Any]]:
    """Results events on held companies that have no finished card, oldest attempt first.
    With `force`, finished cards are rebuilt too."""
    done = ("~force~",) if force else ("ok", "needs_a_look")
    return fetch_all(
        conn,
        "select e.id, e.isin, e.first_seen_at, a.value as symbol,"
        " e.enrichment -> 'results_card' ->> 'status' as status,"
        " e.enrichment -> 'results_card' ->> 'attempted_at' as attempted_at"
        " from events e"
        " join company_aliases a on a.isin = e.isin and a.kind = 'nse_symbol'"
        "   and a.valid_to is null"
        " where e.family = 'results' and e.first_seen_at >= now() - make_interval(days => %s)"
        "   and e.isin in (select isin from holdings)"
        "   and coalesce(e.stage, 'filing') in ('filing', 'press_release')"
        "   and coalesce(e.enrichment -> 'results_card' ->> 'status', '') <> all(%s)"
        " order by e.enrichment -> 'results_card' ->> 'attempted_at' nulls first,"
        "   e.first_seen_at desc"
        " limit %s",
        [days, list(done), limit],
    )


def due(attempted_at: str | None, now: datetime) -> bool:
    if not attempted_at:
        return True
    return now - datetime.fromisoformat(attempted_at) >= RETRY_AFTER
