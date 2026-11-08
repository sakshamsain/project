"""Headlines from what the exchange already wrote, without a model.

NSE describes each attachment in one sentence ("Tata Power Company Limited has informed
the Exchange regarding Cessation of Mr X (DIN: 0123) as Independent Director..."). Strip
the boilerplate and that sentence is a usable headline for most filings. Press releases
carry their own title in quotes. When the description says nothing beyond the subject
("...about General Updates"), NSE's summary is used if there is one, else the subject.

A model rewrites headlines only for front-page events, and only from the filing itself.
"""

from __future__ import annotations

import re

from finn.push.classify import is_generic

MAX_CHARS = 140

_INFORMED = re.compile(
    r"^.{0,200}?\bhas\s+(?:informed|submitted|intimated)\b(?:\s+to)?(?:\s+the)?(?:\s+exchange)?"
    r"(?:\s+(?:about|regarding|that|of|with))?\s*",
    re.I,
)
_PURSUANT = re.compile(
    r"^.{0,400}?\b(?:this is to inform you|we (?:wish|would like) to inform(?: you)?|"
    r"we (?:hereby )?inform(?: you)?|please note)\s+that\s+",
    re.I,
)
_TITLED = re.compile(r"\btitled\s*[\"“]?\s*(.+?)\s*[\"”]?\s*\.?\s*$", re.I)
_FURTHER = re.compile(
    r"\.\s*further,?\s+the\s+company\s+has\s+informed\s+the\s+exchange\s+(?:regarding|about)\s+",
    re.I,
)
_DIN = re.compile(r"\s*\((?:DIN|PAN|Membership)[^)]*\)", re.I)
_OF_COMPANY = re.compile(r"\s+of\s+the\s+company\b", re.I)
_BROKEN_HYPHEN = re.compile(r"(\w)-\s+(\w)")


def clean_description(text: str) -> str:
    """NSE's attachment sentence without the "X has informed the Exchange" frame."""
    s = re.sub(r"\s+", " ", text).strip()
    if not s:
        return ""
    titled = _TITLED.search(s)
    if titled and len(titled.group(1)) >= 12:
        s = titled.group(1).strip(" \"'“”")
    else:
        s = _FURTHER.sub("; ", s)
        s = _INFORMED.sub("", s, count=1)
        s = _PURSUANT.sub("", s, count=1)
    s = _DIN.sub("", s)
    s = _OF_COMPANY.sub("", s)
    s = _BROKEN_HYPHEN.sub(r"\1-\2", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip(" ;,")
    if s.lower().startswith(("a ", "an ", "the ")) and len(s) > 3 or s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def first_sentence(text: str, limit: int = MAX_CHARS) -> str:
    m = re.match(r"(.+?[.!?])(?:\s|$)", text.strip())
    return shorten(m.group(1) if m else text.strip(), limit)


def shorten(text: str, limit: int = MAX_CHARS) -> str:
    s = text.strip()
    if len(s) <= limit:
        return s
    cut = s[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


def headline_for(subject: str, text: str, summary: str | None = None) -> str:
    cleaned = clean_description(text)
    says_nothing = (
        not cleaned
        or cleaned.rstrip(".").lower() == subject.strip().rstrip(".").lower()
        or is_generic(cleaned.rstrip("."))
    )
    if not says_nothing:
        return shorten(cleaned.rstrip("."))
    if summary:
        return first_sentence(summary)
    return shorten(subject.strip() or "Exchange filing")
