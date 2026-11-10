from datetime import date, datetime

from finn.pull.transcripts import call_rank, discussed_quarter, transcript_refs
from finn.sources.nse import IST, Announcement


def ann(
    text: str, day: str, url: str = "https://nsearchives.nseindia.com/corporate/x.pdf"
) -> Announcement:
    return Announcement(
        exchange_id=day + text[:5],
        symbol="INFY",
        reported_isin=None,
        company_name="Infosys Limited",
        subject="Analysts/Institutional Investor Meet/Con. Call Updates",
        text=text,
        summary=None,
        attachment_url=url,
        filed_at=datetime.fromisoformat(day + "T18:00:00").replace(tzinfo=IST),
        industry=None,
        has_xbrl=False,
    )


def test_quarter_discussed_by_a_call() -> None:
    assert discussed_quarter(date(2026, 10, 28)) == "Q2FY27"
    assert discussed_quarter(date(2026, 4, 20)) == "Q4FY26"
    assert discussed_quarter(date(2026, 1, 16)) == "Q3FY26"


def test_earnings_calls_beat_agm_and_investor_days() -> None:
    call = ann(
        "Infosys has informed the Exchange about transcript of the earnings call", "2026-04-20"
    )
    agm = ann("Transcript of the 45th Annual General Meeting", "2026-06-30")
    ai_day = ann("Transcript of AI Day held on February 17, 2026", "2026-02-24")
    audio = ann("Audio recording of the earnings call", "2026-04-18")
    assert call_rank(call) == 2
    assert call_rank(agm) == call_rank(ai_day) == call_rank(audio) == 0
    refs = transcript_refs([call, agm, ai_day, audio])
    assert [(r.period, r.filed_at_date) for r in refs] == [("Q4FY26", date(2026, 4, 20))]


def test_one_transcript_per_quarter_newest_first() -> None:
    q2 = ann("Transcript of earnings call", "2026-10-28", "https://nsearchives.nseindia.com/a.pdf")
    q2_fix = ann(
        "Revised transcript of earnings call",
        "2026-10-30",
        "https://nsearchives.nseindia.com/b.pdf",
    )
    q1 = ann("Transcript of earnings call", "2026-07-28", "https://nsearchives.nseindia.com/c.pdf")
    refs = transcript_refs([q1, q2, q2_fix])
    assert [r.url.rsplit("/", 1)[-1] for r in refs] == ["b.pdf", "c.pdf"]


def _fixture_pages(name: str) -> list[str]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "fixtures" / "nse" / "transcripts" / name
    return list(json.loads(path.read_text())["pages"])


def test_a_letter_that_links_to_the_transcript_yields_the_link() -> None:
    from finn.pull.transcripts import linked_transcript_url

    pages = _fixture_pages("GLENMARK_cover_letter.json")
    assert linked_transcript_url(pages) == (
        "https://glenmark.b-cdn.net/gpl_pdfs/Financials/Quarterly/Glenmark-Earnings-Nov06-2026.pdf"
    )


def test_a_real_transcript_is_not_a_cover_letter() -> None:
    from finn.pull.transcripts import linked_transcript_url

    call = [
        "Transcript of the Q2 FY27 earnings call. Visit https://www.infosys.com/investors.html",
        "Moderator: Good evening ...",
        "Salil Parekh: Our operating margin guidance remains at 20% to 22% ...",
    ]
    assert linked_transcript_url(call) is None
    assert linked_transcript_url([]) is None


def test_wrapped_links_are_rejoined_and_exchange_links_ignored() -> None:
    from finn.pull.transcripts import linked_transcript_url

    letter = [
        "Sub: Transcript of the Earnings Call\n"
        "Copy filed with https://www.nseindia.com and https://www.bseindia.com.\n"
        "The transcript is available at https://www.example-co.in/investors/\n"
        "Q2FY27_Call_Transcript.pdf.\n"
    ]
    assert linked_transcript_url(letter) == (
        "https://www.example-co.in/investors/Q2FY27_Call_Transcript.pdf"
    )
    no_hyphen = ["Transcript of earnings call at https://x.example.com/files/Q2\nCall.pdf\n"]
    assert linked_transcript_url(no_hyphen) == "https://x.example.com/files/Q2Call.pdf"


def test_a_letter_without_a_pdf_link_needs_transcript_wording_near_the_link() -> None:
    from finn.pull.transcripts import linked_transcript_url

    page_link = [
        "The transcript of the earnings call is uploaded at https://co.example.com/investor-relations"
    ]
    assert linked_transcript_url(page_link) == "https://co.example.com/investor-relations"
    unrelated = ["Transcript to follow.\n" + "x " * 300 + "\nW: https://www.co.example.com"]
    assert linked_transcript_url(unrelated) is None
