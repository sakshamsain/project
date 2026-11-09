"""The annual-report half of the Dossier, end to end against Postgres: a recorded NSE
listing, recorded report pages and recorded model answers."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from annual_helpers import REPORTS, full_pages, recorded_llm

from finn.core.db import connect, fetch_all
from finn.pull import annual
from finn.pull.annual_reports import ReadReport, find_sections
from finn.sources.nse import AnnualReport

ISIN = "INE009A01021"


class Listing:
    def annual_reports(self, symbol: str) -> Any:
        return json.loads((REPORTS / "listing_INFY.json").read_text())

    def fetch_bytes(self, url: str, max_bytes: int = 0) -> bytes | None:
        raise AssertionError("read_report is replaced in this test")


def _read(src: Any, ref: AnnualReport) -> ReadReport:
    if ref.fiscal_year != "FY26":
        return ReadReport(ref, "missing")
    pages, outline = full_pages("INFY_FY26")
    sections = find_sections(pages, outline)
    keep = {n: pages[n - 1] for n in sections.pages()}
    return ReadReport(ref, "read", len(pages), keep, sections)


@pytest.fixture()
def infy(clean_db: str) -> str:
    with connect(clean_db) as conn:
        fetch_all(conn, "insert into companies (isin, name) values (%s, 'Infosys Limited')", [ISIN])
    return clean_db


def test_build_annual_stores_each_section(infy: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(annual, "read_report", _read)
    llm, transport = recorded_llm()
    said: list[str] = []
    result = annual.build_annual(
        infy,
        Listing(),
        llm,
        ISIN,
        "Infosys Limited",
        "INFY",
        {},
        False,
        said.append,
        date(2026, 11, 9),
    )
    # FY26 read; FY25 missing, so FY24 is tried as the fallback and is missing too.
    assert result["read"] == 1 and result["annual_reports"] == 3
    assert transport.tasks == ["statements", "business", "auditor", "risks", "case"]
    assert said[0] == "Finding annual reports on NSE"
    with connect(infy) as conn:
        sections = {
            r["section"]: r["body"]
            for r in fetch_all(
                conn, "select section, body from dossier_sections where isin = %s", [ISIN]
            )
        }
        doc = fetch_all(
            conn,
            "select id, doc_type, period, pages, (select count(*) from doc_pages p"
            " where p.document_id = d.id) as kept from documents d where isin = %s",
            [ISIN],
        )
    assert set(sections) == {"annual_reports", "cash", "business", "auditor", "risks", "case"}
    assert [r["status"] for r in sections["annual_reports"]["reports"]] == [
        "read",
        "missing",
        "missing",
    ]
    assert doc[0]["doc_type"] == "annual_report" and doc[0]["period"] == "FY26"
    assert doc[0]["pages"] == 384 and 0 < doc[0]["kept"] < 30  # only the pages read
    cash = sections["cash"]
    assert cash["basis"] == "consolidated"
    assert [y["fiscal_year"] for y in cash["years"]] == ["FY26", "FY25"]
    assert cash["years"][0]["document_id"] == doc[0]["id"]
    assert sections["auditor"]["kind"] == "unmodified"
    case = sections["case"]
    assert case["bull"] or case["bear"]
    used = {f["id"] for f in case["facts"]}
    assert all(set(p["facts"]) <= used for p in case["bull"] + case["bear"])


def test_a_company_without_readable_reports_keeps_only_sources(
    infy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(annual, "read_report", lambda src, ref: ReadReport(ref, "scanned", 120))
    llm, transport = recorded_llm()
    result = annual.build_annual(
        infy, Listing(), llm, ISIN, "Infosys Limited", "INFY", {}, False, lambda m: None
    )
    assert result == {"annual_reports": 3, "read": 0}
    assert transport.tasks == []
    with connect(infy) as conn:
        rows = fetch_all(conn, "select section from dossier_sections where isin = %s", [ISIN])
    assert [r["section"] for r in rows] == ["annual_reports"]
