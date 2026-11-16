"""Engine fill rules on hand-made bars where the correct answer is known."""

import numpy as np
import pandas as pd
import pytest

from xauscalp.backtest.engine import run_backtest
from xauscalp.config import CostModel
from xauscalp.strategies.base import Signal

NOCOST = CostModel(extra_spread_usd=0.0, slippage_usd=0.0, commission_per_lot_usd=0.0)


def bars(rows, spread=0.2):
    """rows: list of bid (o,h,l,c); ask = bid + spread."""
    idx = pd.date_range("2025-03-03 08:00", periods=len(rows), freq="1min", tz="UTC")
    b = np.array(rows, dtype=float)
    df = pd.DataFrame(b, index=idx, columns=["bid_o", "bid_h", "bid_l", "bid_c"])
    for c in "ohlc":
        df[f"ask_{c}"] = df[f"bid_{c}"] + spread
    df["volume"] = 1.0
    return df


def sig(direction=1, sl=1.0, tp=2.0, hold=60):
    return Signal(decision_idx=0, direction=direction, sl_dist=sl, tp_dist=tp,
                  max_hold_min=hold, strategy="t", session="x")


def test_long_tp_hit_entry_at_next_ask_open():
    df = bars([(100, 100, 100, 100), (100, 100.1, 99.9, 100), (100, 102.5, 100, 102)])
    t = run_backtest(df, [sig()], NOCOST).iloc[0]
    assert t.entry == pytest.approx(100.2)          # ask open of bar 1
    assert t.reason == "TP" and t.exit == pytest.approx(102.2)
    assert t.r == pytest.approx(2.0)


def test_same_bar_sl_and_tp_assumes_sl_first():
    df = bars([(100, 100, 100, 100), (100, 103, 98, 100)])
    t = run_backtest(df, [sig()], NOCOST).iloc[0]
    assert t.reason == "SL" and t.ambiguous_bar
    assert t.r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open_not_at_stop():
    df = bars([(100, 100, 100, 100), (100, 100.1, 99.95, 100), (97, 97.5, 96.8, 97)])
    t = run_backtest(df, [sig()], NOCOST).iloc[0]
    assert t.reason == "SL" and t.exit == pytest.approx(97.0)
    assert t.r < -1.0


def test_short_uses_ask_for_exit():
    df = bars([(100, 100, 100, 100), (100, 100.1, 99.9, 100), (99, 99.1, 97.0, 97.5)])
    t = run_backtest(df, [sig(direction=-1)], NOCOST).iloc[0]
    assert t.entry == pytest.approx(100.0)  # bid open
    assert t.reason == "TP" and t.exit == pytest.approx(98.0)


def test_time_stop_and_costs():
    rows = [(100, 100.05, 99.95, 100)] * 10
    costs = CostModel(extra_spread_usd=0.2, slippage_usd=0.05, commission_per_lot_usd=7.0)
    t = run_backtest(bars(rows), [sig(hold=3)], costs).iloc[0]
    assert t.reason == "TIME" and t.hold_min == pytest.approx(3)
    # paid: spread 0.2 + extra 0.2 + 2*slip 0.1 + commission 7/100 per oz -> pnl = -0.57
    assert t.pnl_price == pytest.approx(-0.57)


def test_one_position_at_a_time():
    rows = [(100, 100.05, 99.95, 100)] * 20
    s1, s2 = sig(hold=10), Signal(3, 1, 1.0, 2.0, 10, "t", "x")
    out = run_backtest(bars(rows), [s1, s2], NOCOST)
    assert len(out) == 1
