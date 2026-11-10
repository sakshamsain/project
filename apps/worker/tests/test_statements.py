from __future__ import annotations

import copy

import pytest
from annual_helpers import page_map, recorded, recorded_llm

from finn.pull.statements import (
    Extracted,
    Line,
    Year,
    against_quarters,
    balance_year,
    cash_table,
    extract_statements,
    matched_row,
    missing_lines,
    row_after,
    verify_lines,
    year_failures,
)
from finn.push.results_math import StatementLines

SHEET = (286, 287)  # the balance sheet
FLOWS = (288, 289, 295, 296)  # profit and loss, cash flows


def infy_pages() -> dict[int, str]:
    pages = page_map("INFY_FY26")
    return {n: pages[n] for n in SHEET + FLOWS}


def infy() -> Extracted:
    return verify_lines(recorded("statements"), infy_pages(), SHEET)


def read_by_code(name: str, sheet: list[int], flows: list[int]) -> Extracted:
    """What code reads from a report's statements with no model answer at all."""
    pages = page_map(name)
    return verify_lines({"lines": []}, {n: pages[n] for n in {*sheet, *flows}}, sheet, flows)


def summed(ex: Extracted, key: str) -> tuple[float, float]:
    rows = [ln for ln in ex.lines if ln.key == key]
    return (
        round(sum(ln.current or 0.0 for ln in rows), 2),
        round(sum(ln.prior or 0.0 for ln in rows), 2),
    )


def test_a_row_is_its_first_two_figures_after_note_numbers() -> None:
    # Depreciation and amortization | 2.2, 2.4.2 and 2.21 | 4,902 | 4,812
    row = row_after(" 2.2, 2.4.2 and 2.21 4,902 4,812 interest and dividend income (2,630)")
    assert matched_row("4,902", "4,812", [row]) == (4902.0, 4812.0)
    assert matched_row("4,812", "4,902", [row]) is None  # columns swapped
    assert matched_row("2,630", None, [row]) is None  # the next row's figure


def test_a_dash_is_nil_and_must_be_printed() -> None:
    row = row_after(" (18,058) - net cash used in financing activities")
    assert matched_row("(18,058)", "-", [row]) == (-18058.0, 0.0)
    assert matched_row("(18,058)", "(1,000)", [row]) is None


def test_figures_from_a_wide_table_are_refused() -> None:
    # Statement of changes in equity: "final dividend paid - - - (2,991) - (2,991)"
    row = row_after(" - - - (2,991) - (2,991) interim dividend paid")
    assert matched_row("-", "(2,991)", [row]) is None
    assert matched_row(None, "(2,991)", [row]) is None


def test_a_heading_is_not_a_row() -> None:
    # "Tax expense: Current tax 11,767 12,130": the figures belong to current tax.
    assert row_after(": current tax 2.17 11,767 12,130 deferred tax") == ""
    # A label printed longer than copied still finds its row.
    long = ", net of sale proceeds (refer to note 2.2) (2,727) (2,237) deposits placed"
    assert matched_row("(2,727)", "(2,237)", [row_after(long)]) == (-2727.0, -2237.0)


def test_recorded_infosys_statements_verify_in_full() -> None:
    ex = infy()
    assert ex.unit == "crore" and not ex.incomplete
    # The statement prints current and deferred tax but no total: the part is refused.
    assert ex.dropped == ["tax: 'Current tax' is one part of the tax expense"]
    got = {ln.key: (ln.current, ln.prior) for ln in ex.lines if ln.key != "dividends"}
    assert got["revenue"] == (178650.0, 162990.0)
    assert got["pat"] == (29474.0, 26750.0)
    assert got["cfo"] == (33986.0, 35694.0)
    assert got["cfi"] == (1946.0, -1946.0)
    assert got["net_change"] == (-3854.0, 9587.0)
    assert got["capex"] == (-2727.0, -2237.0)
    assert got["equity"] == (93297.0, 96203.0)
    assert got["total_assets"] == got["total_equity_liabilities"] == (155967.0, 148903.0)
    assert ex.absent == ["borrowings", "inventories", "bank_balances"]


def test_a_figure_not_in_its_row_is_dropped() -> None:
    data = copy.deepcopy(recorded("statements"))
    for line in data["lines"]:
        if line["key"] == "cfo":
            line["current"] = "34,986"  # one digit off
    ex = verify_lines(data, infy_pages(), SHEET)
    assert "cfo" not in {ln.key for ln in ex.lines}
    assert any(d.startswith("cfo:") for d in ex.dropped)


