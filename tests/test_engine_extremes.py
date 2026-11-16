"""Audit finding E1/E2: execution edge cases of the M1-bar engine (evidence level 1)."""
import numpy as np
import pandas as pd
import pytest

from xauscalp.backtest.engine import run_backtest
from xauscalp.backtest.metrics import summarize
from xauscalp.config import CostModel
from xauscalp.strategies.base import Signal

NOCOST = CostModel(0.0, 0.0, 0.0)


def bars(rows, start="2025-03-03 08:00", spread=0.2, times=None):
    idx = pd.DatetimeIndex(times, tz="UTC") if times is not None else \
        pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    df = pd.DataFrame(np.array(rows, float), index=idx,
                      columns=["bid_o", "bid_h", "bid_l", "bid_c"])
    for c in "ohlc":
        df[f"ask_{c}"] = df[f"bid_{c}"] + spread
    df["volume"] = 1.0
    return df


def sig(i=0, d=1, sl=1.0, tp=2.0, hold=60, sess="x"):
    return Signal(i, d, sl, tp, hold, "t", sess)


FLAT = (100, 100.05, 99.95, 100)


def test_directions_align_with_caller_order_not_sorted_order():
    df = bars([FLAT] * 3 + [(100, 103, 100, 103)] + [FLAT] * 30
              + [FLAT] * 3 + [(100, 103, 100, 103)] + [FLAT] * 5)
    late, early = sig(i=36, d=1), sig(i=2, d=1)
    out = run_backtest(df, [late, early], NOCOST, directions=np.array([-1, 1]))
    by_entry = out.set_index("entry_time")["direction"]
    assert by_entry.iloc[0] == 1 and by_entry.iloc[1] == -1   # early=+1, late=-1


def test_direction_count_mismatch_raises():
    with pytest.raises(ValueError):
        run_backtest(bars([FLAT] * 5), [sig()], NOCOST, directions=np.array([1, -1]))


def test_data_hole_while_open_invalidates_trade():
    t = list(pd.date_range("2021-03-03 08:00", periods=5, freq="1min")) + \
        list(pd.date_range("2025-10-02 08:00", periods=5, freq="1min"))
    rows = [FLAT] * 5 + [(4000, 4001, 3999, 4000)] * 5
    out = run_backtest(bars(rows, times=t), [sig(i=0, hold=10_000)], NOCOST)
    r = out.iloc[0]
    assert r.reason == "DATA_GAP" and not r.valid
    assert r.exit_time == pd.Timestamp("2021-03-03 08:04", tz="UTC")   # last bar before hole
    assert summarize(out)["n_trades"] == 0 and summarize(out)["n_invalid_excluded"] == 1


def test_weekend_gap_keeps_position_and_fills_at_reopen():
    t = list(pd.date_range("2025-03-07 20:55", periods=5, freq="1min")) + \
        list(pd.date_range("2025-03-09 22:00", periods=3, freq="1min"))
    rows = [FLAT] * 5 + [(97, 97.2, 96.8, 97)] * 3            # gaps below the stop
    r = run_backtest(bars(rows, times=t), [sig(i=0, hold=10_000)], NOCOST).iloc[0]
    assert r.valid and r.gap_during_trade and r.reason == "SL"
    assert r.exit == pytest.approx(97.0) and r.r < -2.5        # gap loss beyond 1R


def test_favourable_gap_through_tp_fills_at_open():
    t = list(pd.date_range("2025-03-07 20:55", periods=3, freq="1min")) + \
        list(pd.date_range("2025-03-09 22:00", periods=2, freq="1min"))
    rows = [FLAT] * 3 + [(105, 105.5, 104.8, 105)] * 2
    r = run_backtest(bars(rows, times=t), [sig(i=0, hold=10_000)], NOCOST).iloc[0]
    assert r.reason == "TP" and r.exit == pytest.approx(105.0)   # better than TP 102.2


def test_short_ambiguous_bar_takes_stop():
    r = run_backtest(bars([FLAT, (100, 102, 97, 100)]), [sig(d=-1)], NOCOST).iloc[0]
    assert r.reason == "SL" and r.ambiguous_bar and r.r == pytest.approx(-1.0)


def test_entry_skipped_when_next_bar_is_far():
    t = ["2025-03-03 08:00", "2025-03-03 08:20", "2025-03-03 08:21"]
    assert run_backtest(bars([FLAT] * 3, times=t), [sig()], NOCOST).empty


def test_spread_larger_than_stop_stops_out_on_entry_bar():
    r = run_backtest(bars([FLAT] * 3, spread=2.0), [sig(sl=1.0)], NOCOST).iloc[0]
    assert r.reason == "SL" and r.r <= -1.0


def test_open_at_end_of_data_is_invalid():
    r = run_backtest(bars([FLAT] * 4), [sig(hold=600)], NOCOST).iloc[0]
    assert r.reason == "END" and not r.valid


def test_joint_simulation_never_overlaps_positions():
    """London and NY signal lists merged -> one chronological single-position run."""
    df = bars([FLAT] * 400)
    london = [sig(i=i, hold=90, sess="london") for i in (0, 150, 300)]
    newyork = [sig(i=i, hold=90, sess="newyork") for i in (40, 200, 320)]
    out = run_backtest(df, london + newyork, NOCOST)
    ent, ex = out["entry_time"].to_numpy(), out["exit_time"].to_numpy()
    assert (ent[1:] >= ex[:-1]).all()
    assert len(out) == 3                                      # NY signals were busy-skipped


def test_slippage_and_commission_on_every_market_fill():
    costs = CostModel(extra_spread_usd=0.0, slippage_usd=0.1, commission_per_lot_usd=10.0)
    r = run_backtest(bars([FLAT, FLAT, (100, 100.1, 98.0, 98.5)]), [sig()], costs).iloc[0]
    # entry 100.2+0.1; SL at 99.3 -> fill 99.3-0.1; commission 0.10/oz
    assert r.pnl_price == pytest.approx((99.2 - 100.3) - 0.10)


def test_trades_report_evidence_level():
    out = run_backtest(bars([FLAT] * 5), [sig(hold=2)], NOCOST)
    assert out.attrs["evidence_level"].startswith("1-")
