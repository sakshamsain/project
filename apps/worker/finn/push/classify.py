"""Rules-first classification of exchange filings.

Most filings carry enough signal in their subject line to be classified for free.
`classify` returns None when no rule matches, which sends the filing to the small model.
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
BODY_CHARS = 600


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
        patterns = tuple(re.compile(p, re.IGNORECASE) for p in r["any"])
        rules.append(
            Rule(
                id=str(r["id"]),
                category=str(r["category"]),
                patterns=patterns,
                attributes={str(k): str(v) for k, v in (r.get("attributes") or {}).items()},
                confidence=float(r.get("confidence", 0.9)),
            )
        )
    return tuple(rules)


@lru_cache(maxsize=1)
def load_rules(path: str = str(RULES_PATH)) -> tuple[Rule, ...]:
    with open(path, encoding="utf-8") as fh:
        return _compile(yaml.safe_load(fh))


def classify(
    subject: str,
    exchange_category: str | None = None,
    body: str | None = None,
    rules: Sequence[Rule] | None = None,
) -> Classification | None:
    text = " ".join(part for part in (subject, exchange_category or "", (body or "")[:BODY_CHARS]))
    text = re.sub(r"\s+", " ", text)
    for rule in rules if rules is not None else load_rules():
        if any(p.search(text) for p in rule.patterns):
            return Classification(rule.category, dict(rule.attributes), rule.confidence, rule.id)
    return None
