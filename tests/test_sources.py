"""Data-source layer: canonical output, metadata and timezone honesty."""
from datetime import date

import pandas as pd
import pytest

from xauscalp.data.server_time import ServerTimePolicy, TimezoneUnknown
from xauscalp.data.sources import CANONICAL, MT5BrokerM1Source, MT5BrokerTicksSource

UTC_POLICY = ServerTimePolicy(kind="fixed", offset_min=120, source="test")


def ticks_csv(tmp_path):
    t0 = pd.Timestamp("2026-03-04 10:00")      # server time (+2h -> 08:00 UTC)
    rows = []
    for k, (b, a) in enumerate([(3000.0, 3000.3), (3001.0, 3001.4), (2999.5, 2999.8),
                                (3000.5, 3000.7), (0.0, 1.0), (3002.0, 3001.0)]):
        ms = int((t0 + pd.Timedelta(seconds=15 * k)).value // 1_000_000)
        rows.append(f"{ms},{b},{a},6")
    ms2 = int((t0 + pd.Timedelta(minutes=1, seconds=20)).value // 1_000_000)
    rows.append(f"{ms2},3003.0,3003.2,6")
    p = tmp_path / "t.csv"
    p.write_text("#tz_policy,UNKNOWN\n#point,0.01\ntime_msc_server,bid,ask,flags\n"
                 + "\n".join(rows) + "\n")
    return p


def test_ticks_aggregate_to_exact_bid_ask_m1(tmp_path):
    src = MT5BrokerTicksSource(ticks_csv(tmp_path), UTC_POLICY)
    md = src.load(date(2026, 3, 4), date(2026, 3, 4), max_date=None)
    assert list(md.m1.columns) == CANONICAL
    first = md.m1.iloc[0]
    assert md.m1.index[0] == pd.Timestamp("2026-03-04 08:00", tz="UTC")
    assert (first.bid_o, first.bid_h, first.bid_l, first.bid_c) == (3000.0, 3001.0, 2999.5, 3000.5)
    assert (first.ask_h, first.ask_l) == (3001.4, 2999.8)
    assert first.volume == 4                       # 2 invalid ticks dropped (zero bid, ask<bid)
    assert src.ticks().attrs["invalid_ticks_dropped"] == 2
    assert not md.meta.use_extra_spread and md.meta.ask_source.startswith("real")


def test_ticks_refuse_unknown_timezone(tmp_path):
    with pytest.raises(TimezoneUnknown):
        MT5BrokerTicksSource(ticks_csv(tmp_path), ServerTimePolicy()).load(
            date(2026, 3, 4), date(2026, 3, 4), max_date=None)


def test_broker_m1_marks_ask_as_derived(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("#server_minus_gmt_seconds_at_export,7200\n#point,0.01\n"
                 "time_server,open,high,low,close,tick_volume,spread_points\n"
                 "2026.03.04 10:00,3000,3001,2999,3000.5,10,30\n"
                 "2026.03.04 10:01,3000.5,3002,3000,3001,12,25\n")
    md = MT5BrokerM1Source(p, UTC_POLICY).load(date(2026, 3, 4), date(2026, 3, 4), max_date=None)
    assert md.m1["ask_c"].iloc[0] == pytest.approx(3000.8)
    assert "derived" in md.meta.ask_source and "OPTIMISTIC" in md.meta.spread_semantics


def test_sources_respect_max_date(tmp_path):
    md = MT5BrokerTicksSource(ticks_csv(tmp_path), UTC_POLICY).load(
        date(2026, 3, 1), date(2026, 3, 10), max_date=date(2026, 3, 3))
    assert md.m1.empty or md.m1.index.max() < pd.Timestamp("2026-03-04", tz="UTC")
