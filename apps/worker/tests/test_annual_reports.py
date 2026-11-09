from __future__ import annotations

import json

from annual_helpers import REPORTS, full_pages, page_map

from finn.pull.annual_reports import (
    figure_count,
    figures_on,
    find_sections,
    flat,
    mdna_pages,
    parse_figure,
    statement_scale,
)
from finn.sources.nse import latest_annual_reports, parse_annual_reports


def test_listing_keeps_the_last_filing_for_each_year() -> None:
    reports = parse_annual_reports(json.loads((REPORTS / "listing_INFY.json").read_text()))
    assert reports[0].fiscal_year == "FY26"
    latest = latest_annual_reports(reports, 2)
    assert [r.fiscal_year for r in latest] == ["FY26", "FY25"]
    # FY26 was filed on 29 May and revised on 30 May: the revision wins.
    assert latest[0].revised and "_U_" in latest[0].url
    assert all(r.url.startswith("https://nsearchives.nseindia.com/") for r in reports)


def test_figures_are_read_signed_and_a_dash_is_not_a_minus() -> None:
    assert parse_figure("2,67,021") == 267021
    assert parse_figure("(12,845)") == -12845
    assert parse_figure("72,776.01") == 72776.01
    assert parse_figure("-") == 0.0
    assert parse_figure("about 3") is None
    # "- 28": a nil column, then 28 -- not minus 28. "2025-26" is two years, not -26.
    assert figures_on("sale of shares - 28") == [28.0]
    assert figures_on("fiscal 2025-26 (1,861) -40") == [2025.0, 26.0, -1861.0, -40.0]
    assert figure_count("2,67,021 2,55,324 4,402 (473) 2026") == 4  # years do not count


def test_unit_is_read_from_the_word_whatever_the_rupee_glyph() -> None:
    assert statement_scale(["Consolidated Statement of Profit and Loss | (H crores) | Note"]) == (
        "crore",
        1.0,
    )
    assert statement_scale(["(C in crore) | For the year ended 31 March"]) == ("crore", 1.0)
    assert statement_scale(["Year ended 31st March, 2026 | ` / Lakhs | ` / Lakhs"]) == (
        "lakh",
        0.01,
    )
    assert statement_scale(["(All amounts in crores of ₹, except share data)"]) == ("crore", 1.0)
    assert statement_scale(["(₹ in million)"]) == ("million", 0.1)
    assert statement_scale(["Year ended March 31, 2026"]) is None


def test_sections_found_in_infosys_report() -> None:
    pages, outline = full_pages("INFY_FY26")
    s = find_sections(pages, outline)
    assert s.basis == "consolidated"
    assert s.profit_and_loss == [288, 289]
    assert s.cash_flow == [295, 296]
    assert s.auditor[0] == 277 and len(s.auditor) == 7
    assert s.business[:2] == [142, 143]
    assert s.mdna[0] == 76 and s.mdna[-1] == 90  # from the PDF's bookmarks
    assert set(s.risks) <= set(s.mdna)


def test_statement_stops_where_the_next_statement_starts() -> None:
    # Dixon's cash-flow statement is followed by the statement of changes in equity,
    # a wide table of dashes and figures that must not be read as part of it.
    pages, outline = full_pages("DIXON_FY26")
    s = find_sections(pages, outline)
    assert s.profit_and_loss == [419]
    assert s.cash_flow == [420, 421]
    assert s.auditor[0] == 409
    assert statement_scale([pages[418]]) == ("lakh", 0.01)


def test_title_at_the_bottom_of_the_page_counts() -> None:
    # HCLTech's PDF puts each statement's heading after its figures.
    pages, outline = full_pages("HCLTECH_FY26")
    s = find_sections(pages, outline)
    assert s.profit_and_loss == [398, 399]
    assert s.cash_flow == [402]
    assert s.auditor[0] == 390


def test_auditor_report_found_by_its_opening_when_the_heading_is_an_image() -> None:
    pages, outline = full_pages("BAJFINANCE_FY26")
    s = find_sections(pages, outline)
    assert s.auditor[0] == 399
    assert s.profit_and_loss == [413, 414]
    assert s.cash_flow == [417, 418]


def test_mdna_from_running_headers_without_bookmarks() -> None:
    pages = ["cover"] + ["Management Discussion and Analysis | text"] * 5 + ["Board's report"] * 3
    pages += ["Notes | management discussion and analysis is referred to"]
    assert mdna_pages([flat(p) for p in pages]) == [2, 3, 4, 5, 6]
    merged = [(1, "03 Dixon-MDA-01-09-2025 v2.pdf", 127), (1, "04 Dixon _CG_.pdf", 139)]
    assert mdna_pages([""] * 200, merged) == list(range(127, 139))


def test_only_read_pages_are_kept() -> None:
    pages, outline = full_pages("INFY_FY26")
    s = find_sections(pages, outline)
    kept = s.pages()
    assert 295 in kept and 143 in kept and 277 in kept
    assert len(kept) < 30
    assert set(kept) <= set(page_map("INFY_FY26"))


def test_a_report_too_large_or_unfetchable_is_skipped_not_fatal() -> None:
    from finn.pull.annual_reports import read_report
    from finn.sources.nse import AnnualReport, NseError

    class Big:
        def annual_reports(self, symbol: str) -> object:
            return {}

        def fetch_bytes(self, url: str, max_bytes: int = 0) -> bytes | None:
            raise NseError(f"{url}: 253443410 bytes is over the {max_bytes} limit")

    ref = AnnualReport("FY25", "https://nsearchives.nseindia.com/x.pdf", None, False, 0)
    assert read_report(Big(), ref).status == "too large"
