"""High-impact macro event blackout from a user-maintained CSV (no invented feeds).

config/events.csv columns: utc_time (ISO, UTC), event, impact (high|medium|low).
Populate it from OFFICIAL free sources (see docs/00_viabilidad.md §noticias):
  FOMC  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  CPI / NFP / unemployment  https://www.bls.gov/schedule/
If the file is empty the system cannot know about news: that is reported, not hidden,
and the volatility/spread gates remain the only protection.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_events(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    if df.empty:
        return pd.DataFrame({"utc_time": pd.DatetimeIndex([], tz="UTC"), "event": [],
                             "impact": []})
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True)
    return df.sort_values("utc_time").reset_index(drop=True)


def blackout_mask(index: pd.DatetimeIndex, events: pd.DataFrame, before_min: int = 30,
                  after_min: int = 30, impacts: tuple[str, ...] = ("high",)) -> np.ndarray:
    """True where a timestamp is within [event - before, event + after]."""
    ev = events[events["impact"].isin(impacts)]["utc_time"]
    mask = np.zeros(len(index), dtype=bool)
    t = index.as_unit("ns").asi8
    for e in ev:
        lo = (e - pd.Timedelta(minutes=before_min)).value
        hi = (e + pd.Timedelta(minutes=after_min)).value
        mask[np.searchsorted(t, lo, "left"):np.searchsorted(t, hi, "right")] = True
    return mask
