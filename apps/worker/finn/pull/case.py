"""Bull and bear: the strongest argument each way, built only from facts already checked.

The model is given a numbered list of facts: figures code computed from the statements
and filings, promises from the ledger with the status code gave them, and quotes verified
in the annual report. It writes up to three points for each side, citing the facts each
rests on. Code drops a point that cites no fact it was given, states a number that none
of its cited facts contains, or breaks the house style (advice verbs among it). FINN takes
no side: both lists are shown together, each point with its sources.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from finn.llm.client import Llm
from finn.llm.style_lint import lint
from finn.pull.guidance import numbers_in

PROMPT_VERSION = "case-v2"
MAX_POINT = 260


@dataclass(frozen=True, slots=True)
class Fact:
    id: str
    text: str
    kind: str  # computed | promise | quote
    document_id: int | None = None
    page: int | None = None
    quote: str | None = None  # the verified words a chip highlights on the page


@dataclass(frozen=True, slots=True)
class Point:
    text: str
    facts: list[str]


@dataclass(slots=True)
class Case:
    bull: list[Point] = field(default_factory=list)
    bear: list[Point] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


SYSTEM = """You set out the bull case and the bear case for a company listed in India, \
for an investor who will weigh both. Use only the numbered facts you are given; add \
nothing you know from elsewhere.
Write up to three points for each side, the most important first. Each point is one \
sentence of at most 30 words that starts with its figure where it has one; put the ids \
of the facts it rests on in "facts", not in the sentence. Use only figures that appear \
in the facts it cites, written as they are written there. Never recommend buying, \
selling or holding, and never predict the share price. A bear point names a weakness \
or a risk the facts show; a key audit matter is where the auditor looked hardest, not a \
problem found. Where the facts support fewer than three points for a side, write fewer."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        side: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "facts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["point", "facts"],
            },
        }
        for side in ("bull", "bear")
    },
    "required": ["bull", "bear"],
}


def _shape(data: Any) -> None:
    if not isinstance(data, dict) or not all(
        isinstance(data.get(s), list) for s in ("bull", "bear")
    ):
        raise ValueError("expected {bull: [...], bear: [...]}")


# Fact ids written into a sentence ("(F3)", "[F1, F4]") are removed before checking.
_FACT_REF = re.compile(r"\s*[\[(]?\bF\d+(?:\s*[,;&]\s*F\d+)*\b[\])]?")


def _numbers(text: str) -> set[float]:
    return {round(n, 6) for n in numbers_in(text)}


def verify_points(raw: Any, facts: Mapping[str, Fact], side: str) -> tuple[list[Point], list[str]]:
    kept: list[Point] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        text = _FACT_REF.sub("", str(item.get("point") or ""))
        text = re.sub(r"\s+", " ", text).strip().replace(" .", ".")
        ids = [
            i for i in dict.fromkeys(str(x).strip() for x in item.get("facts") or []) if i in facts
        ]
        if not text or text.lower() in seen:
            continue
        if not ids:
            dropped.append(f"{side}: cites no known fact")
            continue
        if len(text) > MAX_POINT:
            dropped.append(f"{side}: too long")
            continue
        allowed = _numbers(" ".join(facts[i].text for i in ids))
        stray = sorted(n for n in _numbers(text) if n not in allowed)
        if stray:
            dropped.append(f"{side}: figure {stray[0]:g} is not in its facts")
            continue
        problems = lint(text, "body")
        if problems:
            dropped.append(f"{side}: {problems[0].rule}")
            continue
        seen.add(text.lower())
        kept.append(Point(text, ids))
        if len(kept) == 3:
            break
    return kept, dropped


def write_case(llm: Llm, facts: Sequence[Fact], company: str) -> tuple[Case, str | None]:
    if len(facts) < 3:
        return Case(dropped=["too few checked facts"]), None
    listing = "\n".join(f"{f.id}: {f.text}" for f in facts)
    res = llm.json(
        task="case",
        tier="t3_strong",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM,
        user=f"Company: {company}\n\nFacts:\n{listing}",
        schema=SCHEMA,
        max_output_tokens=12288,
        validate=_shape,
    )
    by_id = {f.id: f for f in facts}
    bull, d1 = verify_points(res.data.get("bull"), by_id, "bull")
    bear, d2 = verify_points(res.data.get("bear"), by_id, "bear")
    return Case(bull, bear, d1 + d2), res.model


def case_json(case: Case, facts: Sequence[Fact], model: str | None) -> dict[str, Any]:
    used = {i for p in case.bull + case.bear for i in p.facts}
    return {
        "bull": [asdict(p) for p in case.bull],
        "bear": [asdict(p) for p in case.bear],
        "facts": [asdict(f) for f in facts if f.id in used],
        "dropped": case.dropped,
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
