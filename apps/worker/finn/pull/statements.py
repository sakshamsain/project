"""Profit and loss and cash flow, from the statements in an annual report.

A model copies the lines it is asked for, figures exactly as printed. Code keeps a line
only if its label is on the cited page and each figure is printed right after that label
(the same row), converts the statement's unit to crore, and does every sum: capex, free
cash flow, cash conversion, payouts. Two identities must hold before a year is shown:

    operating + investing + financing = change in cash (with or without exchange effects)
    profit before tax - tax = profit for the year (with or without associates' share)

and full-year revenue and profit are compared with the four quarterly XBRL filings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from finn.llm.client import Llm
from finn.pull.annual_reports import numbered, parse_figure, statement_scale
from finn.pull.quotes import normalize
from finn.push.results_math import StatementLines, pct_change

PROMPT_VERSION = "statements-v1"
SINGLE = [
    "revenue",
    "pbt",
    "tax",
    "pat",
    "pat_owners",
    "cfo",
    "cfi",
    "cff",
    "fx_effect",
    "net_change",
]
MULTI = ["capex", "dividends", "buyback"]
KEYS = SINGLE + MULTI
WINDOW = 160  # characters after a label in which its row's figures must appear

SYSTEM = """You read the statement of profit and loss and the statement of cash flows \
from the annual report of a company listed in India. Use only the pages you are given.
List the lines below where they appear. For each line give:
- key: one of the keys below
- label: the line's label exactly as printed, without its note number
- current: the figure in the column for the year the report covers
- prior: the figure in the column for the year before
- page: the number in the [[page N]] marker above the line
Copy each figure character for character as printed, with its commas, decimals and \
brackets, for example "2,67,021", "(12,845)" or "72,776.01". Write "-" where the column \
shows a dash. Never add, convert, round or compute anything.
Keys:
- revenue: revenue from operations (for a lender, total revenue from operations)
- pbt: profit before tax
- tax: total tax expense
- pat: profit for the year
- pat_owners: profit for the year attributable to owners of the company
- cfo: net cash from or used in operating activities
- cfi: net cash from or used in investing activities
- cff: net cash from or used in financing activities
- fx_effect: effect of exchange rate changes on cash and cash equivalents
- net_change: net increase or decrease in cash and cash equivalents
- capex: payments for property, plant and equipment, capital work in progress or \
intangible assets; one item for each such line
- dividends: dividends paid, one item for each line (to owners, to non-controlling \
interests)
- buyback: payments to buy back shares, with their tax and expenses; one item per line
Give each of the first ten keys at most once; leave out any the statements do not show."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": KEYS},
                    "label": {"type": "string"},
                    "current": {"type": "string"},
                    "prior": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["key", "label", "current", "page"],
            },
        }
    },
    "required": ["lines"],
}


@dataclass(frozen=True, slots=True)
class Line:
    key: str
    label: str
    page: int
    current: float | None  # crore
    prior: float | None


@dataclass(slots=True)
class Extracted:
    lines: list[Line]
    unit: str | None
    dropped: list[str] = field(default_factory=list)  # why lines were left out
    # Lines code found on the pages that the model did not list, by column: a sum made
    # without them would be wrong, so it is not made.
    incomplete: dict[str, list[str]] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)  # summed lines code read itself


