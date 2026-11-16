"""Exact replay of a trade list through the prop-firm checker (floating equity, daily reset).

Per minute inside a trade the equity uses the ADVERSE extreme of the M1 bar (long: bid low,
short: ask high), so intrabar floating losses can breach the daily/maximum loss before the
trade closes, exactly as the firm's equity rule does. Commission is charged at entry.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from xauscalp.propfirm.rules import (
    Observation,
    Phase,
    PropChecker,
    PropRules,
    Status,
    size_lots,
)


def trade_mae_r(trades: pd.DataFrame, m1: pd.DataFrame, extra_spread: float = 0.0) -> np.ndarray:
    """Maximum adverse excursion of each trade in R (>= 0), from the M1 path."""
    half = extra_spread / 2
    t = m1.index.as_unit("ns").asi8
    lo, hi = m1["bid_l"].to_numpy() - half, m1["ask_h"].to_numpy() + half
    out = np.zeros(len(trades))
    ent = pd.DatetimeIndex(trades["entry_time"]).as_unit("ns").asi8
    ext = pd.DatetimeIndex(trades["exit_time"]).as_unit("ns").asi8
    for k, (e, x, d, px, sl) in enumerate(zip(ent, ext, trades["direction"], trades["entry"],
                                              trades["sl_dist"], strict=True)):
        a, b = np.searchsorted(t, e, "left"), np.searchsorted(t, x, "right")
        if b <= a:
            continue
        adverse = (px - lo[a:b].min()) if d == 1 else (hi[a:b].max() - px)
        out[k] = max(0.0, adverse) / sl
    return out


def replay(trades: pd.DataFrame, m1: pd.DataFrame, rules: PropRules, phase: Phase, initial: float,
           risk_pct: float, *, extra_spread: float = 0.0, commission_per_lot: float = 7.0,
           contract_size: float = 100.0, lot_step: float = 0.01, lot_min: float = 0.01) -> dict:
    """Run `trades` (columns entry_time, exit_time, direction, entry, sl_dist, pnl_price) from the
    first trade onward. Returns status, reason, timestamps, margins and counts."""
    chk = PropChecker(rules, phase, initial)
    half = extra_spread / 2
    t = m1.index.as_unit("ns").asi8
    lo, hi = m1["bid_l"].to_numpy() - half, m1["ask_h"].to_numpy() + half
    balance, taken, skipped, prev_ts = initial, 0, 0, None
    for tr in trades.sort_values("entry_time").itertuples():
        lots = size_lots(risk_pct / 100 * initial, tr.sl_dist, contract_size=contract_size,
                         lot_step=lot_step, lot_min=lot_min)
        if lots <= 0:
            skipped += 1
            continue
        e_ts, x_ts = pd.Timestamp(tr.entry_time), pd.Timestamp(tr.exit_time)
        if prev_ts is not None:                                   # day resets between trades
            for mid in pd.date_range(prev_ts.tz_convert(rules.tz).normalize() + pd.Timedelta(days=1),
                                     e_ts.tz_convert(rules.tz), freq="D", tz=rules.tz):
                if mid.tz_convert("UTC") > prev_ts and mid.tz_convert("UTC") < e_ts:
                    chk.update(Observation(mid.tz_convert("UTC"), balance, balance))
        a = np.searchsorted(t, e_ts.as_unit("ns").value, "left")
        b = np.searchsorted(t, x_ts.as_unit("ns").value, "right")
        comm = commission_per_lot * lots
        d = tr.direction
        for i in range(a, max(b, a + 1)):
            worst = (lo[i] - tr.entry) if d == 1 else (tr.entry - hi[i])
            eq = balance + worst * lots * contract_size - comm
            chk.update(Observation(m1.index[i], balance, eq, positions_open=1, opened_position=i == a))
            if chk.status is not Status.RUNNING:
                break
        if chk.status is not Status.RUNNING:
            break
        balance += tr.pnl_price * lots * contract_size   # pnl_price already nets commission
        taken += 1
        chk.update(Observation(x_ts, balance, balance, positions_open=0))
        prev_ts = x_ts
        if chk.status is not Status.RUNNING:
            break
    return {"status": chk.status.value, "reason": chk.reason, "pass_ts": chk.pass_ts,
            "breach_ts": chk.breach_ts, "final_balance": balance, "trades_taken": taken,
            "trades_skipped_cannot_size": skipped, "trading_days": len(chk.trading_days),
            "min_daily_margin_pct": (chk.min_daily_margin * 100 if math.isfinite(chk.min_daily_margin) else None),
            "min_total_margin_pct": (chk.min_total_margin * 100 if math.isfinite(chk.min_total_margin) else None)}
