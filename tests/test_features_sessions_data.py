import lzma
from datetime import date

import numpy as np
import pandas as pd
import pytest

from xauscalp.data.dukascopy import RECORD, day_url, decode_day
from xauscalp.data.quality import DataIntegrityError, check_m1
from xauscalp.features.core import build_features, htf_to_ltf, resample_ohlc
from xauscalp.features.sessions import local_anchor_utc, session_labels


def synthetic_m1(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-03-04 00:00", periods=n, freq="1min", tz="UTC")
    c = 2000 + np.cumsum(rng.normal(0, 0.3, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 0.3, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.3, n)
    df = pd.DataFrame({"bid_o": o, "bid_h": h, "bid_l": l, "bid_c": c}, index=idx)
    for x in "ohlc":
        df[f"ask_{x}"] = df[f"bid_{x}"] + 0.25
    df["volume"] = 1.0
    return df


def test_features_have_no_lookahead():
    """Features at time t must be identical whether or not future bars exist."""
    full = synthetic_m1()
    f_full = build_features(full)
    for cut in (1234, 3001, 4500):
        f_trunc = build_features(full.iloc[:cut])
        a = f_full.iloc[:cut][["spread", "atr_m5", "er_h1"]]
        b = f_trunc[["spread", "atr_m5", "er_h1"]]
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12)


def test_htf_bar_visible_only_after_close():
    m1 = synthetic_m1(30)
    m5 = resample_ohlc(m1, "5min")
    al = htf_to_ltf(m5[["c"]], pd.Timedelta(minutes=5), m1.index)
    # row 3 (00:03) decides at 00:04 -> no M5 bar closed yet
    assert np.isnan(al["c"].iloc[3])
    # row 4 decides at 00:05 -> the 00:00-00:05 bar just closed and equals bid_c of row 4
    assert al["c"].iloc[4] == pytest.approx(m1["bid_c"].iloc[4])
    assert al["c"].iloc[8] == pytest.approx(m1["bid_c"].iloc[4])


def test_dst_session_anchors():
    # London 08:00 is 08:00 UTC in winter and 07:00 UTC in summer
    assert local_anchor_utc(pd.Timestamp("2025-01-15"), "Europe/London", "08:00").hour == 8
    assert local_anchor_utc(pd.Timestamp("2025-07-15"), "Europe/London", "08:00").hour == 7
    # US switches 2 weeks before the UK: on 2025-03-12 NY 08:20 = 12:20 UTC
    assert local_anchor_utc(pd.Timestamp("2025-03-12"), "America/New_York", "08:20").hour == 12


def test_session_labels_overlap():
    idx = pd.DatetimeIndex(["2025-01-15 13:30", "2025-01-15 03:00", "2025-01-15 22:30"],
                           tz="UTC")
    assert list(session_labels(idx)) == ["overlap", "asia", "off"]


def test_dukascopy_decode_roundtrip():
    rec = np.zeros(2, dtype=RECORD)
    rec["t"] = [0, 60]
    rec["o"], rec["c"], rec["l"], rec["h"] = [2000500, 2001000], [2001000, 2000000], \
        [2000000, 1999000], [2001500, 2001200]
    rec["v"] = [0.5, 0.0]
    df = decode_day(lzma.compress(rec.tobytes()), date(2025, 1, 2), 1000.0)
    assert df.index[1] == pd.Timestamp("2025-01-02 00:01", tz="UTC")
    assert df["o"].iloc[0] == pytest.approx(2000.5)
    assert df["h"].iloc[1] == pytest.approx(2001.2)
    assert decode_day(b"", date(2025, 1, 2), 1000.0).empty


def test_dukascopy_month_is_zero_based():
    assert "/2025/00/02/" in day_url("XAUUSD", date(2025, 1, 2), "BID")


def test_quality_rejects_duplicates_and_bad_ohlc():
    df = synthetic_m1(50)
    check_m1(df)
    with pytest.raises(DataIntegrityError):
        check_m1(pd.concat([df, df.iloc[[3]]]).sort_index())
    bad = df.copy()
    bad.iloc[5, bad.columns.get_loc("bid_h")] = bad["bid_l"].iloc[5] - 1
    with pytest.raises(DataIntegrityError):
        check_m1(bad)
