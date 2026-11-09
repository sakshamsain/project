"""The bridge: a results filing checks the company's promises again, in code."""

from __future__ import annotations

from datetime import date

from test_results_card import Recorded

from finn.core.db import Jsonb, connect, fetch_all
from finn.pull.bridge import recheck_after_results

ISIN = "INE081A01020"


def _seed(url: str, with_promise: bool) -> int:
    with connect(url) as conn:
        fetch_all(conn, "insert into companies (isin, name) values (%s, 'Tata Steel')", [ISIN])
        doc = fetch_all(
            conn,
            "insert into documents (isin, doc_type, source_url, pages, has_text_layer)"
            " values (%s, 'transcript', 'https://nsearchives.nseindia.com/t.pdf', 20, true)"
            " returning id",
            [ISIN],
        )[0]["id"]
        if with_promise:
            # "Revenue growth of 5 to 8% this year": FY27, checked against filed quarters.
            fetch_all(
                conn,
                "insert into guidance (isin, metric, metric_key, kind, basis, value_low,"
                " value_high, unit, period_label, period_start, period_end, quote, page,"
                " document_id, call_date, scope)"
                " values (%s, 'Revenue growth', 'revenue_growth', 'growth', 'inr', 5, 8, '%%',"
                " 'FY27', '2026-04-01', '2027-03-31', %s, 4, %s, %s, 'company')",
                [ISIN, "We expect revenue growth of 5 to 8% this year.", doc, date(2026, 7, 30)],
            )
        fetch_all(
            conn,
            "insert into dossier_sections (isin, section, docset_hash, prompt_version, body)"
            " values (%s, 'ledger', 'latest', 'guidance-v3', %s)",
            [ISIN, Jsonb({"counts": {}})],
        )
        event = fetch_all(
            conn,
            "insert into events (isin, category, first_seen_at, last_filed_at, enrichment)"
            " values (%s, 'results', now(), now(), '{}') returning id",
            [ISIN],
        )
        return int(event[0]["id"])


def test_no_ledger_means_nothing_to_check(clean_db: str) -> None:
    event = _seed(clean_db, with_promise=False)
    assert recheck_after_results(clean_db, Recorded(), ISIN, "TATASTEEL", event) is None


def test_results_check_promises_and_mark_the_event(clean_db: str) -> None:
    event = _seed(clean_db, with_promise=True)
    summary = recheck_after_results(clean_db, Recorded(), ISIN, "TATASTEEL", event)
    assert summary is not None
    assert sum(summary["counts"].values()) == 1
    assert "Q2 FY27" in summary["quarters_on_file"]
    with connect(clean_db) as conn:
        row = fetch_all(conn, "select status, checked_at from guidance where isin = %s", [ISIN])[0]
        ev = fetch_all(
            conn, "select enrichment -> 'ledger' as l from events where id = %s", [event]
        )
        ledger = fetch_all(
            conn, "select body -> 'counts' as c from dossier_sections where isin = %s", [ISIN]
        )
        stored = fetch_all(conn, "select count(*) as n from financials where isin = %s", [ISIN])
    assert row["status"] is not None and row["checked_at"] is not None
    assert ev[0]["l"]["counts"] == summary["counts"]
    assert ledger[0]["c"] == summary["counts"]
    assert int(stored[0]["n"]) > 0  # the quarters it checked against are kept
