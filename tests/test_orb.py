"""ORB rules on a constructed day where the correct signal is known."""
import numpy as np
import pandas as pd

from xauscalp.config import CostModel
from xauscalp.strategies.orb import ORBParams, orb_signals

COSTS = CostModel(extra_spread_usd=0.0, slippage_usd=0.0)


def _day(break_at: int, direction: int):
    # Winter day: London 08:00 local == 08:00 UTC. Index in pandas-3 default (us) resolution.
    idx = pd.date_range("2025-01-15 07:00", "2025-01-15 10:00", freq="1min", tz="UTC")
    c = np.full(len(idx), 2000.0)
    pos = idx.get_loc(pd.Timestamp("2025-01-15 08:00", tz="UTC")) + break_at
    c[pos:] = 2000.0 + direction * 3.0
    m1 = pd.DataFrame({"bid_o": c, "bid_h": c + 0.1, "bid_l": c - 0.1, "bid_c": c}, index=idx)
    for x in "ohlc":
        m1[f"ask_{x}"] = m1[f"bid_{x}"] + 0.2
    feats = pd.DataFrame({"atr_m5": np.full(len(idx), 1.0)}, index=idx)
    return m1, feats, pos


P = ORBParams(session="london", tz="Europe/London", open_hhmm="08:00", or_minutes=15,
              sl_atr=1.5, tp_r=1.0)


def test_breakout_long_signal_at_first_close_beyond_range():
    m1, feats, pos = _day(break_at=20, direction=1)
    sigs, _stats = orb_signals(m1, feats, P, COSTS)
    assert len(sigs) == 1 and sigs[0].direction == 1
    assert sigs[0].decision_idx == pos           # decided at close of the breakout bar
    assert sigs[0].sl_dist == 1.5 and sigs[0].tp_dist == 1.5


def test_breakout_inside_opening_range_is_ignored():
    m1, feats, _ = _day(break_at=5, direction=-1)   # move happens INSIDE the OR -> no signal
    sigs, stats = orb_signals(m1, feats, P, COSTS)
    assert sigs == [] and stats["no_trigger"] >= 1


def test_cost_filter_blocks_when_spread_too_large():
    m1, feats, _ = _day(break_at=20, direction=1)
    sigs, stats = orb_signals(m1, feats, P, CostModel(extra_spread_usd=1.0, slippage_usd=0.0))
    assert sigs == [] and stats["cost_filtered"] == 1
