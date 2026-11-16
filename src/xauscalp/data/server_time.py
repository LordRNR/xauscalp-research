"""MT5 server time -> UTC, without inventing the broker's timezone.

What MT5 provides (official MQL5 API):
  * bar/tick timestamps are SERVER time;
  * TimeTradeServer() - TimeGMT() gives the CURRENT offset only (TimeGMT() is derived from
    the local computer clock; in the Strategy Tester TimeGMT() equals server time);
  * TimeGMTOffset()/TimeDaylightSavings() describe the LOCAL computer, not the server;
  * there is NO API for the server's historical offsets/DST rule.
Applying the offset observed at export time to the whole history is therefore wrong
whenever the server observes DST (audit finding T1).

Policies:
  unknown   -> conversion refused (TimezoneUnknown). Default.
  fixed     -> constant offset, e.g. a server that is plain UTC.
  iana      -> the server follows a real IANA zone (e.g. "Europe/Athens").
  base_dst  -> UTC+base, +1h while ANOTHER zone observes DST (e.g. the common
               "UTC+2, +3 during US DST" convention: base=120, dst_of=America/New_York).
  inferred  -> per-trading-week offsets estimated by aligning broker bars with a UTC
               reference (Dukascopy); weeks without a confident match are dropped.
Declared policies (fixed/iana/base_dst) must still be VERIFIED with infer_weekly_offsets
on overlapping data before results are trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# trading-week boundary in server time: Saturday 12:00. The gold market is closed from
# Friday ~21:00 UTC to Sunday ~22:00 UTC, so for any offset in [-12h, +14h] no bar falls
# near this boundary and DST switches (which happen on Sunday mornings) never split a week.
WEEK_ANCHOR = pd.Timestamp("2000-01-01 12:00")  # a Saturday


class TimezoneUnknown(RuntimeError):
    pass


def _offset_minutes(utc: pd.DatetimeIndex, zone: str) -> np.ndarray:
    """UTC offset of `zone` at these instants, in minutes (unit-independent)."""
    loc = utc.tz_convert(zone).tz_localize(None)
    return ((loc - utc.tz_localize(None)) / pd.Timedelta(minutes=1)).to_numpy()


def _dst_mask(utc: pd.DatetimeIndex, zone: str) -> np.ndarray:
    """True where `zone` observes DST at these UTC instants (vectorised)."""
    years = sorted(set(utc.year))
    probes = pd.DatetimeIndex([pd.Timestamp(y, m, 15, tz="UTC") for y in years for m in (1, 7)])
    std = _offset_minutes(probes, zone).min()
    return _offset_minutes(utc, zone) > std


def trading_week_id(server_naive: pd.DatetimeIndex) -> np.ndarray:
    return ((server_naive - WEEK_ANCHOR) // pd.Timedelta(days=7)).to_numpy()


@dataclass(frozen=True)
class ServerTimePolicy:
    kind: str = "unknown"                 # unknown | fixed | iana | base_dst | inferred
    offset_min: int | None = None         # fixed
    zone: str | None = None               # iana
    base_min: int | None = None           # base_dst
    dst_of: str | None = None             # base_dst
    weekly_offsets_min: dict[int, int] = field(default_factory=dict)  # inferred
    source: str = ""                      # how it was established (for reports)

    @property
    def exact(self) -> bool:
        return self.kind != "unknown"

    def to_utc(self, server: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """Naive server timestamps -> tz-aware UTC. NaT where undeterminable."""
        if server.tz is not None:
            raise ValueError("server timestamps must be naive (server wall clock)")
        server = server.as_unit("ns")
        if self.kind == "unknown":
            raise TimezoneUnknown(
                "Server timezone unknown: refusing to convert. Declare a policy or infer it "
                "with infer_weekly_offsets() against a UTC reference (see docs).")
        if self.kind == "fixed":
            return (server - pd.Timedelta(minutes=self.offset_min)).tz_localize("UTC")
        if self.kind == "iana":
            return server.tz_localize(self.zone, ambiguous="NaT",
                                      nonexistent="NaT").tz_convert("UTC")
        if self.kind == "base_dst":
            base = pd.Timedelta(minutes=self.base_min)
            u1 = (server - base).tz_localize("UTC")                       # if no DST
            u2 = (server - base - pd.Timedelta(hours=1)).tz_localize("UTC")  # if DST
            ok1, ok2 = ~_dst_mask(u1, self.dst_of), _dst_mask(u2, self.dst_of)
            out = np.where(ok1 & ~ok2, u1.asi8, np.where(ok2 & ~ok1, u2.asi8, np.iinfo(np.int64).min))
            return pd.DatetimeIndex(out.view("M8[ns]")).tz_localize("UTC")
        if self.kind == "inferred":
            wk = trading_week_id(server)
            off = np.array([self.weekly_offsets_min.get(int(w), np.nan) for w in wk])
            ns = np.where(np.isnan(off), np.iinfo(np.int64).min,
                          server.asi8 - np.nan_to_num(off).astype(np.int64) * 60_000_000_000)
            return pd.DatetimeIndex(ns.view("M8[ns]")).tz_localize("UTC")
        raise ValueError(f"unknown policy kind {self.kind}")


def infer_weekly_offsets(
    broker_close: pd.Series,
    reference_close_utc: pd.Series,
    candidates_min: range = range(-12 * 60, 14 * 60 + 1, 30),
    min_overlap: int = 300,
    min_corr: float = 0.7,
    min_margin: float = 0.2,
) -> pd.DataFrame:
    """Estimate the server offset for each trading week by matching 1-minute returns.

    broker_close: naive server-time index; reference_close_utc: tz-aware UTC index.
    Returns one row per week: offset_min, corr, second_corr, n_overlap, confident.
    """
    ref = reference_close_utc.copy()
    ref.index = ref.index.tz_convert("UTC").tz_localize(None).as_unit("ns")
    ref_ret = ref.diff()
    ref_ret = ref_ret[ref.index.to_series().diff() == pd.Timedelta(minutes=1)]
    b = broker_close.copy()
    b.index = b.index.as_unit("ns")
    rows = []
    for wk, grp in b.groupby(trading_week_id(b.index)):
        r = grp.diff()[grp.index.to_series().diff() == pd.Timedelta(minutes=1)]
        scores = []
        for off in candidates_min:
            shifted = r.copy()
            shifted.index = shifted.index - pd.Timedelta(minutes=off)
            j = pd.concat([shifted, ref_ret], axis=1, join="inner").dropna()
            if len(j) >= min_overlap and j.iloc[:, 0].std() > 0 and j.iloc[:, 1].std() > 0:
                scores.append((float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1]), off, len(j)))
        if not scores:
            rows.append(dict(week=int(wk), offset_min=None, corr=np.nan, second_corr=np.nan,
                             n_overlap=0, confident=False))
            continue
        scores.sort(reverse=True)
        best, second = scores[0], (scores[1][0] if len(scores) > 1 else -1.0)
        rows.append(dict(week=int(wk), week_start_server=WEEK_ANCHOR + pd.Timedelta(days=7) * wk,
                         offset_min=best[1], corr=best[0], second_corr=second,
                         n_overlap=best[2],
                         confident=best[0] >= min_corr and best[0] - second >= min_margin))
    return pd.DataFrame(rows)


def policy_from_inference(table: pd.DataFrame, source: str) -> ServerTimePolicy:
    ok = table[table["confident"]]
    return ServerTimePolicy(kind="inferred", source=source,
                            weekly_offsets_min={int(w): int(o) for w, o in
                                                zip(ok["week"], ok["offset_min"])})


RULE_ZONES = {"base+US_DST": "America/New_York", "base+EU_DST": "Europe/London"}
EA_POLICY = {"fixed": "TZ_FIXED", "base+US_DST": "TZ_BASE_PLUS_US_DST",
             "base+EU_DST": "TZ_BASE_PLUS_EU_DST"}


@dataclass(frozen=True)
class RuleVerdict:
    """Which simple server-time rule explains EVERY confident week, and whether the data
    can tell the candidates apart.

    status: CONSISTENT (exactly one rule fits and the data discriminates) | AMBIGUOUS
    (several rules fit: the weeks that would separate them are missing) | INCONSISTENT
    (no simple rule fits: policy changed, or bad weeks) | INSUFFICIENT (too few weeks).
    """

    status: str
    rule: str | None
    base_min: int | None
    fits: dict[str, int | None]
    n_confident: int
    n_dst_mixed: dict[str, bool]
    n_us_eu_discriminating: int

    @property
    def ea_inputs(self) -> str | None:
        if self.status != "CONSISTENT":
            return None
        return f"InpTzPolicy={EA_POLICY[self.rule]}, InpTzBaseMinutes={self.base_min}"

    @property
    def cli_spec(self) -> str | None:
        if self.status != "CONSISTENT":
            return None
        if self.rule == "fixed":
            return f"fixed:{self.base_min}"
        return f"base_dst:{self.base_min}:{RULE_ZONES[self.rule]}"

    @property
    def policy(self) -> ServerTimePolicy | None:
        if self.status != "CONSISTENT":
            return None
        if self.rule == "fixed":
            return ServerTimePolicy(kind="fixed", offset_min=self.base_min, source="study04")
        return ServerTimePolicy(kind="base_dst", base_min=self.base_min,
                                dst_of=RULE_ZONES[self.rule], source="study04")


def fit_server_rule(table: pd.DataFrame, min_confident: int = 8,
                    min_discriminating: int = 1) -> RuleVerdict:
    """Fit fixed / base+US DST / base+EU DST to the confident weeks of infer_weekly_offsets.

    A rule is declared only when it is the ONLY one that fits and the data contains the
    weeks able to refute the alternatives:
      * DST vs fixed needs weeks on both sides of a DST switch of that zone;
      * US vs EU needs >= min_discriminating weeks where they disagree (2nd Sunday of
        March -> last Sunday of March, last Sunday of October -> 1st Sunday of November).
    """
    ok = table[table["confident"]] if len(table) else table
    n = len(ok)
    empty = RuleVerdict("INSUFFICIENT", None, None, {}, n, {}, 0)
    if n == 0:
        return empty
    # Tuesday ~noon server time: far from any DST switch (they happen on Sundays)
    mid = pd.DatetimeIndex(pd.to_datetime(ok["week_start_server"]) + pd.Timedelta(days=3)
                           ).tz_localize("UTC")
    off = ok["offset_min"].astype(int).to_numpy()
    dst = {name: _dst_mask(mid, zone) for name, zone in RULE_ZONES.items()}
    mixed = {name: bool(m.any() and (~m).any()) for name, m in dst.items()}
    disc = int((dst["base+US_DST"] != dst["base+EU_DST"]).sum())
    fits: dict[str, int | None] = {"fixed": int(off[0]) if len(set(off)) == 1 else None}
    for name, m in dst.items():
        base = off - 60 * m.astype(int)
        fits[name] = int(base[0]) if len(set(base)) == 1 else None
    fitting = [k for k, v in fits.items() if v is not None]
    if n < min_confident:
        return RuleVerdict("INSUFFICIENT", None, None, fits, n, mixed, disc)
    if not fitting:
        return RuleVerdict("INCONSISTENT", None, None, fits, n, mixed, disc)
    # can the evidence refute the alternatives?
    refutable = {
        "fixed": mixed["base+US_DST"] or mixed["base+EU_DST"],
        "base+US_DST": mixed["base+US_DST"] and disc >= min_discriminating,
        "base+EU_DST": mixed["base+EU_DST"] and disc >= min_discriminating,
    }
    if len(fitting) == 1 and refutable[fitting[0]]:
        r = fitting[0]
        return RuleVerdict("CONSISTENT", r, fits[r], fits, n, mixed, disc)
    return RuleVerdict("AMBIGUOUS", None, None, fits, n, mixed, disc)
