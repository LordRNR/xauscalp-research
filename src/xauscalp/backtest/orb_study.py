"""Walk-forward ORB study as a reusable function (protocol of research/02, parametrised).

Protocol (unchanged from study 2, pre-registered in config/default.yaml):
  * research slice only; a fold counts only if BOTH train and test have >= min_fold_coverage;
  * per session a small grid (or_minutes x sl_atr x tp_r): best TRAIN mean-R combo with
    >= min_train_trades; non-positive best train expectancy -> ABSTAIN;
  * FINAL OOS = one joint chronological simulation (single position);
  * benchmarks on the SAME signal list: random direction, faded direction, zero cost.
New here: the cost model is an argument (scenarios are pre-registered by the caller) and an
optional news blackout drops signals whose DECISION time is within the blackout window
(the EA applies the same rule at the decision bar).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import run_backtest
from xauscalp.backtest.metrics import breakdown, monte_carlo_drawdown, summarize
from xauscalp.backtest.splits import walk_forward_folds
from xauscalp.calendar.events import blackout_mask
from xauscalp.config import Config, CostModel
from xauscalp.strategies.orb import ORBParams, orb_signals


@dataclass
class StudyResult:
    n_combos: int
    n_valid_folds: int
    validatable: bool
    summary: dict
    bench: dict
    mc: dict
    folds: pd.DataFrame
    oos: pd.DataFrame
    by_year: pd.DataFrame = field(default_factory=pd.DataFrame)
    by_session: pd.DataFrame = field(default_factory=pd.DataFrame)
    combos_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_signals_blackout_removed: int = 0


def build_combos(rd, cfg: Config, costs: CostModel, events: pd.DataFrame | None,
                 before_min: int = 30, after_min: int = 30):
    sc = cfg.strategy["orb"]
    blk = None
    removed = 0
    if events is not None and len(events):
        # decision time of row i is its open + 1 minute
        blk = blackout_mask(rd.m1.index + pd.Timedelta(minutes=1), events, before_min, after_min)
    combos = {}
    for sess, scfg in sc["sessions"].items():
        for orm, sla, tpr in itertools.product(*sc["grid"].values()):
            p = ORBParams(session=sess, tz=scfg["tz"], open_hhmm=scfg["open"], or_minutes=orm,
                          sl_atr=sla, tp_r=tpr, entry_window_min=sc["entry_window_min"],
                          max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                          max_cost_frac=sc["max_cost_frac"])
            sigs, _ = orb_signals(rd.m1, rd.feats, p, costs, cfg.risk.max_spread_usd)
            if blk is not None:
                kept = [s for s in sigs if not blk[s.decision_idx]]
                removed += len(sigs) - len(kept)
                sigs = kept
            tr = run_backtest(rd.m1, sigs, costs, cfg.symbol)
            if not tr.empty:
                tr = tr[tr["valid"]]
            combos[p.name] = (p, sigs, tr)
    return combos, removed


def run_orb_walkforward(rd, cfg: Config, costs: CostModel,
                        events: pd.DataFrame | None = None) -> StudyResult:
    v = cfg.validation
    rng = np.random.default_rng(v["seed"])
    m1, cov = rd.m1, rd.coverage
    start = pd.Timestamp(rd.requested_start, tz="UTC")
    end = pd.Timestamp(rd.requested_end, tz="UTC") + pd.Timedelta(days=1)
    min_cov, min_folds = v.get("min_fold_coverage", 0.9), v.get("min_valid_folds", 4)
    combos, removed = build_combos(rd, cfg, costs, events)
    folds = walk_forward_folds(start, end, v["wf_train_months"], v["wf_test_months"])
    rows, oos_signals, valid_days, n_valid = [], [], 0, 0
    for tr0, tr1, te0, te1 in folds:
        c_tr, c_te = cov.usable_fraction(tr0, tr1), cov.usable_fraction(te0, te1)
        ok = c_tr >= min_cov and c_te >= min_cov
        if ok:
            n_valid += 1
            valid_days += int(c_te * len(pd.bdate_range(te0, te1 - pd.Timedelta(days=1))))
        for sess in cfg.strategy["orb"]["sessions"]:
            row = {"session": sess, "train": f"{tr0.date()}→{tr1.date()}",
                   "test": f"{te0.date()}→{te1.date()}", "cov_train": round(c_tr, 2),
                   "cov_test": round(c_te, 2)}
            if not ok:
                rows.append({**row, "chosen": "INSUFFICIENT_DATA"})
                continue
            best, best_exp, best_n = None, -np.inf, 0
            for name, (p, _, tr) in combos.items():
                if p.session != sess or tr.empty:
                    continue
                w = tr[(tr.entry_time >= tr0) & (tr.entry_time < tr1)]
                if len(w) >= v["min_train_trades"] and w["r"].mean() > best_exp:
                    best, best_exp, best_n = name, w["r"].mean(), len(w)
            if best is None or best_exp <= 0:
                rows.append({**row, "chosen": "ABSTAIN", "train_exp_r": best_exp,
                             "train_n": best_n})
                continue
            i0, i1 = m1.index.searchsorted(te0), m1.index.searchsorted(te1)
            sel = [s for s in combos[best][1] if i0 <= s.decision_idx < i1]
            oos_signals += sel
            rows.append({**row, "chosen": best, "train_exp_r": round(best_exp, 4),
                         "train_n": best_n, "test_signals": len(sel)})
    folds_df = pd.DataFrame(rows).set_index("session") if rows else pd.DataFrame()
    oos_signals.sort(key=lambda s: s.decision_idx)
    oos = run_backtest(m1, oos_signals, costs, cfg.symbol) if oos_signals else pd.DataFrame()
    summ = (summarize(oos, n_boot=v["bootstrap_samples"], seed=v["seed"],
                      period_days=max(1, valid_days)) if len(oos) else {"n_trades": 0})
    bench, mc, by_year, by_sess = {}, {}, pd.DataFrame(), pd.DataFrame()
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
                 "random_dir_exp_r_p95": float(np.quantile(rand, 0.95)),
                 "p_value_vs_random_dir": float((1 + (rand >= actual).sum()) / (1 + len(rand))),
                 "faded_direction_exp_r": fade, "zero_cost_exp_r": zero}
        mc = monte_carlo_drawdown(oos.loc[oos["valid"], "r"].to_numpy(), 5000, rng)
        ok_tr = oos[oos["valid"]].copy()
        ok_tr["year"] = pd.DatetimeIndex(ok_tr["entry_time"]).year
        by_year, by_sess = breakdown(ok_tr, "year"), breakdown(ok_tr, "session")
    tab = []
    for name, (p, sigs, tr) in combos.items():
        r = tr["r"].to_numpy() if len(tr) else np.array([])
        tab.append({"combo": name, "n": len(r),
                    "exp_r": float(r.mean()) if len(r) else np.nan,
                    "se": float(r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 2 else np.nan})
    return StudyResult(n_combos=len(combos), n_valid_folds=n_valid,
                       validatable=n_valid >= min_folds, summary=summ, bench=bench, mc=mc,
                       folds=folds_df, oos=oos, by_year=by_year, by_session=by_sess,
                       combos_table=pd.DataFrame(tab).set_index("combo"),
                       n_signals_blackout_removed=removed)
