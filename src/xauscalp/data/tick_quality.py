"""Quality and spread analysis of broker tick exports (XAU_ExportTicks.mq5).

Three different claims must never be confused:
  1. "ticks were exported"            -> a file exists (checked by integrity()).
  2. "the history is complete enough" -> coverage + agreement with the server's own M1 bars
     (compare_with_m1()): every weekday present, no long silent gaps, and the tick counts
     reproduce the bars' tick_volume and OHLC.
  3. "a strategy is profitable"       -> needs a validated backtest; nothing here says that.

All functions take ticks with a UTC DatetimeIndex and columns bid, ask (flags optional).
Time-weighted statistics weight each quote by how long it was the live quote, capped at
CAP_S seconds so market-closed periods and feed stalls do not dominate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CAP_S = 60.0
# MqlTick.flags: the official page lists BID/ASK/LAST/VOLUME/BUY/SELL without numeric values
# and does NOT document bits 128 and 1024 that appear on >99 % of this server's ticks.
# They are reported as-is and given no meaning.
GAP_THRESHOLDS_S = (5, 30, 60, 300)


def clean_quotes(ticks: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop quotes that cannot be real (non-finite, bid <= 0, ask < bid). Returns counts."""
    bid, ask = ticks["bid"].to_numpy(float), ticks["ask"].to_numpy(float)
    nonfinite = ~(np.isfinite(bid) & np.isfinite(ask))
    with np.errstate(invalid="ignore"):
        nonpos = (bid <= 0) | (ask <= 0)
        crossed = ask < bid
    bad = nonfinite | nonpos | crossed
    return ticks[~bad], {"non_finite": int(nonfinite.sum()), "non_positive": int(nonpos.sum()),
                         "crossed": int(crossed.sum()), "dropped": int(bad.sum())}


def integrity(ticks: pd.DataFrame) -> dict:
    ts = ticks.index.as_unit("ns").asi8
    out: dict = {"n": len(ticks)}
    _, cnt = clean_quotes(ticks)
    out.update(cnt)
    sp = (ticks["ask"] - ticks["bid"]).to_numpy()
    out["zero_spread"] = int((np.abs(sp) < 1e-9).sum())
    out["same_timestamp_pairs"] = int((np.diff(ts) == 0).sum())
    out["monotonic"] = bool((np.diff(ts) >= 0).all())
    same = (ticks["bid"].diff() == 0) & (ticks["ask"].diff() == 0)
    out["consecutive_identical_quotes"] = int(same.sum())
    if "flags" in ticks:
        out["flags"] = {int(k): int(v) for k, v in ticks["flags"].value_counts().items()}
    return out


