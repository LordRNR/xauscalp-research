"""Daily signal generators for the preregistered multi-asset study (docs/08_hipotesis_multiactivo.md).

M1 = time-series momentum (sign of the last L sessions), M2 = Donchian breakout on daily bars.
M3 (FX mean reversion) reuses strategies.alt "mean_reversion" unchanged. Sessions close at 21:00 UTC
(the FX/metals rollover); the decision row is the last M1 row before the close and execution is the
next M1 open, as everywhere else. Indicators are causal; tests check truncation invariance.
GRID is CLOSED (18 configurations x basket): do not change it after seeing results.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from xauscalp.data.coverage import segment_ids
from xauscalp.features.core import resample_ohlc, wilder_atr
from xauscalp.strategies.alt import GRID as ALT_GRID
from xauscalp.strategies.alt import NO_TP, alt_signals
from xauscalp.strategies.base import Signal

CLOSE_HOUR_UTC = 21
SESSION_MIN = 24 * 60
GRID: dict[str, list[dict]] = {
    "m1_tsmom": [{"lookback": lb, "hold": h} for lb in (60, 120, 250) for h in (5, 20)],
    "m2_donchian": [{"n": n, "sl_atr": k} for n in (50, 100, 200) for k in (2.0, 3.0)],
    "m3_fx_reversion": ALT_GRID["mean_reversion"],           # z in {2, 2.5, 3} x sl_atr in {2, 3}
}
N_CONFIGS = sum(len(v) for v in GRID.values())               # 18
FX_ONLY = {"m3_fx_reversion"}


def all_configs(fx: bool) -> list[tuple[str, dict]]:
    return [(f, p) for f, ps in GRID.items() if fx or f not in FX_ONLY for p in ps]


def _daily(seg: pd.DataFrame):
    """Daily bid bars closing at 21:00 UTC + decision row (within seg) + completeness."""
    shifted = seg.copy()
    shifted.index = seg.index - pd.Timedelta(hours=CLOSE_HOUR_UTC)
    b = resample_ohlc(shifted, "1D")
    b.index = b.index + pd.Timedelta(hours=CLOSE_HOUR_UTC)           # label = bar OPEN (prev 21:00)
    t = seg.index.as_unit("ns").asi8
    end = (b.index + pd.Timedelta(days=1)).as_unit("ns").asi8
    pos = np.searchsorted(t, end, side="left") - 1
    ok = pos >= 0
    pos = np.where(ok, pos, 0)
    complete = ok & (t[pos] >= end - pd.Timedelta(minutes=10).value) & (t[pos] < end)
    return b, pos, complete


def _segment(seg: pd.DataFrame, offset: int, family: str, p: dict) -> list[Signal]:
    b, pos, complete = _daily(seg)
    if len(b) < 260:
        return []
    c = b["c"]
    atr = wilder_atr(b["h"], b["l"], b["c"]).to_numpy()
    if family == "m1_tsmom":
        ret = (c / c.shift(p["lookback"]) - 1.0).to_numpy()
        long_, short_ = ret > 0, ret < 0
        sl_mult, hold = 3.0, p["hold"] * SESSION_MIN
    elif family == "m2_donchian":
        hi, lo = b["h"].rolling(p["n"]).max().shift(1), b["l"].rolling(p["n"]).min().shift(1)
        long_, short_ = (c > hi).to_numpy(), (c < lo).to_numpy()
        sl_mult, hold = p["sl_atr"], 60 * SESSION_MIN
    else:
        raise ValueError(family)
    name = family + ":" + ",".join(f"{k}={v}" for k, v in p.items())
    out = []
    for i in np.flatnonzero(complete & np.isfinite(atr) & (long_ | short_)):
        sl = sl_mult * atr[i]
        if np.isfinite(sl) and sl > 0:
            out.append(Signal(decision_idx=int(offset + pos[i]), direction=1 if long_[i] else -1, sl_dist=float(sl),
                              tp_dist=float(NO_TP * sl), max_hold_min=int(hold), strategy=name, session=family,
                              context={"atr": float(atr[i])}))
    return out


def multi_signals(m1: pd.DataFrame, family: str, params: dict) -> list[Signal]:
    if family == "m3_fx_reversion":
        return alt_signals(m1, "mean_reversion", params)
    seg = segment_ids(m1.index)
    edges = [0, *(np.flatnonzero(np.diff(seg)) + 1).tolist(), len(m1)]
    sigs: list[Signal] = []
    for a, b in itertools.pairwise(edges):
        if b > a:
            sigs += _segment(m1.iloc[a:b], a, family, params)
    sigs.sort(key=lambda s: s.decision_idx)
    return sigs
