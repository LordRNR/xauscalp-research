"""Tick-quality maths on tiny synthetic feeds with hand-computed answers."""
import numpy as np
import pandas as pd
import pytest

from xauscalp.data import tick_quality as tq


def mk(rows, start="2025-10-06 10:00:00"):
    """rows: (seconds_from_start, bid, ask)"""
    t0 = pd.Timestamp(start, tz="UTC")
    return pd.DataFrame({"bid": [r[1] for r in rows], "ask": [r[2] for r in rows]},
                        index=pd.DatetimeIndex([t0 + pd.Timedelta(seconds=r[0]) for r in rows]))


def test_clean_quotes_counts_each_defect():
    t = mk([(0, 100.0, 100.2), (1, 0.0, 1.0), (2, 100.5, 100.3), (3, np.nan, 100.0),
            (4, 100.1, 100.3)])
    clean, c = tq.clean_quotes(t)
    assert len(clean) == 2
    assert (c["non_finite"], c["non_positive"], c["crossed"], c["dropped"]) == (1, 1, 1, 3)


def test_integrity_duplicates_and_order():
    t = mk([(0, 100.0, 100.2), (0, 100.1, 100.3), (1, 100.1, 100.3)])
    r = tq.integrity(t)
    assert r["same_timestamp_pairs"] == 1 and r["consecutive_identical_quotes"] == 1
    assert r["monotonic"] and r["zero_spread"] == 0


def test_time_weighted_spread_differs_from_tick_weighted():
    # spread 0.2 for 10 s, then 1.0 for 50 s, then a closing tick (weight 0)
    t = mk([(0, 100.0, 100.2), (10, 100.0, 101.0), (60, 100.0, 100.2)])
    s = tq.spread_stats(t, thresholds=(0.6,))
    assert s["tick_mean"] == pytest.approx((0.2 + 1.0 + 0.2) / 3)
    assert s["time_mean"] == pytest.approx((0.2 * 10 + 1.0 * 50) / 60)
    assert s["share_time_above"][0.6] == pytest.approx(50 / 60)
    assert s["max"] == pytest.approx(1.0)


def test_long_silence_is_capped_not_counted():
    t = mk([(0, 100.0, 100.2), (3600, 100.0, 100.2)])
    assert tq.durations(t)[0] == tq.CAP_S


def test_weighted_quantile_is_weight_aware():
    q = tq.weighted_quantile(np.array([1.0, 2.0]), np.array([1.0, 3.0]), [0.5])[0]
    assert q > 1.5
    assert np.isnan(tq.weighted_quantile(np.array([1.0]), np.array([0.0]), [0.5])[0])


def test_gap_table_separates_weekly_close():
    t = mk([(0, 1, 1.1), (70, 1, 1.1), (70 + 400, 1, 1.1), (70 + 400 + 8 * 3600, 1, 1.1)])
    counts, top = tq.gap_table(t)
    assert counts.loc["30 s - 5 min", "count"] == 1             # the 70 s gap
    assert counts.loc["5 - 30 min (silence)", "count"] == 1     # the 400 s gap
    assert counts.loc["> 6 h (weekly close)", "count"] == 1
    assert top["seconds"].iloc[0] == pytest.approx(400)


def test_daily_break_and_silences_are_classified_apart():
    t = mk([(0, 1, 1.1), (600, 1, 1.1), (600 + 3700, 1, 1.1)])      # 10 min, then 61 min
    counts, _ = tq.gap_table(t)
    assert counts.loc["5 - 30 min (silence)", "count"] == 1
    assert counts.loc["30 min - 6 h (daily break)", "count"] == 1


def test_silences_vs_bars_tells_server_outage_from_export_loss():
    t = mk([(0, 1, 1.1), (600, 1, 1.1)])
    bars_empty = pd.DataFrame({"tick_volume": [1]}, index=[t.index[0].floor("min")])
    s = tq.silences_vs_bars(t, bars_empty)
    assert len(s) == 1 and s["server_bars_inside"].iloc[0] == 0
    inside = pd.DataFrame({"tick_volume": [5, 5]}, index=pd.DatetimeIndex(
        [t.index[0].floor("min") + pd.Timedelta(minutes=k) for k in (3, 5)]))
    assert tq.silences_vs_bars(t, inside)["server_bars_inside"].iloc[0] == 2


