"""End-of-day anomaly rules.

Pure functions over one company's daily bars, oldest first. No I/O: the EOD job loads
bars from `eod_prices`, calls `evaluate`, and writes hits to `anomalies`.

Prices from the bhavcopy are not adjusted for corporate actions. On a bonus, split or
large-dividend ex-date the raw close drops mechanically, so the caller passes
`suppress_price_rules=True` for that bar (the volume rule still runs).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, pstdev, stdev

MIN_BARS = 6  # today plus at least five prior sessions


@dataclass(frozen=True, slots=True)
class Bar:
    trade_date: str  # ISO date, e.g. "2026-11-11"
    close: float
    volume: int
    delivery_pct: float | None = None


@dataclass(frozen=True, slots=True)
class Thresholds:
    volume_multiple: float = 2.0  # today's volume vs its lookback average
    price_move_pct: float = 5.0  # absolute daily return, percent
    sigma: float = 2.5  # daily return vs its lookback volatility
    relative_to_index: bool = False  # subtract the index's return first
    delivery_multiple: float | None = None  # e.g. 1.5 turns on the delivery rule
    lookback: int = 20


@dataclass(frozen=True, slots=True)
class Hit:
    kind: str  # volume_multiple | price_move | sigma_move | delivery_spike
    value: float
    threshold: float
    zscore: float | None = None


DEFAULT_THRESHOLDS = Thresholds()


def daily_returns_pct(closes: Sequence[float]) -> list[float]:
    """Simple daily returns in percent; `closes` must be positive."""
    out: list[float] = []
    for prev, cur in zip(closes, closes[1:], strict=False):
        if prev <= 0:
            raise ValueError(f"non-positive close: {prev}")
        out.append((cur / prev - 1.0) * 100.0)
    return out


def evaluate(
    history: Sequence[Bar],
    t: Thresholds = DEFAULT_THRESHOLDS,
    index_returns_pct: Sequence[float] | None = None,
    suppress_price_rules: bool = False,
) -> list[Hit]:
    """Evaluate the last bar of `history` against the bars before it.

    `index_returns_pct` holds the benchmark's daily returns aligned with the stock's,
    newest last; it is used only when `t.relative_to_index` is set.
    """
    if len(history) < MIN_BARS:
        return []

    hits: list[Hit] = []
    today = history[-1]
    window = list(history[-(t.lookback + 1) : -1])

    vols = [b.volume for b in window]
    avg_vol = fmean(vols)
    if avg_vol > 0:
        multiple = today.volume / avg_vol
        if multiple >= t.volume_multiple:
            sd_vol = pstdev(vols)
            z_vol = (today.volume - avg_vol) / sd_vol if sd_vol > 0 else None
            hits.append(Hit("volume_multiple", round(multiple, 4), t.volume_multiple, _r(z_vol)))

    if not suppress_price_rules:
        closes = [b.close for b in history[-(t.lookback + 2) :]]
        rets = daily_returns_pct(closes)
        if t.relative_to_index and index_returns_pct is not None:
            bench = list(index_returns_pct)[-len(rets) :]
            if len(bench) == len(rets):
                rets = [r - i for r, i in zip(rets, bench, strict=True)]
        if rets:
            r_today = rets[-1]
            if abs(r_today) >= t.price_move_pct:
                hits.append(Hit("price_move", round(r_today, 4), t.price_move_pct))
            past = rets[:-1]
            if len(past) >= 2:
                mu, sd = fmean(past), stdev(past)
                if sd > 0:
                    z = (r_today - mu) / sd
                    if abs(z) >= t.sigma:
                        hits.append(Hit("sigma_move", round(r_today, 4), t.sigma, _r(z)))

    volume_hit = any(h.kind == "volume_multiple" for h in hits)
    if t.delivery_multiple and volume_hit and today.delivery_pct is not None:
        past_d = [b.delivery_pct for b in window if b.delivery_pct is not None]
        if past_d:
            avg_d = fmean(past_d)
            if avg_d > 0 and today.delivery_pct / avg_d >= t.delivery_multiple:
                hits.append(
                    Hit(
                        "delivery_spike",
                        round(today.delivery_pct, 4),
                        round(t.delivery_multiple * avg_d, 4),
                    )
                )
    return hits


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)
