"""Build the Promise Ledger for one company.

    transcripts (NSE) -> pages -> guidance (model, then verified) -> checks (code) -> ledger

Re-running is safe: documents are keyed by URL, a transcript's guidance is replaced as a
whole, and every check is recomputed from the quarters on file.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any, Protocol

from finn.core.db import Conn, Jsonb, fetch_all
from finn.llm.client import Llm
from finn.pull.financials import lines_by_label, quarterly_results, store_quarters
from finn.pull.fiscal import parse_period
from finn.pull.guidance import PROMPT_VERSION, GuidanceItem, extract_guidance
from finn.pull.ledger import Promise, check
from finn.pull.transcripts import TranscriptRef, find_transcripts, store_document, stored_pages
from finn.push.results_math import StatementLines
from finn.sources.pdf import NotAPdf, pdf_text


class DossierSource(Protocol):
    def announcements(
        self, day_from: date, day_to: date, symbol: str | None = None
    ) -> list[Any]: ...
    def integrated_filings(self, symbol: str) -> Any: ...
    def fetch_text(self, url: str) -> str | None: ...
    def fetch_bytes(self, url: str, max_bytes: int = ...) -> bytes | None: ...


def company(conn: Conn, symbol: str) -> tuple[str, str] | None:
    rows = fetch_all(
        conn,
        "select c.isin, c.name from company_aliases a join companies c on c.isin = a.isin"
        " where a.kind = 'nse_symbol' and a.value = upper(%s) and a.valid_to is null limit 1",
        [symbol],
    )
    return (str(rows[0]["isin"]), str(rows[0]["name"])) if rows else None


def existing_document(conn: Conn, url: str) -> int | None:
    rows = fetch_all(
        conn,
        "select id from documents where source_url = %s and pages > 0 and has_text_layer",
        [url],
    )
    return int(rows[0]["id"]) if rows else None


def store_guidance(
    conn: Conn, isin: str, document_id: int, call_date: date, items: list[GuidanceItem]
) -> int:
    fetch_all(conn, "delete from guidance where document_id = %s", [document_id])
    for g in items:
        start, end = g.period.bounds() if g.period else (None, None)
        fetch_all(
            conn,
            "insert into guidance (isin, metric, target_period, value_low, value_high, unit,"
            " qualifier, quote, speaker, document_id, page, call_date, metric_key, kind,"
            " basis, period_label, period_start, period_end, extraction, scope, scope_note)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " %s, %s, %s)"
            " on conflict do nothing",
            [
                isin,
                g.metric or g.metric_key,
                g.period_label,
                g.value_low,
                g.value_high,
                g.unit,
                g.kind,
                g.quote,
                g.speaker,
                document_id,
                g.page,
                call_date,
                g.metric_key,
                g.kind,
                g.basis,
                g.period_label,
                start,
                end,
                Jsonb(g.raw),
                g.scope,
                g.scope_note,
            ],
        )
    return len(items)


def recheck(conn: Conn, isin: str, series: dict[str, StatementLines]) -> dict[str, int]:
    """Recompute every promise of a company against the quarters on file."""
    counts: dict[str, int] = {}
    rows = fetch_all(
        conn,
        "select id, metric_key, kind, basis, value_low, value_high, unit, period_label,"
        " call_date, scope, scope_note, extraction ->> 'metric_key' as claimed"
        " from guidance where isin = %s",
        [isin],
    )
    for r in rows:
        period = parse_period(r["period_label"], r["call_date"]) if r["period_label"] else None
        c = check(
            Promise(
                metric_key=str(r["metric_key"] or "other"),
                kind=str(r["kind"] or "qualitative"),
                basis=str(r["basis"] or "inr"),
                value_low=None if r["value_low"] is None else float(r["value_low"]),
                value_high=None if r["value_high"] is None else float(r["value_high"]),
                unit=str(r["unit"] or "other"),
                period=period,
                scope=str(r["scope"] or "company"),
                scope_note=r["scope_note"],
                claimed_metric=r["claimed"],
            ),
            series,
        )
        fetch_all(
            conn,
            "update guidance set status = %s, actual_value = %s, actual_note = %s,"
            " checked_at = now() where id = %s",
            [c.status, c.actual, c.note, r["id"]],
        )
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts


def build_dossier(
    url: str,
    src: DossierSource,
    llm: Llm,
    symbol: str,
    transcripts: int = 4,
    today: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    from finn.core.db import connect

    today = today or date.today()
    with connect(url) as conn:
        found = company(conn, symbol)
    if found is None:
        return {"symbol": symbol, "status": "unknown symbol"}
    isin, name = found
    say = progress or (lambda _msg: None)

    say("Finding earnings-call transcripts on NSE")
    refs: list[TranscriptRef] = find_transcripts(src, symbol.upper(), today)[:transcripts]
    say(f"Found {len(refs)} transcripts; reading the quarterly figures filed with NSE")
    basis, quarters = quarterly_results(src, symbol.upper(), quarters=10)
    series = lines_by_label(quarters)
    with connect(url) as conn:
        if basis:
            store_quarters(conn, isin, basis, quarters)

    docs: list[dict[str, Any]] = []
    for ref in refs:
        entry: dict[str, Any] = {
            "period": ref.period,
            "filed_on": ref.filed_at_date.isoformat(),
            "url": ref.url,
        }
        with connect(url) as conn:
            doc_id = existing_document(conn, ref.url)
            pages = stored_pages(conn, doc_id) if doc_id else []
        if not pages:
            data = src.fetch_bytes(ref.url)
            if data is None:
                docs.append({**entry, "status": "missing"})
                continue
            try:
                text = pdf_text(data)
            except NotAPdf:
                docs.append({**entry, "status": "not a pdf"})
                continue
            pages = text.pages
            with connect(url) as conn:
                doc_id = store_document(
                    conn,
                    isin,
                    "transcript",
                    ref.url,
                    ref.title,
                    ref.filed_at_date,
                    ref.period,
                    pages,
                    text.scanned,
                )
            if text.scanned:
                docs.append({**entry, "status": "scanned", "pages": len(pages)})
                continue
        say(f"Reading the {ref.period.replace('FY', ' FY')} call ({len(pages)} pages)")
        verified, model = extract_guidance(llm, pages, name, ref.filed_at_date, ref.period)
        with connect(url) as conn:
            store_guidance(conn, isin, int(doc_id or 0), ref.filed_at_date, verified.items)
        docs.append(
            {
                **entry,
                "status": "read",
                "document_id": doc_id,
                "pages": len(pages),
                "promises": len(verified.items),
                "dropped_quotes": verified.dropped_quotes,
                "dropped_figures": verified.dropped_figures,
                "model": model,
            }
        )

    say(f"Checking promises against {len(quarters)} quarters of filed figures")
    with connect(url) as conn:
        current = [int(d["document_id"]) for d in docs if d.get("document_id")]
        # Promises from transcripts no longer in the last four calls leave the ledger.
        fetch_all(
            conn,
            "delete from guidance where isin = %s and not (document_id = any(%s))",
            [isin, current],
        )
        counts = recheck(conn, isin, series)
        body = {
            "symbol": symbol.upper(),
            "company": name,
            "basis": basis,
            "quarters_on_file": sorted(quarters, key=lambda q: (q[-2:], q)),
            "transcripts": docs,
            "counts": counts,
            "prompt_version": PROMPT_VERSION,
            "built_on": today.isoformat(),
        }
        fetch_all(
            conn,
            "insert into dossier_sections (isin, section, docset_hash, prompt_version, body)"
            " values (%s, 'ledger', 'latest', %s, %s)"
            " on conflict (isin, section, docset_hash, prompt_version)"
            " do update set body = excluded.body, built_at = now()",
            [isin, PROMPT_VERSION, Jsonb(body)],
        )
    return {"symbol": symbol.upper(), "transcripts": len(docs), "counts": counts}