def test_a_summed_line_left_out_is_read_by_code() -> None:
    data = copy.deepcopy(recorded("statements"))
    data["lines"] = [ln for ln in data["lines"] if ln["key"] != "buyback"]
    ex = verify_lines(data, infy_pages(), SHEET)
    # The recorded answer has no capex line either: code reads both rows itself.
    assert not ex.incomplete and {a.split(":")[0] for a in ex.added} == {"capex", "buyback"}
    fy26 = cash_table([("FY26", ex, 1)], {}, lender=False)["years"][0]
    assert fy26["buyback"] == 18058.0 and fy26["capex"] == 2727.0 and fy26["withheld"] == []


def test_a_line_code_cannot_place_withholds_the_sum() -> None:
    # A capex line printed without brackets is left to the model; missing, the sum goes.
    pages = {
        5: "Cash flow from investing activities\nPurchase of property, plant and equipment\n"
        "1,234\n1,100\nProceeds from sale of investments\n50\n40\n(In ` crore)"
    }
    ex = verify_lines({"lines": []}, pages)
    assert ex.added == [] and ex.incomplete == {"current": ["capex"], "prior": ["capex"]}


def test_a_footnote_is_not_a_row() -> None:
    from finn.pull.statements import add_code_rows

    pages = {7: "Note: purchase of property, plant and equipment includes capital advances of 120"}
    assert add_code_rows([], pages, {}, 1.0) == []


def test_buyback_escrow_rows_are_not_buyback_payments() -> None:
    pages = page_map("TCS_FY25")
    lines = [
        Line("buyback", "Buy-back of equity shares", 186, None, -17000.0),
        Line("buyback", "Tax on buy-back of equity shares", 186, None, -3959.0),
        Line("buyback", "Expenses for buy-back of equity shares", 186, None, -46.0),
    ]
    assert "buyback" not in missing_lines(lines, pages, {}, 1.0).get("prior", [])
    assert "buyback" in missing_lines(lines[:1], pages, {}, 1.0).get("prior", [])


def _year(**v: float) -> Year:
    return Year("FY26", dict(v), {}, {})


def test_cash_flows_must_add_up() -> None:
    ok = _year(cfo=33986, cfi=1946, cff=-39786, net_change=-3854)
    assert year_failures(ok) == []
    assert year_failures(_year(cfo=33986, cfi=-1946, cff=-39786, net_change=-3854)) == [
        "cash_flows_do_not_add_up"
    ]
    # Some statements give the change in cash after exchange-rate effects.
    fx = _year(cfo=100, cfi=-40, cff=-50, fx_effect=5, net_change=15)
    assert year_failures(fx) == []
    assert year_failures(_year(pbt=39995, tax=10521, pat=29474)) == []


def test_profit_must_reconcile() -> None:
    assert year_failures(_year(pbt=100, tax=25, pat=75)) == []
    assert year_failures(_year(pbt=100, tax=11.767, pat=29.474)) == ["profit_does_not_reconcile"]


def _q(revenue: float, pat: float) -> StatementLines:
    return StatementLines(revenue, 0, 0, 0, pat * 1.3, 0, pat * 1.3, pat * 0.3, pat)


def test_full_year_checked_against_the_four_quarters() -> None:
    y = _year(revenue=178650, pat=29474)
    series = {
        "Q1 FY26": _q(42279, 6921),
        "Q2 FY26": _q(44490, 7364),
        "Q3 FY26": _q(45479, 6654),
        "Q4 FY26": _q(46402, 8535),
    }
    assert against_quarters(y, series)["status"] == "matches"
    series["Q4 FY26"] = _q(56402, 8535)
    assert against_quarters(y, series)["status"] == "differs"
    del series["Q4 FY26"]
    assert against_quarters(y, series)["status"] == "quarters_missing"


def test_cash_table_computes_free_cash_flow_and_conversion() -> None:
    t = cash_table([("FY26", infy(), 9)], {}, lender=False)
    fy26, fy25 = t["years"]
    assert fy26["fiscal_year"] == "FY26" and fy26["failures"] == []
    assert fy26["capex"] == 2727.0
    assert fy26["fcf"] == pytest.approx(33986 - 2727)
    assert fy26["cash_conversion_pct"] == pytest.approx(round(33986 / 29474 * 100, 1))
    assert fy26["payout"] == pytest.approx(18653 + 3 + 18058)
    assert fy26["revenue_growth_pct"] == pytest.approx(round((178650 / 162990 - 1) * 100, 1))
    assert fy26["document_id"] == 9 and fy26["pages"]["cfo"] == 295
    assert fy25["revenue_growth_pct"] is None  # no FY24 in this report
    assert t["totals"]["fcf"] == pytest.approx(31259 + 33457)