def _shape(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        raise ValueError("expected {lines: [...]}")


_NOTE_REF = re.compile(
    r"\((?:refer(?:\s+to)?\s+)?notes?\b[^)]*\)|\brefer(?:\s+to)?\s+notes?\s+[\w.()]+"
)
_NEXT_LABEL = re.compile(r"[a-z]{4,}")
_ROW_TOKEN = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?|(?<!\S)[-\u2013\u2014](?!\S)")
LABEL_RUN = 90  # how far a printed label may run on past what the model copied


def row_after(text: str) -> str:
    """A label's row: from the first figure after it to the next label, taken as the
    next word of four or more letters. A label printed longer than the model copied it
    ("..., net of sale proceeds") still finds its row; note references are skipped."""
    t = _NOTE_REF.sub(" ", text[:WINDOW])
    first = _ROW_TOKEN.search(t)
    if first is None or first.start() > LABEL_RUN or ":" in t[: first.start()]:
        return ""  # a heading ("Tax expense:") is not a row; its sub-lines are
    rest = t[first.start() :]
    m = _NEXT_LABEL.search(rest)
    return rest[: m.start()] if m else rest


def row_tokens(row: str) -> list[float | None]:
    """The row's figures in print order, signed as printed; None for a dash."""
    out: list[float | None] = []
    for m in _ROW_TOKEN.finditer(row):
        tok = m.group(0)
        if tok in ("-", "\u2013", "\u2014"):
            out.append(None)
            continue
        v = parse_figure(tok)
        if v is not None:
            out.append(v)
    return out


def _windows(label: str, text: str) -> list[str]:
    """The row after each place the label is printed (normalised text)."""
    hay = normalize(text)
    needle = normalize(re.sub(r"\s*\(?\b(?:refer )?note\b.*$", "", label, flags=re.I)) or ""
    if len(needle) < 3:
        return []
    out: list[str] = []
    start = hay.find(needle)
    while start != -1:
        out.append(row_after(hay[start + len(needle) :]))
        start = hay.find(needle, start + 1)
    return out


MAX_NOTE_TOKENS = 5  # note references before a row's figures: "2.2, 2.4.2 and 2.21"


def _note_like(t: float | None) -> bool:
    """A note number (12, 2.17, 3.19), not a figure: small, positive, not a dash."""
    return t is not None and 0 < t < 100


def _same(t: float | None, value: float) -> bool:
    if value == 0.0:
        return t is None or t == 0.0
    return t is not None and abs(abs(t) - abs(value)) < 1e-9


def matched_row(current: Any, prior: Any, rows: Sequence[str]) -> tuple[float | None, ...] | None:
    """(current, prior) when a row prints them as its first two figures, after at most
    a few note numbers: the column layout of every Schedule III statement. Anything
    else, such as a figure from a wide table or the columns swapped, returns None.
    Values keep the sign printed in the row; a dash is 0."""
    cur, pri = parse_figure(current), parse_figure(prior)
    for row in rows:
        toks = row_tokens(row)
        for k in range(min(len(toks), MAX_NOTE_TOKENS + 1)):
            if k and not _note_like(toks[k - 1]):
                break
            c = toks[k]
            if cur is not None and not _same(c, cur):
                continue
            p = toks[k + 1] if k + 1 < len(toks) else None
            if pri is not None and (k + 1 >= len(toks) or not _same(p, pri)):
                continue
            return (
                None if cur is None else (0.0 if c is None else c),
                None if pri is None else (0.0 if p is None else p),
            )
    return None


def verify_lines(data: Any, pages: Mapping[int, str]) -> Extracted:
    unit = statement_scale([pages[n] for n in sorted(pages)])
    if unit is None:
        return Extracted([], None, ["no unit printed on the statement pages"])
    _word, scale = unit
    out = Extracted([], _word)
    seen: set[str] = set()
    for raw in data.get("lines", []):
        key = raw.get("key")
        page = raw.get("page")
        label = str(raw.get("label") or "").strip()
        if key not in KEYS or page not in pages or not label:
            out.dropped.append(f"{key}: no label or page")
            continue
        if key in SINGLE and key in seen:
            out.dropped.append(f"{key}: listed twice")
            continue
        if key in MULTI and not is_summed_label(key, label):
            # Code and model must agree a line belongs in a sum: an advance for a lease
            # is not capex, cash parked for a buyback is not a buyback.
            out.dropped.append(f"{key}: '{label[:60]}' is not a {key} line")
            continue
        windows = _windows(label, pages[page])
        if not windows:
            out.dropped.append(f"{key}: label not on p. {page}")
            continue
        found = matched_row(raw.get("current"), raw.get("prior"), windows)
        if found is None or all(v is None for v in found):
            out.dropped.append(f"{key}: figures not in the row on p. {page}")
            continue
        cur, pri = found
        seen.add(key)
        out.lines.append(
            Line(
                key,
                label[:160],
                int(page),
                None if cur is None else round(cur * scale, 4),
                None if pri is None else round(pri * scale, 4),
            )
        )
    out.added = add_code_rows(out.lines, pages, scale)
    out.incomplete = missing_lines(out.lines, pages, scale)
    return out


# Lines that are summed: code finds them itself, checks the model listed each one, and
# adds any the model left out.
_SUMMED = {
    "capex": re.compile(
        r"(?:purchase|acquisition|payments?|expenditure|additions?|investment)s? "
        r"(?:of |on |for |in |towards |to )?[^.;:]{0,30}?"
        r"(?:property|plant and equipment|capital work|intangible|fixed assets|capital assets)"
    ),
    "dividends": re.compile(r"dividends? paid|payments? of (?:final |interim )?dividends?"),
    "buyback": re.compile(r"buy ?-?back"),
}


# Cash parked for a buyback, or advances, are not the payment itself.
_NOT_SUMMED = re.compile(
    r"escrow|deposit|advances? (?:for|towards|paid for)|proceeds from|received|income|refund"
)
_LABEL_START = re.compile(r"(?:\d|\)|\s-)\s")


def is_summed_label(key: str, label: str) -> bool:
    text = normalize(label)
    return bool(_SUMMED[key].search(text)) and not _NOT_SUMMED.search(text)


@dataclass(frozen=True, slots=True)
class CodeRow:
    """A summed line code found on its own: the label up to its figures, and the first
    two figures of the row after any note numbers."""

    page: int
    label: str
    current: float | None
    prior: float | None
    at: int  # where the row's figures start in the page's normalised text


def row_figures(toks: Sequence[float | None]) -> list[float | None]:
    """The row's two figures after any note numbers, as `matched_row` reads them."""
    k = 0
    while k < MAX_NOTE_TOKENS and len(toks) - k > 2 and _note_like(toks[k]):
        k += 1
    return list(toks[k : k + 2])


def code_rows(pages: Mapping[int, str], key: str) -> list[CodeRow]:
    """Every row on the pages whose label names a summed line, one per row."""
    out: list[CodeRow] = []
    seen: set[tuple[int, int]] = set()
    for page, text in sorted(pages.items()):
        hay = normalize(text)
        for m in _SUMMED[key].finditer(hay):
            post = hay[m.end() : m.end() + WINDOW]
            first = _ROW_TOKEN.search(post)
            if first is None:
                continue
            label = _LABEL_START.split(hay[max(0, m.start() - 80) : m.start()])[-1]
            label = re.sub(r"\s+", " ", label + hay[m.start() : m.end()] + post[: first.start()])
            if _NOT_SUMMED.search(label) or (page, m.end() + first.start()) in seen:
                continue
            figs = row_figures(row_tokens(row_after(post)))
            if not figs:
                continue
            seen.add((page, m.end() + first.start()))
            label = label.strip(" -:;,")
            out.append(
                CodeRow(
                    page,
                    label[:1].upper() + label[1:160],
                    figs[0],
                    figs[1] if len(figs) > 1 else None,
                    m.end() + first.start(),
                )
            )
    return out


def summed_rows(pages: Mapping[int, str], key: str) -> list[tuple[float | None, float | None]]:
    """(current, prior) of every row on the pages whose label names a summed line."""
    return [(r.current, r.prior) for r in code_rows(pages, key)]


def _covered(lines: Sequence[Line], key: str, row: CodeRow, scale: float) -> bool:
    for ln in lines:
        if ln.key != key:
            continue
        for mine, theirs in ((ln.current, row.current), (ln.prior, row.prior)):
            if theirs is None or theirs == 0.0 or mine is None:
                continue
            if abs(abs(mine) - abs(theirs) * scale) < 1e-6:
                return True
    return False


def _statement_outflow(row: CodeRow) -> bool:
    """A row code may add on its own: both year columns printed (a dash counts) and
    every figure an outflow in brackets, as cash-flow statements print payments. A
    footnote's "includes capital advances of 120" fails and stays the model's to read."""
    figs = [row.current, row.prior]
    if row.prior is None and row.current is None:
        return False
    values = [f for f in figs if f is not None and f != 0.0]
    return bool(values) and all(v < 0 for v in values) and row.at >= 0 and len(figs) == 2


def add_code_rows(lines: list[Line], pages: Mapping[int, str], scale: float) -> list[str]:
    """Summed lines code found that the model left out, added to `lines` (rules before
    models: the same row rules that check the model's lines read them)."""
    added: list[str] = []
    for key in MULTI:
        for row in code_rows(pages, key):
            if not _statement_outflow(row) or _covered(lines, key, row, scale):
                continue
            lines.append(
                Line(
                    key,
                    row.label,
                    row.page,
                    None if row.current is None else round(row.current * scale, 4),
                    None if row.prior is None else round(row.prior * scale, 4),
                )
            )
            added.append(f"{key}: {row.label[:60]} (p. {row.page})")
    return added


def missing_lines(
    lines: Sequence[Line], pages: Mapping[int, str], scale: float
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key in MULTI:
        listed = [ln for ln in lines if ln.key == key]
        for column, idx in (("current", 0), ("prior", 1)):
            have = [abs(getattr(ln, column)) for ln in listed if getattr(ln, column) is not None]
            for row in summed_rows(pages, key):
                v = row[idx]
                if v is None or v == 0.0:
                    continue
                if not any(abs(h - abs(v) * scale) < 1e-6 for h in have):
                    out.setdefault(column, []).append(key)
                    break
    return out


def extract_statements(
    llm: Llm, pages: Mapping[int, str], company: str, fiscal_year: str, basis: str
) -> tuple[Extracted, str]:
    year = 2000 + int(fiscal_year[2:])
    user = (
        f"Company: {company}\nAnnual report for {fiscal_year}: April {year - 1} to March {year}\n"
        f"Statements: {basis}\n\n{numbered(pages, sorted(pages))}"
    )
    best: tuple[int, Extracted, str] | None = None
    for escalate in (False, True):
        res = llm.json(
            task="statements",
            tier="t2_reader",
            prompt_version=PROMPT_VERSION,
            system=SYSTEM,
            user=user,
            schema=SCHEMA,
            max_output_tokens=8192,
            validate=_shape,
            escalate=escalate,
        )
        ex = verify_lines(res.data, pages)
        score = quality(ex, fiscal_year)
        if best is None or score > best[0]:
            best = (score, ex, res.model)
        if score >= FULL_MARKS:
            break
    assert best is not None
    return best[1], best[2]


CORE = ("revenue", "pat", "cfo", "cfi", "cff", "net_change")
FULL_MARKS = 2 * len(CORE) + 4


def quality(ex: Extracted, fiscal_year: str) -> int:
    """Core lines read in both columns, plus 2 per year that adds up, less 1 per summed
    line left out: a weaker answer is asked again of the stronger model."""
    score = 0
    for key in CORE:
        line = next((ln for ln in ex.lines if ln.key == key), None)
        if line is not None:
            score += int(line.current is not None) + int(line.prior is not None)
    for y in years_from(ex, fiscal_year, None):
        score += 2 * int(not year_failures(y, y.scale))
    return score - sum(len(keys) for keys in ex.incomplete.values())


# --- one fiscal year -------------------------------------------------------------------


@dataclass(slots=True)
class Year:
    """One fiscal year's figures in crore, from one report's current or prior column."""

    fiscal_year: str
    values: dict[str, float]  # single keys
    parts: dict[str, list[float]]  # capex, dividends, buyback lines, as outflows
    pages: dict[str, int]
    document_id: int | None = None
    scale: float = 1.0  # crore per printed unit, for rounding tolerance
    incomplete: list[str] = field(default_factory=list)  # summed keys missing a line

    def get(self, key: str) -> float | None:
        if key in self.incomplete:
            return None
        if key in self.values:
            return self.values[key]
        if key in self.parts:
            return sum(self.parts[key])
        return None


def years_from(ex: Extracted, fiscal_year: str, document_id: int | None) -> list[Year]:
    """The current-year and prior-year columns of one report."""
    prior_fy = f"FY{int(fiscal_year[2:]) - 1:02d}"
    out = []
    for fy, pick in ((fiscal_year, "current"), (prior_fy, "prior")):
        y = Year(fy, {}, {}, {}, document_id, _scale(ex), list(ex.incomplete.get(pick, [])))
        for line in ex.lines:
            v = getattr(line, pick)
            if v is None:
                continue
            if line.key in MULTI:
                y.parts.setdefault(line.key, []).append(abs(v))
            else:
                y.values[line.key] = v
            y.pages.setdefault(line.key, line.page)
        if y.values or y.parts:
            out.append(y)
    return out


def _close(a: float, b: float, scale: float, rel: float = 0.003, floor: float = 2.0) -> bool:
    return abs(a - b) <= max(floor * scale, rel * max(abs(a), abs(b), 1.0))


def year_failures(y: Year, scale: float = 1.0) -> list[str]:
    """Identities a year's figures must satisfy before FINN shows them."""
    v = y.values
    out = []
    if all(k in v for k in ("cfo", "cfi", "cff", "net_change")):
        total = v["cfo"] + v["cfi"] + v["cff"]
        options = [total, total + v.get("fx_effect", 0.0)]
        size = max(abs(v["cfo"]), abs(v["cfi"]), abs(v["cff"]))
        if not any(abs(t - v["net_change"]) <= max(3 * scale, 0.003 * size) for t in options):
            out.append("cash_flows_do_not_add_up")
    elif "cfo" in v:
        out.append("cash_flow_totals_missing")
    if all(k in v for k in ("pbt", "tax", "pat")) and not _close(
        v["pbt"] - v["tax"], v["pat"], scale, rel=0.01
    ):
        out.append("profit_does_not_reconcile")
    return out


def quarters_of_year(fiscal_year: str) -> list[str]:
    fy = fiscal_year[2:]
    return [f"Q{q} FY{fy}" for q in (1, 2, 3, 4)]


def against_quarters(
    y: Year, series: Mapping[str, StatementLines], lender: bool = False
) -> dict[str, Any]:
    """Full-year revenue and profit against the sum of the four quarterly filings."""
    qs = [series.get(q) for q in quarters_of_year(y.fiscal_year)]
    if any(q is None for q in qs):
        return {"status": "quarters_missing"}
    out: dict[str, Any] = {"status": "matches"}
    for key, attr in (("revenue", "revenue_from_operations"), ("pat", "profit_after_tax")):
        if key not in y.values:
            continue
        total = sum(float(getattr(q, attr)) for q in qs if q is not None)
        out[key] = {"annual": y.values[key], "quarters": round(total, 2)}
        if not _close(total, y.values[key], 1.0, rel=0.005, floor=2.0):
            out["status"] = "differs"
    return out


@dataclass(slots=True)
class CashYear:
    fiscal_year: str
    revenue: float | None
    pat: float | None
    cfo: float | None
    capex: float | None
    fcf: float | None
    cash_conversion_pct: float | None
    dividends: float | None
    buyback: float | None
    payout: float | None
    revenue_growth_pct: float | None
    pat_growth_pct: float | None
    pages: dict[str, int]
    document_id: int | None
    failures: list[str]
    quarters: dict[str, Any]
    withheld: list[str] = field(default_factory=list)  # sums not made: a line was missing


def cash_year(y: Year, before: Year | None, lender: bool, failures: list[str]) -> CashYear:
    v = y.values
    pat = v.get("pat", v.get("pat_owners"))
    cfo = v.get("cfo")
    capex = y.get("capex")
    fcf = None if lender or cfo is None or capex is None else round(cfo - capex, 2)
    conv = None
    if not lender and cfo is not None and pat is not None and pat > 0:
        conv = round(cfo / pat * 100.0, 1)
    div, buy = y.get("dividends"), y.get("buyback")
    payout = None if div is None and buy is None else round((div or 0.0) + (buy or 0.0), 2)
    if {"dividends", "buyback"} & set(y.incomplete):
        payout = None
    prev = before.values if before else {}
    prev_pat = prev.get("pat", prev.get("pat_owners"))
    rg = pct_change(v["revenue"], prev.get("revenue")) if "revenue" in v else None
    pg = pct_change(pat, prev_pat) if pat is not None else None
    return CashYear(
        fiscal_year=y.fiscal_year,
        revenue=v.get("revenue"),
        pat=pat,
        cfo=cfo,
        capex=None if capex is None else round(capex, 2),
        fcf=fcf,
        cash_conversion_pct=conv,
        dividends=None if div is None else round(div, 2),
        buyback=None if buy is None else round(buy, 2),
        payout=payout,
        revenue_growth_pct=None if rg is None else round(rg, 1),
        pat_growth_pct=None if pg is None else round(pg, 1),
        pages=dict(y.pages),
        document_id=y.document_id,
        failures=failures,
        quarters={},
        withheld=list(y.incomplete),
    )


Report = tuple[str, "Extracted", int | None]  # fiscal year, lines, document id


def _next_fy(fy: str) -> str:
    return f"FY{int(fy[2:]) + 1:02d}"


def merge_years(reports: Sequence[Report]) -> tuple[list[Year], list[dict[str, Any]]]:
    """One Year per fiscal year, newest first. The latest report wins for a year it
    covers (its prior column is that year as now presented); a restatement is noted."""
    by_fy: dict[str, Year] = {}
    notes: list[dict[str, Any]] = []
    for fiscal_year, ex, doc in sorted(reports, key=lambda r: r[0], reverse=True):
        for y in years_from(ex, fiscal_year, doc):
            if y.fiscal_year not in by_fy:
                by_fy[y.fiscal_year] = y
                continue
            kept = by_fy[y.fiscal_year]
            for key in ("revenue", "pat", "cfo"):
                a, b = kept.values.get(key), y.values.get(key)
                if a is not None and b is not None and not _close(a, b, 1.0, rel=0.005):
                    notes.append(
                        {
                            "kind": "restated",
                            "fiscal_year": y.fiscal_year,
                            "line": key,
                            "was": b,
                            "now": a,
                            "in_report": _next_fy(y.fiscal_year),
                        }
                    )
    return [by_fy[k] for k in sorted(by_fy, key=lambda fy: int(fy[2:]), reverse=True)], notes


def cash_table(
    reports: Sequence[Report],
    series: Mapping[str, StatementLines],
    lender: bool,
) -> dict[str, Any]:
    """The Cash tab: three years of figures and the sums code made from them."""
    years, notes = merge_years(reports)
    rows: list[CashYear] = []
    for i, y in enumerate(years):
        before = years[i + 1] if i + 1 < len(years) else None
        fails = year_failures(y, y.scale)
        row = cash_year(y, before, lender, fails)
        row.quarters = against_quarters(y, series, lender)
        status = row.quarters.get("status")
        if status == "differs" and not lender:
            row.failures.append("differs_from_quarterly_filings")
        if status == "matches" and "profit_does_not_reconcile" in row.failures:
            # Tax is not shown; profit itself agrees with the four quarterly filings.
            row.failures.remove("profit_does_not_reconcile")
            notes.append({"kind": "profit_checked_by_quarters", "fiscal_year": y.fiscal_year})
        rows.append(row)
    shown = [r for r in rows if not r.failures]
    totals: dict[str, float | None] = {}
    if len(shown) >= 2 and not lender:
        cfo = [r.cfo for r in shown if r.cfo is not None]
        pat = [r.pat for r in shown if r.pat is not None]
        fcf = [r.fcf for r in shown if r.fcf is not None]
        payouts = [r.payout for r in shown if r.payout is not None]
        complete = len(shown)
        if len(cfo) == complete and len(pat) == complete and sum(pat) > 0:
            totals["cfo"] = round(sum(cfo), 2)
            totals["pat"] = round(sum(pat), 2)
            totals["cash_conversion_pct"] = round(sum(cfo) / sum(pat) * 100.0, 1)
        if len(fcf) == complete:
            totals["fcf"] = round(sum(fcf), 2)
            if len(payouts) == complete:
                totals["payout"] = round(sum(payouts), 2)
                totals["payout_of_fcf_pct"] = (
                    round(sum(payouts) / sum(fcf) * 100.0, 1) if sum(fcf) > 0 else None
                )
    return {
        "lender": lender,
        "years": [asdict(r) for r in rows],
        "totals": totals,
        "years_in_totals": [r.fiscal_year for r in shown] if totals else [],
        "notes": notes,
    }


def _scale(ex: Extracted) -> float:
    from finn.pull.annual_reports import SCALE_TO_CRORE

    return SCALE_TO_CRORE.get(ex.unit or "crore", 1.0)
