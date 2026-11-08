from datetime import datetime, timedelta

from finn.push.events import EventDraft, FilingFacts, assign, build, family, window
from finn.sources.nse import IST

T0 = datetime(2026, 11, 7, 17, 0, tzinfo=IST)


def f(
    key: str,
    category: str,
    hours: float = 0.0,
    isin: str = "INE245A01021",
    **attrs: str,
) -> FilingFacts:
    return FilingFacts(
        key=key,
        isin=isin,
        filed_at=T0 + timedelta(hours=hours),
        subject=category,
        text=f"X has informed the Exchange regarding {key}",
        summary=None,
        category=category,
        attributes=attrs,
    )


def test_families() -> None:
    assert family("results", {"stage": "intimation"}) == "results_intimation"
    assert family("results", {"stage": "filing"}) == "results"
    assert family("unclassified", {"kind": "trading_window"}) == "unclassified:trading_window"
    assert family("press_release", {}) == "press_release:general"
    assert window("press_release:order_win") == timedelta(0)


def test_three_director_exits_on_one_day_are_one_event() -> None:
    drafts = assign(
        [
            f("a", "management_change", 0, role="independent_director", action="resign"),
            f("b", "management_change", 0, role="independent_director", action="resign"),
            f("c", "management_change", 0.1, role="independent_director", action="resign"),
        ],
        [],
    )
    assert len(drafts) == 1 and len(drafts[0].members) == 3
    assert drafts[0].cluster_key == "a"


def test_results_filing_and_presentation_join_but_intimation_does_not() -> None:
    drafts = assign(
        [
            f("intim", "results", -24 * 7, stage="intimation"),
            f("res", "results", 0, stage="filing"),
            f("pres", "results", 2, stage="presentation"),
            f("ad", "results", 30, stage="newspaper_ad"),
        ],
        [],
    )
    by_key = {d.cluster_key: d for d in drafts}
    assert set(by_key) == {"intim", "res"}
    assert {m.key for m in by_key["res"].members} == {"res", "pres", "ad"}
    assert by_key["res"].representative.key == "res"  # the filing outweighs the ad


def test_press_releases_never_cluster() -> None:
    drafts = assign([f("p1", "press_release", 0), f("p2", "press_release", 0.5)], [])
    assert len(drafts) == 2


def test_different_companies_never_cluster() -> None:
    drafts = assign(
        [f("a", "credit_rating", 0), f("b", "credit_rating", 0, isin="INE040A01034")], []
    )
    assert len(drafts) == 2


def test_new_filing_joins_an_open_event_from_the_database() -> None:
    open_event = EventDraft(
        "old", "INE245A01021", "credit_rating", [f("old", "credit_rating", -5)], 41
    )
    drafts = assign([f("new", "credit_rating", 0)], [open_event])
    assert len(drafts) == 1 and drafts[0].event_id == 41
    assert [m.key for m in drafts[0].members] == ["old", "new"]


def test_outside_the_window_starts_a_new_event() -> None:
    open_event = EventDraft(
        "old", "INE245A01021", "credit_rating", [f("old", "credit_rating", -60)], 41
    )
    drafts = assign([f("new", "credit_rating", 0)], [open_event])
    assert [d.cluster_key for d in drafts] == ["new"]


def test_build_scores_results_front_and_a_repeat_meeting_lower() -> None:
    res = assign([f("res", "results", 0, stage="filing")], [])[0]
    row = build(res)
    assert row.tier == "front" and row.breakdown["is_first_filing"] is True
    meet = assign([f("m", "investor_meetings", 0)], [])[0]
    first, repeat = build(meet), build(meet, [T0 - timedelta(days=10)])
    assert repeat.score < first.score and repeat.breakdown["is_first_filing"] is False
    assert first.tier == "folded"


def test_cfo_resignation_is_a_floor_event() -> None:
    d = assign([f("cfo", "management_change", 0, role="cfo", action="resign")], [])[0]
    row = build(d)
    assert row.tier == "front" and row.breakdown["floor_applied"] is True


def test_reaction_raises_the_score() -> None:
    d = assign([f("lit", "litigation", 0)], [])[0]
    calm = build(d)
    d.reaction = {"abnormal_return_pct": -6.2, "volume_z": 4.0}
    moved = build(d)
    assert moved.score > calm.score and moved.breakdown["reaction"] == 1.0


def test_restatement_loses_novelty() -> None:
    d = assign([f("rev", "results", 0, stage="filing")], [])[0]
    d.members[0] = FilingFacts(**{**_asdict(d.members[0]), "subject": "Revised results"})
    assert build(d).breakdown["novelty"] == 0.0


def _asdict(x: FilingFacts) -> dict[str, object]:
    return {k: getattr(x, k) for k in FilingFacts.__slots__}


def test_contributions_add_up_to_the_score_without_a_floor() -> None:
    d = assign([f("lit", "litigation", 0)], [])[0]
    d.reaction = {"abnormal_return_pct": -3.0, "volume_z": 1.0}
    row = build(d)
    c = row.breakdown["contributions"]
    assert row.breakdown["floor_applied"] is False
    assert abs(sum(c.values()) - row.score) < 1e-3


def test_results_event_takes_the_release_title_as_headline() -> None:
    filing = f("res", "results", 0, stage="filing")
    release = FilingFacts(
        key="pr",
        isin="INE245A01021",
        filed_at=T0 + timedelta(minutes=20),
        subject="Press Release",
        text="X has informed the Exchange regarding a press release dated November 06, 2026, "
        'titled "Tata Steel reports Consolidated EBITDA of Rs 10,665 crores for the quarter".',
        summary=None,
        category="results",
        attributes={"stage": "press_release"},
    )
    d = assign([filing, release], [])
    assert len(d) == 1
    row = build(d[0])
    assert row.headline.startswith("Tata Steel reports Consolidated EBITDA")
    assert row.breakdown["representative"] == "res"
