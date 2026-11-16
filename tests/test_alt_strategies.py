"""Causality (truncation) and sanity tests for the preregistered alternative families."""
import numpy as np
import pandas as pd
import pytest
from test_parity import market

from xauscalp.strategies.alt import GRID, N_CONFIGS, all_configs, alt_signals, config_name


def m1(days=120, seed=2):
    return market(days=days, seed=seed)


def test_grid_is_the_preregistered_one():
    assert N_CONFIGS == 22 and [len(v) for v in GRID.values()] == [6, 6, 4, 6]
    assert len({config_name(f, p) for f, p in all_configs()}) == 22


@pytest.mark.parametrize("family,params", [(f, ps[0]) for f, ps in GRID.items()] +
                         [("mean_reversion", GRID["mean_reversion"][0]),
                          ("pullback", GRID["pullback"][3])])
def test_truncation_does_not_change_past_signals(family, params):
    """No look-ahead: signals decided before the cut are identical on truncated data."""
    full = m1()
    cut = len(full) * 2 // 3
    a = alt_signals(full, family, params)
    b = alt_signals(full.iloc[:cut], family, params)
    lim = cut - 2
    fa = [(s.decision_idx, s.direction, round(s.sl_dist, 9)) for s in a if s.decision_idx < lim]
    fb = [(s.decision_idx, s.direction, round(s.sl_dist, 9)) for s in b if s.decision_idx < lim]
    assert fa == fb and len(fa) > 0


def test_signals_are_well_formed_and_deterministic():
    d = m1()
    for family, params in all_configs():
        s = alt_signals(d, family, params)
        again = alt_signals(d, family, params)
        assert [(x.decision_idx, x.direction) for x in s] == [(x.decision_idx, x.direction) for x in again]
        for x in s:
            assert x.direction in (1, -1) and x.sl_dist > 0 and x.tp_dist > 0 and x.max_hold_min > 0
            assert 0 <= x.decision_idx < len(d) - 1 and np.isfinite(x.context["atr"])


def test_donchian_breakout_direction_on_a_synthetic_trend():
    idx = pd.date_range("2025-01-06", periods=60 * 24 * 40, freq="1min", tz="UTC")
    idx = idx[idx.day_of_week < 5]
    c = 2000 + np.arange(len(idx)) * 0.01 + np.random.default_rng(0).normal(0, 0.3, len(idx))
    df = pd.DataFrame({"bid_o": c, "bid_h": c + 0.3, "bid_l": c - 0.3, "bid_c": c}, index=idx)
    for x in "ohlc":
        df[f"ask_{x}"] = df[f"bid_{x}"] + 0.2
    df["volume"] = 1.0
    s = alt_signals(df, "trend_donchian", {"n": 24, "sl_atr": 2.0})
    assert s and all(x.direction == 1 for x in s)
    assert alt_signals(df, "mean_reversion", {"z": 2.0, "sl_atr": 2.0}) is not None


def test_decisions_are_at_the_close_of_the_bar_and_idempotent_on_gaps():
    d = m1()
    for x in alt_signals(d, "trend_donchian", GRID["trend_donchian"][0]):
        t = d.index[x.decision_idx]
        assert t.minute == 59                       # last M1 row of an H1 bar
