"""The bridge between the Brief and the Promise Ledger: new results against old promises.

When a company with a ledger files results, its promises are checked again against the
quarters now on file. Code does the checking; no model is called. The results event
records what was found, so its card can say whether the company is on track, and the
ledger on the research page moves with it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from finn.core.db import Conn, Jsonb, fetch_all
from finn.pull.dossier import recheck
from finn.pull.financials import lines_by_label, quarterly_results, store_quarters
from finn.push.results import ResultsSource

MEASURED = ("delivered", "missed", "on_track", "off_track")


def _statuses(conn: Conn, isin: str) -> dict[int, str]:
    rows = fetch_all(conn, "select id, status from guidance where isin = %s", [isin])
    return {int(r["id"]): str(r["status"]) for r in rows}


def ledger_summary(conn: Conn, isin: str, before: dict[int, str]) -> dict[str, Any]:
    """Counts by status, the measured promises (latest call first) and what moved."""
    rows = fetch_all(
        conn,
        "select g.id, g.metric, g.metric_key, g.period_label, g.status, g.actual_note,"
        " g.value_low, g.value_high, g.unit, g.basis, g.quote, g.page, g.document_id,"
        " g.call_date::text as call_date"
        " from guidance g where g.isin = %s order by g.call_date desc, g.id",
        [isin],
    )
    counts: dict[str, int] = {}
    for r in rows:
        counts[str(r["status"])] = counts.get(str(r["status"]), 0) + 1
    measured = [
        {
            "id": int(r["id"]),
            "metric": r["metric"],
            "metric_key": r["metric_key"],
            "period": r["period_label"],
            "status": r["status"],
            "note": r["actual_note"],
            "low": None if r["value_low"] is None else float(r["value_low"]),
            "high": None if r["value_high"] is None else float(r["value_high"]),
            "unit": r["unit"],
            "basis": r["basis"],
            "quote": r["quote"],
            "page": r["page"],
            "document_id": int(r["document_id"]),
            "call_date": r["call_date"],
        }
        for r in rows
        if r["status"] in MEASURED
    ]
    changes = [
        {"id": m["id"], "metric": m["metric"], "period": m["period"], "was": before.get(m["id"])}
        for m in measured
        if before.get(m["id"]) not in (None, m["status"])
    ]
    return {"counts": counts, "measured": measured[:6], "changes": changes}


def recheck_after_results(
    url: str, src: ResultsSource, isin: str, symbol: str, event_id: int | None = None
) -> dict[str, Any] | None:
    """Check a company's promises against its quarters now on file; None without a
    ledger. The summary goes on the results event and into the ledger's counts."""
    from finn.core.db import connect

    with connect(url) as conn:
        before = _statuses(conn, isin)
    if not before:
        return None
    basis, quarters = quarterly_results(src, symbol, quarters=10)
    series = lines_by_label(quarters)
    with connect(url) as conn:
        if basis:
            store_quarters(conn, isin, basis, quarters)
        recheck(conn, isin, series)
        summary = ledger_summary(conn, isin, before)
        summary["checked_at"] = datetime.now(UTC).isoformat()
        summary["quarters_on_file"] = sorted(quarters, key=lambda q: (q[-2:], q))
        if event_id is not None:
            fetch_all(
                conn,
                "update events set enrichment = jsonb_set(enrichment, '{ledger}', %s)"
                " where id = %s",
                [Jsonb(summary), event_id],
            )
        fetch_all(
            conn,
            "update dossier_sections set body = jsonb_set(body, '{counts}', %s)"
            " where isin = %s and section = 'ledger'",
            [Jsonb(summary["counts"]), isin],
        )
    return summary
