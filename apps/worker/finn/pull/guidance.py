"""Forward guidance from an earnings-call transcript, quoted and checked.

A model lists what management promised and copies the sentence it was said in. Code then
keeps an item only if the sentence is really in the transcript (its page comes from the
text, not the model), keeps a figure only if that figure appears in the sentence, and
reads the period with `finn.pull.fiscal.parse_period`. The model never computes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from finn.llm.client import Llm
from finn.pull.fiscal import Period, parse_period
from finn.pull.quotes import normalize, verify_quote
from finn.sources.pdf import PdfText

PROMPT_VERSION = "guidance-v2"
METRIC_KEYS = [
    "revenue",
    "revenue_growth",
    "ebitda",
    "ebitda_growth",
    "ebitda_margin",
    "ebit_margin",
    "pat",
    "pat_growth",
    "pat_margin",
    "capex",
    "capacity",
    "order_inflow",
    "order_book",
    "volume",
    "aum_growth",
    "loan_growth",
    "credit_cost",
    "net_interest_margin",
    "deal_wins",
    "headcount",
    "other",
]
KINDS = ["growth", "margin", "level", "qualitative"]
BASES = ["inr", "constant_currency", "usd", "other"]
UNITS = ["%", "bps", "crore", "other"]
SCOPES = ["company", "segment", "adjusted"]

SYSTEM = """You read the transcript of one earnings call of a company listed in India.
Use only the transcript you are given; do not add anything you know from elsewhere.
List the forward-looking statements made by the company's management (never by \
analysts) that commit to an outcome: guidance for revenue or its growth, margins, profit, \
capital expenditure, capacity, order inflow, loan or AUM growth, credit cost and similar, \
and dated commitments such as a plant starting by a given quarter.
For each statement:
- quote: copy the shortest exact span that contains it, at most two sentences, character \
for character as in the transcript. Never shorten, join or reword.
- page: the page number from the [[page N]] marker above the quote.
- value_low and value_high: the numbers as stated (for "20 to 22%" give 20 and 22; for \
"about 15%" give 15 and 15; for "at least 10%" give only value_low). Do not compute or \
convert anything. Leave both out when no number is stated.
- period: a fiscal label. India's fiscal year FY27 runs April 2026 to March 2027; Q3 FY27 \
is October to December 2026; H2 FY27 is October 2026 to March 2027. Resolve "this year", \
"next quarter" and similar from the call date. Write "unspecified" if none is said.
- basis: constant_currency when growth is stated in constant currency, usd for dollar \
figures, inr for rupees. If management says anywhere in the call that its revenue \
guidance is in constant currency or in dollars, use that basis for revenue guidance \
from this call even where a sentence does not repeat it. Use inr only when nothing \
suggests another basis.
- scope: company for the whole company; segment for one business, segment, product, \
subsidiary or geography (name it in scope_note); adjusted when the figure excludes or \
adds something, such as "excluding the JV" (say what in scope_note).
Report each distinct promise once, from the place it is stated most precisely."""

_QUOTE_ITEM = {
    "type": "object",
    "properties": {
        "metric": {"type": "string"},
        "metric_key": {"type": "string", "enum": METRIC_KEYS},
        "kind": {"type": "string", "enum": KINDS},
        "basis": {"type": "string", "enum": BASES},
        "value_low": {"type": "number"},
        "value_high": {"type": "number"},
        "unit": {"type": "string", "enum": UNITS},
        "period": {"type": "string"},
        "scope": {"type": "string", "enum": ["company", "segment", "adjusted"]},
        "scope_note": {"type": "string"},
        "speaker": {"type": "string"},
        "quote": {"type": "string"},
        "page": {"type": "integer"},
    },
    "required": [
        "metric",
        "metric_key",
        "kind",
        "basis",
        "scope",
        "unit",
        "period",
        "quote",
        "page",
    ],
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": _QUOTE_ITEM}},
    "required": ["items"],
}


@dataclass(frozen=True, slots=True)
class GuidanceItem:
    metric: str
    metric_key: str
    kind: str
    basis: str
    value_low: float | None
    value_high: float | None
    unit: str
    period_label: str | None
    period: Period | None
    speaker: str | None
    quote: str
    page: int
    raw: dict[str, Any] = field(compare=False)
    scope: str = "company"
    scope_note: str | None = None


@dataclass(slots=True)
class Verified:
    items: list[GuidanceItem]
    dropped_quotes: int = 0
    dropped_figures: int = 0


def _shape(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("expected {items: [...]}")


def numbers_in(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", normalize(text).replace(",", ""))]


def figure_is_stated(value: float, quote: str) -> bool:
    return any(abs(value - n) < 1e-9 for n in numbers_in(quote))


# A computable metric must be named in the quote itself; otherwise code does not check it.
_NAMES = {
    "ebitda": re.compile(r"\bebitda\b", re.I),
    "ebit": re.compile(r"\bebit\b|operating (?:profit )?margin", re.I),
    "pat": re.compile(r"\bpat\b|profit after tax|net profit|net income|bottom[- ]line", re.I),
    "revenue": re.compile(r"revenue|top[- ]?line|\bsales\b|turnover|income from operations", re.I),
}
_NEEDS = {
    "ebitda": "ebitda",
    "ebitda_growth": "ebitda",
    "ebitda_margin": "ebitda",
    "ebit_margin": "ebit",
    "pat": "pat",
    "pat_growth": "pat",
    "pat_margin": "pat",
    "revenue": "revenue",
    "revenue_growth": "revenue",
}
_ADJUSTED = re.compile(r"\b(without|excluding|excl\.|ex-|other than|apart from|except)\b", re.I)


def resolve_metric(metric_key: str, quote: str) -> str:
    """The metric the quote actually names: EBIT is not EBITDA, and an unnamed ratio is
    not a margin. Anything code cannot match becomes "other" and is not checked."""
    if metric_key in ("ebitda_margin", "ebit_margin"):
        if _NAMES["ebitda"].search(quote):
            return "ebitda_margin"
        if _NAMES["ebit"].search(quote):
            return "ebit_margin"
        return "other"
    need = _NEEDS.get(metric_key)
    if need is None or _NAMES[need].search(quote):
        return metric_key
    return "other"


def resolve_scope(scope: Any, quote: str) -> str:
    if scope == "segment":
        return "segment"
    if _ADJUSTED.search(quote):
        return "adjusted"
    return scope if scope in SCOPES else "company"


def verify_items(data: Any, pages: list[str], call_date: date) -> Verified:
    out = Verified([])
    seen: set[str] = set()
    for raw in data.get("items", []):
        quote = str(raw.get("quote", "")).strip()
        if len(quote) < 15 or quote in seen:
            out.dropped_quotes += int(bool(quote) and quote not in seen)
            continue
        m = verify_quote(quote, pages)
        if not m.found or m.page_index is None:
            out.dropped_quotes += 1
            continue
        seen.add(quote)
        lo, hi = raw.get("value_low"), raw.get("value_high")
        kind = raw.get("kind") if raw.get("kind") in KINDS else "qualitative"
        if any(v is not None and not figure_is_stated(float(v), quote) for v in (lo, hi)):
            out.dropped_figures += 1
            lo = hi = None
            kind = "qualitative"
        label = str(raw.get("period") or "").strip()
        period = None if label.lower() in ("", "unspecified") else parse_period(label, call_date)
        out.items.append(
            GuidanceItem(
                metric=str(raw.get("metric", "")).strip()[:120],
                metric_key=resolve_metric(
                    raw.get("metric_key") if raw.get("metric_key") in METRIC_KEYS else "other",
                    quote,
                ),
                kind=str(kind),
                basis=raw.get("basis") if raw.get("basis") in BASES else "other",
                value_low=None if lo is None else float(lo),
                value_high=None if hi is None else float(hi),
                unit=raw.get("unit") if raw.get("unit") in UNITS else "other",
                period_label=period.label if period else (label or None),
                period=period,
                speaker=(str(raw["speaker"]).strip()[:120] or None) if raw.get("speaker") else None,
                quote=quote,
                page=m.page_index + 1,
                raw=dict(raw),
                scope=resolve_scope(raw.get("scope"), quote),
                scope_note=(str(raw.get("scope_note") or "").strip()[:120] or None),
            )
        )
    return out


def extract_guidance(
    llm: Llm, pages: list[str], company: str, call_date: date, discussed: str
) -> tuple[Verified, str]:
    user = (
        f"Company: {company}\nCall date: {call_date.isoformat()}\n"
        f"Results discussed: {discussed}\n\nTranscript:\n{PdfText(pages, False).numbered(400_000)}"
    )
    res = llm.json(
        task="guidance",
        tier="t2_reader",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM,
        user=user,
        schema=SCHEMA,
        max_output_tokens=16384,
        validate=_shape,
    )
    return verify_items(res.data, pages, call_date), res.model
