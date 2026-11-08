from finn.llm.style_lint import lint


def rules(text: str, kind: str = "body") -> set[str]:
    return {v.rule for v in lint(text, kind)}  # type: ignore[arg-type]


def test_clean_one_liner_passes() -> None:
    assert lint("Revenue +14% YoY to ₹4,210 Cr; EBITDA margin down 120 bps.", "oneliner") == []


def test_adjective_needs_a_figure_in_the_same_sentence() -> None:
    assert "adjective_without_figure" in rules("A strong quarter for the company.")
    assert "adjective_without_figure" not in rules("Strong quarter: revenue +14% YoY.")


def test_banned_phrases_and_advice() -> None:
    assert "banned_phrase" in rules("Poised for growth amid a changing landscape, up 3%.")
    assert "advice_language" in rules("Investors should buy on dips at ₹500.")


def test_buyback_and_sell_side_are_not_advice() -> None:
    assert "advice_language" not in rules("Board approves a ₹500 Cr buyback; sell-side views vary.")


def test_length_limits() -> None:
    assert "too_long" in rules("x" * 120 + " 5%", "oneliner")
    assert "too_long" in rules("y" * 80, "headline")


def test_one_liner_must_carry_a_number() -> None:
    assert "no_figure" in rules("Management commentary was upbeat.", "oneliner")
