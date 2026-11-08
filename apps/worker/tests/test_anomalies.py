from finn.push.anomalies import Bar, Thresholds, daily_returns_pct, evaluate


def flat_history(n: int = 22, close: float = 100.0, volume: int = 100_000) -> list[Bar]:
    # Small alternating moves give the return series a non-zero, realistic volatility.
    bars = []
    price = close
    for i in range(n):
        price *= 1.003 if i % 2 == 0 else 0.997
        bars.append(Bar(f"2026-10-{i + 1:02d}", round(price, 4), volume, 40.0))
    return bars


def with_today(
    history: list[Bar], move_pct: float, volume: int, delivery: float = 40.0
) -> list[Bar]:
    last = history[-1].close
    return [*history, Bar("2026-11-11", last * (1 + move_pct / 100), volume, delivery)]


def kinds(hits: list) -> set[str]:
    return {h.kind for h in hits}


def test_volume_spike_detected_at_2_5x() -> None:
    hits = evaluate(with_today(flat_history(), 0.2, 250_000))
    vol = next(h for h in hits if h.kind == "volume_multiple")
    assert vol.value == 2.5
    assert vol.threshold == 2.0


def test_volume_below_threshold_is_quiet() -> None:
    assert "volume_multiple" not in kinds(evaluate(with_today(flat_history(), 0.2, 150_000)))


def test_price_move_over_five_percent() -> None:
    hits = evaluate(with_today(flat_history(), 6.0, 100_000))
    assert "price_move" in kinds(hits)


def test_small_move_is_quiet_for_fixed_threshold() -> None:
    assert "price_move" not in kinds(evaluate(with_today(flat_history(), 3.0, 100_000)))


def test_sigma_rule_catches_big_move_for_a_calm_stock() -> None:
    # A 1.5% day is under the 5% rule but far outside a ~0.3% daily range.
    hits = evaluate(with_today(flat_history(), 1.5, 100_000))
    assert "sigma_move" in kinds(hits)
    assert "price_move" not in kinds(hits)


def test_relative_to_index_strips_market_wide_days() -> None:
    history = with_today(flat_history(), 6.0, 100_000)
    n_returns = len(history[-(20 + 2) :]) - 1
    index = [0.0] * (n_returns - 1) + [5.5]
    hits = evaluate(history, Thresholds(relative_to_index=True), index_returns_pct=index)
    assert "price_move" not in kinds(hits)


def test_delivery_spike_needs_a_volume_spike() -> None:
    t = Thresholds(delivery_multiple=1.5)
    quiet_volume = evaluate(with_today(flat_history(), 0.2, 120_000, delivery=80.0), t)
    assert "delivery_spike" not in kinds(quiet_volume)
    spike = evaluate(with_today(flat_history(), 0.2, 300_000, delivery=80.0), t)
    assert "delivery_spike" in kinds(spike)


def test_corporate_action_day_suppresses_price_rules_only() -> None:
    history = with_today(flat_history(), -50.0, 400_000)  # 1:1 bonus ex-date
    hits = evaluate(history, suppress_price_rules=True)
    assert kinds(hits) == {"volume_multiple"}


def test_short_history_returns_nothing() -> None:
    assert evaluate(flat_history(n=4)) == []


def test_daily_returns_rejects_non_positive_close() -> None:
    try:
        daily_returns_pct([100.0, 0.0, 10.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError")