def test_contiguous_blocks_and_bid_tick_count():
    idx = pd.DatetimeIndex(["2025-10-23 17:09", "2025-10-23 17:10", "2025-10-23 17:11",
                            "2025-10-23 18:00"], tz="UTC")
    b = tq.contiguous_blocks(idx)
    assert list(b["minutes"]) == [3, 1]
    t = mk([(0, 100.0, 100.4), (10, 100.0, 100.5), (20, 100.1, 100.5)])
    t["flags"] = [134, 4, 130]                    # 2nd tick changed only the ask
    m = tq.minute_frame(t)
    assert m["n"].iloc[0] == 3 and m["n_bid"].iloc[0] == 2
    bars = pd.DataFrame({"open": m.bid_o, "high": m.bid_h, "low": m.bid_l, "close": m.bid_c,
                         "tick_volume": m.n_bid, "spread": m.sp_min})
    r = tq.compare_with_m1(m, bars)
    assert r["bidtick_equals_tickvolume_share"] == 1.0
    assert r["tickcount_equal_share"] == 0.0


def test_daily_coverage_marks_weekend_days_empty():
    t = mk([(0, 1, 1.1)], start="2025-10-03 10:00:00")                 # Friday
    t2 = mk([(0, 1, 1.1)], start="2025-10-06 10:00:00")                # Monday
    d = tq.daily_coverage(pd.concat([t, t2]), t.index[0], t2.index[0])
    assert list(d["weekday"]) == ["Fri", "Sat", "Sun", "Mon"]
    assert list(d["ticks"]) == [1, 0, 0, 1]


def bars_from(minutes: pd.DataFrame, spread_col: str) -> pd.DataFrame:
    return pd.DataFrame({"open": minutes.bid_o, "high": minutes.bid_h, "low": minutes.bid_l,
                         "close": minutes.bid_c, "tick_volume": minutes.n,
                         "spread": minutes[spread_col]})


def test_compare_with_m1_perfect_feed_and_bar_spread_is_min():
    t = mk([(0, 100.0, 100.4), (20, 101.0, 101.2), (40, 99.5, 99.9),            # minute 0
            (65, 100.0, 100.2), (90, 100.5, 100.9)])                           # minute 1
    m = tq.minute_frame(t)
    assert list(m["n"]) == [3, 2]
    assert m["bid_h"].iloc[0] == 101.0 and m["bid_l"].iloc[0] == 99.5
    r = tq.compare_with_m1(m, bars_from(m, "sp_min"))
    assert r["bars_without_ticks"] == 0 and r["minutes_with_ticks_without_bar"] == 0
    assert r["ohlc_close_equal"] == 1.0 and r["tickcount_total_ratio"] == 1.0
    assert r["bar_spread_equals"]["min_in_minute"] == 1.0
    assert r["bar_spread_equals"]["max_in_minute"] < 1.0


def test_compare_with_m1_detects_thinned_ticks_and_missing_minutes():
    t = mk([(0, 100.0, 100.4), (20, 101.0, 101.2), (65, 100.0, 100.2), (125, 100.0, 100.2)])
    m = tq.minute_frame(t)
    bars = bars_from(m, "sp_last")
    bars["tick_volume"] = bars["tick_volume"] * 2          # server saw twice as many ticks
    r = tq.compare_with_m1(m, bars)
    assert r["tickcount_total_ratio"] == pytest.approx(0.5)
    assert r["tickcount_equal_share"] == 0.0
    r2 = tq.compare_with_m1(m, bars.drop(bars.index[1]))
    assert r2["minutes_with_ticks_without_bar"] == 1


def test_first_tick_spread_at_respects_max_wait():
    t = mk([(0, 100.0, 100.2), (30, 100.0, 100.7)])
    when = pd.DatetimeIndex([t.index[0] + pd.Timedelta(seconds=s) for s in (-5, 10, 31)])
    out = tq.first_tick_spread_at(t, when, max_wait_s=60)
    assert out[0] == pytest.approx(0.2) and out[1] == pytest.approx(0.7) and np.isnan(out[2])
    assert np.isnan(tq.first_tick_spread_at(t, when, max_wait_s=3)[1])
