"""Causal feature engineering.

Timing convention used everywhere in this project:
  - every row is indexed by its bar OPEN time;
  - a decision on row i happens at the CLOSE of bar i (index[i] + bar period);
  - it is executed at the OPEN of bar i+1.
Therefore a feature on row i may only use data whose bars closed at or before
index[i] + 1 minute. Higher-timeframe bars become visible only once they have CLOSED
(see htf_to_ltf). tests/test_features_sessions_data.py (test_features_have_no_lookahead) and
tests/test_alt_strategies.py (truncation tests) enforce this.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from xauscalp.data.coverage import segment_ids

M1 = pd.Timedelta(minutes=1)


def resample_ohlc(m1: pd.DataFrame, rule: str, side: str = "bid") -> pd.DataFrame:
    agg = m1.resample(rule, label="left", closed="left").agg(
        {f"{side}_o": "first", f"{side}_h": "max", f"{side}_l": "min", f"{side}_c": "last"}
    )
    agg.columns = ["o", "h", "l", "c"]
    return agg.dropna()


def wilder_atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def efficiency_ratio(c: pd.Series, n: int) -> pd.Series:
    """Kaufman efficiency ratio in [0,1]: ~1 trending, ~0 choppy."""
    net = (c - c.shift(n)).abs()
    path = c.diff().abs().rolling(n, min_periods=n).sum()
    return net / path.replace(0, np.nan)


def htf_to_ltf(htf: pd.DataFrame, period: pd.Timedelta, ltf_index: pd.DatetimeIndex,
               ltf_period: pd.Timedelta = M1) -> pd.DataFrame:
    """Align higher-timeframe values to a lower-timeframe index WITHOUT look-ahead.

    An HTF bar opening at T is only usable once it closes (T + period). An LTF row i is
    decided at ltf_index[i] + ltf_period. We take the latest HTF bar with
    close_time <= decision_time.
    """
    right = htf.copy()
    right["_avail"] = right.index + period
    right = right.sort_values("_avail")
    left = pd.DataFrame({"_decision": ltf_index + ltf_period})
    merged = pd.merge_asof(left, right, left_on="_decision", right_on="_avail",
                           direction="backward")
    merged.index = ltf_index
    return merged.drop(columns=["_decision", "_avail"])


def _build_segment(m1: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=m1.index)
    f["spread"] = m1["ask_c"] - m1["bid_c"]          # spread at the close of the bar

    m5 = resample_ohlc(m1, "5min")
    m5_feats = pd.DataFrame(index=m5.index)
    m5_feats["atr_m5"] = wilder_atr(m5["h"], m5["l"], m5["c"], 14)
    # volatility regime: where current ATR sits vs. the trailing ~20 trading days
    m5_feats["atr_m5_pct"] = m5_feats["atr_m5"].rolling(20 * 276, min_periods=2000).rank(pct=True)
    f = f.join(htf_to_ltf(m5_feats, pd.Timedelta(minutes=5), m1.index))

    h1 = resample_ohlc(m1, "1h")
    h1_feats = pd.DataFrame(index=h1.index)
    h1_feats["er_h1"] = efficiency_ratio(h1["c"], 12)
    h1_feats["ema_slope_h1"] = ema(h1["c"], 20).diff(3)
    return f.join(htf_to_ltf(h1_feats, pd.Timedelta(hours=1), m1.index))


def build_features(m1: pd.DataFrame) -> pd.DataFrame:
    """Lean, causal feature set used by the baseline strategy and regime labels.

    Computed independently inside each continuous data segment (no gap > 96 h): indicator
    state is never carried across a data hole (audit finding D1). Each segment restarts
    its warm-up, so the first bars of a segment have NaN features by design.
    """
    seg = segment_ids(m1.index)
    edges = [0, *(np.flatnonzero(np.diff(seg)) + 1).tolist(), len(m1)]
    parts = [_build_segment(m1.iloc[a:b]) for a, b in itertools.pairwise(edges) if b > a]
    f = pd.concat(parts) if parts else pd.DataFrame(index=m1.index)
    f["segment"] = seg
    return f
