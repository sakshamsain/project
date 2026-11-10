"""Quote verification for the Promise Ledger.

A model-extracted promise is kept only if its quote appears in the transcript. Matching
tolerates PDF artefacts (curly quotes, dashes, line-break hyphenation, whitespace) but
not paraphrase. An ellipsis splits a quote into fragments that must appear in order,
close together.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
        "₹": "rs ",
    }
)
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")
MAX_GAP = 400  # characters allowed between ellipsis fragments


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)  # re-join words hyphenated across lines
    t = re.sub(r"[\x00-\x1f\s]+", " ", t)  # control characters some PDFs use as bullets
    return t.strip().lower()


@dataclass(frozen=True, slots=True)
class QuoteMatch:
    found: bool
    page_index: int | None = None
    offset: int | None = None


def find_quote(quote: str, text: str) -> int | None:
    """Offset of the quote in normalised text, or None."""
    hay = normalize(text)
    fragments = [normalize(f) for f in _ELLIPSIS.split(quote) if normalize(f)]
    if not fragments:
        return None
    start = hay.find(fragments[0])
    while start != -1:
        pos = start + len(fragments[0])
        ok = True
        for frag in fragments[1:]:
            nxt = hay.find(frag, pos)
            if nxt == -1 or nxt - pos > MAX_GAP:
                ok = False
                break
            pos = nxt + len(frag)
        if ok:
            return start
        start = hay.find(fragments[0], start + 1)
    return None


def verify_quote(quote: str, pages: Sequence[str]) -> QuoteMatch:
    """Look for the quote page by page, then across page breaks."""
    for i, page in enumerate(pages):
        off = find_quote(quote, page)
        if off is not None:
            return QuoteMatch(True, i, off)
    for i in range(len(pages) - 1):
        off = find_quote(quote, pages[i] + "\n" + pages[i + 1])
        if off is not None:
            return QuoteMatch(True, i, off)
    return QuoteMatch(False)