def daily_coverage(ticks: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """One row per calendar UTC day in [first, last]: weekday, tick count."""
    days = pd.date_range(first.normalize(), last.normalize(), freq="D", tz="UTC")
    n = pd.Series(1, index=ticks.index).groupby(ticks.index.normalize()).size()
    df = pd.DataFrame({"weekday": days.day_name().str[:3], "ticks": n.reindex(days).fillna(0)
                       .astype(int).to_numpy()}, index=days.date)
    df.index.name = "day_utc"
    return df


def gap_table(ticks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Silent periods between consecutive ticks, as (counts, top gaps).

    Categories: 30 s - 5 min, real silences in (5 min, 30 min], the scheduled daily break in
    (30 min, 6 h] (one per trading night) and weekly closes (> 6 h). The two long categories
    are expected from the market calendar and are not data faults."""
    ts = ticks.index.as_unit("ns").asi8
    d = np.diff(ts) / 1e9
    rows = [{"category": "30 s - 5 min", "count": int(((d > 30) & (d <= 300)).sum())},
            {"category": "5 - 30 min (silence)", "count": int(((d > 300) & (d <= 1800)).sum())},
            {"category": "30 min - 6 h (daily break)",
             "count": int(((d > 1800) & (d <= 6 * 3600)).sum())},
            {"category": "> 6 h (weekly close)", "count": int((d > 6 * 3600).sum())}]
    idx = np.argsort(-np.where(d <= 1800, d, 0))[:10]
    top = pd.DataFrame({"gap_start_utc": ticks.index[idx], "seconds": d[idx]})
    return pd.DataFrame(rows).set_index("category"), top.reset_index(drop=True)


def silences_vs_bars(ticks: pd.DataFrame, bars: pd.DataFrame, min_s: float = 300,
                     max_s: float = 1800) -> pd.DataFrame:
    """Each silence in (min_s, max_s] and how many server M1 bars fall inside it.

    0 bars inside = the SERVER itself recorded nothing (feed outage), not an export loss."""
    ts = ticks.index.as_unit("ns").asi8
    d = np.diff(ts) / 1e9
    rows = []
    for i in np.where((d > min_s) & (d <= max_s))[0]:
        a, z = ticks.index[i], ticks.index[i + 1]
        inside = bars[(bars.index > a.floor("min")) & (bars.index < z.floor("min"))]
        rows.append({"start_utc": a, "end_utc": z, "seconds": float(d[i]),
                     "server_bars_inside": len(inside)})
    return pd.DataFrame(rows, columns=["start_utc", "end_utc", "seconds", "server_bars_inside"])


def durations(ticks: pd.DataFrame, cap_s: float = CAP_S) -> np.ndarray:
    """Seconds each quote stayed live (capped); the last tick gets 0."""
    ts = ticks.index.as_unit("ns").asi8
    d = np.zeros(len(ts))
    d[:-1] = np.minimum(np.diff(ts) / 1e9, cap_s)
    return d


def weighted_quantile(values: np.ndarray, weights: np.ndarray, qs: list[float]) -> np.ndarray:
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    keep = np.isfinite(values) & (weights > 0)
    if not keep.any():
        return np.full(len(qs), np.nan)
    v, w = values[keep], weights[keep]
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    cum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(qs, cum, v)


QS = [0.5, 0.75, 0.9, 0.95, 0.99]


def spread_stats(ticks: pd.DataFrame, thresholds: tuple[float, ...] = (0.30, 0.60, 1.00)) -> dict:
    """Tick-weighted and time-weighted spread (ask - bid) summary."""
    sp = (ticks["ask"] - ticks["bid"]).to_numpy(float)
    w = durations(ticks)
    out: dict = {"ticks": len(sp), "seconds_weighted": float(w.sum())}
    out["tick_q"] = dict(zip(QS, np.quantile(sp, QS), strict=True))
    out["time_q"] = dict(zip(QS, weighted_quantile(sp, w, QS), strict=True))
    out["tick_mean"] = float(sp.mean())
    out["time_mean"] = float((sp * w).sum() / w.sum()) if w.sum() > 0 else float("nan")
    out["max"] = float(sp.max())
    out["share_time_above"] = {t: float(w[sp > t].sum() / w.sum()) if w.sum() > 0 else float("nan")
                               for t in thresholds}
    return out


def spread_by_hour(ticks: pd.DataFrame, thresholds: tuple[float, ...] = (0.60,)) -> pd.DataFrame:
    """Per UTC hour: ticks, time-weighted mean/p50/p90/p99 and share of time above thresholds."""
    sp = (ticks["ask"] - ticks["bid"]).to_numpy(float)
    w = durations(ticks)
    hour = ticks.index.hour.to_numpy()
    rows = []
    for h in range(24):
        m = hour == h
        if not m.any():
            continue
        q = weighted_quantile(sp[m], w[m], [0.5, 0.9, 0.99])
        row = {"hour_utc": h, "ticks": int(m.sum()),
               "tw_mean": float((sp[m] * w[m]).sum() / max(w[m].sum(), 1e-9)),
               "p50": q[0], "p90": q[1], "p99": q[2]}
        for t in thresholds:
            row[f"time>{t:g}"] = float(w[m & (sp > t)].sum() / max(w[m].sum(), 1e-9))
        rows.append(row)
    return pd.DataFrame(rows).set_index("hour_utc")


def minute_frame(ticks: pd.DataFrame) -> pd.DataFrame:
    """Per UTC minute: tick count, bid OHLC and spread first/last/min/max/tick-mean/time-mean."""
    sp = (ticks["ask"] - ticks["bid"]).rename("sp")
    w = pd.Series(durations(ticks), index=ticks.index, name="w")
    df = pd.concat([ticks["bid"], sp, w, (sp * w).rename("spw")], axis=1)
    g = df.groupby(df.index.floor("min"))
    out = pd.DataFrame({
        "n": g["bid"].size(), "bid_o": g["bid"].first(), "bid_h": g["bid"].max(),
        "bid_l": g["bid"].min(), "bid_c": g["bid"].last(),
        "sp_first": g["sp"].first(), "sp_last": g["sp"].last(), "sp_min": g["sp"].min(),
        "sp_max": g["sp"].max(), "sp_mean": g["sp"].mean(),
    })
    out["sp_tw"] = g["spw"].sum() / g["w"].sum().replace(0, np.nan)
    if "flags" in ticks:
        bid_chg = (ticks["flags"].to_numpy() & 2) > 0          # TICK_FLAG_BID: bid changed
        out["n_bid"] = pd.Series(bid_chg, index=ticks.index).groupby(
            ticks.index.floor("min")).sum().astype(int)
    return out


def compare_with_m1(minutes: pd.DataFrame, bars: pd.DataFrame, tol: float = 0.005) -> dict:
    """Do the exported ticks reproduce the server's own M1 bars?

    `bars` (UTC index): open, high, low, close, tick_volume, spread (price units).
    Restricted to the minutes covered by the ticks. Reports missing minutes, OHLC agreement,
    the ratio exported-ticks / tick_volume, and which tick statistic MqlRates.spread equals."""
    lo, hi = minutes.index.min(), minutes.index.max()
    b = bars[(bars.index >= lo) & (bars.index <= hi)]
    j = b.join(minutes, how="inner")
    out: dict = {"bars_in_window": len(b), "bars_with_ticks": len(j),
                 "bars_without_ticks": len(b) - len(j),
                 "minutes_with_ticks_without_bar": len(minutes.index.difference(b.index))}
    if j.empty:
        return out
    for tick_col, bar_col in (("bid_o", "open"), ("bid_h", "high"), ("bid_l", "low"),
                              ("bid_c", "close")):
        diff = (j[tick_col] - j[bar_col]).abs()
        out[f"ohlc_{bar_col}_equal"] = float((diff <= tol).mean())
        out[f"ohlc_{bar_col}_maxdiff"] = float(diff.max())
    ratio = j["n"] / j["tick_volume"].replace(0, np.nan)
    out["tickcount_equal_share"] = float((j["n"] == j["tick_volume"]).mean())
    out["tickcount_ratio_q"] = dict(zip([0.01, 0.05, 0.5, 0.95, 0.99],
                                        ratio.quantile([0.01, 0.05, 0.5, 0.95, 0.99]), strict=True))
    out["tickcount_total_ratio"] = float(j["n"].sum() / j["tick_volume"].sum())
    if "n_bid" in j:
        out["bidtick_equals_tickvolume_share"] = float((j["n_bid"] == j["tick_volume"]).mean())
        out["bidtick_total_ratio"] = float(j["n_bid"].sum() / j["tick_volume"].sum())
    out["bar_spread_equals"] = {
        k: float(((j["spread"] - j[col]).abs() <= tol).mean())
        for k, col in (("first_tick", "sp_first"), ("last_tick", "sp_last"),
                       ("min_in_minute", "sp_min"), ("max_in_minute", "sp_max"),
                       ("time_weighted_mean", "sp_tw"))}
    out["bar_spread_vs_min_signed_q"] = dict(zip(
        [0.05, 0.5, 0.95], (j["spread"] - j["sp_min"]).quantile([0.05, 0.5, 0.95]), strict=True))
    return out


def first_tick_spread_at(ticks: pd.DataFrame, when_utc: pd.DatetimeIndex,
                         max_wait_s: float = 60.0) -> np.ndarray:
    """Spread of the first tick at or after each instant (what the EA reads when a new M1 bar
    opens). NaN if no tick arrives within max_wait_s."""
    ts = ticks.index.as_unit("ns").asi8
    want = pd.DatetimeIndex(when_utc).as_unit("ns").asi8
    pos = np.searchsorted(ts, want, side="left")
    sp = (ticks["ask"] - ticks["bid"]).to_numpy(float)
    out = np.full(len(want), np.nan)
    ok = pos < len(ts)
    wait = np.where(ok, ts[np.minimum(pos, len(ts) - 1)] - want, np.inf) / 1e9
    good = ok & (wait <= max_wait_s)
    out[good] = sp[pos[good]]
    return out


def contiguous_blocks(minutes: pd.DatetimeIndex) -> pd.DataFrame:
    """Group minute stamps into contiguous blocks (start, end, n)."""
    if len(minutes) == 0:
        return pd.DataFrame(columns=["start_utc", "end_utc", "minutes"])
    m = pd.DatetimeIndex(sorted(minutes))
    brk = np.where(np.diff(m.as_unit("ns").asi8) != 60 * 10**9)[0] + 1
    starts, ends = np.r_[0, brk], np.r_[brk - 1, len(m) - 1]
    return pd.DataFrame({"start_utc": m[starts], "end_utc": m[ends], "minutes": ends - starts + 1})
