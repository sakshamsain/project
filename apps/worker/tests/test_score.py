from finn.push.score import FRONT_THRESHOLD, EventFeatures, assign_tiers, score


def test_auditor_resignation_never_folds() -> None:
    f = EventFeatures("management_change", {"role": "auditor", "action": "resign"})
    b = score(f, user_weight=0.0)  # even if the user muted the category
    assert b.floor_applied
    assert b.score >= FRONT_THRESHOLD


def test_rating_reaffirmation_folds() -> None:
    b = score(EventFeatures("credit_rating", {"direction": "reaffirm"}))
    [ranked] = assign_tiers([("r1", b)])
    assert ranked.tier == "folded"


def test_results_with_big_reaction_outrank_dividend() -> None:
    results = score(EventFeatures("results", abnormal_return_pct=-6.0, volume_z=4.0))
    dividend = score(EventFeatures("dividend"))
    assert results.score > dividend.score


def test_results_intimation_is_not_front_page() -> None:
    b = score(EventFeatures("results", {"stage": "intimation"}))
    assert b.score < FRONT_THRESHOLD


def test_deal_size_relative_to_market_cap_raises_score() -> None:
    small = score(EventFeatures("M&A", size_ratio=0.001))
    large = score(EventFeatures("M&A", size_ratio=0.08))
    assert large.score > small.score
    assert large.size == 1.0


def test_front_page_is_capped_and_floors_become_one_liners() -> None:
    items = [
        (f"res{i}", score(EventFeatures("results", abnormal_return_pct=6.0))) for i in range(6)
    ]
    cfo = score(EventFeatures("management_change", {"role": "cfo", "action": "resign"}))
    items.append(("cfo", cfo))
    ranked = {r.key: r.tier for r in assign_tiers(items)}
    assert sum(1 for t in ranked.values() if t == "front") == 5
    assert ranked["cfo"] in {"front", "oneliner"}


def test_follow_up_filings_score_lower_than_first() -> None:
    first = score(EventFeatures("capex", is_first_filing=True))
    follow = score(EventFeatures("capex", is_first_filing=False))
    restated = score(EventFeatures("capex", is_restatement=True))
    assert first.score > follow.score > restated.score
