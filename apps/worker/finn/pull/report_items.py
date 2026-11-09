"""What an annual report says beyond its statements: the business, the auditor, the risks.

Each item is a quote the model copied from the report. Code keeps it only if the quote is
on one of the pages it was given (`verify_quote`), takes the page number from the text,
and keeps a figure only if it is printed next to what it describes. Titles are the
model's own short labels and must pass the house style. The auditor's opinion is read by
code from the report's headings, which auditing standards fix (SA 700 and SA 705).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from finn.llm.client import Llm
from finn.llm.style_lint import lint
from finn.pull.annual_reports import figures_on, flat, numbered, parse_figure
from finn.pull.quotes import find_quote, normalize, verify_quote

PROMPT_VERSION = "report-items-v1"
MAX_QUOTE = 400


@dataclass(frozen=True, slots=True)
class Cited:
    title: str
    quote: str
    page: int


@dataclass(slots=True)
class Kept:
    items: list[Cited] = field(default_factory=list)
    dropped: int = 0


def _ordered(pages: Mapping[int, str]) -> tuple[list[int], list[str]]:
    numbers = sorted(pages)
    return numbers, [pages[n] for n in numbers]


def cited(raw_items: Any, pages: Mapping[int, str], limit: int = 8) -> Kept:
    """Items whose quote is in the pages; the page is where the quote was found."""
    numbers, texts = _ordered(pages)
    out = Kept()
    seen: set[str] = set()
    for raw in raw_items if isinstance(raw_items, list) else []:
        quote = str(raw.get("quote") or "").strip()
        title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip().rstrip(".")
        if len(quote) < 20 or len(quote) > MAX_QUOTE or normalize(quote) in seen:
            out.dropped += 1
            continue
        m = verify_quote(quote, texts)
        if not m.found or m.page_index is None:
            out.dropped += 1
            continue
        if not title or len(title) > 80 or lint(title, "headline"):
            title = ""
        seen.add(normalize(quote))
        out.items.append(Cited(title, quote, numbers[m.page_index]))
        if len(out.items) >= limit:
            break
    return out


def _item_schema(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {
        "title": {"type": "string"},
        "quote": {"type": "string"},
        "page": {"type": "integer"},
        **(extra or {}),
    }
    return {"type": "object", "properties": props, "required": ["title", "quote", "page"]}


def _call(llm: Llm, task: str, system: str, user: str, schema: dict[str, Any]) -> Any:
    def shape(data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("expected an object")

    res = llm.json(
        task=task,
        tier="t2_reader",
        prompt_version=PROMPT_VERSION,
        system=system,
        user=user,
        schema=schema,
        max_output_tokens=8192,
        validate=shape,
    )
    return res.data, res.model


# --- auditor ---------------------------------------------------------------------------

_OPINIONS = (
    ("disclaimer", re.compile(r"basis for disclaimer of opinion")),
    ("adverse", re.compile(r"basis for adverse opinion")),
    ("qualified", re.compile(r"basis for qualified opinion")),
    ("unmodified", re.compile(r"basis for opinion")),
)
_EMPHASIS = re.compile(r"emphasis of matters?\b")
_GOING_CONCERN = re.compile(r"material uncertainty related to going concern")


_PARAGRAPH_END = re.compile(
    r"not modified in respect of (?:this|these|the above) matters?\.?|"
    r"(?=\b(?:other matters?|key audit matters?|information other than)\b)",
    re.I,
)


def drawn_attention(pages: Mapping[int, str]) -> list[dict[str, Any]]:
    """The auditor's Emphasis of Matter and going-concern paragraphs, cut from the text
    by code: what follows the heading, up to "not modified in respect of this matter"."""
    out: list[dict[str, Any]] = []
    for n in sorted(pages):
        text = re.sub(r"\s+", " ", pages[n])
        for m in re.finditer(
            r"emphasis of matters?|material uncertainty related to going concern", text, re.I
        ):
            body = text[m.end() : m.end() + 1500].lstrip(" :.-")
            end = _PARAGRAPH_END.search(body, 40)
            quote = body[
                : end.end() if end and end.end() > end.start() else (end.start() if end else 700)
            ]
            quote = quote.strip()
            if len(quote) > 60 and not quote.lower().startswith(("paragraph", "section")):
                kind = "going_concern" if "going concern" in m.group(0).lower() else "emphasis"
                out.append({"kind": kind, "quote": quote[:900], "page": n})
    return out[:4]


def auditor_opinion(pages: Mapping[int, str]) -> dict[str, Any]:
    """The opinion as its heading names it, and whether the report draws attention to
    anything (an emphasis of matter or a going-concern uncertainty)."""
    numbers, texts = _ordered(pages)
    flats = [flat(t) for t in texts]
    opinion: dict[str, Any] = {"kind": None, "page": None}
    for kind, pattern in _OPINIONS:
        hit = next((n for n, f in zip(numbers, flats, strict=True) if pattern.search(f)), None)
        if hit is not None:
            opinion = {"kind": kind, "page": hit}
            break
    opinion["emphasis_pages"] = [
        n for n, f in zip(numbers, flats, strict=True) if _EMPHASIS.search(f)
    ]
    opinion["going_concern_pages"] = [
        n for n, f in zip(numbers, flats, strict=True) if _GOING_CONCERN.search(f)
    ]
    return opinion


AUDITOR_SYSTEM = """You read the independent auditor's report on the financial statements \
in the annual report of a company listed in India. Use only the pages you are given.
Give:
- firm: the audit firm's name exactly as printed where the report is signed, for \
example "Deloitte Haskins & Sells LLP". Leave it empty if the pages do not show it.
- matters: each key audit matter the auditor reports. For each: title, a name for the \
matter in at most eight plain words; quote, one or two sentences copied character for \
character from the report that describe the matter; page, from the [[page N]] marker.
- emphasis: each "Emphasis of Matter" or "Material Uncertainty Related to Going \
Concern" paragraph, with title, quote and page as above. Usually there is none."""

AUDITOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "firm": {"type": "string"},
        "matters": {"type": "array", "items": _item_schema()},
        "emphasis": {"type": "array", "items": _item_schema()},
    },
    "required": ["matters"],
}


def read_auditor(llm: Llm, pages: Mapping[int, str], company: str) -> tuple[dict[str, Any], str]:
    data, model = _call(
        llm,
        "auditor",
        AUDITOR_SYSTEM,
        f"Company: {company}\n\n{numbered(pages, sorted(pages))}",
        AUDITOR_SCHEMA,
    )
    firm = re.sub(r"\s+", " ", str(data.get("firm") or "")).strip()
    texts = [pages[n] for n in sorted(pages)]
    firm_ok = (
        bool(firm) and len(firm) <= 100 and any(find_quote(firm, t) is not None for t in texts)
    )
    matters = cited(data.get("matters"), pages, limit=8)
    emphasis = cited(data.get("emphasis"), pages, limit=4)
    return {
        **auditor_opinion(pages),
        "firm": firm if firm_ok else None,
        "matters": [asdict(c) for c in matters.items],
        "emphasis": [asdict(c) for c in emphasis.items],
        "drawn_attention": drawn_attention(pages),
        "dropped": matters.dropped + emphasis.dropped,
    }, model


# --- the business (BRSR Section A) -----------------------------------------------------

BUSINESS_SYSTEM = """You read Section A of the Business Responsibility and Sustainability \
Report (BRSR) in the annual report of a company listed in India. Use only the pages you \
are given. Copy every name and figure exactly as printed; never compute or round.
Give:
- description: one or two sentences copied from the report that say what the company \
does, with page.
- activities: each row of "Details of business activities": name, the description of \
main activity as printed; share, its % of turnover as printed; page.
- products: each row of "Products/Services sold by the entity": name as printed; nic, \
the NIC code as printed; share, % of turnover as printed; page.
- states and countries: the number of states and of countries in "Markets served by \
the entity", as printed, with page.
- exports: "contribution of exports as a percentage of the total turnover", as printed, \
with page."""

_ROW = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "nic": {"type": "string"},
        "share": {"type": "string"},
        "page": {"type": "integer"},
    },
    "required": ["name", "page"],
}
_FIGURE = {
    "type": "object",
    "properties": {"figure": {"type": "string"}, "page": {"type": "integer"}},
    "required": ["figure", "page"],
}
BUSINESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {
            "type": "object",
            "properties": {"quote": {"type": "string"}, "page": {"type": "integer"}},
            "required": ["quote", "page"],
        },
        "activities": {"type": "array", "items": _ROW},
        "products": {"type": "array", "items": _ROW},
        "states": _FIGURE,
        "countries": _FIGURE,
        "exports": _FIGURE,
    },
    "required": ["activities"],
}


def figure_near(
    raw: Any, text: str, anchor: str, reach: int, first: bool = False, skip: str = ""
) -> float | None:
    """A figure printed within `reach` characters after `anchor` on the page; with
    `first`, it must be the first figure printed after it (as in a table row), not
    counting the numbers in `skip`, such as a product's NIC code printed between."""
    value = parse_figure(raw.rstrip("%").strip() if isinstance(raw, str) else raw)
    if value is None or value < 0:
        return None
    hay = normalize(text)
    needle = normalize(anchor)
    skipped = set(figures_on(skip)) if skip else set()
    start = hay.find(needle)
    while start != -1:
        figs = figures_on(hay[start + len(needle) : start + len(needle) + reach])
        if first:
            figs = [f for f in figs if f not in skipped][:1]
        if any(abs(f - value) < 1e-9 for f in figs):
            return value
        start = hay.find(needle, start + 1)
    return None


