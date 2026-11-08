"""Filings into events: clustering, the representative filing, and the event's score.

One corporate happening often arrives as several filings: results come with a press
release, a presentation and a newspaper ad; three directors leaving the same board are
three filings. The Brief ranks events, so filings of the same company and family that
arrive within the family's window join one event.

Everything here is pure. `finn.push.pipeline` loads open events, calls `assign` and
`build`, and writes the results.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from finn.push.headline import headline_for
from finn.push.score import (
    ALPHA,
    BETA,
    GAMMA,
    Breakdown,
    EventFeatures,
    absolute_tier,
    base_weight,
    score,
)

DAY = timedelta(days=1)

# How long an event stays open to new filings of the same family.
WINDOWS: Mapping[str, timedelta] = {
    "results": 3 * DAY,
    "results_intimation": 2 * DAY,
    "earnings_call": 3 * DAY,
    "investor_meetings": 2 * DAY,
    "management_change": 2 * DAY,
    "credit_rating": 2 * DAY,
    "dividend": 3 * DAY,
    "agm_egm": 3 * DAY,
    "postal_ballot": 3 * DAY,
    "bonus_split": 3 * DAY,
    "fund_raise": 2 * DAY,
    "M&A": DAY,
    "capex": DAY,
    "litigation": DAY,
    "insider_trading": DAY,
    "pledging": DAY,
    "unclassified": DAY,
    "press_release": timedelta(0),  # two press releases are two stories
}
NOVELTY_LOOKBACK = timedelta(days=30)

_RESTATEMENT = re.compile(r"\brevis|\bcorrigendum|\bcorrection|\brestat|inadvertent", re.I)


def family(category: str, attributes: Mapping[str, str]) -> str:
    """The clustering key within a company."""
    if category == "results" and attributes.get("stage") == "intimation":
        return "results_intimation"
    if category == "unclassified":
        return f"unclassified:{attributes.get('kind', 'other')}"
    if category == "press_release":
        return f"press_release:{attributes.get('kind', 'general')}"
    return category


def window(fam: str) -> timedelta:
    return WINDOWS.get(fam.split(":", 1)[0], DAY)


@dataclass(frozen=True, slots=True)
class FilingFacts:
    key: str  # stable id: "NSE:<seq_id>"
    isin: str
    filed_at: datetime
    subject: str
    text: str
    summary: str | None
    category: str
    attributes: Mapping[str, str]
    attachment_url: str | None = None

    @property
    def family(self) -> str:
        return family(self.category, self.attributes)

    @property
    def weight(self) -> float:
        return base_weight(self.category, self.attributes)


@dataclass(slots=True)
class EventDraft:
    cluster_key: str
    isin: str
    family: str
    members: list[FilingFacts] = field(default_factory=list)
    event_id: int | None = None  # set when the event already exists
    reaction: Mapping[str, Any] | None = None  # from the EOD job, kept across rescoring

    @property
    def first_seen_at(self) -> datetime:
        return min(m.filed_at for m in self.members)

    @property
    def last_filed_at(self) -> datetime:
        return max(m.filed_at for m in self.members)

    @property
    def representative(self) -> FilingFacts:
        """The filing that says the most: highest base weight, earliest on ties."""
        return min(self.members, key=lambda m: (-m.weight, m.filed_at, m.key))

    def accepts(self, f: FilingFacts) -> bool:
        if f.isin != self.isin or f.family != self.family:
            return False
        w = window(self.family)
        if w <= timedelta(0):
            return False
        return self.first_seen_at - w <= f.filed_at <= self.last_filed_at + w


def assign(filings: Sequence[FilingFacts], open_events: Sequence[EventDraft]) -> list[EventDraft]:
    """Attach each filing to an open event or start a new one. Returns the touched drafts,
    existing ones first. Filings are taken oldest first so windows grow in order."""
    pool: list[EventDraft] = list(open_events)
    touched: dict[str, EventDraft] = {}
    for f in sorted(filings, key=lambda x: (x.filed_at, x.key)):
        match = max(
            (e for e in pool if e.accepts(f)),
            key=lambda e: e.last_filed_at,
            default=None,
        )
        if match is None:
            match = EventDraft(cluster_key=f.key, isin=f.isin, family=f.family)
            pool.append(match)
        if all(m.key != f.key for m in match.members):
            match.members.append(f)
        touched[match.cluster_key] = match
    return sorted(touched.values(), key=lambda e: (e.event_id is None, e.first_seen_at))


@dataclass(frozen=True, slots=True)
class EventRow:
    cluster_key: str
    isin: str
    family: str
    category: str
    attributes: dict[str, str]
    stage: str | None
    first_seen_at: datetime
    last_filed_at: datetime
    filing_count: int
    headline: str
    score: float
    tier: str
    breakdown: dict[str, Any]


def build(draft: EventDraft, prior_first_seen: Sequence[datetime] = ()) -> EventRow:
    """Score an event from its representative filing.

    `prior_first_seen` holds first-seen times of other events of the same company and
    family; one inside the lookback makes this event less novel.
    """
    rep = draft.representative
    lead = _headline_source(draft, rep)
    start = draft.first_seen_at
    is_first = not any(start - NOVELTY_LOOKBACK <= t < start for t in prior_first_seen)
    reaction = draft.reaction or {}
    features = EventFeatures(
        category=rep.category,
        attributes=dict(rep.attributes),
        abnormal_return_pct=_opt_float(reaction.get("abnormal_return_pct")),
        volume_z=_opt_float(reaction.get("volume_z")),
        is_first_filing=is_first,
        is_restatement=bool(_RESTATEMENT.search(f"{rep.subject} {rep.text}")),
    )
    b: Breakdown = score(features)
    attrs = {k: str(v) for k, v in rep.attributes.items()}
    return EventRow(
        cluster_key=draft.cluster_key,
        isin=draft.isin,
        family=draft.family,
        category=rep.category,
        attributes=attrs,
        stage=attrs.get("stage"),
        first_seen_at=start,
        last_filed_at=draft.last_filed_at,
        filing_count=len(draft.members),
        headline=headline_for(lead.subject, lead.text, lead.summary),
        score=b.score,
        tier=absolute_tier(b),
        breakdown={
            **asdict(b),
            # What each term added, so the app can explain a score without redoing it.
            "contributions": {
                "category": round(b.user_weight * b.base, 4),
                "size": round(ALPHA * b.size, 4),
                "reaction": round(BETA * b.reaction, 4),
                "novelty": round(GAMMA * b.novelty, 4),
            },
            "representative": rep.key,
            "is_first_filing": is_first,
            "is_restatement": features.is_restatement,
        },
    )


def _headline_source(draft: EventDraft, rep: FilingFacts) -> FilingFacts:
    """Results events take their headline from the company's own release when there is
    one: it leads with the numbers, where the filing's description only names the period."""
    if draft.family == "results":
        for m in sorted(draft.members, key=lambda x: x.filed_at):
            if m.attributes.get("stage") == "press_release":
                return m
    return rep


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
