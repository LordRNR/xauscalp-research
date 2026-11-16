"""Study 8: trend / momentum / pullback / mean reversion on the broker's M1 (preregistered).

Hypotheses, grid (22 configurations), costs, protocol and the 8 acceptance criteria are fixed
in docs/06_hipotesis_alternativas.md and src/xauscalp/strategies/alt.py, committed BEFORE the
first execution of this script. Nothing here may be changed after seeing results.

    uv run python research/08_alt_strategies.py data/mt5/XAUUSD_M1_20210101_20261113.csv \
        --tz base_dst:120:Europe/London
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

from xauscalp.backtest.family_study import (
    build_family_combos,
    run_family_walkforward,
    trades_hash,
)
from xauscalp.config import ROOT, CostModel, load_config
from xauscalp.parity import parse_tz
from xauscalp.pipeline import load_broker_research_data, md_table
from xauscalp.strategies.alt import GRID, N_CONFIGS, all_configs, alt_signals

SCENARIOS = {"A_demo_as_is": CostModel(0.00, 0.05, 0.0), "B_base": CostModel(0.15, 0.10, 7.0),
             "C_stress": CostModel(0.30, 0.30, 7.0)}
N_FAMILIES = len(GRID)
P_THRESHOLD = 0.05 / N_FAMILIES            # Bonferroni, preregistered
MIN_TRADES = 150
MIN_FOLD_POSITIVE = 0.60
MIN_YEARS_POSITIVE = 3


_G: dict = {}


def _task(t):
    fam, name, which = t
    return run_family_walkforward(_G["rd"], _G["cfg"], SCENARIOS[name], fam, _G[which][name] if which == "combos" else _G[which])


def criteria(fam: str, b, fold_r, c, b2_hash: str) -> list[tuple[str, bool, str]]:
    s, bm = b.summary, b.bench
    ci = s.get("expectancy_r_ci95_weekblock", (np.nan, np.nan))
    yr = b.by_year["total_r"] if len(b.by_year) else pd.Series(dtype=float)
    fpos = float((fold_r["sum_r"] > 0).mean()) if len(fold_r) else 0.0
    return [
        ("1 validable (≥ 4 folds)", b.validatable, f"{b.n_valid_folds} folds"),
        (f"2 ≥ {MIN_TRADES} operaciones", s.get("n_trades", 0) >= MIN_TRADES, f"n={s.get('n_trades', 0)}"),
        ("3 IC95 bloques semanales > 0", bool(ci[0] > 0), f"[{ci[0]:.3f}, {ci[1]:.3f}]"),
        (f"4 p vs dirección aleatoria < {P_THRESHOLD:.4f}",
         bm.get("p_value_vs_random_dir", 1.0) < P_THRESHOLD, f"p={bm.get('p_value_vs_random_dir', float('nan')):.3f}"),
        ("5 expectativa > 0 con costes C", c.summary.get("expectancy_r", -1) > 0,
         f"C: {c.summary.get('expectancy_r', float('nan')):.3f} R"),
        (f"6 ≥ {MIN_FOLD_POSITIVE:.0%} folds y ≥ {MIN_YEARS_POSITIVE}/5 años positivos",
         fpos >= MIN_FOLD_POSITIVE and int((yr > 0).sum()) >= MIN_YEARS_POSITIVE,
         f"folds+ {fpos:.0%}, años+ {int((yr > 0).sum())}/{len(yr)}"),
        ("7 dirección invertida < 0", bm.get("faded_direction_exp_r", 1.0) < 0,
         f"{bm.get('faded_direction_exp_r', float('nan')):.3f} R"),
        ("8 reproducible (mismo hash en 2 ejecuciones)", trades_hash(b.oos) == b2_hash, b2_hash),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("m1_csv")
    ap.add_argument("--tz", required=True)
    a = ap.parse_args()
    cfg = load_config()
    rd = load_broker_research_data(cfg, Path(a.m1_csv), parse_tz(a.tz))
    print(f"broker M1 {rd.m1.index[0]} -> {rd.m1.index[-1]} ({len(rd.m1):,}) coverage {rd.coverage.coverage_pct:.1f}%")
    # Execution mechanics only (no design change): the random-direction benchmark is slow with
    # long holds, so (family, scenario) tasks run in parallel forked processes. Every task seeds
    # its own generator from the config seed, so results do not depend on the scheduling.
    combos_by = {name: build_family_combos(rd, cfg, costs, all_configs(), alt_signals)
                 for name, costs in SCENARIOS.items()}
    again = build_family_combos(rd, cfg, SCENARIOS["B_base"], all_configs(), alt_signals)
    _G.update(rd=rd, cfg=cfg, combos=combos_by, again=again)
    tasks = [(fam, name, "combos") for name in SCENARIOS for fam in GRID] + \
            [(fam, "B_base", "again") for fam in GRID]
    with mp.get_context("fork").Pool(min(10, len(tasks))) as pool:
        out = pool.map(_task, tasks)
    res, folds_r, hashes2 = {}, {}, {}
    for (fam, name, which), (r, fr) in zip(tasks, out, strict=True):
        if which == "again":
            hashes2[fam] = trades_hash(r.oos)
        else:
            res[(fam, name)], folds_r[(fam, name)] = r, fr
            print(fam, name, r.summary.get("n_trades"), r.summary.get("expectancy_r"), flush=True)
    md = ["# Estudio 8 — Estrategias alternativas en XAUUSD (preregistrado)", "",
          ("> Hipótesis, rejilla, costes, protocolo y criterios fijados en `docs/06_hipotesis_alternativas.md` y "
          "`src/xauscalp/strategies/alt.py` **antes** de ejecutar. Nivel de evidencia 1 (M1 del bróker de MetaQuotes-Demo; "
          f"Ask = Bid + spread de la vela). Periodo reservado (≥ {cfg.validation['holdout_start']}) **no leído**."), ""]
    verdicts = {}
    for fam in GRID:
        b, c = res[(fam, "B_base")], res[(fam, "C_stress")]
        cr = criteria(fam, b, folds_r[(fam, "B_base")], c, hashes2[fam])
        verdicts[fam] = all(ok for _, ok, _ in cr)
    anyv = any(verdicts.values())
    md += [f"**Veredicto global: {'AL MENOS UNA FAMILIA CUMPLE LOS 8 CRITERIOS (candidata, NO autoriza ejecución)' if anyv else 'SIN EVIDENCIA DE VENTAJA NETA EN NINGUNA FAMILIA'}**",
           f"Configuraciones evaluadas: {N_CONFIGS} en {N_FAMILIES} familias; los resultados siguientes son de la ejecución B (base) salvo indicación.", "",
           "## Resumen por familia (B = costes base)"]
    rows = []
    for fam in GRID:
        sB, sA, sC = (res[(fam, n)].summary for n in ("B_base", "A_demo_as_is", "C_stress"))
        bm = res[(fam, "B_base")].bench
        rows.append({"familia": fam, "n OOS": sB.get("n_trades"), "exp R (B)": sB.get("expectancy_r"),
                     "IC95 inf": (sB.get("expectancy_r_ci95_weekblock") or (np.nan, np.nan))[0],
                     "exp R (A)": sA.get("expectancy_r"), "exp R (C)": sC.get("expectancy_r"),
                     "R a coste cero": bm.get("zero_cost_exp_r"), "R invertida": bm.get("faded_direction_exp_r"),
                     "p aleat.": bm.get("p_value_vs_random_dir"), "cumple 8/8": "SÍ" if verdicts[fam] else "no"})
    md += [md_table(pd.DataFrame(rows).set_index("familia"), "{:.4f}"), ""]
    for fam in GRID:
        b = res[(fam, "B_base")]
        cr = criteria(fam, b, folds_r[(fam, "B_base")], res[(fam, "C_stress")], hashes2[fam])
        md += [f"## {fam}", "", "| criterio | cumple | dato |", "|---|---|---|"]
        md += [f"| {n} | {'✅' if ok else '❌'} | {d} |" for n, ok, d in cr]
        if len(b.by_year):
            md += ["", "OOS por año:", md_table(b.by_year, "{:.3f}")]
        if len(folds_r[(fam, "B_base")]):
            md += ["", "R por fold OOS:", md_table(folds_r[(fam, "B_base")].set_index("test_start"), "{:.2f}")]
        if b.summary.get("n_trades"):
            sl = b.oos.loc[b.oos["valid"], "sl_dist"]
            md += ["", (f"Viabilidad de capital (aparte): SL mediano {sl.median():.1f} USD → 0,01 lotes arriesgan "
                   f"≈ {sl.median():.1f} USD; para un riesgo del 0,5 % haría falta ≈ {sl.median() / 0.005:,.0f} USD de capital.")]
        md += [""]
    allc = []
    for (fam, params, _, tr) in combos_by["B_base"].values():
        r = tr["r"].to_numpy() if len(tr) else np.array([])
        allc.append({"config": f"{fam} {params}", "n": len(r), "exp_R": float(r.mean()) if len(r) else np.nan})
    ct = pd.DataFrame(allc).set_index("config").sort_values("exp_R", ascending=False)
    md += [f"## Las {len(ct)} configuraciones en todo el periodo (descriptivo, B; NO se usa para elegir)",
           f"Con {len(ct)} configuraciones el máximo está sesgado al alza por azar. Con expectativa > 0: {(ct.exp_R > 0).sum()} de {len(ct)}.",
           md_table(ct, "{:.4f}"), ""]
    out = ROOT / "reports"
    (out / "08_alt_strategies.md").write_text("\n".join(md))
    for fam in GRID:
        o = res[(fam, "B_base")].oos
        if len(o):
            o.to_csv(out / f"08_oos_trades_{fam}.csv", index=False)
    print("\n".join(md[:14]))


if __name__ == "__main__":
    main()
