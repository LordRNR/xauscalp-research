"""Walk-forward for strategy FAMILIES (same protocol as study 2 / orb_study, generic groups).

For each family: per fold, pick the configuration with the best TRAIN net expectancy
(>= min_train_trades; abstain if <= 0); the OOS signals of all selected configurations are
simulated JOINTLY in one chronological single-position run. Benchmarks on the same signals:
random direction, faded direction, zero cost.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import run_backtest
from xauscalp.backtest.metrics import breakdown, monte_carlo_drawdown, summarize
from xauscalp.backtest.orb_study import StudyResult
from xauscalp.backtest.splits import walk_forward_folds
from xauscalp.config import Config, CostModel


def build_family_combos(rd, cfg: Config, costs: CostModel, configs, signal_fn):
    """{name: (family, signals, valid trades)} for every (family, params)."""
    out = {}
    for family, params in configs:
        sigs = signal_fn(rd.m1, family, params)
        tr = run_backtest(rd.m1, sigs, costs, cfg.symbol)
        if not tr.empty:
            tr = tr[tr["valid"]]
        out[(family, tuple(sorted(params.items())))] = (family, params, sigs, tr)
    return out


def trades_hash(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "empty"
    cols = ["entry_time", "exit_time", "direction", "entry", "exit", "r"]
    s = df[cols].round(6).to_csv(index=False)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def run_family_walkforward(rd, cfg: Config, costs: CostModel, family: str, combos) -> tuple[StudyResult, pd.DataFrame]:
    v = cfg.validation
    rng = np.random.default_rng(v["seed"])
    m1, cov = rd.m1, rd.coverage
    start = pd.Timestamp(rd.requested_start, tz="UTC")
    end = pd.Timestamp(rd.requested_end, tz="UTC") + pd.Timedelta(days=1)
    min_cov, min_folds = v.get("min_fold_coverage", 0.9), v.get("min_valid_folds", 4)
    mine = {k: c for k, c in combos.items() if c[0] == family}
    folds = walk_forward_folds(start, end, v["wf_train_months"], v["wf_test_months"])
    rows, oos_signals, valid_days, n_valid, fold_windows = [], [], 0, 0, []
    for tr0, tr1, te0, te1 in folds:
        c_tr, c_te = cov.usable_fraction(tr0, tr1), cov.usable_fraction(te0, te1)
        ok = c_tr >= min_cov and c_te >= min_cov
        row = {"train": f"{tr0.date()}→{tr1.date()}", "test": f"{te0.date()}→{te1.date()}",
               "cov_train": round(c_tr, 2), "cov_test": round(c_te, 2)}
        if not ok:
            rows.append({**row, "chosen": "INSUFFICIENT_DATA"})
            continue
        n_valid += 1
        valid_days += int(c_te * len(pd.bdate_range(te0, te1 - pd.Timedelta(days=1))))
        best, best_exp, best_n = None, -np.inf, 0
        for key, (_, params, _, tr) in mine.items():
            if tr.empty:
                continue
            w = tr[(tr.entry_time >= tr0) & (tr.entry_time < tr1)]
            if len(w) >= v["min_train_trades"] and w["r"].mean() > best_exp:
                best, best_exp, best_n = key, w["r"].mean(), len(w)
        if best is None or best_exp <= 0:
            rows.append({**row, "chosen": "ABSTAIN", "train_exp_r": best_exp, "train_n": best_n})
            continue
        i0, i1 = m1.index.searchsorted(te0), m1.index.searchsorted(te1)
        sel = [s for s in mine[best][2] if i0 <= s.decision_idx < i1]
        oos_signals += sel
        fold_windows.append((te0, te1))
        rows.append({**row, "chosen": str(dict(best[1])), "train_exp_r": round(best_exp, 4),
                     "train_n": best_n, "test_signals": len(sel)})
    folds_df = pd.DataFrame(rows)
    oos_signals.sort(key=lambda s: s.decision_idx)
    oos = run_backtest(m1, oos_signals, costs, cfg.symbol) if oos_signals else pd.DataFrame()
    summ = (summarize(oos, n_boot=v["bootstrap_samples"], seed=v["seed"],
                      period_days=max(1, valid_days)) if len(oos) else {"n_trades": 0})
    bench, mc, by_year = {}, {}, pd.DataFrame()
    fold_r = pd.DataFrame()
    if len(oos) and oos["valid"].any():
        def exp_r(df):
            return float(df.loc[df["valid"], "r"].mean())
        actual = exp_r(oos)
        rand = np.array([exp_r(run_backtest(m1, oos_signals, costs, cfg.symbol,
                                            rng.choice([-1, 1], size=len(oos_signals))))
                         for _ in range(v["random_benchmark_runs"])])
        fade = exp_r(run_backtest(m1, oos_signals, costs, cfg.symbol,
                                  -np.array([s.direction for s in oos_signals])))
        zero = exp_r(run_backtest(m1, oos_signals, CostModel(0.0, 0.0, 0.0), cfg.symbol))
        bench = {"signals_universe": len(oos_signals), "actual_exp_r": actual,
                 "random_dir_exp_r_median": float(np.median(rand)),
                 "p_value_vs_random_dir": float((1 + (rand >= actual).sum()) / (1 + len(rand))),
                 "faded_direction_exp_r": fade, "zero_cost_exp_r": zero}
        ok_tr = oos[oos["valid"]].copy()
        mc = monte_carlo_drawdown(ok_tr["r"].to_numpy(), 5000, rng)
        ok_tr["year"] = pd.DatetimeIndex(ok_tr["entry_time"]).year
        by_year = breakdown(ok_tr, "year")
        et = pd.DatetimeIndex(ok_tr["entry_time"])
        fr = []
        for te0, te1 in fold_windows:
            m = (et >= te0) & (et < te1)
            if m.any():
                fr.append({"test_start": te0.date(), "n": int(m.sum()),
                           "sum_r": float(ok_tr.loc[m, "r"].sum())})
        fold_r = pd.DataFrame(fr)
    tab = []
    for key, (_, params, _sigs, tr) in mine.items():
        r = tr["r"].to_numpy() if len(tr) else np.array([])
        tab.append({"config": str(dict(key[1])), "n": len(r),
                    "exp_r": float(r.mean()) if len(r) else np.nan})
    res = StudyResult(n_combos=len(mine), n_valid_folds=n_valid, validatable=n_valid >= min_folds,
                      summary=summ, bench=bench, mc=mc, folds=folds_df, oos=oos, by_year=by_year,
                      combos_table=pd.DataFrame(tab))
    return res, fold_r
