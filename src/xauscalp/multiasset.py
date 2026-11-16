"""Costs relative to each symbol's own spread + basket walk-forward with three controls.

Preregistered in docs/08_hipotesis_multiactivo.md. The basket (not each symbol) is the unit: ONE
configuration per family and fold is chosen on the POOLED training trades of all symbols (fewer
degrees of freedom than per-symbol selection), abstaining if its pooled train expectancy is <= 0.
Controls on the pooled OOS result: random direction, ALWAYS LONG with the same signals, and RANDOM
ENTRY TIMES with the same direction mix and distances (removes market drift).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import run_backtest
from xauscalp.backtest.metrics import breakdown, summarize
from xauscalp.backtest.splits import walk_forward_folds
from xauscalp.config import Config, CostModel, SymbolSpec
from xauscalp.strategies.base import Signal

COMMISSION_USD_PER_LOT = 7.0
# multipliers of the symbol's median spread s (preregistered): (extra spread, slippage)
SCENARIO_MULT = {"A": (0.0, 0.0, 0.0), "B": (1.0, 0.5, COMMISSION_USD_PER_LOT),
                 "C": (2.0, 1.0, COMMISSION_USD_PER_LOT)}


def median_spread(m1: pd.DataFrame) -> float:
    return float((m1["ask_c"] - m1["bid_c"]).median())


def fx_quote_per_usd(currency_profit: str, currency_base: str, median_price: float) -> float:
    """Commission is quoted in USD per lot; convert to the profit currency (price-unit maths)."""
    if currency_profit == "USD":
        return 1.0
    if currency_base == "USD":
        return float(median_price)
    raise ValueError(f"cannot convert USD commission for {currency_base}/{currency_profit}")


def cost_model_for(m1: pd.DataFrame, scenario: str, currency_profit: str, currency_base: str) -> CostModel:
    extra, slip, comm = SCENARIO_MULT[scenario]
    s = median_spread(m1)
    conv = fx_quote_per_usd(currency_profit, currency_base, float(m1["bid_c"].median()))
    return CostModel(extra * s, slip * s, comm * conv)       # per-lot commission, engine divides by contract


@dataclass
class BasketResult:
    summary: dict
    bench: dict
    folds: pd.DataFrame
    oos: pd.DataFrame
    by_symbol: pd.DataFrame
    by_year: pd.DataFrame
    n_valid_folds: int
    fold_r: pd.DataFrame


def _trades(rd, spec: SymbolSpec, costs: CostModel, sigs, dirs=None):
    tr = run_backtest(rd.m1, sigs, costs, spec, dirs)
    return tr[tr["valid"]] if len(tr) else tr


def run_basket(rds: dict, specs: dict[str, SymbolSpec], costs: dict[str, CostModel], configs, signal_fn,
               cfg: Config, family: str, *, n_controls: int = 200) -> BasketResult:
    v = cfg.validation
    rng = np.random.default_rng(v["seed"])
    first = next(iter(rds.values()))
    start = pd.Timestamp(first.requested_start, tz="UTC")
    end = pd.Timestamp(first.requested_end, tz="UTC") + pd.Timedelta(days=1)
    mine = [(f, p) for f, p in configs if f == family]
    sigs = {s: {i: signal_fn(rds[s].m1, f, p) for i, (f, p) in enumerate(mine)} for s in rds}
    trs = {s: {i: _trades(rds[s], specs[s], costs[s], sigs[s][i]) for i in sigs[s]} for s in rds}
    folds = walk_forward_folds(start, end, v["wf_train_months"], v["wf_test_months"])
    rows, sel_sigs, windows, n_valid = [], {s: [] for s in rds}, [], 0
    for tr0, tr1, te0, te1 in folds:
        cov_ok = all(rd.coverage.usable_fraction(tr0, tr1) >= v["min_fold_coverage"] and
                     rd.coverage.usable_fraction(te0, te1) >= v["min_fold_coverage"] for rd in rds.values())
        row = {"train": f"{tr0.date()}→{tr1.date()}", "test": f"{te0.date()}→{te1.date()}"}
        if not cov_ok:
            rows.append({**row, "chosen": "INSUFFICIENT_DATA"})
            continue
        n_valid += 1
        best, best_exp, best_n = None, -np.inf, 0
        for i in range(len(mine)):
            r = np.concatenate([t[i][(t[i].entry_time >= tr0) & (t[i].entry_time < tr1)]["r"].to_numpy()
                                for t in trs.values() if len(t[i])] or [np.array([])])
            if len(r) >= v["min_train_trades"] * 2 and r.mean() > best_exp:
                best, best_exp, best_n = i, float(r.mean()), len(r)
        if best is None or best_exp <= 0:
            rows.append({**row, "chosen": "ABSTAIN", "train_exp_r": best_exp, "train_n": best_n})
            continue
        for s, rd in rds.items():
            i0, i1 = rd.m1.index.searchsorted(te0), rd.m1.index.searchsorted(te1)
            sel_sigs[s] += [x for x in sigs[s][best] if i0 <= x.decision_idx < i1]
        windows.append((te0, te1))
        rows.append({**row, "chosen": str(mine[best][1]), "train_exp_r": round(best_exp, 4), "train_n": best_n})
    parts = []
    for s, rd in rds.items():
        tr = _trades(rd, specs[s], costs[s], sorted(sel_sigs[s], key=lambda x: x.decision_idx)) if sel_sigs[s] else pd.DataFrame()
        if len(tr):
            tr = tr.assign(symbol=s)
            parts.append(tr)
    oos = pd.concat(parts, ignore_index=True).sort_values("entry_time") if parts else pd.DataFrame()
    summ = summarize(oos, n_boot=v["bootstrap_samples"], seed=v["seed"]) if len(oos) else {"n_trades": 0}
    bench, by_sym, by_year, fold_r = {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if len(oos):
        actual = float(oos["r"].mean())

        def pooled(make_sigs, dirs_fn=None, cost_none=False):
            rr = []
            for s, rd in rds.items():
                sg = make_sigs(s, rd)
                if not sg:
                    continue
                d = dirs_fn(s, sg) if dirs_fn else None
                t = _trades(rd, specs[s], CostModel(0, 0, 0) if cost_none else costs[s], sg, d)
                if len(t):
                    rr.append(t["r"].to_numpy())
            return float(np.concatenate(rr).mean()) if rr else float("nan")

        base = lambda s, rd: sorted(sel_sigs[s], key=lambda x: x.decision_idx)
        rand_dir = np.array([pooled(base, lambda s, sg: rng.choice([-1, 1], size=len(sg))) for _ in range(n_controls)])
        always_long = pooled(base, lambda s, sg: np.ones(len(sg), dtype=int))
        fade = pooled(base, lambda s, sg: -np.array([x.direction for x in sg]))
        zero = pooled(base, cost_none=True)
        # random entry times: same count, direction, distances and holds; decision rows redrawn
        cand = {}
        for s, rd in rds.items():
            idx = np.arange(len(rd.m1))
            m = np.zeros(len(idx), bool)
            for te0, te1 in windows:
                m |= (rd.m1.index >= te0) & (rd.m1.index < te1)
            cand[s] = idx[m][:-2]

        def shifted(s, rd):
            out = []
            for x in sel_sigs[s]:
                if len(cand[s]):
                    out.append(Signal(decision_idx=int(rng.choice(cand[s])), direction=x.direction, sl_dist=x.sl_dist,
                                      tp_dist=x.tp_dist, max_hold_min=x.max_hold_min, strategy=x.strategy,
                                      session=x.session, context=x.context))
            return sorted(out, key=lambda z: z.decision_idx)
        rand_time = np.array([pooled(shifted) for _ in range(n_controls)])
        p = lambda arr: float((1 + (arr[np.isfinite(arr)] >= actual).sum()) / (1 + np.isfinite(arr).sum()))
        bench = {"actual_exp_r": actual, "p_random_direction": p(rand_dir), "p_random_entry_times": p(rand_time),
                 "always_long_exp_r": always_long, "faded_direction_exp_r": fade, "zero_cost_exp_r": zero,
                 "p_vs_always_long_note": "actual must also exceed always_long_exp_r"}
        by_sym = breakdown(oos, "symbol")
        oos["year"] = pd.DatetimeIndex(oos["entry_time"]).year
        by_year = breakdown(oos, "year")
        et = pd.DatetimeIndex(oos["entry_time"])
        fr = [{"test_start": a.date(), "n": int(((et >= a) & (et < b)).sum()),
               "sum_r": float(oos.loc[(et >= a) & (et < b), "r"].sum())} for a, b in windows if ((et >= a) & (et < b)).any()]
        fold_r = pd.DataFrame(fr)
    return BasketResult(summ, bench, pd.DataFrame(rows), oos, by_sym, by_year, n_valid, fold_r)
