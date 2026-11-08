import json
from datetime import date
from pathlib import Path

import pytest

from finn.push.results_math import build_card, consistency_failures, ebitda_excl_other_income
from finn.sources.nse import parse_integrated_filings, pick_filing
from finn.sources.xbrl import XbrlError, parse_results_xbrl, quarter_start_for

NSE = Path(__file__).resolve().parents[3] / "fixtures" / "nse"


def test_quarter_start() -> None:
    assert quarter_start_for(date(2026, 9, 30)) == date(2026, 7, 1)
    assert quarter_start_for(date(2026, 3, 31)) == date(2026, 1, 1)
    assert quarter_start_for(date(2025, 12, 31)) == date(2025, 10, 1)
    assert quarter_start_for(date(2026, 1, 31)) == date(2025, 11, 1)


def test_tata_steel_q2_fy27_consolidated() -> None:
    q = parse_results_xbrl(
        (NSE / "xbrl_TATASTEEL_Q2FY27_consolidated.xml").read_bytes(), date(2026, 9, 30)
    )
    s = q.lines
    assert q.basis == "Consolidated" and q.audited == "Unaudited"
    assert s.revenue_from_operations == pytest.approx(65436.24)
    assert s.other_income == pytest.approx(248.28)
    assert s.finance_costs == pytest.approx(2005.32)
    assert s.depreciation == pytest.approx(3781.83)
    assert s.profit_before_exceptional_and_tax == pytest.approx(4994.2)
    assert s.exceptional_items == pytest.approx(348.68)
    assert s.profit_before_tax == pytest.approx(5342.88)
    assert s.tax_expense == pytest.approx(1755.56)
    assert s.profit_after_tax == pytest.approx(3699.59)
    assert s.share_of_associates_jv == pytest.approx(112.27)
    assert consistency_failures(s) == []
    assert ebitda_excl_other_income(s) == pytest.approx(10533.07)


def test_card_from_one_quarter_has_no_comparisons() -> None:
    q = parse_results_xbrl(
        (NSE / "xbrl_TATASTEEL_Q2FY27_consolidated.xml").read_bytes(), date(2026, 9, 30)
    )
    card = build_card(q.lines, None, None)
    assert [r.name for r in card.rows] == ["Revenue", "EBITDA (excl. other income)", "PBT", "PAT"]
    assert all(r.qoq_pct is None and r.yoy_pct is None for r in card.rows)


def test_wrong_quarter_is_refused() -> None:
    with pytest.raises(XbrlError):
        parse_results_xbrl(
            (NSE / "xbrl_TATASTEEL_Q2FY27_consolidated.xml").read_bytes(), date(2026, 6, 30)
        )
    with pytest.raises(XbrlError):
        parse_results_xbrl(b"not xml", date(2026, 9, 30))


def test_integrated_filing_listing() -> None:
    payload = json.loads((NSE / "integrated_filing_TATASTEEL.json").read_text())
    filings = parse_integrated_filings(payload)
    assert filings and all(f.taxonomy == "indas" for f in filings)
    assert filings[0].quarter_end == date(2026, 9, 30)
    cur = pick_filing(filings, date(2026, 9, 30), "Consolidated")
    prev = pick_filing(filings, date(2026, 6, 30), "Consolidated")
    year_ago = pick_filing(filings, date(2025, 9, 30), "Consolidated")
    assert cur and prev and year_ago
    assert cur.xbrl_url.endswith("INTEGRATED_FILING_INDAS_1755442_07112026053333_WEB.xml")
    banks = parse_integrated_filings(
        json.loads((NSE / "integrated_filing_HDFCBANK.json").read_text())
    )
    assert banks and all(f.taxonomy == "banking" for f in banks)


def test_nbfc_reads_as_a_lender() -> None:
    q = parse_results_xbrl(
        (NSE / "xbrl_MUTHOOTFIN_Q2FY27_consolidated.xml").read_bytes(), date(2026, 9, 30), "nbfc"
    )
    assert q.lender
    assert q.lines.net_interest_income == pytest.approx(6139.17, abs=0.01)
    assert q.lines.operating_profit_before_provisions == pytest.approx(4992.38, abs=0.01)
    assert consistency_failures(q.lines) == []
    card = build_card(q.lines, None, None, bank_like=True)
    assert [r.name for r in card.rows] == ["NII", "PPOP", "PBT", "PAT"]


def test_bank_taxonomy() -> None:
    q = parse_results_xbrl(
        (NSE / "xbrl_HDFCBANK_Q2FY27_consolidated.xml").read_bytes(), date(2026, 9, 30), "banking"
    )
    assert q.lender
    assert q.lines.revenue_from_operations == pytest.approx(129358.69)
    assert q.lines.exceptional_items == pytest.approx(-837.06)
    assert consistency_failures(q.lines) == []
