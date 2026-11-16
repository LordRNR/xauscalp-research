"""Baseline strategy: Opening-Range Breakout (ORB) at a session open.

Hypothesis (to be tested, not assumed): at the London open and the COMEX/New York open
gold's volatility expands; a close beyond the first N minutes' range may continue far
enough to pay costs.

Exact rules (one attempt per session per day):
  1. Opening range (OR) = Bid high/low of the first `or_minutes` M1 bars after the local
     session open (DST handled via zoneinfo). Need >= 80% of those bars present.
  2. Entry window: the next `entry_window_min` minutes. First M1 Bid CLOSE above
     OR_high + buffer_atr*ATR(M5) -> BUY; below OR_low - buffer -> SELL. Execute at the
     next bar open (Ask for buys, Bid for sells).
  3. SL = sl_atr * ATR(M5,14) from the fill; TP = tp_r * SL distance.
  4. Time stop: close after `max_hold_min` minutes.
  5. Spread gate (same as the Risk Manager's max_spread_usd, when given).
  6. Cost filter: skip if (spread + 2*slippage) > max_cost_frac * SL distance.
  7. Invalidation: missing ATR, gap in data at the decision bar.

orb_scan() returns ONE RECORD PER (day, session) with a status, so diagnostics can tell
"no technical signal" (NO_BREAKOUT) apart from "a breakout existed but was not tradable"
(REJECT_SPREAD / REJECT_COST / DATA_GAP_AT_SIGNAL). Rules are unchanged by the refactor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from xauscalp.config import CostModel
from xauscalp.features.sessions import local_anchor_utc
from xauscalp.strategies.base import Signal

STATUSES = ("NO_DATA", "OR_INCOMPLETE", "NO_ATR", "NO_BREAKOUT", "DATA_GAP_AT_SIGNAL",
            "REJECT_SPREAD", "REJECT_COST", "SIGNAL")
TECHNICAL_SIGNAL = {"DATA_GAP_AT_SIGNAL", "REJECT_SPREAD", "REJECT_COST", "SIGNAL"}


@dataclass(frozen=True)
class ORBParams:
    session: str
    tz: str
    open_hhmm: str
    or_minutes: int
    sl_atr: float
    tp_r: float
    entry_window_min: int = 60
    max_hold_min: int = 90
    buffer_atr: float = 0.10
    max_cost_frac: float = 0.20

    @property
    def name(self) -> str:
        return f"orb_{self.session}_or{self.or_minutes}_sl{self.sl_atr}_tp{self.tp_r}"


@dataclass
class ORBDayRecord:
    day: str
    session: str
    anchor_utc: str
    status: str
    or_bars: int = 0
    or_high: float = np.nan
    or_low: float = np.nan
    atr: float = np.nan
    or_width_atr: float = np.nan
    decision_idx: int = -1
    decision_time: str = ""
    direction: int = 0
    spread: float = np.nan
    sl_dist: float = np.nan
    cost: float = np.nan
    cost_frac: float = np.nan


def orb_scan(m1: pd.DataFrame, feats: pd.DataFrame, p: ORBParams, costs: CostModel,
             max_spread_usd: float | None = None) -> list[ORBDayRecord]:
    t = m1.index.as_unit("ns").asi8  # pandas>=3 defaults to us; Timestamp.value is ns
    bid_h = m1["bid_h"].to_numpy()
    bid_l = m1["bid_l"].to_numpy()
    bid_c = m1["bid_c"].to_numpy()
    spread = (m1["ask_c"] - m1["bid_c"]).to_numpy() + costs.extra_spread_usd
    atr = feats["atr_m5"].to_numpy()
    n = len(t)
    one_min = pd.Timedelta(minutes=1).value
    out: list[ORBDayRecord] = []
    if n == 0:
        return out

    for day in pd.bdate_range(m1.index[0].date(), m1.index[-1].date()):
        a = local_anchor_utc(day, p.tz, p.open_hhmm)
        rec = ORBDayRecord(day=str(day.date()), session=p.session, anchor_utc=str(a),
                           status="")
        out.append(rec)
        or_end = a + pd.Timedelta(minutes=p.or_minutes)
        i0, i1 = np.searchsorted(t, a.value), np.searchsorted(t, or_end.value)
        rec.or_bars = int(i1 - i0)
        if i1 == i0:
            rec.status = "NO_DATA"
            continue
        if i1 - i0 < 0.8 * p.or_minutes:
            rec.status = "OR_INCOMPLETE"
            continue
        rec.or_high, rec.or_low = float(bid_h[i0:i1].max()), float(bid_l[i0:i1].min())
        i2 = np.searchsorted(t, (or_end + pd.Timedelta(minutes=p.entry_window_min)).value)
        for i in range(i1, min(i2, n - 1)):
            a_ = atr[i]
            if not np.isfinite(a_) or a_ <= 0:
                rec.status = "NO_ATR"
                break
            rec.atr, rec.or_width_atr = float(a_), float((rec.or_high - rec.or_low) / a_)
            buf = p.buffer_atr * a_
            if bid_c[i] > rec.or_high + buf:
                d = 1
            elif bid_c[i] < rec.or_low - buf:
                d = -1
            else:
                continue
            sl = p.sl_atr * a_
            cost = spread[i] + 2 * costs.slippage_usd
            rec.decision_idx, rec.direction = i, d
            rec.decision_time = str(m1.index[i])
            rec.spread, rec.sl_dist, rec.cost = float(spread[i]), float(sl), float(cost)
            rec.cost_frac = float(cost / sl)
            if t[i + 1] - t[i] > 5 * one_min:
                rec.status = "DATA_GAP_AT_SIGNAL"
            elif max_spread_usd is not None and spread[i] > max_spread_usd:
                rec.status = "REJECT_SPREAD"
            elif cost > p.max_cost_frac * sl:
                rec.status = "REJECT_COST"
            else:
                rec.status = "SIGNAL"
            break
        if not rec.status:
            rec.status = "NO_BREAKOUT"
    return out


def records_to_signals(records: list[ORBDayRecord], p: ORBParams) -> list[Signal]:
    return [
        Signal(decision_idx=r.decision_idx, direction=r.direction, sl_dist=r.sl_dist,
               tp_dist=p.tp_r * r.sl_dist, max_hold_min=p.max_hold_min, strategy=p.name,
               session=p.session,
               context={"or_width_atr": r.or_width_atr, "atr_m5": r.atr,
                        "spread_at_signal": r.spread})
        for r in records if r.status == "SIGNAL"
    ]


def orb_signals(
    m1: pd.DataFrame, feats: pd.DataFrame, p: ORBParams, costs: CostModel,
    max_spread_usd: float | None = None,
) -> tuple[list[Signal], dict]:
    recs = orb_scan(m1, feats, p, costs, max_spread_usd)
    counts = pd.Series([r.status for r in recs]).value_counts().to_dict() if recs else {}
    stats = {s: int(counts.get(s, 0)) for s in STATUSES}
    stats.update(days=len(recs), no_trigger=stats["NO_BREAKOUT"],
                 cost_filtered=stats["REJECT_COST"], signals=stats["SIGNAL"])
    return records_to_signals(recs, p), stats


def records_frame(records: list[ORBDayRecord]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in records])
