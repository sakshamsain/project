from datetime import datetime

from finn.push.alerts import Limits, StoredHit, limits_from_rules, passes
from finn.push.notify import allowed_endpoint, in_quiet_hours
from finn.sources.nse import IST


def test_limits_default_and_floor() -> None:
    assert limits_from_rules([]) == Limits()
    lim = limits_from_rules(
        [{"kind": "volume_multiple", "value": 1.0}, {"kind": "price_move", "value": 7.5}]
    )
    assert lim.volume == 1.5  # never below the stored floor
    assert lim.price == 7.5


def test_passes_follows_each_rule() -> None:
    lim = Limits()
    vol = StoredHit("volume_multiple", 2.4, 1.5, 3.1)
    small_vol = StoredHit("volume_multiple", 1.7, 1.5, 1.2)
    assert passes(vol, lim, [vol]) and not passes(small_vol, lim, [small_vol])
    assert passes(StoredHit("price_move", -5.2, 3.0, None), lim, [])
    assert not passes(StoredHit("price_move", 4.0, 3.0, None), lim, [])
    assert passes(StoredHit("sigma_move", -4.0, 2.0, -2.7), lim, [])
    # delivery: stored threshold 1.3 x usual 40% = 52; 64% is 1.6x usual
    deliv = StoredHit("delivery_spike", 64.0, 52.0, None)
    assert passes(deliv, lim, [vol, deliv])
    assert not passes(deliv, lim, [small_vol, deliv])  # needs the volume limit too


def test_quiet_hours_in_ist() -> None:
    assert in_quiet_hours(datetime(2026, 11, 8, 22, 30, tzinfo=IST))
    assert in_quiet_hours(datetime(2026, 11, 9, 6, 59, tzinfo=IST))
    assert not in_quiet_hours(datetime(2026, 11, 9, 7, 0, tzinfo=IST))


def test_only_real_push_services() -> None:
    assert allowed_endpoint("https://fcm.googleapis.com/fcm/send/abc")
    assert allowed_endpoint("https://web.push.apple.com/QGx")
    assert not allowed_endpoint("http://fcm.googleapis.com/fcm/send/abc")
    assert not allowed_endpoint("https://evil.example.com/fcm.googleapis.com")
    assert not allowed_endpoint("https://fcm.googleapis.com.evil.example/x")
