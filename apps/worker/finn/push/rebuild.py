"""Replay stored filings through the current rules and clustering.

Rules change; filings do not. After a change to `rules.yaml`, the classifier or the event
windows, `reclassify` re-reads every rules-classified filing (model and human labels are
left alone) and `recluster` rebuilds events from scratch, oldest day first, exactly as the
live pipeline would have built them. Anomaly links are cleared with the events; the EOD
rescan restores them.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from finn.core.db import Conn, fetch_all
from finn.push.classify import classify
from finn.push.events import FilingFacts, assign
from finn.push.pipeline import MAX_WINDOW, load_open_events, write_events


def reclassify(conn: Conn) -> int:
    rows = fetch_all(
        conn,
        "select id, subject, exchange_category, body_text, summary, category, attributes,"
        " rule_id from filings where coalesce(classified_by, 'rules') = 'rules'",
    )
    ids: list[int] = []
    cats: list[str] = []
    attrs: list[str] = []
    rule_ids: list[str | None] = []
    confs: list[float | None] = []
    bys: list[str | None] = []
    for r in rows:
        body = " ".join(x for x in (r["body_text"], r["summary"]) if x)
        c = classify(r["subject"], r["exchange_category"], body)
        category = c.category if c else "unclassified"
        attributes = dict(c.attributes) if c else {}
        rule_id = c.rule_id if c else None
        if (category, attributes, rule_id) == (r["category"], r["attributes"] or {}, r["rule_id"]):
            continue
        ids.append(int(r["id"]))
        cats.append(category)
        attrs.append(json.dumps(attributes))
        rule_ids.append(rule_id)
        confs.append(c.confidence if c else None)
        bys.append("rules" if c else None)
    if ids:
        fetch_all(
            conn,
            "update filings f set category = v.category, attributes = v.attributes,"
            " rule_id = v.rule_id, confidence = v.confidence, classified_by = v.classified_by"
            " from unnest(%s::bigint[], %s::text[], %s::jsonb[], %s::text[], %s::float8[],"
            " %s::text[]) as v(id, category, attributes, rule_id, confidence, classified_by)"
            " where f.id = v.id",
            [ids, cats, attrs, rule_ids, confs, bys],
        )
    return len(ids)


def detach_all(conn: Conn) -> int:
    """Drop every event; filings and anomalies keep their rows, unlinked."""
    fetch_all(conn, "update anomalies set linked_event_id = null where linked_event_id is not null")
    fetch_all(conn, "update filings set event_id = null where event_id is not null")
    gone = fetch_all(conn, "delete from events returning id")
    return len(gone)


def filing_days(conn: Conn) -> list[date]:
    rows = fetch_all(
        conn,
        "select distinct (filed_at at time zone 'Asia/Kolkata')::date as d from filings order by d",
    )
    return [r["d"] for r in rows]


def recluster_day(conn: Conn, day: date) -> int:
    """Cluster one IST day's filings onto the events built so far."""
    rows = fetch_all(
        conn,
        "select id, exchange, exchange_id, isin, filed_at, subject, body_text, summary,"
        " category, attributes, attachment_url from filings"
        " where (filed_at at time zone 'Asia/Kolkata')::date = %s and event_id is null"
        " order by filed_at, id",
        [day],
    )
    if not rows:
        return 0
    facts = [_facts(r) for r in rows]
    by_key = {f.key: int(r["id"]) for f, r in zip(facts, rows, strict=True)}
    since: datetime = min(f.filed_at for f in facts) - MAX_WINDOW
    touched = assign(facts, load_open_events(conn, {f.isin for f in facts}, since))
    event_ids = write_events(conn, touched)
    pairs = [
        (by_key[m.key], event_ids[d.cluster_key])
        for d in touched
        for m in d.members
        if m.key in by_key
    ]
    fetch_all(
        conn,
        "update filings f set event_id = v.event_id"
        " from unnest(%s::bigint[], %s::bigint[]) as v(filing_id, event_id)"
        " where f.id = v.filing_id",
        [[p[0] for p in pairs], [p[1] for p in pairs]],
    )
    return len(event_ids)


def _facts(r: dict[str, Any]) -> FilingFacts:
    return FilingFacts(
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
