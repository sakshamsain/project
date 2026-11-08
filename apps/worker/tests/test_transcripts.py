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
