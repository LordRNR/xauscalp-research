"""Study 7 plumbing: scenario costs reach the engine and the news blackout drops signals."""
import pandas as pd
from test_parity import market

from xauscalp.backtest.orb_study import build_combos
from xauscalp.config import CostModel, load_config
from xauscalp.features.core import build_features
from xauscalp.pipeline import ResearchData


def _rd():
    m1 = market(days=40, seed=5)
    return ResearchData(m1=m1, feats=build_features(m1), quality={}, coverage=None,
                        requested_start=m1.index[0].date(), requested_end=m1.index[-1].date())


def test_blackout_removes_only_signals_inside_the_window():
    cfg, rd = load_config(), _rd()
    costs = CostModel(0.0, 0.05, 0.0)
    base, removed0 = build_combos(rd, cfg, costs, None)
    sigs = [s for v in base.values() for s in v[1]]
    assert sigs and removed0 == 0
    t = rd.m1.index[sigs[0].decision_idx] + pd.Timedelta(minutes=1)
    ev = pd.DataFrame({"utc_time": [t], "event": ["x"], "impact": ["high"]})
    cut, removed = build_combos(rd, cfg, costs, ev)
    assert removed >= 1
    for (_, kept, _) in cut.values():
        assert all(abs((rd.m1.index[s.decision_idx] + pd.Timedelta(minutes=1) - t)
                       .total_seconds()) > 30 * 60 for s in kept)


def test_higher_costs_never_create_more_signals():
    cfg, rd = load_config(), _rd()
    lo, _ = build_combos(rd, cfg, CostModel(0.0, 0.05, 0.0), None)
    hi, _ = build_combos(rd, cfg, CostModel(0.30, 0.30, 7.0), None)
    assert sum(len(v[1]) for v in hi.values()) <= sum(len(v[1]) for v in lo.values())
