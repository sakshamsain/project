from finn.pull.quotes import find_quote, normalize, verify_quote

PAGE = (
    "Moderator: Thank you. Next question.\n"
    "CFO: For FY27 we continue to expect revenue growth in the range of 12% to 14%,\n"
    "and EBITDA margins of around 18% to 19%. On capex, we will spend approxi-\n"
    "mately ₹ 1,200 crore this year, largely on the new plant.\n"
)


def test_exact_quote_is_found() -> None:
    assert find_quote("revenue growth in the range of 12% to 14%", PAGE) is not None


def test_line_breaks_and_hyphenation_are_tolerated() -> None:
    assert find_quote("we will spend approximately Rs 1,200 crore this year", PAGE) is not None


def test_curly_quotes_and_case_are_tolerated() -> None:
    assert normalize("“EBITDA Margins”") == '"ebitda margins"'


def test_paraphrase_is_rejected() -> None:
    assert find_quote("revenue will grow 12-14% in FY27", PAGE) is None


def test_ellipsis_fragments_must_appear_in_order() -> None:
    assert (
        find_quote("we continue to expect revenue growth ... margins of around 18%", PAGE)
        is not None
    )
    assert (
        find_quote("margins of around 18% ... we continue to expect revenue growth", PAGE) is None
    )


def test_verify_reports_the_page_and_spans_page_breaks() -> None:
    pages = [
        "Opening remarks only.",
        "CFO: we expect revenue growth in",
        "the range of 12% to 14%.",
    ]
    match = verify_quote("revenue growth in the range of 12% to 14%", pages)
    assert match.found and match.page_index == 1
    assert not verify_quote("a promise nobody made", pages).found
