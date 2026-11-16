"""Trading-session labels computed from UTC timestamps with real DST rules (zoneinfo).

Sessions are defined in each market's LOCAL time, so DST shifts are handled
automatically (London and New York change DST on different dates).
  asia     : Tokyo 08:00-17:00 JST (no DST in Japan)
  london   : London 08:00-16:30 local
  newyork  : New York 08:00-17:00 local
  overlap  : london AND newyork
  off      : everything else (e.g. late US / pre-Asia)
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TOKYO = ZoneInfo("Asia/Tokyo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


def _local_minutes(idx: pd.DatetimeIndex, tz: ZoneInfo) -> np.ndarray:
    loc = idx.tz_convert(tz)
    return (loc.hour * 60 + loc.minute).to_numpy()


def in_window(idx: pd.DatetimeIndex, tz: ZoneInfo, start: str, end: str) -> np.ndarray:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    m = _local_minutes(idx, tz)
    return (m >= sh * 60 + sm) & (m < eh * 60 + em)


def session_labels(idx: pd.DatetimeIndex) -> pd.Series:
    if idx.tz is None:
        raise ValueError("index must be tz-aware (UTC)")
    asia = in_window(idx, TOKYO, "08:00", "17:00")
    lon = in_window(idx, LONDON, "08:00", "16:30")
    ny = in_window(idx, NEW_YORK, "08:00", "17:00")
    lab = np.full(len(idx), "off", dtype=object)
    lab[asia] = "asia"
    lab[ny] = "newyork"
    lab[lon] = "london"
    lab[lon & ny] = "overlap"
    return pd.Series(lab, index=idx, name="session")


def local_anchor_utc(day: pd.Timestamp, tz: str, hhmm: str) -> pd.Timestamp:
    """UTC timestamp of local time `hhmm` on calendar date `day` in timezone `tz`."""
    h, m = map(int, hhmm.split(":"))
    loc = pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=h, minute=m, tz=tz)
    return loc.tz_convert("UTC")
