from __future__ import annotations

import copy

import pytest
from annual_helpers import page_map, recorded, recorded_llm

from finn.pull.statements import (
    Extracted,
    Line,
    Year,
    against_quarters,
    cash_table,
    extract_statements,
    matched_row,
    missing_lines,
    row_after,
    verify_lines,
    year_failures,
)
from finn.push.results_math import StatementLines

STATEMENT_PAGES = (288, 289, 295, 296)


def infy_pages() -> dict[int, str]:
    pages = page_map("INFY_FY26")
    return {n: pages[n] for n in STATEMENT_PAGES}


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
    ex = verify_lines(recorded("statements"), infy_pages())
    assert ex.unit == "crore" and not ex.dropped and not ex.incomplete
    got = {ln.key: (ln.current, ln.prior) for ln in ex.lines if ln.key != "dividends"}
    assert got["revenue"] == (178650.0, 162990.0)
    assert got["pat"] == (29474.0, 26750.0)
    assert got["cfo"] == (33986.0, 35694.0)
    assert got["cfi"] == (1946.0, -1946.0)
    assert got["net_change"] == (-3854.0, 9587.0)
    assert got["capex"] == (-2727.0, -2237.0)


def test_a_figure_not_in_its_row_is_dropped() -> None:
    data = copy.deepcopy(recorded("statements"))
    for line in data["lines"]:
        if line["key"] == "cfo":
            line["current"] = "34,986"  # one digit off
    ex = verify_lines(data, infy_pages())
    assert "cfo" not in {ln.key for ln in ex.lines}
    assert any(d.startswith("cfo:") for d in ex.dropped)


def test_a_summed_line_left_out_withholds_the_sum() -> None:
    data = copy.deepcopy(recorded("statements"))
    data["lines"] = [ln for ln in data["lines"] if ln["key"] != "buyback"]
    ex = verify_lines(data, infy_pages())
    assert ex.incomplete == {"current": ["buyback"]}
    table = cash_table([("FY26", ex, 1)], {}, lender=False)
    fy26 = table["years"][0]
    assert fy26["buyback"] is None and fy26["payout"] is None
    assert fy26["withheld"] == ["buyback"]


def test_buyback_escrow_rows_are_not_buyback_payments() -> None:
    pages = page_map("TCS_FY25")
    lines = [
        Line("buyback", "Buy-back of equity shares", 186, None, -17000.0),
        Line("buyback", "Tax on buy-back of equity shares", 186, None, -3959.0),
        Line("buyback", "Expenses for buy-back of equity shares", 186, None, -46.0),
    ]
    assert "buyback" not in missing_lines(lines, pages, 1.0).get("prior", [])
    assert "buyback" in missing_lines(lines[:1], pages, 1.0).get("prior", [])


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
    ex = verify_lines(recorded("statements"), infy_pages())
    t = cash_table([("FY26", ex, 9)], {}, lender=False)
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
    ex, model = extract_statements(llm, infy_pages(), "Infosys Limited", "FY26", "consolidated")
    assert len(ex.lines) == len(recorded("statements")["lines"])
    assert transport.tasks == ["statements"]


def test_a_weak_answer_is_asked_again_of_the_stronger_model() -> None:
    weak = {"lines": recorded("statements")["lines"][:2]}
    llm, transport = recorded_llm({"statements": weak})
    extract_statements(llm, infy_pages(), "Infosys Limited", "FY26", "consolidated")
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
