"""Which ex-dates move a stock's price mechanically.

Bhavcopy closes are not adjusted. On a bonus or split ex-date the close halves (or worse)
with nothing to report; a large dividend knocks a few percent off. Price rules are muted
on those days so the alert feed does not cry wolf; the volume rule still runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A dividend this large relative to the previous close mutes price rules for the day.
DIVIDEND_MUTE_FRACTION = 0.02

_KINDS = (
    ("bonus", r"\bbonus\b"),
    ("split", r"\bsplit\b|sub-?division"),
    ("consolidation", r"consolidat"),
    ("rights", r"\brights?\b"),
    ("demerger", r"demerg|spin[- ]?off|scheme of arrangement"),
    ("capital_reduction", r"capital reduction|reduction of capital"),
    ("buyback", r"buy\s*-?\s*back"),
    ("dividend", r"dividend|distribution"),
    ("interest", r"interest payment|redemption"),
)
_MECHANICAL = {"bonus", "split", "consolidation", "rights", "demerger", "capital_reduction"}
_AMOUNT = re.compile(r"(?:rs\.?|re\.?|inr|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/-)?\s*per\s+share", re.I)


@dataclass(frozen=True, slots=True)
class ParsedAction:
    kind: str
    amount_rs: float | None  # per share, dividends only


def parse_action(subject: str) -> ParsedAction:
    s = subject.lower()
    kind = next((k for k, pat in _KINDS if re.search(pat, s)), "other")
    amount = None
    if kind == "dividend":
        amounts = [float(m.group(1)) for m in _AMOUNT.finditer(subject)]
        amount = sum(amounts) if amounts else None
    return ParsedAction(kind, amount)


def mutes_price_rules(subject: str, prev_close: float | None) -> bool:
    a = parse_action(subject)
    if a.kind in _MECHANICAL:
        return True
    if a.kind == "dividend" and a.amount_rs and prev_close and prev_close > 0:
        return a.amount_rs / prev_close >= DIVIDEND_MUTE_FRACTION
    return False
