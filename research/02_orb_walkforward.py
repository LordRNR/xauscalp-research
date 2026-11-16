"""Study 2: Opening-Range Breakout baseline — walk-forward OOS evaluation and benchmarks.

Protocol (pre-registered in config/default.yaml BEFORE results were seen):
  * research slice only (holdout untouched, never decoded);
  * a fold is used only if BOTH its train and test windows have >= min_fold_coverage of
    usable trading days; otherwise it is INSUFFICIENT_DATA (no selection, no test);
  * per session, a small grid (or_minutes x sl_atr x tp_r); best train mean-R combo with
    >= min_train_trades; if the best train expectancy is <= 0 the session ABSTAINS;
  * FINAL OOS RESULT = ONE chronological joint simulation of all selected OOS signals of
    all sessions (single XAUUSD position at a time). Per-session tables are diagnostics;
  * benchmarks (random direction, faded direction, zero cost) run on EXACTLY the same OOS
    signal list through the same engine;
  * if fewer than min_valid_folds folds are usable the study is declared NOT VALIDATABLE
    and no performance figures are reported as evidence.
Capital needs are NOT computed here (they need the broker's real contract and the
current FX rate): see research/03_orb_diagnostics.py and the MT5 feasibility report.
Evidence level: M1-bar approximation (level 1), see backtest/engine.py.

    uv run python research/02_orb_walkforward.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import run_backtest
from xauscalp.backtest.metrics import breakdown, monte_carlo_drawdown, summarize
from xauscalp.backtest.splits import walk_forward_folds
from xauscalp.config import ROOT, CostModel, load_config
from xauscalp.pipeline import load_research_data, md_table
from xauscalp.strategies.orb import ORBParams, orb_signals


def fmt(d: dict) -> str:
    def conv(v):
        if isinstance(v, float):
            return round(v, 4)
        if isinstance(v, tuple):
            return tuple(round(x, 4) for x in v)
        return v
    return "```\n" + json.dumps({k: conv(v) for k, v in d.items()}, indent=1, default=str) + "\n```"


def build_combos(rd, cfg):
    sc = cfg.strategy["orb"]
    combos = {}
    for sess, scfg in sc["sessions"].items():
        for orm, sla, tpr in itertools.product(*sc["grid"].values()):
            p = ORBParams(session=sess, tz=scfg["tz"], open_hhmm=scfg["open"], or_minutes=orm,
                          sl_atr=sla, tp_r=tpr, entry_window_min=sc["entry_window_min"],
                          max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                          max_cost_frac=sc["max_cost_frac"])
            sigs, _ = orb_signals(rd.m1, rd.feats, p, cfg.costs, cfg.risk.max_spread_usd)
            tr = run_backtest(rd.m1, sigs, cfg.costs, cfg.symbol)
            if not tr.empty:
                tr = tr[tr["valid"]]
            combos[p.name] = (p, sigs, tr)
    return combos


def main() -> None:
    cfg = load_config()
    v = cfg.validation
    rng = np.random.default_rng(v["seed"])
    rd = load_research_data(cfg)
    m1, cov = rd.m1, rd.coverage
    start = pd.Timestamp(rd.requested_start, tz="UTC")
    end = pd.Timestamp(rd.requested_end, tz="UTC") + pd.Timedelta(days=1)
    min_cov, min_folds = v.get("min_fold_coverage", 0.9), v.get("min_valid_folds", 4)
    print(f"research data {m1.index[0]} -> {m1.index[-1]} ({len(m1):,} M1 bars), "
          f"coverage {cov.coverage_pct:.1f}%")

    combos = build_combos(rd, cfg)
    folds = walk_forward_folds(start, end, v["wf_train_months"], v["wf_test_months"])
    fold_rows, oos_signals, valid_test_days, n_valid_folds = [], [], 0, 0
    for tr0, tr1, te0, te1 in folds:
        c_tr, c_te = cov.usable_fraction(tr0, tr1), cov.usable_fraction(te0, te1)
        fold_ok = c_tr >= min_cov and c_te >= min_cov
        if fold_ok:
            n_valid_folds += 1
            valid_test_days += int(c_te * len(pd.bdate_range(te0, te1 - pd.Timedelta(days=1))))
        for sess in cfg.strategy["orb"]["sessions"]:
            row = {"session": sess, "train": f"{tr0.date()}→{tr1.date()}",
                   "test": f"{te0.date()}→{te1.date()}", "cov_train": round(c_tr, 2),
                   "cov_test": round(c_te, 2)}
            if not fold_ok:
                fold_rows.append({**row, "chosen": "INSUFFICIENT_DATA"})
                continue
            best, best_exp, best_n = None, -np.inf, 0
            for name, (p, _, tr) in combos.items():
                if p.session != sess or tr.empty:
                    continue
                w = tr[(tr.entry_time >= tr0) & (tr.entry_time < tr1)]
                if len(w) >= v["min_train_trades"] and w["r"].mean() > best_exp:
                    best, best_exp, best_n = name, w["r"].mean(), len(w)
            if best is None or best_exp <= 0:
                fold_rows.append({**row, "chosen": "ABSTAIN", "train_exp_r": best_exp,
                                  "train_n": best_n})
                continue
            i0, i1 = m1.index.searchsorted(te0), m1.index.searchsorted(te1)
            sel = [s for s in combos[best][1] if i0 <= s.decision_idx < i1]
            oos_signals += sel
            fold_rows.append({**row, "chosen": best, "train_exp_r": round(best_exp, 4),
                              "train_n": best_n, "test_signals": len(sel)})
    folds_df = pd.DataFrame(fold_rows).set_index("session") if fold_rows else pd.DataFrame()
    validatable = n_valid_folds >= min_folds

    # ---- final: ONE joint chronological simulation (single position) ----
    oos_signals.sort(key=lambda s: s.decision_idx)
    oos = run_backtest(m1, oos_signals, cfg.costs, cfg.symbol) if oos_signals else pd.DataFrame()
    summ = summarize(oos, n_boot=v["bootstrap_samples"], seed=v["seed"],
                     period_days=max(1, valid_test_days)) if len(oos) else {"n_trades": 0}
    bench, mc = {}, {}
    if len(oos) and oos["valid"].any():
        def exp_r(df):
            return float(df.loc[df["valid"], "r"].mean())
        actual = exp_r(oos)
        rand = np.array([exp_r(run_backtest(m1, oos_signals, cfg.costs, cfg.symbol,
                                            rng.choice([-1, 1], size=len(oos_signals))))
                         for _ in range(v["random_benchmark_runs"])])
        fade = exp_r(run_backtest(m1, oos_signals, cfg.costs, cfg.symbol,
                                  -np.array([s.direction for s in oos_signals])))
        zero = exp_r(run_backtest(m1, oos_signals, CostModel(0.0, 0.0, 0.0), cfg.symbol))
        bench = {"signals_universe": len(oos_signals), "actual_exp_r": actual,
                 "random_dir_exp_r_median": float(np.median(rand)),
                 "random_dir_exp_r_p95": float(np.quantile(rand, 0.95)),
                 "p_value_vs_random_dir": float((1 + (rand >= actual).sum()) / (1 + len(rand))),
                 "faded_direction_exp_r": fade, "zero_cost_exp_r": zero}
        mc = monte_carlo_drawdown(oos.loc[oos["valid"], "r"].to_numpy(), 5000, rng)

    # ---- report ----
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    verdict = ("VALIDABLE" if validatable else
               f"**NO VALIDABLE**: solo {n_valid_folds} folds con cobertura ≥ {min_cov:.0%} "
               f"(se exigen {min_folds}). Cualquier cifra de abajo es DIAGNÓSTICO, no evidencia.")
    md = [
        "# Estudio 2 — ORB (London / COMEX open): walk-forward fuera de muestra",
        "",
        f"> Veredicto de datos: {verdict}",
        (f"> Cobertura del tramo de investigación: {cov.coverage_pct:.1f} % "
        f"({cov.usable_days}/{cov.expected_days} días utilizables). Nivel de evidencia: "
        "1 — aproximación con velas M1 (no ticks reales, no DEMO)."),
        "",
        (f"Periodo solicitado: {rd.requested_start} → {rd.requested_end} · holdout "
        f"≥ {v['holdout_start']} **no leído**. Folds: train {v['wf_train_months']}m / test "
        f"{v['wf_test_months']}m. Configuraciones probadas: {len(combos)}."),
        "",
        "## Resultado OOS — simulación conjunta (1 posición, orden cronológico)",
        fmt(summ),
        "## Benchmarks sobre las MISMAS señales OOS",
        fmt(bench) if bench else "_sin señales OOS_",
        "## Monte Carlo de drawdown (R)",
        fmt(mc) if mc else "_n/a_",
        "## Selección por fold",
        md_table(folds_df),
        "",
    ]
    if len(oos) and oos["valid"].any():
        ok = oos[oos["valid"]].copy()
        ok["year"] = pd.DatetimeIndex(ok["entry_time"]).year
        for by in ("year", "session"):
            md += [f"## OOS por {by}", md_table(breakdown(ok, by)), ""]
        oos.to_csv(out / "02_orb_oos_trades.csv", index=False)
    (out / "02_orb_baseline.md").write_text("\n".join(md))
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
