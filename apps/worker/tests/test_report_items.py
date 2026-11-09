from __future__ import annotations

from annual_helpers import page_map, recorded_llm

from finn.pull.report_items import (
    auditor_opinion,
    brsr_boundary,
    cited,
    drawn_attention,
    figure_near,
    pages_for,
    read_auditor,
    read_business,
    read_risks,
)

INFY = page_map("INFY_FY26")
DIXON = page_map("DIXON_FY26")


def test_opinion_is_read_from_the_headings() -> None:
    op = auditor_opinion(pages_for(INFY, range(277, 284)))
    assert op["kind"] == "unmodified" and op["page"] == 277
    assert op["emphasis_pages"] == [] and op["going_concern_pages"] == []
    qualified = {5: "Basis for Qualified Opinion\nWe conducted our audit ..."}
    assert auditor_opinion(qualified)["kind"] == "qualified"
    assert auditor_opinion({5: "Basis for Disclaimer of Opinion"})["kind"] == "disclaimer"


def test_emphasis_of_matter_is_cut_from_the_text_by_code() -> None:
    drawn = drawn_attention(pages_for(DIXON, range(409, 416)))
    assert len(drawn) == 1 and drawn[0]["kind"] == "emphasis" and drawn[0]["page"] == 409
    assert drawn[0]["quote"].startswith("We draw attention to Note 59 (a)")
    assert "production linked incentive" in drawn[0]["quote"].lower()
    assert drawn_attention(pages_for(INFY, range(277, 284))) == []


def test_only_quotes_on_the_pages_are_kept() -> None:
    pages = pages_for(INFY, [76, 77])
    real = "We operate in an environment marked by intense competition in traditional services"
    kept = cited(
        [
            {"title": "Competition", "quote": real, "page": 3},  # wrong page: fixed from text
            {"title": "Made up", "quote": "Our margins will collapse next year.", "page": 76},
            {"title": "Competition", "quote": real, "page": 76},  # a repeat
        ],
        pages,
    )
    assert [c.page for c in kept.items] == [76] and kept.dropped == 2


def test_a_share_must_be_the_first_figure_after_its_name() -> None:
    text = "Software and IT consulting (GICS) long description here 95.23 Products 620 and 631"
    assert figure_near("95.23", text, "Software and IT consulting", 400, first=True) == 95.23
    assert figure_near("620", text, "Software and IT consulting", 400, first=True) is None
    # Dixon prints shares before names: "36% home appliances & engineering 2% mobile phones"
    row = "lighting (until 31st july) 36% home appliances & engineering 2% mobile phones"
    assert figure_near("36", row, "home appliances & engineering", 300, first=True) is None


def test_brsr_boundary() -> None:
    assert brsr_boundary(pages_for(INFY, range(142, 146))) in ("consolidated", "standalone")
    assert brsr_boundary({1: "13. Reporting boundary : standalone basis"}) == "standalone"
    assert brsr_boundary({1: "nothing here"}) is None


def test_recorded_auditor_business_and_risks_verify() -> None:
    llm, _ = recorded_llm()
    auditor, _m = read_auditor(llm, pages_for(INFY, range(277, 284)), "Infosys Limited")
    assert auditor["kind"] == "unmodified"
    assert auditor["firm"] and "deloitte" in auditor["firm"].lower()
    assert auditor["matters"] and all(m["page"] in range(277, 284) for m in auditor["matters"])

    business, _m = read_business(llm, pages_for(INFY, range(142, 146)), "Infosys Limited")
    assert business["activities"][0]["share"] == 95.23
    assert business["exports"] == {"value": 97.4, "page": 143}
    assert business["countries"] == {"value": 84.0, "page": 143}

    risks, _m = read_risks(llm, pages_for(INFY, [76, 77, 82, 83, 84, 87]), "Infosys Limited")
    assert 1 <= len(risks["risks"]) <= 6
    assert all(r["page"] in (76, 77, 82, 83, 84, 87) for r in risks["risks"])


def test_a_fabricated_figure_is_not_kept() -> None:
    llm, _ = recorded_llm(
        {
            "business": {
                "activities": [
                    {"name": "Software and IT consulting", "share": "99.9", "page": 143}
                ],
                "exports": {"figure": "88.8%", "page": 143},
            }
        }
    )
    business, _m = read_business(llm, pages_for(INFY, range(142, 146)), "Infosys Limited")
    assert business["activities"][0]["share"] is None
    assert business["exports"] is None
