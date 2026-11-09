"""Annual reports from NSE: find the last two, read them, locate the parts FINN uses.

An annual report runs to 300-600 pages, laid out differently by every company, so parts
are found by what is on the page rather than by page number:

    profit_and_loss, cash_flow   statement pages: the title near the top of the page,
                                 dozens of figures, and lines every such statement has
    auditor                      the independent auditor's report on those statements
    business                     BRSR Section A, the format SEBI prescribes: activities and
                                 products with their share of turnover, plants, markets
    mdna                         Management Discussion and Analysis, from the PDF's
                                 bookmarks or from the running header its pages carry

Consolidated statements are used when the company files them, as for quarterly results.
Only the pages FINN reads are stored, under their page numbers in the PDF, so a citation
"p. 295" opens the original at that page.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from finn.core.db import Conn, copy_upsert, fetch_all
from finn.sources.nse import AnnualReport, latest_annual_reports, parse_annual_reports
from finn.sources.pdf import NotAPdf, pdf_text

MAX_BYTES = 80_000_000
MAX_PAGES = 900
HEAD = 500  # characters at the top of a page where a statement's title sits
TAIL = 350
MIN_FIGURES = 20  # a statement page carries dozens of figures; a page that cites one does not
MAX_MDNA_PAGES = 40
AUDITOR_PAGES = 7


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


# --- figures -----------------------------------------------------------------------------

# A minus sign only directly before a digit: "- 28" in a statement is a nil column and 28.
_TOKEN = re.compile(r"(?<![\w,.])(\()?(-)?(\d[\d,]*(?:\.\d+)?)(\))?")
_GROUPED = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\b\d+\.\d{1,2}\b")


def figure_count(text: str) -> int:
    """Figures printed the way statements print them: 2,67,021 or 72,776.01."""
    return len(_GROUPED.findall(text))


def figures_on(text: str) -> list[float]:
    """Every number on a page, signed: (12,845) and -12,845 are negative."""
    out: list[float] = []
    for m in _TOKEN.finditer(text.replace("\u2212", "-")):
        digits = m.group(3).replace(",", "")
        try:
            v = float(digits)
        except ValueError:
            continue
        negative = (m.group(1) and m.group(4)) or m.group(2)
        out.append(-v if negative else v)
    return out


def parse_figure(text: Any) -> float | None:
    """A figure as a model copied it: "2,67,021", "(12,845)", "-", "72,776.01"."""
    if text is None:
        return None
    s = str(text).strip().replace("−", "-").replace("–", "-")
    if s in ("-", "--", "—", "nil", "Nil", "NIL"):
        return 0.0
    m = re.fullmatch(r"(\()?\s*(-)?\s*(\d[\d,]*(?:\.\d+)?)\s*(\))?", s)
    if not m:
        return None
    v = float(m.group(3).replace(",", ""))
    return -v if (m.group(1) and m.group(4)) or m.group(2) else v


_UNIT_WORD = r"(crores?|cr\b|lakhs?|lacs?|millions?|mn\b|thousands?|billions?)"
_UNIT_PAREN = re.compile(r"\(([^()]{0,60}?)\b" + _UNIT_WORD + r"[^()]{0,60}\)")
_UNIT_PLAIN = re.compile(r"\b(?:in|amounts? in|figures in)\s+(?:\S{1,3}\s*)?" + _UNIT_WORD)
_UNIT_MARK = re.compile(r"(?:[`\u20b9]|\brs\.?|\binr\b)\s*/?\s*(?:in\s+)?" + _UNIT_WORD)
SCALE_TO_CRORE = {
    "crore": 1.0,
    "cr": 1.0,
    "lakh": 0.01,
    "lac": 0.01,
    "million": 0.1,
    "mn": 0.1,
    "thousand": 0.0001,
    "billion": 100.0,
}


def statement_scale(texts: Sequence[str]) -> tuple[str, float] | None:
    """The unit a statement is printed in, from its own pages: ("crore", 1.0).

    The rupee sign often comes out of the PDF as a stray glyph ("(H crores)", "(C in
    crore)", "(In ` crore)"), so the unit is read from the word."""
    for text in texts:
        f = flat(text)
        for pattern in (_UNIT_PAREN, _UNIT_MARK, _UNIT_PLAIN):
            m = pattern.search(f)
            if m:
                word = m.group(m.lastindex or 1).rstrip("s")
                if word in SCALE_TO_CRORE:
                    return word, SCALE_TO_CRORE[word]
    return None


# --- sections ----------------------------------------------------------------------------

_TITLES = {
    "profit_and_loss": re.compile(
        r"statement of profit (?:and|&) loss|profit (?:and|&) loss (?:statement|account)"
    ),
    "cash_flow": re.compile(r"statement of cash ?flows?|cash ?flow statement"),
}
_ANCHORS = {
    "profit_and_loss": re.compile(
        r"revenue from operations|total income|interest income|income from operations"
    ),
    "cash_flow": re.compile(r"operating activities"),
}
_ENDS = {
    "profit_and_loss": re.compile(r"earnings per (?:equity )?share"),
    "cash_flow": re.compile(
        r"cash and cash equivalents,? (?:as )?at (?:the )?(?:end|close) of (?:the )?(?:year|period)"
        r"|closing (?:balance of )?cash and cash equivalents"
    ),
}
_MAX_STATEMENT_PAGES = {"profit_and_loss": 2, "cash_flow": 3}
_OTHER_STATEMENT = re.compile(
    r"statement of changes in equity|balance sheet|notes? (?:to|forming part of)"
)
_AUDIT_OF = {
    True: re.compile(
        r"\brepor\w* on (?:the )?audit of (?:the )?consolidated (?:ind ?as )?financial statements"
    ),
    False: re.compile(
        r"\brepor\w* on (?:the )?audit of (?:the )?(?:standalone )?(?:ind ?as )?"
        r"financial statements"
    ),
}
_OPENING = {
    True: re.compile(r"we have (?:jointly )?audited the (?:accompanying )?consolidated"),
    False: re.compile(
        r"we have (?:jointly )?audited the (?:accompanying )?(?:standalone )?(?:ind ?as )?financial"
    ),
}
_BRSR = re.compile(r"details of business activities|products ?/ ?services sold by the entity")
_MDNA = re.compile(
    r"management.{0,3}s? discussion (?:and|&) analysis|(?<![a-z])md ?& ?a(?![a-z])"
    r"|(?<![a-z])mda(?![a-z])"
)
_RISK_WORDS = re.compile(r"\brisks?\b|\bthreats?\b|\bconcerns?\b|headwinds?|uncertaint")


def _titled(page: str, kind: str, consolidated: bool) -> bool:
    """The statement's title at the top of the page, or at the bottom, where some PDFs
    put the text of a page's heading."""
    for part in (page[:HEAD], page[-TAIL:]):
        for m in _TITLES[kind].finditer(part):
            named = "consolidated" in part[max(0, m.start() - 30) : m.start()]
            if named == consolidated and (consolidated or "consolidated" not in part):
                return True
    return False


def statement_pages(
    flats: Sequence[str], kind: str, consolidated: bool, start: int = 0
) -> list[int]:
    """Page numbers (1-based) of one statement, the first found from page `start`."""
    for i in range(start, len(flats)):
        p = flats[i]
        if not (
            _titled(p, kind, consolidated)
            and _ANCHORS[kind].search(p)
            and figure_count(p) >= MIN_FIGURES
        ):
            continue
        pages = [i + 1]
        j = i
        while (
            not _ENDS[kind].search(flats[j])
            and j + 1 < len(flats)
            and len(pages) < _MAX_STATEMENT_PAGES[kind]
            and figure_count(flats[j + 1]) >= MIN_FIGURES // 2
            and not _OTHER_STATEMENT.search(flats[j + 1][:HEAD])
        ):
            j += 1
            pages.append(j + 1)
        return pages
    return []


def auditor_start(flats: Sequence[str], consolidated: bool) -> int | None:
    """Index of the first page of the independent auditor's report on the statements:
    its heading, or (where the heading is an image) its opening paragraph."""
    pattern = _AUDIT_OF[consolidated]
    for i, p in enumerate(flats):
        if pattern.search(p) and "independent auditor" in p:
            if not consolidated and "consolidated" in p[: p.find("independent auditor") + 400]:
                continue
            return i
    opening = _OPENING[consolidated]
    for i, p in enumerate(flats):
        if "to the members of" in p[:1500] and opening.search(p[:2500]):
            return i
    return None


def _runs(pages: Iterable[int], gap: int = 2) -> list[list[int]]:
    out: list[list[int]] = []
    for n in sorted(pages):
        if out and n - out[-1][-1] <= gap:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def mdna_pages(flats: Sequence[str], outline: Sequence[tuple[int, str, int]] = ()) -> list[int]:
    """Management Discussion and Analysis: the bookmarked range if the PDF names it,
    else the longest run of pages whose running header or footer names it."""
    for k, (level, title, page) in enumerate(outline):
        if page > 0 and _MDNA.search(title.lower()):
            end = next(
                (p for lv, _t, p in outline[k + 1 :] if lv <= level and p > page),
                page + MAX_MDNA_PAGES,
            )
            return list(range(page, min(end, page + MAX_MDNA_PAGES, len(flats) + 1)))
    tagged = [i + 1 for i, p in enumerate(flats) if _MDNA.search(p[:150]) or _MDNA.search(p[-150:])]
    runs = [r for r in _runs(tagged) if len(r) >= 3]
    if not runs:
        return []
    best = max(runs, key=len)
    return list(range(best[0], min(best[-1], best[0] + MAX_MDNA_PAGES - 1) + 1))


def risk_pages(flats: Sequence[str], mdna: Sequence[int], limit: int = 10) -> list[int]:
    """The MD&A pages that talk most about risks, in page order."""
    scored = [(len(_RISK_WORDS.findall(flats[n - 1])), n) for n in mdna if n <= len(flats)]
    best = sorted((s for s in scored if s[0] >= 2), reverse=True)[:limit]
    return sorted(n for _s, n in best)


def business_pages(flats: Sequence[str]) -> list[int]:
    """BRSR Section A from the page before its business-activities table (where the
    reporting boundary is stated) to two pages after it."""
    for i, p in enumerate(flats):
        if _BRSR.search(p):
            return [n + 1 for n in range(max(0, i - 1), min(i + 3, len(flats)))]
    return []


@dataclass(frozen=True, slots=True)
class Sections:
    basis: str  # consolidated | standalone
    profit_and_loss: list[int] = field(default_factory=list)
    cash_flow: list[int] = field(default_factory=list)
    auditor: list[int] = field(default_factory=list)
    business: list[int] = field(default_factory=list)
    mdna: list[int] = field(default_factory=list)
    risks: list[int] = field(default_factory=list)

    def pages(self) -> list[int]:
        """Every page FINN reads from the report."""
        keep: set[int] = set()
        for part in (
            self.profit_and_loss,
            self.cash_flow,
            self.auditor,
            self.business,
            self.risks,
        ):
            keep.update(part)
        return sorted(keep)

    def found(self) -> dict[str, list[int]]:
        return {
            "profit_and_loss": self.profit_and_loss,
            "cash_flow": self.cash_flow,
            "auditor": self.auditor,
            "business": self.business,
            "mdna": [self.mdna[0], self.mdna[-1]] if self.mdna else [],
            "risks": self.risks,
        }


def find_sections(pages: Sequence[str], outline: Sequence[tuple[int, str, int]] = ()) -> Sections:
    flats = [flat(p) for p in pages]
    sections: Sections | None = None
    for consolidated in (True, False):
        audit = auditor_start(flats, consolidated)
        start = audit or 0
        cash = statement_pages(flats, "cash_flow", consolidated, start)
        pl = statement_pages(flats, "profit_and_loss", consolidated, start)
        if not (cash or pl) and audit is not None:  # statements before the report
            cash = statement_pages(flats, "cash_flow", consolidated)
            pl = statement_pages(flats, "profit_and_loss", consolidated)
        if cash or pl:
            first = min([*cash, *pl])
            auditor: list[int] = []
            if audit is not None:
                stop = first - 1 if first - 1 > audit else audit + AUDITOR_PAGES
                auditor = list(range(audit + 1, min(stop, audit + AUDITOR_PAGES) + 1))
            sections = Sections(
                basis="consolidated" if consolidated else "standalone",
                profit_and_loss=pl,
                cash_flow=cash,
                auditor=auditor,
            )
            break
    mdna = mdna_pages(flats, outline)
    base = sections or Sections(basis="unknown")
    return Sections(
        basis=base.basis,
        profit_and_loss=base.profit_and_loss,
        cash_flow=base.cash_flow,
        auditor=base.auditor,
        business=business_pages(flats),
        mdna=mdna,
        risks=risk_pages(flats, mdna),
    )


def numbered(pages: Mapping[int, str], numbers: Iterable[int]) -> str:
    """Pages with the markers a model cites, keeping their numbers in the PDF."""
    return "\n".join(f"[[page {n}]]\n{pages[n]}\n" for n in numbers if n in pages)


# --- collect and store ----------------------------------------------------------------


class AnnualReportSource(Protocol):
    def annual_reports(self, symbol: str) -> Any: ...
    def fetch_bytes(self, url: str, max_bytes: int = ...) -> bytes | None: ...


@dataclass(slots=True)
class ReadReport:
    ref: AnnualReport
    status: str  # read | missing | not a pdf | scanned
    total_pages: int = 0
    pages: dict[int, str] = field(default_factory=dict)  # only the pages FINN reads
    sections: Sections | None = None
    document_id: int | None = None


def find_reports(src: AnnualReportSource, symbol: str, years: int = 2) -> list[AnnualReport]:
    return latest_annual_reports(parse_annual_reports(src.annual_reports(symbol)), years)


def read_report(src: AnnualReportSource, ref: AnnualReport) -> ReadReport:
    data = src.fetch_bytes(ref.url, max_bytes=MAX_BYTES)
    if data is None:
        return ReadReport(ref, "missing")
    try:
        text = pdf_text(data, max_pages=MAX_PAGES)
    except NotAPdf:
        return ReadReport(ref, "not a pdf")
    if text.scanned:
        return ReadReport(ref, "scanned", total_pages=len(text.pages))
    sections = find_sections(text.pages, text.outline)
    keep = {n: text.pages[n - 1] for n in sections.pages()}
    return ReadReport(ref, "read", len(text.pages), keep, sections)


def store_report(conn: Conn, isin: str, report: ReadReport, title: str) -> int:
    """The report's row in `documents` and the pages FINN read, by PDF page number."""
    ref = report.ref
    filed = ref.filed_at.date() if ref.filed_at else None
    rows = fetch_all(
        conn,
        "insert into documents (isin, doc_type, period, published_on, source_url, pages,"
        " has_text_layer, parsed_at, title, filed_at, event_period)"
        " values (%s, 'annual_report', %s, %s, %s, %s, %s, now(), %s, %s, %s)"
        " on conflict (source_url) where source_url is not null do update set"
        " pages = excluded.pages, has_text_layer = excluded.has_text_layer,"
        " parsed_at = now(), title = excluded.title"
        " returning id",
        [
            isin,
            ref.fiscal_year,
            filed,
            ref.url,
            report.total_pages,
            report.status == "read",
            title[:300],
            filed,
            ref.fiscal_year,
        ],
    )
    doc_id = int(rows[0]["id"])
    fetch_all(conn, "delete from doc_pages where document_id = %s", [doc_id])
    copy_upsert(
        conn,
        "doc_pages",
        ["document_id", "page_no", "text"],
        [(doc_id, n, t) for n, t in sorted(report.pages.items())],
        conflict=["document_id", "page_no"],
        update=["text"],
    )
    return doc_id
