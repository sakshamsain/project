"""The annual-report half of the Dossier, for one company.

    NSE annual reports (last two) -> sections found on the page -> statements (model
    copies, code checks and sums) + business, auditor, risks (verified quotes) -> facts
    -> bull and bear (model writes, code checks) -> dossier_sections

Each part is stored as its own dossier section, so one that fails does not take the rest
down, and the Ledger, built from call transcripts, stands on its own either way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

from finn.core.db import Conn, Jsonb, fetch_all
from finn.llm.client import Llm, LlmError
from finn.pull.annual_reports import (
    AnnualReportSource,
    ReadReport,
    find_reports,
    read_report,
    store_report,
)
from finn.pull.case import Fact, case_json, write_case
from finn.pull.report_items import PROMPT_VERSION as ITEMS_VERSION
from finn.pull.report_items import pages_for, read_auditor, read_business, read_risks
from finn.pull.statements import PROMPT_VERSION as STATEMENTS_VERSION
from finn.pull.statements import Extracted, cash_table, extract_statements
from finn.push.results_math import StatementLines

STATUS_WORDS = {
    "delivered": "delivered",
    "missed": "missed",
    "on_track": "on track",
    "off_track": "off track",
    "too_early": "too early to tell",
    "not_measurable": "not in the filings",
}


OPINION_WORDS = {
    "unmodified": "an unmodified (clean) opinion",
    "qualified": "a qualified opinion",
    "adverse": "an adverse opinion",
    "disclaimer": "a disclaimer of opinion",
}


def crore(x: float) -> str:
    """₹ crore in Indian digit grouping: 178650 -> 1,78,650; small amounts keep a decimal."""
    if abs(x) < 10:
        return f"{x:.1f}".replace("-", "−")
    n = round(abs(x))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("−" if x < 0 else "") + s


def pct(x: float) -> str:
    """A percentage as code writes it: 9.6, 115.3, 0.12 (two decimals below 1)."""
    text = f"{x:.2f}" if abs(x) < 1 else f"{x:.1f}"
    return text.rstrip("0").rstrip(".")


def _fy_range(years: Sequence[str]) -> str:
    ys = sorted(years, key=lambda fy: int(fy[2:]))
    return ys[0] if len(ys) == 1 else f"{ys[0]}-{ys[-1][2:]}"


def cash_facts(cash: Mapping[str, Any]) -> list[Fact]:
    """Sentences from the Cash table, written by code from the figures it computed."""
    out: list[Fact] = []
    rows = [r for r in cash.get("years", []) if not r["failures"]]
    for r in rows[:2]:
        fy, doc, pages = r["fiscal_year"], r["document_id"], r["pages"]
        if r["revenue"] is not None and r["revenue_growth_pct"] is not None:
            g = r["revenue_growth_pct"]
            out.append(
                Fact(
                    "",
                    f"{fy} revenue from operations was ₹{crore(r['revenue'])} crore, "
                    f"{'up' if g >= 0 else 'down'} {pct(abs(g))}% on the year before.",
                    "computed",
                    doc,
                    pages.get("revenue"),
                )
            )
        if r["pat"] is not None and r["pat_growth_pct"] is not None:
            g = r["pat_growth_pct"]
            out.append(
                Fact(
                    "",
                    f"{fy} profit for the year was ₹{crore(r['pat'])} crore, "
                    f"{'up' if g >= 0 else 'down'} {pct(abs(g))}% on the year before.",
                    "computed",
                    doc,
                    pages.get("pat") or pages.get("pat_owners"),
                )
            )
        if cash.get("lender"):
            continue  # a lender's operating cash flow tracks its lending: no case either way
        if r["cash_conversion_pct"] is not None:
            out.append(
                Fact(
                    "",
                    f"{fy} operating cash flow of ₹{crore(r['cfo'])} crore was "
                    f"{pct(r['cash_conversion_pct'])}% of profit for the year "
                    f"(₹{crore(r['pat'])} crore).",
                    "computed",
                    doc,
                    pages.get("cfo"),
                )
            )
        if r["fcf"] is not None:
            out.append(
                Fact(
                    "",
                    f"{fy} free cash flow was ₹{crore(r['fcf'])} crore: operating cash flow "
                    f"less ₹{crore(r['capex'])} crore of capital expenditure.",
                    "computed",
                    doc,
                    pages.get("capex") or pages.get("cfo"),
                )
            )
    latest = next((r for r in rows if r.get("balance") and not r.get("balance_failures")), None)
    if latest is not None and not cash.get("lender"):
        b, fy = latest["balance"], latest["fiscal_year"]
        end = f"31 March 20{fy[2:]}"
        if b.get("net_debt") is not None:
            if b["net_debt"] <= 0:
                text = (
                    f"At {end}, cash and bank balances exceeded borrowings by "
                    f"₹{crore(-b['net_debt'])} crore (net cash)."
                )
            else:
                text = (
                    f"At {end}, borrowings exceeded cash and bank balances by "
                    f"₹{crore(b['net_debt'])} crore"
                    + (
                        f"; debt was {b['debt_to_equity']:g} times equity."
                        if b.get("debt_to_equity") is not None
                        else "."
                    )
                )
            out.append(Fact("", text, "computed", latest["document_id"], None))
        if b.get("roce_pct") is not None:
            out.append(
                Fact(
                    "",
                    f"{fy} return on capital employed was {pct(b['roce_pct'])}% (profit before "
                    "tax and finance costs over year-end equity and borrowings).",
                    "computed",
                    latest["document_id"],
                    None,
                )
            )
        if b.get("receivable_days") is not None:
            out.append(
                Fact(
                    "",
                    f"At {end}, trade receivables equalled {b['receivable_days']:g} days of "
                    f"{fy} revenue.",
                    "computed",
                    latest["document_id"],
                    None,
                )
            )
    t = cash.get("totals") or {}
    years = cash.get("years_in_totals") or []
    if t.get("payout") is not None and t.get("payout_of_fcf_pct") is not None:
        out.append(
            Fact(
                "",
                f"Over {_fy_range(years)}, dividends and buybacks of ₹{crore(t['payout'])} crore "
                f"were {pct(t['payout_of_fcf_pct'])}% of free cash flow "
                f"(₹{crore(t['fcf'])} crore).",
                "computed",
            )
        )
    return out


def report_facts(
    business: Mapping[str, Any] | None,
    auditor: Mapping[str, Any] | None,
    risks: Mapping[str, Any] | None,
    document_id: int | None,
    fiscal_year: str,
) -> list[Fact]:
    out: list[Fact] = []
    if business:
        for a in business.get("activities", [])[:2]:
            if a.get("share") is not None:
                out.append(
                    Fact(
                        "",
                        f"{pct(a['share'])}% of turnover came from {a['name']} "
                        f"({fiscal_year} BRSR).",
                        "quote",
                        document_id,
                        a["page"],
                    )
                )
        if business.get("exports"):
            e = business["exports"]
            out.append(
                Fact(
                    "",
                    f"Exports were {pct(e['value'])}% of turnover ({fiscal_year} BRSR).",
                    "quote",
                    document_id,
                    e["page"],
                )
            )
    if auditor and auditor.get("kind"):
        firm = f" ({auditor['firm']})" if auditor.get("firm") else ""
        opinion = OPINION_WORDS.get(str(auditor["kind"]), str(auditor["kind"]))
        out.append(
            Fact(
                "",
                f"The auditor{firm} gave {opinion} on the {fiscal_year} financial statements.",
                "quote",
                document_id,
                auditor.get("page"),
            )
        )
        for d in auditor.get("drawn_attention", [])[:2]:
            out.append(
                Fact(
                    "",
                    f'The auditor draws attention to: "{d["quote"][:300]}"',
                    "quote",
                    document_id,
                    d["page"],
                    d["quote"],
                )
            )
        for m in auditor.get("matters", [])[:3]:
            label = m["title"] or "a key audit matter"
            out.append(
                Fact(
                    "",
                    f"Key audit matter (an area the auditor judged most significant, not a "
                    f'finding), {label}: "{m["quote"]}"',
                    "quote",
                    document_id,
                    m["page"],
                    m["quote"],
                )
            )
    if risks:
        for r in risks.get("risks", [])[:5]:
            label = f" ({r['title']})" if r["title"] else ""
            out.append(
                Fact(
                    "",
                    f'Management names a risk{label}: "{r["quote"]}"',
                    "quote",
                    document_id,
                    r["page"],
                    r["quote"],
                )
            )
    return out


def _range(lo: Any, hi: Any, unit: str | None) -> str:
    u = "%" if unit == "%" else (" bps" if unit == "bps" else (" crore" if unit == "crore" else ""))
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None and float(lo) != float(hi):
        return f"{pct(float(lo))}-{pct(float(hi))}{u}"
    v = lo if lo is not None else hi
    return f"{pct(float(v))}{u}"


def ledger_facts(conn: Conn, isin: str, limit: int = 8) -> list[Fact]:
    """Promises from the ledger, the measured ones first, in words code writes."""
    rows = fetch_all(
        conn,
        "select metric, value_low, value_high, unit, period_label, status, actual_note,"
        " call_date, document_id, page, quote, basis"
        " from guidance where isin = %s"
        " order by (status in ('delivered','missed','on_track','off_track')) desc,"
        " call_date desc, id limit %s",
        [isin, limit],
    )
    out: list[Fact] = []
    for r in rows:
        what = str(r["metric"])
        rng = _range(r["value_low"], r["value_high"], r["unit"])
        basis = " in constant currency" if r["basis"] == "constant_currency" else ""
        period = f" for {r['period_label']}" if r["period_label"] else ""
        status = STATUS_WORDS.get(str(r["status"]), str(r["status"]))
        note = f" ({r['actual_note']})" if r["actual_note"] else ""
        day = r["call_date"]
        on = f" on the {day:%d %b %Y} call" if isinstance(day, date) else ""
        target = f" of {rng}{basis}" if rng else ""
        out.append(
            Fact(
                "",
                f"Promise made{on}: {what}{target}{period}. Status: {status}{note}.",
                "promise",
                int(r["document_id"]),
                r["page"],
                str(r["quote"]),
            )
        )
    return out


def numbered_facts(groups: Sequence[Sequence[Fact]]) -> list[Fact]:
    out: list[Fact] = []
    for group in groups:
        for f in group:
            out.append(Fact(f"F{len(out) + 1}", f.text, f.kind, f.document_id, f.page, f.quote))
    return out


def store_section(
    conn: Conn, isin: str, section: str, version: str, body: Mapping[str, Any]
) -> None:
    fetch_all(
        conn,
        "insert into dossier_sections (isin, section, docset_hash, prompt_version, body)"
        " values (%s, %s, 'latest', %s, %s)"
        " on conflict (isin, section, docset_hash, prompt_version)"
        " do update set body = excluded.body, built_at = now()",
        [isin, section, version, Jsonb(dict(body))],
    )
    fetch_all(
        conn,
        "delete from dossier_sections where isin = %s and section = %s and prompt_version <> %s",
        [isin, section, version],
    )


def _report_entry(r: ReadReport) -> dict[str, Any]:
    return {
        "fiscal_year": r.ref.fiscal_year,
        "url": r.ref.url,
        "filed_on": r.ref.filed_at.date().isoformat() if r.ref.filed_at else None,
        "revised": r.ref.revised,
        "status": r.status,
        "pages": r.total_pages,
        "document_id": r.document_id,
        "basis": r.sections.basis if r.sections else None,
        "sections": r.sections.found() if r.sections else {},
    }


def build_annual(
    url: str,
    src: AnnualReportSource,
    llm: Llm,
    isin: str,
    name: str,
    symbol: str,
    series: Mapping[str, StatementLines],
    lender: bool,
    say: Callable[[str], None],
    today: date | None = None,
) -> dict[str, Any]:
    from finn.core.db import connect

    today = today or date.today()
    say("Finding annual reports on NSE")
    refs = find_reports(src, symbol)
    reports: list[ReadReport] = []
    for ref in refs:
        if sum(r.status == "read" for r in reports) >= 2:
            break  # the third report is only a fallback for one that cannot be read
        say(f"Reading the {ref.fiscal_year} annual report")
        r = read_report(src, ref)
        if r.status == "read":
            with connect(url) as conn:
                r.document_id = store_report(
                    conn, isin, r, f"{name} annual report {ref.fiscal_year}"
                )
        reports.append(r)
    read = [r for r in reports if r.status == "read" and r.sections is not None]
    sources = {"reports": [_report_entry(r) for r in reports], "built_on": today.isoformat()}
    with connect(url) as conn:
        store_section(conn, isin, "annual_reports", "sources-v1", sources)
    if not read:
        return {"annual_reports": len(reports), "read": 0}

    extracted: list[tuple[str, Extracted, int | None]] = []
    statement_notes: list[dict[str, Any]] = []
    for r in read:
        assert r.sections is not None
        sec = r.sections
        pm = pages_for(r.pages, sec.balance_sheet + sec.profit_and_loss + sec.cash_flow)
        if not pm:
            continue
        say(f"Checking the {r.ref.fiscal_year} balance sheet, profit and cash flows")
        try:
            ex, model = extract_statements(
                llm,
                pm,
                name,
                r.ref.fiscal_year,
                sec.basis,
                sec.balance_sheet,
                sec.profit_and_loss + sec.cash_flow,
            )
        except LlmError as exc:
            statement_notes.append({"fiscal_year": r.ref.fiscal_year, "error": str(exc)[:300]})
            continue
        extracted.append((r.ref.fiscal_year, ex, r.document_id))
        statement_notes.append(
            {
                "fiscal_year": r.ref.fiscal_year,
                "unit": ex.unit,
                "lines": len(ex.lines),
                "dropped": ex.dropped,
                "incomplete": ex.incomplete,
                "added_by_code": ex.added,
                "model": model,
            }
        )
    cash = cash_table(extracted, series, lender)
    cash["basis"] = read[0].sections.basis if read[0].sections else None
    cash["reports"] = statement_notes
    with connect(url) as conn:
        store_section(conn, isin, "cash", STATEMENTS_VERSION, cash)

    latest = read[0]
    assert latest.sections is not None
    fy = latest.ref.fiscal_year
    parts: dict[str, Any] = {}
    for key, reader, numbers in (
        ("business", read_business, latest.sections.business),
        ("auditor", read_auditor, latest.sections.auditor),
        ("risks", read_risks, latest.sections.risks),
    ):
        pm = pages_for(latest.pages, numbers)
        if not pm:
            continue
        say(
            {
                "business": "Reading what the business does (BRSR)",
                "auditor": "Reading the auditor's report",
                "risks": "Reading the risks management names",
            }[key]
        )
        used: str | None = None
        try:
            body, used = reader(llm, pm, name)
        except LlmError as exc:
            body = {"error": str(exc)[:300]}
        body = {**body, "fiscal_year": fy, "document_id": latest.document_id, "model": used}
        parts[key] = body
        with connect(url) as conn:
            store_section(conn, isin, key, ITEMS_VERSION, body)

    say("Weighing the bull and bear case")
    with connect(url) as conn:
        promises = ledger_facts(conn, isin)
    facts = numbered_facts(
        [
            cash_facts(cash),
            promises,
            report_facts(
                parts.get("business"),
                parts.get("auditor"),
                parts.get("risks"),
                latest.document_id,
                fy,
            ),
        ]
    )
    try:
        case, case_model = write_case(llm, facts, name)
        body = case_json(case, facts, case_model)
    except LlmError as exc:
        body = {"bull": [], "bear": [], "facts": [], "error": str(exc)[:300]}
    with connect(url) as conn:
        store_section(conn, isin, "case", str(body.get("prompt_version", "case-v1")), body)
    return {
        "annual_reports": len(reports),
        "read": len(read),
        "cash_years": len(cash["years"]),
        "bull": len(body.get("bull", [])),
        "bear": len(body.get("bear", [])),
    }
