"""Bar-based backtest engine on M1 Bid/Ask bars with conservative fill rules.

Fill model (documented assumptions, all pessimistic where ambiguous):
  - Entry: market order at the OPEN of the bar after the decision. Buy at Ask, sell at
    Bid, plus adverse slippage. Broker spread = Dukascopy spread + extra_spread
    (applied symmetrically: Ask += extra/2, Bid -= extra/2).
  - Long exits trade at Bid; short exits at Ask.
  - Stop loss: triggered if the bar's adverse extreme crosses it. Fill = SL price, or the
    bar OPEN if it gapped beyond the stop, plus adverse slippage.
  - Take profit: limit fill at TP (or better on a favourable gap), no slippage.
  - If SL and TP are both touched inside the same M1 bar, we assume the SL came first.
  - Time stop: market exit at the open of the first bar at/after entry + max_hold.
  - One position at a time. Signals arriving while a position is open are skipped.
  - Commission is charged per lot round-turn and converted to price units per oz.
  - Data holes: if a gap > 96 h (a hole in the DATA, not a market weekend) occurs while a
    position is open, the outcome is unknowable: the trade is closed at the last bar
    before the hole and flagged valid=False (excluded from metrics, but counted). Normal
    weekend/maintenance gaps keep the position open and fill at the reopening price.
    Trades still open when data ends are also valid=False ("END").
Results are reported per 0.01 lot (1 oz for a 100-oz contract) and in R multiples.

EVIDENCE LEVEL: this is an M1-bar approximation (level 1). Intrabar order of events is
unknown; it is NOT equivalent to a real-tick backtest (level 2: MT5 Strategy Tester
"every tick based on real ticks") nor to DEMO forward testing (level 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from xauscalp.config import CostModel, SymbolSpec
from xauscalp.data.coverage import SEGMENT_GAP
from xauscalp.strategies.base import Signal


def run_backtest(
    m1: pd.DataFrame,
    signals: list[Signal],
    costs: CostModel,
    spec: SymbolSpec | None = None,
    directions: np.ndarray | None = None,
    max_gap_min: int = 5,
) -> pd.DataFrame:
    """Simulate signals (single position, chronological).

    `directions`, if given, overrides the direction of signals[k] for each k IN THE ORDER
    THE CALLER PASSED THEM (used by the random-direction benchmark)."""
    spec = spec or SymbolSpec()
    half = costs.extra_spread_usd / 2
    t = m1.index.as_unit("ns").asi8  # pandas>=3 defaults to us; Timestamp.value is ns
    bo, bh, bl, bc = (m1[c].to_numpy() - half for c in ("bid_o", "bid_h", "bid_l", "bid_c"))
    ao, ah, al = (m1[c].to_numpy() + half for c in ("ask_o", "ask_h", "ask_l"))
    n, slip = len(t), costs.slippage_usd
    comm = costs.commission_per_lot_usd / spec.contract_size  # price units per oz
    one_min = pd.Timedelta(minutes=1).value
    oz_per_001 = spec.contract_size * 0.01

    if directions is not None and len(directions) != len(signals):
        raise ValueError("directions must have one entry per signal")
    dirs = [s.direction for s in signals] if directions is None else [int(x) for x in directions]
    order = sorted(range(len(signals)), key=lambda k: signals[k].decision_idx)
    seg_gap = SEGMENT_GAP.value
    rows, busy_until = [], -1
    for k in order:
        s = signals[k]
        i, e = s.decision_idx, s.decision_idx + 1
        if i < busy_until or e >= n:
            continue
        if t[e] - t[i] > max_gap_min * one_min:
            continue
        d = dirs[k]
        if d not in (1, -1):
            raise ValueError(f"invalid direction {d}")
        entry = ao[e] + slip if d == 1 else bo[e] - slip
        spread_entry = ao[e] - bo[e]
        sl, tp = entry - d * s.sl_dist, entry + d * s.tp_dist
        deadline = t[e] + s.max_hold_min * one_min
        px, reason, ambiguous, j, valid, gap_seen = np.nan, "", False, e, True, False
        while j < n:
            if j > e and t[j] - t[j - 1] > 10 * one_min:
                gap_seen = True
                if t[j] - t[j - 1] > seg_gap:          # hole in the data: unknowable
                    j -= 1
                    px = (bc[j] - slip) if d == 1 else (m1["ask_c"].iat[j] + half + slip)
                    reason, valid = "DATA_GAP", False
                    break
            if d == 1:
                hit_sl, hit_tp = bl[j] <= sl, bh[j] >= tp
            else:
                hit_sl, hit_tp = ah[j] >= sl, al[j] <= tp
            if hit_sl:
                ambiguous = bool(hit_tp)
                px = (min(sl, bo[j]) - slip) if d == 1 else (max(sl, ao[j]) + slip)
                reason = "SL"
                break
            if hit_tp:
                px = max(tp, bo[j]) if d == 1 else min(tp, ao[j])
                reason = "TP"
                break
            if j + 1 < n and t[j + 1] - t[j] > seg_gap:   # hole right after this bar
                px = (bc[j] - slip) if d == 1 else (m1["ask_c"].iat[j] + half + slip)
                reason, valid, gap_seen = "DATA_GAP", False, True
                break
            if j + 1 < n and t[j + 1] >= deadline:
                j += 1
                px = (bo[j] - slip) if d == 1 else (ao[j] + slip)
                reason = "TIME"
                break
            j += 1
        if not reason:  # ran out of data: close at last close
            j = n - 1
            px = (bc[j] - slip) if d == 1 else (m1["ask_c"].iat[j] + half + slip)
            reason, valid = "END", False
        busy_until = j
        pnl = d * (px - entry) - comm
        rows.append({
            "entry_time": m1.index[e], "exit_time": m1.index[j], "direction": d,
            "entry": entry, "exit": px, "sl_dist": s.sl_dist, "tp_dist": s.tp_dist,
            "pnl_price": pnl, "r": pnl / s.sl_dist, "pnl_usd_001": pnl * oz_per_001,
            "cost_price": spread_entry + 2 * slip + comm, "spread_entry": spread_entry,
            "cost_usd_001": (spread_entry + 2 * slip + comm) * oz_per_001,
            "reason": reason, "ambiguous_bar": ambiguous, "valid": valid,
            "gap_during_trade": gap_seen, "session": s.session,
            "strategy": s.strategy, **s.context,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["hold_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60
        df["cost_r"] = df["cost_price"] / df["sl_dist"]
    df.attrs["evidence_level"] = "1-M1_BAR_APPROXIMATION"
    return df
