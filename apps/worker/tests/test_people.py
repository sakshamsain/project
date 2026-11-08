import json
from pathlib import Path

from finn.push.people import card_json, merge_cards, verify_people
from finn.sources.pdf import pdf_text

FIX = Path(__file__).resolve().parents[3] / "fixtures"
MUTHOOT_PDF = FIX / "nse" / "pdf" / "MUTHOOTFIN_01102026181341_Appointment_of_Directors_SD.pdf"


def _muthoot() -> tuple[list[str], dict[str, object]]:
    pages = pdf_text(MUTHOOT_PDF.read_bytes()).pages
    return pages, json.loads((FIX / "llm" / "people_MUTHOOTFIN.json").read_text())


def test_pdf_pages_have_text() -> None:
    t = pdf_text(MUTHOOT_PDF.read_bytes())
    assert len(t.pages) == 5 and not t.scanned
    assert "[[page 4]]" in t.numbered()


def test_recorded_answer_keeps_every_real_sentence_with_its_page() -> None:
    pages, raw = _muthoot()
    x = verify_people(raw, pages, "Muthoot Finance", "recorded")
    names = [p.name for p in x.people]
    assert names == ["Eapen Alexander", "Alexander George", "George Alexander Muthoot"]
    md = x.people[1]
    assert md.role == "Managing Director" and md.change == "appointed"
    assert all(q.page == 4 for q in md.background)
    assert x.dropped_quotes == 0
    assert md.linkedin_search and "Alexander+George" in md.linkedin_search


def test_invented_sentences_and_people_are_dropped() -> None:
    pages, raw = _muthoot()
    forged = json.loads(json.dumps(raw))
    forged["people"][0]["background"].insert(
        0, {"quote": "He previously ran a large Mumbai bank for twenty years.", "page": 3}
    )
    forged["people"].append({"name": "Jane Invented", "role": "CFO", "change": "appointed"})
    x = verify_people(forged, pages, "Muthoot Finance", "recorded")
    assert x.dropped_quotes == 1 and x.dropped_people == 1
    assert "Jane Invented" not in [p.name for p in x.people]


def test_quote_page_comes_from_the_text_not_the_model() -> None:
    pages, raw = _muthoot()
    wrong = json.loads(json.dumps(raw))
    for b in wrong["people"][1]["background"]:
        b["page"] = 1
    x = verify_people(wrong, pages, "Muthoot Finance", "recorded")
    assert all(q.page == 4 for q in x.people[1].background)


def test_cards_merge_by_name() -> None:
    pages = json.loads(
        (FIX / "nse" / "pdf" / "AGL_02102026_change_in_directors.pages.json").read_text()
    )
    raw = json.loads((FIX / "llm" / "people_AGL.json").read_text())
    card = card_json(verify_people(raw, pages, "Allcargo Global", "recorded"), "https://x/a.pdf")
    merged = merge_cards([card, card])
    assert merged["status"] == "ok"
    assert len(merged["people"]) == len(card["people"]) == 2


def test_zipped_pdf_is_unwrapped_and_other_files_refused() -> None:
    import io
    import zipfile

    import pytest

    from finn.sources.pdf import NotAPdf, unwrap

    raw = MUTHOOT_PDF.read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("filing.pdf", raw)
    assert unwrap(buf.getvalue()) == raw
    with pytest.raises(NotAPdf):
        unwrap(b"<html>not found</html>")
