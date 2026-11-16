"""Alternative XAUUSD signal generators: trend, momentum, pullback, mean reversion.

PREREGISTERED in docs/06_hipotesis_alternativas.md (same commit, before any result). The
grid below is CLOSED: 22 configurations. Do not add families, parameters or filters after
seeing results (write a new dated version instead).

Conventions (as the rest of the engine): bars are built from M1 BID within each continuous
data segment; a signal is decided at the CLOSE of a bar (its decision row is the last M1 row
of that bar) and executed at the open of the next M1 row. Indicators are causal (rolling /
ewm on closed bars only); `tests/test_alt_strategies.py` checks truncation invariance.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from xauscalp.data.coverage import segment_ids
from xauscalp.features.core import resample_ohlc, wilder_atr
from xauscalp.strategies.base import Signal

H1 = pd.Timedelta(hours=1)
M15 = pd.Timedelta(minutes=15)
NO_TP = 50.0                      # tp = 50 x SL: effectively none (exit by SL or time)
MOMENTUM_DECISION_HOUR_UTC = 8    # decide at the 07:00-08:00 UTC bar close, fixed (not tuned)

GRID: dict[str, list[dict]] = {
    "trend_donchian": [{"n": n, "sl_atr": k} for n in (24, 48, 96) for k in (2.0, 3.0)],
    "momentum_tsmom": [{"lookback_h": lb, "hold_h": h} for lb in (24, 72, 168) for h in (24, 48)],
    "pullback": [{"sl_atr": s, "tp_r": t} for s in (1.5, 2.5) for t in (1.5, 2.5)],
    "mean_reversion": [{"z": z, "sl_atr": s} for z in (2.0, 2.5, 3.0) for s in (2.0, 3.0)],
}
N_CONFIGS = sum(len(v) for v in GRID.values())          # 22


def config_name(family: str, params: dict) -> str:
    return family + ":" + ",".join(f"{k}={v}" for k, v in params.items())


def all_configs() -> list[tuple[str, dict]]:
    return [(f, p) for f, ps in GRID.items() for p in ps]


def _bars(seg: pd.DataFrame, period: pd.Timedelta):
    """Bid OHLC bars + decision row (within seg) + completeness flag."""
    rule = "1h" if period == H1 else "15min"
    b = resample_ohlc(seg, rule)
    t = seg.index.as_unit("ns").asi8
    end = (b.index + period).as_unit("ns").asi8
    pos = np.searchsorted(t, end, side="left") - 1
    ok = pos >= 0
    pos = np.where(ok, pos, 0)
    complete = ok & (t[pos] == end - pd.Timedelta(minutes=1).value)
    return b, pos, complete


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


def _mk(offset, pos, i, d, sl, tp, hold_min, family, name, atr):
    if not (np.isfinite(sl) and sl > 0 and np.isfinite(tp) and tp > 0):
        return None
    return Signal(decision_idx=int(offset + pos[i]), direction=int(d), sl_dist=float(sl),
                  tp_dist=float(tp), max_hold_min=int(hold_min), strategy=name, session=family,
                  context={"atr": float(atr)})


def _segment_signals(seg: pd.DataFrame, offset: int, family: str, p: dict) -> list[Signal]:
    name = config_name(family, p)
    out: list[Signal] = []
    if family == "mean_reversion":
        b, pos, complete = _bars(seg, M15)
    else:
        b, pos, complete = _bars(seg, H1)
    if len(b) < 250:
        return out
    atr = wilder_atr(b["h"], b["l"], b["c"]).to_numpy()
    c = b["c"]
    cond_long = np.zeros(len(b), bool)
    cond_short = np.zeros(len(b), bool)
    sl_mult, tp_fn, hold = 1.0, None, 60
    if family == "trend_donchian":
        n = p["n"]
        hi = b["h"].rolling(n).max().shift(1)
        lo = b["l"].rolling(n).min().shift(1)
        cond_long, cond_short = (c > hi).to_numpy(), (c < lo).to_numpy()
        sl_mult, hold = p["sl_atr"], 120 * 60
    elif family == "momentum_tsmom":
        ret = (c / c.shift(p["lookback_h"]) - 1.0).to_numpy()
        at_hour = (b.index + H1).hour == MOMENTUM_DECISION_HOUR_UTC
        cond_long, cond_short = at_hour & (ret > 0), at_hour & (ret < 0)
        sl_mult, hold = 3.0, p["hold_h"] * 60
    elif family == "pullback":
        e50, e200 = c.ewm(span=50, adjust=False, min_periods=50).mean(), \
            c.ewm(span=200, adjust=False, min_periods=200).mean()
        r = _rsi(c)
        up, dn = (e50 > e200) & (c > e200), (e50 < e200) & (c < e200)
        cond_long = ((r.shift(1) < 40) & (r >= 40) & up).to_numpy()
        cond_short = ((r.shift(1) > 60) & (r <= 60) & dn).to_numpy()
        sl_mult, hold = p["sl_atr"], 48 * 60
    elif family == "mean_reversion":
        mean, sd = c.rolling(96).mean(), c.rolling(96).std()
        z = ((c - mean) / sd.replace(0, np.nan)).to_numpy()
        er = ((c - c.shift(96)).abs() / c.diff().abs().rolling(96).sum().replace(0, np.nan)).to_numpy()
        rng = er < 0.30
        cond_long, cond_short = rng & (z <= -p["z"]), rng & (z >= p["z"])
        sl_mult, hold = p["sl_atr"], 12 * 60
        mean_v = mean.to_numpy()
        tp_fn = lambda i: abs(c.iat[i] - mean_v[i])
    else:
        raise ValueError(family)
    valid = complete & np.isfinite(atr)
    for i in np.flatnonzero(valid & (cond_long | cond_short)):
        d = 1 if cond_long[i] else -1
        sl = sl_mult * atr[i]
        if family == "pullback":
            tp = p["tp_r"] * sl
        elif family == "mean_reversion":
            tp = tp_fn(i)
        else:
            tp = NO_TP * sl
        s = _mk(offset, pos, i, d, sl, tp, hold, family, name, atr[i])
        if s is not None:
            out.append(s)
    return out


def alt_signals(m1: pd.DataFrame, family: str, params: dict) -> list[Signal]:
    """Signals of one configuration over all continuous segments of `m1` (UTC index)."""
    seg = segment_ids(m1.index)
    edges = [0, *(np.flatnonzero(np.diff(seg)) + 1).tolist(), len(m1)]
    sigs: list[Signal] = []
    for a, b in itertools.pairwise(edges):
        if b > a:
            sigs += _segment_signals(m1.iloc[a:b], a, family, params)
    sigs.sort(key=lambda s: s.decision_idx)
    return sigs