def _shares(rows: Any, pages: Mapping[int, str], with_nic: bool) -> list[dict[str, Any]]:
    """Rows whose name is printed on their page, with a share printed after the name.
    Shares are kept only if together they make 85-100.5% of turnover, as BRSR asks for
    the activities that make up at least 90%."""
    out: list[dict[str, Any]] = []
    for raw in rows if isinstance(rows, list) else []:
        name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()
        page = raw.get("page")
        if not name or page not in pages or find_quote(name, pages[page]) is None:
            continue
        nic = str(raw.get("nic") or "").strip() if with_nic else ""
        if nic and (len(nic) > 60 or find_quote(nic, pages[page]) is None):
            nic = ""
        share = (
            figure_near(raw.get("share"), pages[page], name, 1600, first=True, skip=nic)
            if raw.get("share")
            else None
        )
        out.append({"name": name[:200], "share": share, "nic": nic or None, "page": page})
    total = sum(r["share"] or 0.0 for r in out)
    if out and not (85.0 <= total <= 100.5 and all(r["share"] is not None for r in out)):
        for r in out:
            r["share"] = None
    return out


def brsr_boundary(pages: Mapping[int, str]) -> str | None:
    """Whether the BRSR covers the company alone or its group (item 13 of Section A)."""
    for n in sorted(pages):
        f = flat(pages[n])
        i = f.find("reporting boundary")
        if i != -1:
            window = f[i : i + 260]
            if "consolidated" in window:
                return "consolidated"
            if "standalone" in window:
                return "standalone"
    return None


