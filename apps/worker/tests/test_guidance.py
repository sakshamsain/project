from datetime import date

from finn.pull.guidance import figure_is_stated, resolve_metric, resolve_scope, verify_items

PAGES = [
    "Opening remarks. Revenue grew well this quarter.",
    "Our FY27 growth guidance is now 2.5% to 4%, and our EBIT margin guidance remains at "
    "17.5% to 18.5%. We feel that without the Vivo also, the company will keep growing at "
    "almost 15% to 17%. We are confident of delivering 25 to 40 basis points improvement "
    "for FY '27 in opex to NTI.",
]


def item(quote: str, **kw: object) -> dict[str, object]:
    base = {
        "metric": "x",
        "metric_key": "revenue_growth",
        "kind": "growth",
        "basis": "inr",
        "scope": "company",
        "unit": "%",
        "period": "FY27",
        "quote": quote,
        "page": 9,
    }
    return {**base, **kw}


def test_metric_must_be_named_in_the_quote() -> None:
    assert resolve_metric("ebitda_margin", "our EBIT margin guidance remains") == "ebit_margin"
    assert resolve_metric("ebit_margin", "EBITDA margin of 20%") == "ebitda_margin"
    assert resolve_metric("ebitda_margin", "25 to 40 bps improvement in opex to NTI") == "other"
    assert resolve_metric("revenue_growth", "top line growth will be 22%") == "revenue_growth"
    assert resolve_metric("pat_growth", "AUM growth of 25%") == "other"
    assert resolve_metric("capex", "capex of 500 crore") == "capex"


def test_exclusions_make_a_figure_adjusted() -> None:
    assert resolve_scope("company", "without the Vivo also, we grow 15%") == "adjusted"
    assert resolve_scope("segment", "excluding exports, the lighting segment") == "segment"
    assert resolve_scope("company", "we grow 15%") == "company"


def test_figures_must_appear_in_the_quote() -> None:
    assert figure_is_stated(17.5, "between 17.5 and 18.5")
    assert not figure_is_stated(10, "low double digits")


def test_verification_fixes_metric_scope_and_page() -> None:
    v = verify_items(
        {
            "items": [
                item(
                    "our EBIT margin guidance remains at 17.5% to 18.5%",
                    metric_key="ebitda_margin",
                    kind="margin",
                    value_low=17.5,
                    value_high=18.5,
                ),
                item(
                    "without the Vivo also, the company will keep growing at almost 15% to 17%",
                    value_low=15,
                    value_high=17,
                ),
                item(
                    "25 to 40 basis points improvement for FY '27 in opex to NTI",
                    metric_key="ebitda_margin",
                    kind="margin",
                    unit="bps",
                    value_low=25,
                    value_high=40,
                ),
                item("We will double revenue by FY27 on a page that does not exist", value_low=2),
                item("Our FY27 growth guidance is now 2.5% to 4%", value_low=10, value_high=12),
            ]
        },
        PAGES,
        date(2026, 10, 15),
    )
    by_quote = {i.quote[:20]: i for i in v.items}
    ebit = by_quote["our EBIT margin guid"]
    assert ebit.metric_key == "ebit_margin" and ebit.page == 2
    assert by_quote["without the Vivo als"].scope == "adjusted"
    assert by_quote["25 to 40 basis point"].metric_key == "other"
    wrong_figures = by_quote["Our FY27 growth guid"]
    assert wrong_figures.value_low is None and wrong_figures.kind == "qualitative"
    assert v.dropped_quotes == 1 and v.dropped_figures == 1
    assert all(i.period and i.period.label == "FY27" for i in v.items)