def test_lenders_get_no_free_cash_flow() -> None:
    ex = Extracted(
        [
            Line("revenue", "Total revenue from operations", 413, 81982.38, 68805.71),
            Line("pat", "Profit for the year", 413, 19332.36, 16779.48),
            Line("cfo", "Net cash used in operating activities", 417, -65789.8, -67791.64),
            Line("capex", "Purchase of property, plant and equipment", 417, -961.1, -1081.82),
        ],
        "crore",
    )
    t = cash_table([("FY26", ex, 1)], {}, lender=True)
    row = t["years"][0]
    assert row["fcf"] is None and row["cash_conversion_pct"] is None
    assert row["cfo"] == -65789.8 and t["totals"] == {}


def test_extraction_with_recorded_answer_asks_once() -> None:
    llm, transport = recorded_llm()
    ex, _model = extract_statements(
        llm, infy_pages(), "Infosys Limited", "FY26", "consolidated", SHEET, FLOWS
    )
    assert {ln.key for ln in ex.lines} >= {"revenue", "cfo", "equity", "total_assets", "payables"}
    assert transport.tasks == ["statements"]


def test_a_weak_answer_is_asked_again_of_the_stronger_model() -> None:
    weak = {"lines": recorded("statements")["lines"][:2]}
    llm, transport = recorded_llm({"statements": weak})
    extract_statements(llm, infy_pages(), "Infosys Limited", "FY26", "consolidated", SHEET)
    assert transport.tasks == ["statements", "statements"]


def test_code_and_model_must_agree_a_line_is_summed() -> None:
    from finn.pull.statements import is_summed_label

    assert is_summed_label(
        "capex",
        "Expenditure on property, plant and equipment and intangibles, net of sale proceeds",
    )
    assert is_summed_label(
        "capex", "Purchase of property, plant and equipment (including capital advances)"
    )
    assert is_summed_label("capex", "Payment for purchase of intangible assets")
    assert not is_summed_label("capex", "Advances for acquiring right-of-use assets")
    assert not is_summed_label("capex", "Proceeds from sale of property, plant and equipment")
    assert is_summed_label("dividends", "Dividend paid to non-controlling interests")
    assert not is_summed_label("dividends", "Dividend received")
    assert is_summed_label("buyback", "Tax on buy-back of equity shares")
    assert not is_summed_label("buyback", "Transfer of funds to buy-back escrow account")


# --- the balance sheet -------------------------------------------------------------------


def test_balance_sheet_ratios_are_computed_in_code() -> None:
    fy26 = cash_table([("FY26", infy(), 9)], {}, lender=False)["years"][0]
    b = fy26["balance"]
    assert fy26["balance_failures"] == []
    assert b["equity"] == 93297.0 and b["total_assets"] == 155967.0
    # No line on the sheet is called borrowings: debt is nil, not unread.
    assert b["borrowings"] == 0.0 and b["debt_to_equity"] == 0.0
    assert b["cash_and_bank"] == 22201.0 and b["net_debt"] == -22201.0
    assert b["receivable_days"] == round(35234 / 178650 * 365)
    assert b["payable_days"] == round(4744 / 178650 * 365)
    assert b["inventory_days"] == 0
    assert b["cash_cycle_days"] == b["receivable_days"] - b["payable_days"]
    assert b["interest_cover"] == round((39995 + 416) / 416, 1)
    assert b["roce_pct"] == round((39995 + 416) / 93297 * 100, 1)


def test_a_balance_line_counts_only_on_the_balance_sheet() -> None:
    # "Trade receivables" in the cash-flow statement is the change in the year.
    data = copy.deepcopy(recorded("statements"))
    data["lines"] = [ln for ln in data["lines"] if ln["key"] != "receivables"]
    data["lines"].append(
        {"key": "receivables", "label": "Trade receivables", "current": "(4,076)", "page": 295}
    )
    ex = verify_lines(data, infy_pages(), SHEET)
    assert "receivables: p. 295 is not the statement it belongs on" in ex.dropped
    assert summed(ex, "receivables") == (35234.0, 31158.0)  # read from the sheet by code
    assert any(a.startswith("receivables:") for a in ex.added)