def read_business(llm: Llm, pages: Mapping[int, str], company: str) -> tuple[dict[str, Any], str]:
    data, model = _call(
        llm,
        "business",
        BUSINESS_SYSTEM,
        f"Company: {company}\n\n{numbered(pages, sorted(pages))}",
        BUSINESS_SCHEMA,
    )
    out: dict[str, Any] = {
        "activities": _shares(data.get("activities"), pages, with_nic=False),
        "products": _shares(data.get("products"), pages, with_nic=True),
        "boundary": brsr_boundary(pages),
    }
    desc = data.get("description") or {}
    kept = cited([{"title": "business", **desc}] if desc else [], pages, limit=1)
    out["description"] = asdict(kept.items[0]) if kept.items else None
    for key, anchor, reach in (
        ("states", "states", 40),
        ("countries", "countries", 40),
        ("exports", "contribution of exports", 260),
    ):
        raw = data.get(key) or {}
        page = raw.get("page")
        value = None
        if isinstance(page, int) and page in pages and raw.get("figure"):
            value = figure_near(str(raw["figure"]), pages[page], anchor, reach)
        if key == "exports" and value is not None and value > 100:
            value = None
        out[key] = None if value is None else {"value": value, "page": page}
    return out, model


# --- risks management names (MD&A) -----------------------------------------------------

RISKS_SYSTEM = """You read pages from the Management Discussion and Analysis in the \
annual report of a company listed in India. Use only these pages.
List up to six risks that management says could hurt the company's results, those \
particular to this company first and broad ones such as "macroeconomic conditions" only \
if little else is named. For each: title, a name for the risk in at most eight plain \
words; quote, one or two sentences copied character for character from the report that \
state the risk; page, from the [[page N]] marker."""

RISKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"risks": {"type": "array", "items": _item_schema()}},
    "required": ["risks"],
}


def read_risks(llm: Llm, pages: Mapping[int, str], company: str) -> tuple[dict[str, Any], str]:
    data, model = _call(
        llm,
        "risks",
        RISKS_SYSTEM,
        f"Company: {company}\n\n{numbered(pages, sorted(pages))}",
        RISKS_SCHEMA,
    )
    kept = cited(data.get("risks"), pages, limit=6)
    return {"risks": [asdict(c) for c in kept.items], "dropped": kept.dropped}, model


def pages_for(all_pages: Mapping[int, str], numbers: Sequence[int]) -> dict[int, str]:
    return {n: all_pages[n] for n in numbers if n in all_pages}
