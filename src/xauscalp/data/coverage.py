"""Temporal coverage & quality report for M1 bid/ask histories (audit finding D1).

Definitions (documented approximations):
  * trading date  = calendar date of (UTC time + 2h). Gold CFDs trade ~23h/day from
    Sunday evening to Friday evening; +2h maps Sunday-evening bars to Monday and keeps the
    daily maintenance break between dates.
  * expected days = Monday..Friday trading dates in [start, end]. Exchange holidays are
    counted as expected (and will show as missing): no holiday calendar is assumed.
  * expected bars = 23 h x 60 = 1380 per expected day (approximate; early closes exist).
  * usable day    = a day with >= 80% of expected bars.
  * segment       = run of bars without a gap > 96 h (a normal weekend is ~49 h).
Indicators are computed per segment so nothing is ever carried across a data hole.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SEGMENT_GAP = pd.Timedelta(hours=96)
EXPECTED_BARS_PER_DAY = 1380
USABLE_DAY_FRAC = 0.80
TRADING_DATE_SHIFT = pd.Timedelta(hours=2)


def segment_ids(index: pd.DatetimeIndex, max_gap: pd.Timedelta = SEGMENT_GAP) -> np.ndarray:
    if len(index) == 0:
        return np.array([], dtype=np.int64)
    gaps = np.diff(index.as_unit("ns").asi8) > max_gap.value
    return np.concatenate([[0], np.cumsum(gaps)]).astype(np.int64)


def trading_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return (index + TRADING_DATE_SHIFT).tz_convert("UTC").normalize()


@dataclass
class CoverageReport:
    start: str
    end: str
    expected_days: int
    days_with_data: int
    usable_days: int
    missing_days: int
    expected_bars: int
    available_bars: int
    coverage_pct: float
    duplicates: int
    invalid_prices: int
    bad_ohlc: int
    negative_spread: int
    zero_spread: int
    extreme_spread: int
    ask_below_bid_extremes: int
    spread_median: float
    spread_p99: float
    by_month: pd.DataFrame = field(repr=False)
    segments: pd.DataFrame = field(repr=False)
    gaps: pd.DataFrame = field(repr=False)
    missing_ranges: list[tuple[str, str]] = field(repr=False, default_factory=list)

    def usable_fraction(self, start: pd.Timestamp, end: pd.Timestamp) -> float:
        """Share of expected trading days in [start, end) that are usable."""
        bm = self._daily
        sel = bm[(bm.index >= start.tz_convert("UTC").normalize())
                 & (bm.index < end.tz_convert("UTC").normalize())]
        return float(sel["usable"].mean()) if len(sel) else 0.0

    _daily: pd.DataFrame = field(repr=False, default=None)

    def to_markdown(self) -> str:
        head = (
            f"| métrica | valor |\n|---|---|\n"
            f"| periodo | {self.start} → {self.end} |\n"
            f"| días esperados (L-V) | {self.expected_days} |\n"
            f"| días con datos / utilizables (≥80 %) | {self.days_with_data} / {self.usable_days} |\n"
            f"| días ausentes | {self.missing_days} |\n"
            f"| barras M1 esperadas / disponibles | {self.expected_bars:,} / {self.available_bars:,} |\n"
            f"| **cobertura** | **{self.coverage_pct:.1f} %** |\n"
            f"| duplicados | {self.duplicates} |\n"
            f"| precios inválidos (≤0 o no finitos) | {self.invalid_prices} |\n"
            f"| velas OHLC incoherentes | {self.bad_ohlc} |\n"
            f"| spread negativo / cero / extremo (>5 $) | {self.negative_spread} / "
            f"{self.zero_spread} / {self.extreme_spread} |\n"
            f"| Ask_low < Bid_low (anomalía bid/ask) | {self.ask_below_bid_extremes} |\n"
            f"| spread mediano / p99 ($) | {self.spread_median:.3f} / {self.spread_p99:.3f} |\n"
        )
        return (head + "\n**Segmentos continuos**\n\n" + _md(self.segments)
                + "\n\n**Cobertura por mes**\n\n" + _md(self.by_month)
                + "\n\n**Huecos > 96 h (rompen la continuidad)**\n\n" + _md(self.gaps))


def _md(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(ninguno)_"
    cols = [str(df.index.name or "")] + [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for i, r in df.iterrows():
        cells = [str(i)] + [f"{v:.1f}" if isinstance(v, float) else str(v) for v in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def coverage_report(m1: pd.DataFrame, start: str | pd.Timestamp,
                    end: str | pd.Timestamp) -> CoverageReport:
    """Coverage of `m1` against the requested [start, end] (inclusive dates, UTC)."""
    start = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tz is None else pd.Timestamp(start)
    end = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tz is None else pd.Timestamp(end)
    expected = pd.bdate_range(start.normalize(), end.normalize(), tz="UTC")
    idx = m1.index
    dup = int(idx.duplicated().sum())
    m = m1[~idx.duplicated()]
    td = trading_dates(m.index)
    per_day = pd.Series(1, index=td).groupby(level=0).sum()
    daily = pd.DataFrame(index=expected)
    daily["bars"] = per_day.reindex(expected).fillna(0).astype(int)
    daily["usable"] = daily["bars"] >= USABLE_DAY_FRAC * EXPECTED_BARS_PER_DAY
    daily["has_data"] = daily["bars"] > 0

    price_cols = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]
    px = m[price_cols].to_numpy()
    invalid = int((~np.isfinite(px) | (px <= 0)).any(axis=1).sum())
    bad = 0
    for s in ("bid", "ask"):
        o, h, l, c = (m[f"{s}_{x}"] for x in "ohlc")
        bad += int(((h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)).sum())
    spread = (m["ask_c"] - m["bid_c"])
    month = daily.groupby(daily.index.strftime("%Y-%m")).agg(
        expected_days=("bars", "size"), days_with_data=("has_data", "sum"),
        usable_days=("usable", "sum"), bars=("bars", "sum"))
    month["coverage_pct"] = 100 * month["bars"] / (month["expected_days"] * EXPECTED_BARS_PER_DAY)
    month.index.name = "mes"

    seg = segment_ids(m.index)
    segs = pd.DataFrame({"t": m.index, "seg": seg}).groupby("seg")["t"].agg(["min", "max", "size"])
    segs.columns = ["desde", "hasta", "barras"]
    segs["desde"], segs["hasta"] = segs["desde"].astype(str), segs["hasta"].astype(str)
    segs.index.name = "segmento"
    d = m.index.to_series().diff()
    big = d[d > SEGMENT_GAP]
    gaps = pd.DataFrame({"tras": big.index.astype(str), "duración": big.astype(str).values})
    gaps.index.name = "#"

    miss = daily.index[~daily["has_data"]]
    ranges: list[tuple[str, str]] = []
    if len(miss):
        grp = (miss.to_series().diff() > pd.Timedelta(days=4)).cumsum()
        for _, g in miss.to_series().groupby(grp.values):
            ranges.append((str(g.iloc[0].date()), str(g.iloc[-1].date())))

    rep = CoverageReport(
        start=str(start.date()), end=str(end.date()),
        expected_days=len(expected), days_with_data=int(daily["has_data"].sum()),
        usable_days=int(daily["usable"].sum()), missing_days=int((~daily["has_data"]).sum()),
        expected_bars=len(expected) * EXPECTED_BARS_PER_DAY, available_bars=len(m),
        coverage_pct=100 * len(m) / max(1, len(expected) * EXPECTED_BARS_PER_DAY),
        duplicates=dup, invalid_prices=invalid, bad_ohlc=bad,
        negative_spread=int((spread < 0).sum()), zero_spread=int((spread == 0).sum()),
        extreme_spread=int((spread > 5.0).sum()),
        ask_below_bid_extremes=int((m["ask_l"] < m["bid_l"]).sum()),
        spread_median=float(spread.median()) if len(m) else float("nan"),
        spread_p99=float(spread.quantile(0.99)) if len(m) else float("nan"),
        by_month=month, segments=segs, gaps=gaps, missing_ranges=ranges,
    )
    rep._daily = daily
    return rep
