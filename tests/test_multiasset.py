"""Multi-asset study plumbing on SYNTHETIC data (real exports are not available yet)."""
import numpy as np
import pandas as pd
import pytest
from test_parity import market

from xauscalp.config import SymbolSpec, load_config
from xauscalp.multiasset import cost_model_for, fx_quote_per_usd, median_spread, run_basket
from xauscalp.pipeline import ResearchData
from xauscalp.strategies.multi import GRID, N_CONFIGS, all_configs, multi_signals


def fx_like(days=900, seed=1, drift=0.0):
    idx = pd.date_range("2022-01-03", periods=days * 1440, freq="1min", tz="UTC")
    idx = idx[idx.day_of_week < 5]
    rng = np.random.default_rng(seed)
    c = 1.10 + np.cumsum(rng.normal(drift, 0.00005, len(idx)))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"bid_o": o, "bid_h": np.maximum(o, c) + 0.00003, "bid_l": np.minimum(o, c) - 0.00003, "bid_c": c}, index=idx)
    for x in "ohlc":
        df[f"ask_{x}"] = df[f"bid_{x}"] + 0.00012
    df["volume"] = 1.0
    return df


def test_grid_is_the_preregistered_one():
    assert N_CONFIGS == 18 and [len(v) for v in GRID.values()] == [6, 6, 6]
    assert len(all_configs(fx=True)) == 18 and len(all_configs(fx=False)) == 12


def test_costs_are_relative_to_each_symbols_own_spread():
    eur, xau = fx_like(60), market(days=60)
    se, sx = median_spread(eur), median_spread(xau)
    ce, cx = (cost_model_for(m, "B", "USD", "EUR") for m in (eur, xau))
    assert ce.extra_spread_usd == pytest.approx(1.0 * se) and ce.slippage_usd == pytest.approx(0.5 * se)
    assert cx.extra_spread_usd == pytest.approx(1.0 * sx)
    a = cost_model_for(eur, "A", "USD", "EUR")
    assert a.extra_spread_usd == 0 and a.slippage_usd == 0 and a.commission_per_lot_usd == 0
    c = cost_model_for(eur, "C", "USD", "EUR")
    assert c.extra_spread_usd == pytest.approx(2.0 * se) and c.slippage_usd == pytest.approx(1.0 * se)


def test_commission_is_converted_to_the_profit_currency():
    assert fx_quote_per_usd("USD", "EUR", 1.1) == 1.0
    assert fx_quote_per_usd("JPY", "USD", 150.0) == 150.0
    with pytest.raises(ValueError):
        fx_quote_per_usd("JPY", "EUR", 160.0)


@pytest.mark.parametrize("family,params", [("m1_tsmom", GRID["m1_tsmom"][0]), ("m2_donchian", GRID["m2_donchian"][0])])
def test_daily_signals_are_causal(family, params):
    full = fx_like(900)
    cut = len(full) * 2 // 3
    a, b = multi_signals(full, family, params), multi_signals(full.iloc[:cut], family, params)
    lim = cut - 2
    fa = [(s.decision_idx, s.direction) for s in a if s.decision_idx < lim]
    fb = [(s.decision_idx, s.direction) for s in b if s.decision_idx < lim]
    assert fa == fb and len(fa) > 5


def test_basket_runs_end_to_end_with_all_controls_on_synthetic_data():
    cfg = load_config()
    rds, specs, costs = {}, {}, {}
    from xauscalp.data.coverage import coverage_report
    from xauscalp.features.core import build_features
    for k, sym in enumerate(("AAAUSD", "BBBUSD")):
        m1 = fx_like(900, seed=k + 3, drift=0.00000)
        start, end = m1.index[0].date(), m1.index[-1].date()
        rds[sym] = ResearchData(m1=m1, feats=build_features(m1.iloc[:10]), quality={},
                                coverage=coverage_report(m1, start, end), requested_start=start, requested_end=end)
        specs[sym] = SymbolSpec(name=sym, contract_size=100000.0)
        costs[sym] = cost_model_for(m1, "B", "USD", "AAA")
    res = run_basket(rds, specs, costs, all_configs(fx=False), multi_signals, cfg, "m2_donchian", n_controls=5)
    assert res.n_valid_folds >= 1
    assert not res.folds.empty
    if len(res.oos):                                  # a null market may abstain everywhere: both are valid
        assert {"p_random_direction", "p_random_entry_times", "always_long_exp_r"} <= set(res.bench)
        assert set(res.by_symbol.index) <= {"AAAUSD", "BBBUSD"}
