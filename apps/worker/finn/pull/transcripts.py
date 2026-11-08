"""Earnings-call transcripts from NSE: find them, read them, keep their pages.

Listed companies must file the transcript of each earnings call with the exchange. FINN
reads only those filings (and annual reports): no news, no broker notes. Pages are stored
as text in `doc_pages`, so every quote can be checked and cited as "p. N" of the PDF.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from finn.core.db import Conn, copy_upsert, fetch_all
from finn.pull.fiscal import previous_quarter, quarter_of
from finn.sources.nse import Announcement, parse_announcements

_TRANSCRIPT = re.compile(r"transcript", re.I)
_NOT_TRANSCRIPT = re.compile(r"audio|recording|video|link to", re.I)
_EARNINGS = re.compile(
    r"earnings|con(?:ference)?\.?\s*call|concall|analysts?|investors?\s+call|results\s+call", re.I
)
# Transcripts that are not the quarterly call: the ledger compares call with call.
_OTHER_EVENT = re.compile(
    r"annual general meeting|\bagm\b|\b(?:investor|analyst|ai|capital markets?)\s+day|"
    r"postal ballot|\begm\b|extra-?ordinary",
    re.I,
)
WINDOW_DAYS = 90


class AnnouncementSource(Protocol):
    def announcements(
        self, day_from: date, day_to: date, symbol: str | None = None
    ) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class TranscriptRef:
    symbol: str
    filed_at_date: date
    url: str
    title: str
    period: str  # the quarter the call discussed, e.g. Q2FY27


def is_transcript(a: Announcement) -> bool:
    text = f"{a.subject} {a.text}"
    return bool(_TRANSCRIPT.search(text)) and not (
        _NOT_TRANSCRIPT.search(text) and not re.search(r"transcript of", text, re.I)
    )


def discussed_quarter(filed_on: date) -> str:
    """Calls follow results: a transcript filed in Nov 2026 discusses Q2 FY27."""
    p = previous_quarter(quarter_of(filed_on))
    return p.label.replace(" ", "")


def call_rank(a: Announcement) -> int:
    """2 for an earnings-call transcript, 1 for an unlabelled transcript, 0 to skip."""
    text = f"{a.subject} {a.text} {a.attachment_url or ''}"
    if not is_transcript(a) or _OTHER_EVENT.search(text):
        return 0
    return 2 if _EARNINGS.search(f"{a.text} {a.attachment_url or ''}") else 1


def transcript_refs(anns: Iterable[Announcement]) -> list[TranscriptRef]:
    """One earnings-call transcript per quarter discussed (the best-labelled, then the
    latest filing); newest first."""
    best: dict[str, tuple[int, TranscriptRef]] = {}
    for a in sorted(anns, key=lambda x: x.filed_at):
        rank = call_rank(a)
        if rank == 0 or not a.attachment_url:
            continue
        d = a.filed_at.date()
        ref = TranscriptRef(
            a.symbol, d, a.attachment_url, a.text or a.subject, discussed_quarter(d)
        )
        if ref.period not in best or rank >= best[ref.period][0]:
            best[ref.period] = (rank, ref)
    return sorted((r for _, r in best.values()), key=lambda r: r.filed_at_date, reverse=True)


def find_transcripts(
    src: AnnouncementSource, symbol: str, until: date, months: int = 15
) -> list[TranscriptRef]:
    start = until - timedelta(days=months * 31)
    rows: list[Any] = []
    d = start
    while d <= until:
        end = min(d + timedelta(days=WINDOW_DAYS - 1), until)
        rows += src.announcements(d, end, symbol)
        d = end + timedelta(days=1)
    return transcript_refs(parse_announcements(rows))


def store_document(
    conn: Conn,
    isin: str,
    doc_type: str,
    url: str,
    title: str,
    filed_on: date,
    period: str | None,
    pages: Sequence[str],
    scanned: bool,
) -> int:
    rows = fetch_all(
        conn,
        "insert into documents (isin, doc_type, period, published_on, source_url, pages,"
        " has_text_layer, parsed_at, title, filed_at, event_period)"
        " values (%s, %s, %s, %s, %s, %s, %s, now(), %s, %s, %s)"
        " on conflict (source_url) where source_url is not null do update set"
        " pages = excluded.pages, has_text_layer = excluded.has_text_layer,"
        " parsed_at = now(), title = excluded.title"
        " returning id",
        [
            isin,
            doc_type,
            period,
            filed_on,
            url,
            len(pages),
            not scanned,
            title[:300],
            filed_on,
            period,
        ],
    )
    doc_id = int(rows[0]["id"])
    fetch_all(conn, "delete from doc_pages where document_id = %s", [doc_id])
    copy_upsert(
        conn,
        "doc_pages",
        ["document_id", "page_no", "text"],
        [(doc_id, i, t) for i, t in enumerate(pages, start=1)],
        conflict=["document_id", "page_no"],
        update=["text"],
    )
    return doc_id


def stored_pages(conn: Conn, document_id: int) -> list[str]:
    rows = fetch_all(
        conn,
        "select text from doc_pages where document_id = %s order by page_no",
        [document_id],
    )
    return [str(r["text"]) for r in rows]
