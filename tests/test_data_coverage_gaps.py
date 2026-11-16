"""Audit finding D1: discontinuous histories must not be treated as consecutive."""
import numpy as np
import pandas as pd
import pytest

from xauscalp.data.coverage import coverage_report, segment_ids
from xauscalp.features.core import build_features


def weekday_bars(start, end, seed=0, price=2000.0):
    """~23h/day bars on weekdays (UTC), Sunday 22:00 -> Friday 21:00 like gold."""
    idx = pd.date_range(start, end, freq="1min", tz="UTC", inclusive="left")
    dow, h = idx.day_of_week, idx.hour
    open_ = ~((dow == 5) | ((dow == 4) & (h >= 21)) | ((dow == 6) & (h < 22)) | (h == 21))
    idx = idx[open_]
    rng = np.random.default_rng(seed)
    c = price + np.cumsum(rng.normal(0, 0.3, len(idx)))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"bid_o": o, "bid_h": np.maximum(o, c) + 0.1,
                       "bid_l": np.minimum(o, c) - 0.1, "bid_c": c}, index=idx)
    for x in "ohlc":
        df[f"ask_{x}"] = df[f"bid_{x}"] + 0.3
    df["volume"] = 1.0
    return df


def test_weekend_is_not_a_segment_break_but_a_data_hole_is():
    a = weekday_bars("2025-03-02 22:00", "2025-03-15")
    b = weekday_bars("2025-04-06 22:00", "2025-04-12", price=3000)
    seg = segment_ids(pd.concat([a, b]).index)
    assert seg[0] == 0 and seg[len(a) - 1] == 0      # weekend 7-8 Mar inside segment 0
    assert seg[len(a)] == 1 and seg[-1] == 1         # 3-week hole -> new segment


def test_coverage_report_counts_missing_days_and_anomalies():
    full = weekday_bars("2025-03-02 22:00", "2025-03-22")          # 3 trading weeks
    hole = (full.index >= "2025-03-09 22:00") & (full.index < "2025-03-14 21:00")
    m = full[~hole].copy()
    m.iloc[10, m.columns.get_loc("ask_c")] = m["bid_c"].iloc[10] - 0.1   # negative spread
    m = pd.concat([m, m.iloc[[5]]]).sort_index()                         # a duplicate
    rep = coverage_report(m, "2025-03-03", "2025-03-21")
    assert rep.expected_days == 15
    assert rep.missing_days == 5 and rep.usable_days == 10
    assert rep.duplicates == 1 and rep.negative_spread >= 1
    assert 60 < rep.coverage_pct < 70
    assert rep.usable_fraction(pd.Timestamp("2025-03-10", tz="UTC"),
                               pd.Timestamp("2025-03-15", tz="UTC")) == 0.0
    assert ("2025-03-10", "2025-03-14") in rep.missing_ranges
    assert "cobertura" in rep.to_markdown()


def test_indicators_restart_after_a_data_hole():
    a = weekday_bars("2025-03-02 22:00", "2025-03-08", price=1800)
    b = weekday_bars("2025-06-01 22:00", "2025-06-07", price=4000, seed=3)
    both = build_features(pd.concat([a, b]))
    only_b = build_features(b)
    first_b = b.index[0]
    # warm-up restarts: first bars of the new segment have no ATR (no carry-over)
    assert np.isnan(both.loc[first_b, "atr_m5"])
    # identical to computing segment b in isolation -> nothing leaked from segment a
    pd.testing.assert_series_equal(both.loc[b.index, "atr_m5"], only_b["atr_m5"],
                                   check_names=False)
    assert (both.loc[b.index, "segment"] == 1).all()


@pytest.mark.parametrize("gap_days", [5, 400, 1648])
def test_atr_never_sees_the_price_jump_across_years(gap_days):
    a = weekday_bars("2021-03-01 22:00", "2021-03-06", price=1700)
    start_b = pd.Timestamp("2021-03-06") + pd.Timedelta(days=gap_days)
    start_b = start_b + pd.Timedelta(days=(6 - start_b.day_of_week) % 7)   # next Sunday
    b = weekday_bars(start_b + pd.Timedelta(hours=22), start_b + pd.Timedelta(days=6),
                     price=3900)
    f = build_features(pd.concat([a, b]))
    assert f.loc[b.index, "atr_m5"].max() < 20      # a carried 2200$ "true range" would explode
