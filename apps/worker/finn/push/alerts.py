"""Which stored anomalies cross a profile's own limits.

Anomalies are stored at fixed floors (finn.push.eod.FLOOR_THRESHOLDS). A profile's limits
sit at or above the floors and are applied here for notifications, and by the same rules
in the web app's `passes` (apps/web/lib/queries.ts) for the Pulse page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Mirrors finn.push.eod.FLOOR_THRESHOLDS and USER_DEFAULTS.
FLOORS = {"volume": 1.5, "price": 3.0, "sigma": 2.0, "delivery": 1.3}
DEFAULTS = {"volume": 2.0, "price": 5.0, "sigma": 2.5, "delivery": 1.5}
RULE_KIND = {
    "volume": "volume_multiple",
    "price": "price_move",
    "sigma": "sigma_move",
    "delivery": "delivery_spike",
}


@dataclass(frozen=True, slots=True)
class Limits:
    volume: float = DEFAULTS["volume"]
    price: float = DEFAULTS["price"]
    sigma: float = DEFAULTS["sigma"]
    delivery: float = DEFAULTS["delivery"]


@dataclass(frozen=True, slots=True)
class StoredHit:
    kind: str
    value: float
    threshold: float
    zscore: float | None


def limits_from_rules(rules: Sequence[Mapping[str, object]]) -> Limits:
    """`rules` are alert_rules rows (kind, value) for one profile, all companies."""
    values = dict(DEFAULTS)
    for key, kind in RULE_KIND.items():
        for r in rules:
            v = r.get("value")
            if r.get("kind") == kind and isinstance(v, int | float):
                values[key] = max(FLOORS[key], float(v))
    return Limits(**values)


def passes(h: StoredHit, limits: Limits, same_day: Sequence[StoredHit]) -> bool:
    if h.kind == "volume_multiple":
        return h.value >= limits.volume
    if h.kind == "price_move":
        return abs(h.value) >= limits.price
    if h.kind == "sigma_move":
        return abs(h.zscore or 0.0) >= limits.sigma
    if h.kind == "delivery_spike":
        usual = h.threshold / FLOORS["delivery"]  # stored threshold = floor x usual share
        volume_ok = any(x.kind == "volume_multiple" and x.value >= limits.volume for x in same_day)
        return volume_ok and usual > 0 and h.value / usual >= limits.delivery
    return False
