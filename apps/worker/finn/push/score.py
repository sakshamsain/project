"""Materiality score and tiers.

    S = w_u(c, k) * B(c, a) + ALPHA * size + BETA * reaction + GAMMA * novelty

Every component is kept in the breakdown so the app can answer "why is this here?".
Base weights are hand-set for v0 and meant to be recalibrated on observed price
reactions per category (plan item S7).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

BASE_WEIGHTS: Mapping[str, float] = {
    "results": 0.80,
    "M&A": 0.75,
    "management_change": 0.60,
    "fund_raise": 0.65,
    "pledging": 0.60,
    "litigation": 0.55,
    "capex": 0.55,
    "credit_rating": 0.45,
    "insider_trading": 0.40,
    "bonus_split": 0.30,
    "press_release": 0.30,
    "dividend": 0.25,
    "earnings_call": 0.15,
    "investor_meetings": 0.10,
    "agm_egm": 0.10,
    "postal_ballot": 0.10,
    "unclassified": 0.02,
}

ALPHA, BETA, GAMMA = 0.25, 0.20, 0.10
FRONT_THRESHOLD = 0.75
ONELINER_THRESHOLD = 0.35
FRONT_CAP = 5


@dataclass(frozen=True, slots=True)
class EventFeatures:
    category: str
    attributes: Mapping[str, str] = field(default_factory=dict)
    size_ratio: float | None = None  # amount / market cap, pledge change / 10 pp, notches / 3
    abnormal_return_pct: float | None = None
    volume_z: float | None = None
    is_first_filing: bool = True
    is_restatement: bool = False


@dataclass(frozen=True, slots=True)
class Breakdown:
    base: float
    user_weight: float
    size: float
    reaction: float
    novelty: float
    floor_applied: bool
    score: float


def base_weight(category: str, attributes: Mapping[str, str]) -> float:
    """Category weight, adjusted by the attributes that change what a filing means."""
    w = BASE_WEIGHTS.get(category, BASE_WEIGHTS["unclassified"])
    role, action = attributes.get("role"), attributes.get("action")
    if category == "management_change":
        if role in {"ceo", "cfo", "md", "chairman", "auditor"}:
            w = 0.85
        elif role == "independent_director" and action == "retire":
            w = 0.20
    if category == "credit_rating":
        w = {"downgrade": 0.80, "upgrade": 0.50, "reaffirm": 0.08}.get(
            attributes.get("direction", ""), w
        )
    if category == "results":
        stage_weights = {"intimation": 0.10, "newspaper_ad": 0.0, "presentation": 0.25}
        w = stage_weights.get(attributes.get("stage", ""), w)
    if category == "press_release":
        kind_weights = {"order_win": 0.45, "disruption": 0.65, "clarification": 0.30}
        w = kind_weights.get(attributes.get("kind", ""), w)
    return w


def is_floor_event(f: EventFeatures) -> bool:
    """Events that may never fold, whatever their computed score."""
    a = f.attributes
    if f.category == "management_change" and a.get("action") == "resign":
        return a.get("role") in {"ceo", "cfo", "md", "auditor"}
    if f.category == "credit_rating" and a.get("direction") == "downgrade":
        return True
    return f.category == "pledging" and a.get("direction") == "increase"


def score(f: EventFeatures, user_weight: float = 1.0) -> Breakdown:
    base = base_weight(f.category, f.attributes)
    size = min(1.0, max(0.0, (f.size_ratio or 0.0) / 0.05))  # 5% of market cap saturates
    reaction = 0.0
    if f.abnormal_return_pct is not None:
        reaction = max(reaction, min(1.0, abs(f.abnormal_return_pct) / 5.0))
    if f.volume_z is not None:
        reaction = max(reaction, min(1.0, abs(f.volume_z) / 3.0))
    novelty = 0.0 if f.is_restatement else (1.0 if f.is_first_filing else 0.3)
    s = user_weight * base + ALPHA * size + BETA * reaction + GAMMA * novelty
    floor = is_floor_event(f)
    if floor:
        s = max(s, FRONT_THRESHOLD)
    return Breakdown(base, user_weight, size, reaction, novelty, floor, round(s, 4))


def absolute_tier(b: Breakdown) -> str:
    """The tier an event earns on its own, before the front page's cap is applied."""
    if b.score >= FRONT_THRESHOLD:
        return "front"
    if b.score >= ONELINER_THRESHOLD or b.floor_applied:
        return "oneliner"
    return "folded"


@dataclass(frozen=True, slots=True)
class Ranked:
    key: str
    breakdown: Breakdown
    tier: str  # front | oneliner | folded


def assign_tiers(
    items: Iterable[tuple[str, Breakdown]], front_cap: int = FRONT_CAP
) -> list[Ranked]:
    """Rank by score. The front page takes at most `front_cap` items above the threshold;
    floor events that miss the front page still get a one-liner, never a fold."""
    ordered = sorted(items, key=lambda kv: kv[1].score, reverse=True)
    out: list[Ranked] = []
    front = 0
    for key, b in ordered:
        if b.score >= FRONT_THRESHOLD and front < front_cap:
            tier = "front"
            front += 1
        elif b.score >= ONELINER_THRESHOLD or b.floor_applied:
            tier = "oneliner"
        else:
            tier = "folded"
        out.append(Ranked(key, b, tier))
    return out
