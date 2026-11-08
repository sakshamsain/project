import pytest

from finn.push.results_math import (
    StatementLines,
    build_card,
    consistency_failures,
    ebitda_excl_other_income,
    pct_change,
    to_crore,
)


def lines(
    rev: float,
    pbe: float,
    pat: float,
    *,
    other: float = 20.0,
    fin: float = 10.0,
    dep: float = 30.0,
    exc: float = 0.0,
    tax_rate: float = 0.25,
) -> StatementLines:
    pbt = pbe + exc
    tax = round(pbt * tax_rate, 4)
    return StatementLines(
        revenue_from_operations=rev,
        other_income=other,
        finance_costs=fin,
        depreciation=dep,
        profit_before_exceptional_and_tax=pbe,
        exceptional_items=exc,
        profit_before_tax=pbt,
        tax_expense=tax,
        profit_after_tax=pat if pat is not None else pbt - tax,
    )


def test_ebitda_adds_back_finance_and_depreciation_and_strips_other_income() -> None:
    s = lines(1000.0, 200.0, 150.0)
    assert ebitda_excl_other_income(s) == 200.0 + 10.0 + 30.0 - 20.0


def test_units_convert_to_crore() -> None:
    assert to_crore(12_345.0, "lakhs") == pytest.approx(123.45)
    assert to_crore(4_210.0, "million") == pytest.approx(421.0)
    with pytest.raises(ValueError):
        to_crore(1.0, "furlongs")


def test_pct_change_handles_losses_and_zero_base() -> None:
    assert pct_change(110.0, 100.0) == pytest.approx(10.0)
    assert pct_change(-50.0, -100.0) == pytest.approx(50.0)  # loss halved reads as +50%
    assert pct_change(10.0, 0.0) is None


def test_card_has_qoq_yoy_and_margin_bps() -> None:
    cur = lines(1100.0, 220.0, 165.0)
    prev_q = lines(1000.0, 200.0, 150.0)
    prev_y = lines(1000.0, 180.0, 135.0)
    card = build_card(cur, prev_q, prev_y)
    revenue = card.rows[0]
    assert (revenue.qoq_pct, revenue.yoy_pct) == (10.0, 10.0)
    assert [r.name for r in card.rows] == ["Revenue", "EBITDA (excl. other income)", "PBT", "PAT"]
    # EBITDA margin: 240/1100 = 21.82% now, 220/1000 = 22.0% last quarter -> -18.2 bps
    assert card.margin_qoq_bps == pytest.approx(-18.2, abs=0.1)


def test_card_flags_one_offs_and_turnarounds() -> None:
    cur = lines(1000.0, 100.0, 120.0, exc=60.0)
    prev = lines(900.0, -40.0, -30.0)
    card = build_card(cur, prev, None)
    assert any("one-off gain" in f for f in card.flags)
    assert "Back to profit QoQ" in card.flags


def test_bank_card_uses_ppop() -> None:
    s = StatementLines(
        revenue_from_operations=5000.0,
        other_income=300.0,
        finance_costs=0.0,
        depreciation=0.0,
        profit_before_exceptional_and_tax=1200.0,
        exceptional_items=0.0,
        profit_before_tax=1200.0,
        tax_expense=300.0,
        profit_after_tax=900.0,
        net_interest_income=2100.0,
        operating_profit_before_provisions=1600.0,
    )
    card = build_card(s, None, None, bank_like=True)
    assert card.rows[1].name == "PPOP"
    assert card.rows[1].value == 1600.0


def test_clean_statement_passes_checks() -> None:
    s = lines(1000.0, 200.0, None)  # type: ignore[arg-type]
    assert consistency_failures(s) == []


def test_mistyped_pat_is_caught() -> None:
    s = lines(1000.0, 200.0, 1500.0)  # PAT larger than PBT: an extraction slip
    assert "pat_does_not_reconcile" in consistency_failures(s)
