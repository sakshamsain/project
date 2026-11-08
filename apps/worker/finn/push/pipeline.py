"""The push pipeline's write path: exchange rows in, scored events out.

    raw rows -> raw_records (archive) -> filings (classified by rules) -> events (clustered,
    scored, tiered)

One call runs in one transaction under an advisory lock, so overlapping polls cannot
create the same event twice; a retry after a failure redoes the whole batch. Pure logic
lives in `classify`, `events` and `score`; this module only loads and writes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from finn.core.db import Conn, Jsonb, copy_upsert, fetch_all
from finn.push.classify import classify
from finn.push.events import (
    NOVELTY_LOOKBACK,
    WINDOWS,
    EventDraft,
    EventRow,
    FilingFacts,
    assign,
    build,
)
from finn.sources.nse import Announcement, parse_announcements

INGEST_LOCK = 7_140_001  # pg advisory lock id for the filings pipeline
MAX_WINDOW = max(WINDOWS.values())


@dataclass(slots=True)
class IngestReport:
    fetched: int = 0
    new_filings: int = 0
    new_companies: int = 0
    unclassified: int = 0
    events_written: int = 0
    skipped_locked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


def ingest_announcements(
    conn: Conn, rows: Sequence[Mapping[str, Any]], raw_source: str = "nse_api"
) -> IngestReport:
    report = IngestReport()
    if not _try_lock(conn, INGEST_LOCK):
        report.skipped_locked = True
        return report
    by_id = {str(r.get("seq_id")): r for r in rows if r.get("seq_id")}
    anns = parse_announcements(rows)
    report.fetched = len(anns)
    if not anns:
        return report

    copy_upsert(
        conn,
        "raw_records",
        ["source", "source_key", "payload"],
        [(raw_source, a.exchange_id, Jsonb(dict(by_id[a.exchange_id]))) for a in anns],
        conflict=["source", "source_key"],
    )
    known = {
        r["exchange_id"]
        for r in fetch_all(
            conn,
            "select exchange_id from filings where exchange = 'NSE' and exchange_id = any(%s)",
            [[a.exchange_id for a in anns]],
        )
    }
    new = [a for a in anns if a.exchange_id not in known]
    if not new:
        return report

    isin_of, created = resolve_symbols(conn, new)
    report.new_companies = created
    facts: list[FilingFacts] = []
    filing_rows: list[tuple[Any, ...]] = []
    for a in new:
        isin = isin_of.get(a.symbol)
        if isin is None:
            continue
        c = classify(a.subject, a.subject, a.body)
        category = c.category if c else "unclassified"
        attributes = dict(c.attributes) if c else {}
        if c is None:
            report.unclassified += 1
        filing_rows.append(
            (
                isin,
                "NSE",
                a.exchange_id,
                a.filed_at,
                a.subject,
                a.subject,
                a.text or None,
                a.attachment_url,
                category,
                Jsonb(attributes),
                "rules" if c else None,
                c.rule_id if c else None,
                c.confidence if c else None,
                a.symbol,
                a.summary,
            )
        )
        facts.append(_facts(a, isin, category, attributes))

    inserted = copy_upsert(
        conn,
        "filings",
        [
            "isin",
            "exchange",
            "exchange_id",
            "filed_at",
            "subject",
            "exchange_category",
            "body_text",
            "attachment_url",
            "category",
            "attributes",
            "classified_by",
            "rule_id",
            "confidence",
            "symbol",
            "summary",
        ],
        filing_rows,
        conflict=["exchange", "exchange_id"],
        returning=["id", "exchange_id"],
    )
    report.new_filings = len(inserted)
    filing_id = {f"NSE:{r['exchange_id']}": int(r["id"]) for r in inserted}
    facts = [f for f in facts if f.key in filing_id]
    if not facts:
        return report

    since = min(f.filed_at for f in facts) - MAX_WINDOW
    open_events = load_open_events(conn, {f.isin for f in facts}, since)
    touched = assign(facts, open_events)
    event_ids = write_events(conn, touched)
    report.events_written = len(event_ids)

    pairs = [
        (filing_id[m.key], event_ids[d.cluster_key])
        for d in touched
        for m in d.members
        if m.key in filing_id
    ]
    if pairs:
        fetch_all(
            conn,
            "update filings f set event_id = v.event_id"
            " from unnest(%s::bigint[], %s::bigint[]) as v(filing_id, event_id)"
            " where f.id = v.filing_id",
            [[p[0] for p in pairs], [p[1] for p in pairs]],
        )
    return report


def _facts(a: Announcement, isin: str, category: str, attributes: Mapping[str, str]) -> FilingFacts:
    return FilingFacts(
        key=f"NSE:{a.exchange_id}",
        isin=isin,
        filed_at=a.filed_at,
        subject=a.subject,
        text=a.text,
        summary=a.summary,
        category=category,
        attributes=attributes,
        attachment_url=a.attachment_url,
    )


def _try_lock(conn: Conn, key: int) -> bool:
    rows = fetch_all(conn, "select pg_try_advisory_xact_lock(%s) as ok", [key])
    return bool(rows and rows[0]["ok"])


def resolve_symbols(conn: Conn, anns: Iterable[Announcement]) -> tuple[dict[str, str], int]:
    """Map NSE symbols to canonical ISINs through current aliases. A symbol with no alias
    (a fresh listing the equity master has not caught up with) gets a company under the
    ISIN the filing reports."""
    first: dict[str, Announcement] = {}
    for a in anns:
        first.setdefault(a.symbol, a)
    rows = fetch_all(
        conn,
        "select value, isin from company_aliases"
        " where kind = 'nse_symbol' and value = any(%s) and valid_to is null",
        [sorted(first)],
    )
    isin_of = {r["value"]: r["isin"] for r in rows}
    missing = [a for s, a in first.items() if s not in isin_of and a.reported_isin]
    if not missing:
        return isin_of, 0
    created = copy_upsert(
        conn,
        "companies",
        ["isin", "name", "industry"],
        [(a.reported_isin, a.company_name, a.industry) for a in missing],
        conflict=["isin"],
        returning=["isin"],
    )
    copy_upsert(
        conn,
        "company_aliases",
        ["isin", "kind", "value", "valid_from"],
        [(a.reported_isin, "nse_symbol", a.symbol, date(1900, 1, 1)) for a in missing],
        conflict=["kind", "value", "valid_from"],
    )
    for a in missing:
        if a.reported_isin:
            isin_of[a.symbol] = a.reported_isin
    return isin_of, len(created)


def load_open_events(conn: Conn, isins: Iterable[str], since: datetime) -> list[EventDraft]:
    """Events of these companies with a filing on or after `since`, with their members."""
    heads = fetch_all(
        conn,
        "select id, cluster_key, isin, family, enrichment from events"
        " where isin = any(%s) and last_filed_at >= %s and cluster_key is not null",
        [sorted(isins), since],
    )
    return _with_members(conn, heads)


def _with_members(conn: Conn, heads: Sequence[Mapping[str, Any]]) -> list[EventDraft]:
    if not heads:
        return []
    drafts = {
        int(h["id"]): EventDraft(
            cluster_key=str(h["cluster_key"]),
            isin=str(h["isin"]),
            family=str(h["family"]),
            event_id=int(h["id"]),
            reaction=(h.get("enrichment") or {}).get("reaction"),
        )
        for h in heads
    }
    for r in fetch_all(
        conn,
        "select event_id, exchange, exchange_id, isin, filed_at, subject, body_text, summary,"
        " category, attributes, attachment_url from filings where event_id = any(%s)",
        [sorted(drafts)],
    ):
        drafts[int(r["event_id"])].members.append(
            FilingFacts(
                key=f"{r['exchange']}:{r['exchange_id']}",
                isin=str(r["isin"]),
                filed_at=r["filed_at"],
                subject=str(r["subject"]),
                text=str(r["body_text"] or ""),
                summary=r["summary"],
                category=str(r["category"] or "unclassified"),
                attributes={k: str(v) for k, v in (r["attributes"] or {}).items()},
                attachment_url=r["attachment_url"],
            )
        )
    return [d for d in drafts.values() if d.members]


def write_events(conn: Conn, drafts: Sequence[EventDraft]) -> dict[str, int]:
    """Score and upsert drafts by cluster key; returns cluster key -> event id."""
    if not drafts:
        return {}
    earliest = min(d.first_seen_at for d in drafts) - NOVELTY_LOOKBACK
    prior: dict[tuple[str, str], list[tuple[str, datetime]]] = defaultdict(list)
    for r in fetch_all(
        conn,
        "select isin, family, cluster_key, first_seen_at from events"
        " where isin = any(%s) and first_seen_at >= %s",
        [sorted({d.isin for d in drafts}), earliest],
    ):
        prior[(r["isin"], r["family"])].append((str(r["cluster_key"]), r["first_seen_at"]))
    for d in drafts:  # new drafts count as history for each other
        prior[(d.isin, d.family)].append((d.cluster_key, d.first_seen_at))

    rows: list[EventRow] = []
    for d in drafts:
        others = [t for k, t in prior[(d.isin, d.family)] if k != d.cluster_key]
        rows.append(build(d, others))
    written = copy_upsert(
        conn,
        "events",
        [
            "cluster_key",
            "isin",
            "family",
            "category",
            "attributes",
            "stage",
            "first_seen_at",
            "last_filed_at",
            "filing_count",
            "headline",
            "score",
            "tier",
            "score_breakdown",
            "updated_at",
        ],
        [
            (
                r.cluster_key,
                r.isin,
                r.family,
                r.category,
                Jsonb(r.attributes),
                r.stage,
                r.first_seen_at,
                r.last_filed_at,
                r.filing_count,
                r.headline,
                r.score,
                r.tier,
                Jsonb(r.breakdown),
                datetime.now(r.first_seen_at.tzinfo),
            )
            for r in rows
        ],
        conflict=["cluster_key"],
        update=[
            "family",
            "category",
            "attributes",
            "stage",
            "first_seen_at",
            "last_filed_at",
            "filing_count",
            "headline",
            "score",
            "tier",
            "score_breakdown",
            "updated_at",
        ],
        returning=["id", "cluster_key"],
    )
    return {str(r["cluster_key"]): int(r["id"]) for r in written}


def rescore_events(conn: Conn, event_ids: Iterable[int]) -> int:
    """Recompute scores after something outside the filings changed (a price reaction)."""
    ids = sorted(set(event_ids))
    if not ids:
        return 0
    heads = fetch_all(
        conn,
        "select id, cluster_key, isin, family, enrichment from events"
        " where id = any(%s) and cluster_key is not null",
        [ids],
    )
    return len(write_events(conn, _with_members(conn, heads)))


def rescore_recent(conn: Conn, days: int = 60, batch: int = 500) -> int:
    """Rescore every event first seen in the last `days` (after a scoring change)."""
    ids = [
        int(r["id"])
        for r in fetch_all(
            conn,
            "select id from events where first_seen_at >= now() - make_interval(days => %s)",
            [days],
        )
    ]
    return sum(rescore_events(conn, ids[i : i + batch]) for i in range(0, len(ids), batch))


def session_bounds(prev_trade_date: date, trade_date: date) -> tuple[datetime, datetime]:
    """Filings after the previous close and up to this close move this session's price."""
    from finn.sources.nse import IST

    close = timedelta(hours=15, minutes=30)
    start = datetime.combine(prev_trade_date, datetime.min.time(), IST) + close
    end = datetime.combine(trade_date, datetime.min.time(), IST) + close
    return start, end
