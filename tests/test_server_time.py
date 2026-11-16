"""Audit finding T1: MT5 server time -> UTC across DST changes.

2025 transitions: US DST starts 2025-03-09, ends 2025-11-02; UK/EU start 2025-03-30,
end 2025-10-26. Between them London-New York differ by 4h instead of 5h.
The synthetic broker follows the common "UTC+2, +3 during US DST" convention.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from xauscalp.data.server_time import (
    ServerTimePolicy,
    TimezoneUnknown,
    infer_weekly_offsets,
    policy_from_inference,
)
from xauscalp.features.sessions import local_anchor_utc
from xauscalp.mt5_report import load_mt5_rates_csv

NY_DST_BROKER = ServerTimePolicy(kind="base_dst", base_min=120, dst_of="America/New_York",
                                 source="test")


def trading_minutes(start, end):
    """UTC minutes Sun 22:00 -> Fri 21:00 (approximate gold week; enough for tests)."""
    idx = pd.date_range(start, end, freq="1min", tz="UTC")
    dow, h = idx.day_of_week, idx.hour
    open_ = ~((dow == 5) | ((dow == 4) & (h >= 21)) | ((dow == 6) & (h < 22)))
    return idx[open_]


def utc_to_broker(utc: pd.DatetimeIndex) -> pd.DatetimeIndex:
    ny = utc.tz_convert("America/New_York")
    dst = np.array([t.dst() != pd.Timedelta(0) for t in ny])
    return (utc.tz_localize(None) + pd.to_timedelta(np.where(dst, 180, 120), unit="min"))


@pytest.fixture(scope="module")
def spring():
    utc = trading_minutes("2025-02-28", "2025-04-12")
    rng = np.random.default_rng(7)
    close = pd.Series(3000 + np.cumsum(rng.normal(0, 0.4, len(utc))), index=utc)
    return utc, close


def test_rule_policy_roundtrip_exact(spring):
    utc, _ = spring
    back = NY_DST_BROKER.to_utc(utc_to_broker(utc))
    assert (back == utc).all()


def test_single_export_offset_is_wrong_before_us_dst(spring):
    """The OLD behaviour: one offset (+3h, observed at export in summer) for everything."""
    utc, _ = spring
    server = utc_to_broker(utc)
    old = (server - pd.Timedelta(hours=3)).tz_localize("UTC")
    winter = utc < pd.Timestamp("2025-03-09 07:00", tz="UTC")
    assert (old[winter] != utc[winter]).all()            # off by one hour in winter
    assert ((utc[winter] - old[winter]) == pd.Timedelta(hours=1)).all()


@pytest.mark.parametrize("day,expected_utc_hour", [
    ("2025-03-05", 8),   # winter: London 08:00 = 08:00 UTC
    ("2025-03-19", 8),   # US already on DST, UK not yet: still 08:00 UTC
    ("2025-04-02", 7),   # both on DST: 07:00 UTC
])
def test_london_open_lands_on_right_utc_bar(day, expected_utc_hour):
    anchor = local_anchor_utc(pd.Timestamp(day), "Europe/London", "08:00")
    assert anchor.hour == expected_utc_hour
    server = utc_to_broker(pd.DatetimeIndex([anchor]))
    assert NY_DST_BROKER.to_utc(server)[0] == anchor


@pytest.mark.parametrize("day,expected_utc", [("2025-03-05", "13:20"), ("2025-03-19", "12:20"),
                                              ("2025-10-29", "12:20"), ("2025-11-05", "13:20")])
def test_comex_open_across_us_and_eu_switches(day, expected_utc):
    anchor = local_anchor_utc(pd.Timestamp(day), "America/New_York", "08:20")
    assert anchor.strftime("%H:%M") == expected_utc
    assert NY_DST_BROKER.to_utc(utc_to_broker(pd.DatetimeIndex([anchor])))[0] == anchor


def test_unknown_policy_refuses():
    with pytest.raises(TimezoneUnknown):
        ServerTimePolicy().to_utc(pd.DatetimeIndex(["2025-01-02 10:00"]))


def test_inference_recovers_weekly_offsets(spring):
    utc, close = spring
    rng = np.random.default_rng(1)
    broker = pd.Series(close.to_numpy() + rng.normal(0, 0.02, len(close)),
                       index=utc_to_broker(utc))
    tab = infer_weekly_offsets(broker, close, candidates_min=range(-180, 301, 60))
    assert tab["confident"].all()
    wk_start = tab["week_start_server"]
    exp = np.where(wk_start < pd.Timestamp("2025-03-08"), 120, 180)
    assert (tab["offset_min"].to_numpy() == exp).all()
    pol = policy_from_inference(tab, "test")
    assert (pol.to_utc(broker.index) == utc).all()


def test_inference_not_confident_on_unrelated_series(spring):
    utc, close = spring
    rng = np.random.default_rng(2)
    noise = pd.Series(rng.normal(0, 1, len(close)).cumsum(), index=utc_to_broker(utc))
    tab = infer_weekly_offsets(noise, close, candidates_min=range(-120, 241, 60))
    assert not tab["confident"].any()
    pol = policy_from_inference(tab, "test")
    assert pol.to_utc(noise.index).isna().all()       # undeterminable -> NaT, not a guess


def test_weekly_open_is_stable_in_new_york_time(spring):
    """After a correct conversion the Sunday open is always 18:00 New York (no 1h jumps)."""
    utc, _ = spring
    back = NY_DST_BROKER.to_utc(utc_to_broker(utc))
    s = pd.Series(back, index=back)
    gap = s.index.to_series().diff() > pd.Timedelta(hours=24)
    week_opens = s.index[gap.to_numpy()]
    ny = week_opens.tz_convert("America/New_York")
    # synthetic market opens Sunday 22:00 UTC (not NY-anchored), so NY hour is 17 or 18;
    # the point is that conversion never produces a THIRD value (a 1h error).
    assert set(ny.hour) <= {17, 18}
    assert ((week_opens.hour == 22) & (week_opens.minute == 0)).all()


def test_loader_requires_policy(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("#server_minus_gmt_seconds_at_export,10800\n#point,0.01\n"
                 "time_server,open,high,low,close,tick_volume,spread_points\n"
                 "2025.03.05 10:00,3000,3001,2999,3000.5,10,25\n")
    with pytest.raises(TimezoneUnknown):
        load_mt5_rates_csv(p, ServerTimePolicy(), max_date=date(2025, 12, 31))
    df = load_mt5_rates_csv(p, NY_DST_BROKER, max_date=date(2025, 12, 31))
    assert df.index[0] == pd.Timestamp("2025-03-05 08:00", tz="UTC")   # winter: +2h
    assert df["spread"].iloc[0] == pytest.approx(0.25)
