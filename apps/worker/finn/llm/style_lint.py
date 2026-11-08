"""House style for generated text. A violation triggers one regeneration, then a trim.

Rules: lead with numbers, keep one-liners and headlines short, no filler words, no
advice verbs. Kept deliberately small so it can run on every model output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["oneliner", "headline", "body"]

MAX_CHARS: dict[str, int] = {"oneliner": 110, "headline": 70}
NEEDS_A_FIGURE = ("significant", "significantly", "robust", "strong", "notable", "notably")
BANNED = ("amid", "landscape", "poised", "it is worth noting", "delve", "testament", "showcases")
_ADVICE = re.compile(
    r"\b(?:buy(?!-?back)|sell(?!-side|ing)|accumulate|avoid the (?:stock|shares))\b", re.IGNORECASE
)
_FIGURE = re.compile(r"\d|₹|%")
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    detail: str


def lint(text: str, kind: Kind = "body") -> list[Violation]:
    out: list[Violation] = []
    limit = MAX_CHARS.get(kind)
    if limit is not None and len(text) > limit:
        out.append(Violation("too_long", f"{len(text)} > {limit} characters"))
    for sentence in _SENTENCES.split(text):
        low = sentence.lower()
        for word in NEEDS_A_FIGURE:
            if re.search(rf"\b{word}\b", low) and not _FIGURE.search(sentence):
                out.append(Violation("adjective_without_figure", word))
    low_all = text.lower()
    for phrase in BANNED:
        if re.search(rf"\b{re.escape(phrase)}\b", low_all):
            out.append(Violation("banned_phrase", phrase))
    m = _ADVICE.search(text)
    if m:
        out.append(Violation("advice_language", m.group(0)))
    if kind == "oneliner" and not _FIGURE.search(text):
        out.append(Violation("no_figure", "one-liners lead with a number"))
    return out