def test_owners_equity_is_not_total_equity() -> None:
    data = copy.deepcopy(recorded("statements"))
    for line in data["lines"]:
        if line["key"] == "equity":
            line["label"] = "Total equity attributable to equity holders of the Company"
            line["current"], line["prior"] = "92,852", "95,818"
    ex = verify_lines(data, infy_pages(), SHEET)
    assert any(d.startswith("equity:") and "not the total" in d for d in ex.dropped)
    assert summed(ex, "equity") == (93297.0, 96203.0)  # the one row labelled total equity


def test_a_sheet_that_does_not_balance_shows_no_ratios() -> None:
    values = {"total_assets": 100.0, "total_equity_liabilities": 90.0, "equity": 40.0}
    balance, failures = balance_year(Year("FY26", values, {"borrowings": [30.0]}, {}), False)
    assert failures == ["balance_sheet_does_not_balance"]
    assert "net_debt" not in balance and "roce_pct" not in balance


def test_debt_is_withheld_when_a_borrowings_line_was_not_read() -> None:
    values = {
        "total_assets": 100.0,
        "total_equity_liabilities": 100.0,
        "equity": 40.0,
        "cash": 5.0,
        "pbt": 10.0,
        "finance_costs": 2.0,
        "revenue": 80.0,
    }
    whole = Year("FY26", dict(values), {"borrowings": [30.0, 10.0]}, {}, absent=["bank_balances"])
    balance, failures = balance_year(whole, False)
    assert failures == [] and balance["borrowings"] == 40.0 and balance["net_debt"] == 35.0
    assert balance["debt_to_equity"] == 1.0 and balance["roce_pct"] == 15.0
    assert balance["interest_cover"] == 6.0
    short = Year("FY26", dict(values), {"borrowings": [30.0]}, {}, incomplete=["borrowings"])
    balance, _ = balance_year(short, False)
    assert balance["borrowings"] is None and balance["net_debt"] is None
    assert balance["debt_to_equity"] is None and balance["roce_pct"] is None


def test_lenders_get_equity_and_assets_only() -> None:
    values = {"total_assets": 100.0, "total_equity_liabilities": 100.0, "equity": 12.0}
    balance, failures = balance_year(Year("FY26", values, {"borrowings": [70.0]}, {}), True)
    assert failures == [] and balance == {"equity": 12.0, "total_assets": 100.0}


def test_total_equity_printed_as_a_bare_sum() -> None:
    # Asian Paints: owners' equity, non-controlling interests, then their sum unlabelled.
    ex = read_by_code("ASIANPAINT_FY26", [233], [234, 236])
    assert summed(ex, "equity") == (22014.98, 20059.05)
    assert summed(ex, "borrowings") == (round(1247.17 + 1046.09, 2), round(259.62 + 604.13, 2))
    assert not ex.incomplete


def test_unbilled_receivables_under_their_heading_are_counted() -> None:
    # TCS: "Trade receivables" is a heading over "Billed" and "Unbilled".
    ex = read_by_code("TCS_FY26", [167], [168, 173, 174])
    rows = [ln.label for ln in ex.lines if ln.key == "receivables"]
    assert sorted(rows) == [
        "Trade receivables billed",
        "Trade receivables billed",
        "Unbilled",
        "Unbilled",
    ]
    assert "borrowings" in ex.absent


def test_the_line_after_trade_receivables_is_not_its_sub_line() -> None:
    # Tata Power: "Unbilled revenue" is its own line, after a trade receivables row that
    # carries figures. Each PDF page is a spread holding parts of two statements.
    ex = read_by_code("TATAPOWER_FY26", [245, 246], [246, 247, 248])
    assert {ln.label for ln in ex.lines if ln.key == "receivables"} == {"Trade receivables"}
    assert summed(ex, "receivables")[0] == round(1599.35 + 4423.96, 2)
    assert summed(ex, "payables")[0] == round(809.84 + 6328.39, 2)
    assert summed(ex, "borrowings")[0] == round(61608.57 + 9513.82, 2)
    assert not ex.incomplete


def test_a_heading_with_only_its_note_number_is_not_a_row() -> None:
    # Dixon, in lakh: "iii. Trade payables 34" (note 34), then its two parts.
    ex = read_by_code("DIXON_FY26", [418], [419, 420, 421])
    assert summed(ex, "payables") == (round(166.43 + 10555.75, 2), round(78.30 + 10805.35, 2))
    assert "payables" not in ex.incomplete.get("current", [])
    # Eternal: the parts are bulleted with a control character in the PDF text.
    ex = read_by_code("ETERNAL_FY26", [201, 202], [203, 204, 209, 210])
    assert summed(ex, "payables") == (232 + 2778, 75 + 1461)
    assert ex.absent == ["borrowings"]
