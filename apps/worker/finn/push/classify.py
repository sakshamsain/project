"""Rules-first classification of exchange filings.

Two passes over `rules.yaml`: first the exchange subject alone, then (when the subject is
generic or matched nothing) the subject plus the filing's own text. Returns None when no
rule matches, which sends the filing to the small model.

Attributes that change what a filing means are extracted here too: who changed and how
for management changes, which way a rating moved.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).with_name("rules.yaml")
BODY_CHARS = 700

# Subjects that say nothing on their own; the filing text decides.
GENERIC_SUBJECTS = frozenset(
    {
        "general updates",
        "updates",
        "outcome of board meeting",
        "disclosure of material issue",
        "copy of newspaper publication",
        "analysts/institutional investor meet/con. call updates",
        "analyst/investor meet para a",
        "intimation",
        "general",
        "other",
    }
)

_ROLES: tuple[tuple[str, str], ...] = (
    ("auditor", r"\b(statutory |joint |secretarial )?auditors?\b"),
    ("ceo", r"chief executive officer|\bceo\b"),
    ("cfo", r"chief financial officer|\bcfo\b"),
    ("md", r"managing director|\bmd\b|whole[- ]time director"),
    ("chairman", r"chair(man|person)"),
    ("independent_director", r"independent director"),
    ("cs", r"company secretary|compliance officer"),
    ("senior_management", r"senior management|\bsmp\b|\bkmp\b"),
    ("director", r"\bdirector\b"),
)
_ACTIONS: tuple[tuple[str, str], ...] = (
    ("resign", r"resign|cessation|ceased to be|step(s|ped)? down"),
    ("retire", r"retire|completion of (his|her|the) (tenure|term)"),
    ("appoint", r"appoint|designat"),
)
_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("downgrade", r"downgrad"),
    ("upgrade", r"upgrad"),
    ("reaffirm", r"reaffirm"),
    ("assigned", r"assign"),
)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    category: str
    patterns: tuple[re.Pattern[str], ...]
    attributes: Mapping[str, str] = field(default_factory=dict)
    confidence: float = 0.9


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    attributes: Mapping[str, str]
    confidence: float
    rule_id: str
    classified_by: str = "rules"


def _compile(raw: Sequence[Mapping[str, Any]]) -> tuple[Rule, ...]:
    rules = []
    for r in raw:
        rules.append(
            Rule(
                id=str(r["id"]),
                category=str(r["category"]),
                patterns=tuple(re.compile(p, re.IGNORECASE) for p in r["any"]),
                attributes={str(k): str(v) for k, v in (r.get("attributes") or {}).items()},
                confidence=float(r.get("confidence", 0.9)),
            )
        )
    return tuple(rules)


@lru_cache(maxsize=1)
def load_rules(path: str = str(RULES_PATH)) -> tuple[Rule, ...]:
    with open(path, encoding="utf-8") as fh:
        return _compile(yaml.safe_load(fh))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_INTERNAL = re.compile(
    r"wholly[- ]owned|\bwos\b|step[- ]down subsidiar|between the company and its subsidiar", re.I
)

# Subjects that name a broad kind ("Press Release") rather than what happened: when one
# of these rules matches the subject, the filing's own text gets a chance at a more
# specific rule.
BROAD_RULES = frozenset({"press_release"})


def is_generic(subject: str) -> bool:
    s = _squash(subject).lower()
    s = re.sub(r"\s*-\s*xbrl$", "", s)
    s = re.sub(r"\s*\((revised|updated)\)$", "", s)
    return s in GENERIC_SUBJECTS or s.startswith("analysts/institutional investor meet")


def _first(pairs: Sequence[tuple[str, str]], text: str) -> str | None:
    for name, pattern in pairs:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None


def extract_attributes(category: str, text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    if category == "management_change":
        role, action = _first(_ROLES, text), _first(_ACTIONS, text)
        if role:
            attrs["role"] = role
        if action:
            attrs["action"] = action
    elif category == "credit_rating":
        direction = _first(_DIRECTIONS, text)
        if direction:
            attrs["direction"] = direction
    elif category == "M&A" and _INTERNAL.search(text):
        attrs["kind"] = "internal"  # a reshuffle inside the group, not a deal with outsiders
    return attrs


def _match(rules: Sequence[Rule], text: str) -> Rule | None:
    for rule in rules:
        if any(p.search(text) for p in rule.patterns):
            return rule
    return None


def classify(
    subject: str,
    exchange_category: str | None = None,
    body: str | None = None,
    rules: Sequence[Rule] | None = None,
) -> Classification | None:
    active = rules if rules is not None else load_rules()
    subject = _squash(subject)
    full = _squash(" ".join((subject, (body or "")[:BODY_CHARS])))
    hit: Rule | None = None
    if not is_generic(subject):
        hit = _match(active, _squash(f"{subject} {exchange_category or ''}"))
    if hit is None:
        hit = _match(active, full)
    elif hit.id in BROAD_RULES:
        specific = _match([r for r in active if r.id not in BROAD_RULES], full)
        if specific is not None and specific.category != "unclassified":
            hit = specific
    if hit is None:
        return None
    attrs = {**extract_attributes(hit.category, full), **hit.attributes}
    return Classification(hit.category, attrs, hit.confidence, hit.id)
