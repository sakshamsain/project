"""Who is coming in or going out: a card built from the change-of-director filing itself.

When a listed company appoints a director or key managerial person, SEBI's disclosure
rules make it publish a brief profile of the appointee. The card is that profile, quoted
rather than paraphrased: a model picks the people and the sentences, `verify_quote`
keeps only sentences that are really in the filing, and each one links to its page.
A person whose name is not in the filing is dropped. For more, the card offers a
LinkedIn search link; FINN does not fetch or scrape profiles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote_plus

from finn.llm.client import Llm, LlmError
from finn.pull.quotes import verify_quote
from finn.sources.pdf import PdfText

PROMPT_VERSION = "people-v1"
MAX_BACKGROUND = 4
CHANGES = ["appointed", "reappointed", "redesignated", "resigned", "ceased", "retired", "other"]

SYSTEM = """You read one filing that a company listed in India made to its stock exchange \
about a change in its directors or key managerial personnel.
Use only the filing text you are given. Do not add anything you know from elsewhere.
For each person whose position changes, give the name as written, the role, the kind of \
change, and the effective date as written in the filing.
For "background", copy up to four sentences from the filing that describe the person's \
education, experience or earlier positions. Copy each sentence exactly as it appears, \
character for character; never shorten, join or reword. Give the page number from the \
[[page N]] marker above the sentence.
For a resignation or cessation, copy the sentence that gives the reason, if there is one.
Leave out anything the filing does not say."""

_QUOTE = {
    "type": "object",
    "properties": {"quote": {"type": "string"}, "page": {"type": "integer"}},
    "required": ["quote", "page"],
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "change": {"type": "string", "enum": CHANGES},
                    "effective": {"type": "string"},
                    "background": {"type": "array", "items": _QUOTE},
                    "reason": _QUOTE,
                },
                "required": ["name", "role", "change"],
            },
        }
    },
    "required": ["people"],
}


@dataclass(frozen=True, slots=True)
class Quote:
    text: str
    page: int  # 1-based, as in the PDF


@dataclass(slots=True)
class Person:
    name: str
    role: str
    change: str
    effective: str | None
    background: list[Quote] = field(default_factory=list)
    reason: Quote | None = None
    linkedin_search: str | None = None


@dataclass(slots=True)
class Extraction:
    people: list[Person]
    kept_quotes: int
    dropped_quotes: int
    dropped_people: int
    model: str


def _shape(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("people"), list):
        raise ValueError("expected {people: [...]}")


def _verified(raw: Any, pages: list[str]) -> Quote | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("quote"), str):
        return None
    text = raw["quote"].strip()
    if len(text) < 12:
        return None
    m = verify_quote(text, pages)
    if not m.found or m.page_index is None:
        return None
    return Quote(text, m.page_index + 1)


def extract_people(llm: Llm, pages: list[str], company: str) -> Extraction:
    res = llm.json(
        task="people_card",
        tier="t2_reader",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM,
        user=PdfText(pages, False).numbered(80_000),
        schema=SCHEMA,
        max_output_tokens=4096,
        validate=_shape,
    )
    return verify_people(res.data, pages, company, res.model)


def verify_people(data: Any, pages: list[str], company: str, model: str) -> Extraction:
    """Keep what the filing really says. Pure, so the model's raw answer can be tested."""
    people: list[Person] = []
    kept = dropped = dropped_people = 0
    seen: set[str] = set()
    for p in data.get("people", []):
        name = str(p.get("name", "")).strip()
        if not name or name.lower() in seen or not verify_quote(name, pages).found:
            dropped_people += 1
            continue
        seen.add(name.lower())
        background: list[Quote] = []
        for raw in (p.get("background") or [])[:MAX_BACKGROUND]:
            q = _verified(raw, pages)
            if q is None:
                dropped += 1
            elif all(q.text != b.text for b in background):
                background.append(q)
                kept += 1
        reason = _verified(p.get("reason"), pages)
        change = p.get("change") if p.get("change") in CHANGES else "other"
        people.append(
            Person(
                name=name,
                role=str(p.get("role", "")).strip(),
                change=str(change),
                effective=(str(p["effective"]).strip() or None) if p.get("effective") else None,
                background=background,
                reason=reason,
                linkedin_search="https://www.linkedin.com/search/results/people/?keywords="
                + quote_plus(f"{name} {company}"),
            )
        )
    return Extraction(people, kept, dropped, dropped_people, model)


def card_json(x: Extraction, source_url: str | None) -> dict[str, Any]:
    return {
        "status": "ok" if x.people else "empty",
        "people": [asdict(p) for p in x.people],
        "source": source_url,
        "model": x.model,
        "quotes_kept": x.kept_quotes,
        "quotes_dropped": x.dropped_quotes,
        "people_dropped": x.dropped_people,
        "prompt_version": PROMPT_VERSION,
    }


def merge_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """One card for an event whose filings each carry part of the story."""
    people: list[dict[str, Any]] = []
    names: set[str] = set()
    for c in cards:
        for p in c.get("people", []):
            if p["name"].lower() not in names:
                names.add(p["name"].lower())
                people.append({**p, "source": c.get("source")})
    return {
        "status": "ok" if people else "empty",
        "people": people,
        "sources": [c.get("source") for c in cards],
        "quotes_kept": sum(int(c.get("quotes_kept", 0)) for c in cards),
        "quotes_dropped": sum(int(c.get("quotes_dropped", 0)) for c in cards),
        "prompt_version": PROMPT_VERSION,
    }


def pending_people_events(conn: Any, days: int = 30, limit: int = 6) -> list[dict[str, Any]]:
    """Board or management events on held companies without a finished people card."""
    from finn.core.db import fetch_all

    return fetch_all(
        conn,
        "select e.id, e.isin, c.name as company,"
        " e.enrichment -> 'people_card' ->> 'attempted_at' as attempted_at"
        " from events e join companies c on c.isin = e.isin"
        " where e.family = 'management_change'"
        "   and e.first_seen_at >= now() - make_interval(days => %s)"
        "   and e.isin in (select isin from holdings)"
        "   and coalesce(e.enrichment -> 'people_card' ->> 'status', '')"
        "       not in ('ok', 'empty', 'scanned')"
        " order by e.enrichment -> 'people_card' ->> 'attempted_at' nulls first,"
        "   e.first_seen_at desc limit %s",
        [days, limit],
    )


def event_attachments(conn: Any, event_id: int, limit: int = 3) -> list[str]:
    from finn.core.db import fetch_all

    rows = fetch_all(
        conn,
        "select attachment_url, min(filed_at) as first from filings"
        " where event_id = %s and attachment_url like 'https://nsearchives.nseindia.com/%%'"
        " group by attachment_url order by first limit %s",
        [event_id, limit],
    )
    return [str(r["attachment_url"]) for r in rows]


__all__ = ["Extraction", "LlmError", "Person", "card_json", "extract_people", "merge_cards"]
