"""Study 7: ORB walk-forward on the BROKER's M1 history (MetaQuotes-Demo, 2021-2025-10).

PRE-REGISTERED BEFORE RUNNING (this file was committed before the first execution):
  Data    : broker M1 export, research slice only (< 2025-11-01), verified server tz rule.
            Level-1 evidence (M1 bars, Ask = Bid + bar-minimum spread -> optimistic floor).
  Protocol: identical to study 2 (grid, 12m/3m walk-forward, abstain if train exp <= 0,
            joint single-position OOS, benchmarks on the same signals). No new parameters.
  Costs   : three scenarios fixed here, NOT tuned to results. The demo spread (median
            0.17 USD) is not a real broker's, so A is only a floor:
              A demo_as_is : extra spread 0.00, slippage 0.05, commission 0 USD/lot RT
              B base       : extra spread 0.15, slippage 0.10, commission 7 USD/lot RT
              C stress     : extra spread 0.30, slippage 0.30, commission 7 USD/lot RT
            (7 USD/lot round turn is a typical raw-spread-account commission: an assumption.)
  News    : FOMC/CPI/NFP blackout (30 min before/after, config/events.csv) at the decision.
            Primary = B with blackout; sensitivity = B without blackout.
  Verdict : "EVIDENCE OF NET EDGE" only if ALL hold under the PRIMARY run: validatable
            (>= min_valid_folds), n_trades >= 100, week-block 95 % CI of expectancy_r has a
            lower bound > 0, p vs random direction < 0.05, AND expectancy_r > 0 under C.
            Otherwise "NO EVIDENCE OF NET EDGE" (a valid, publishable result).
  Not used: the holdout (readers stop at the limit), demo-feed spreads as a cost model.

    uv run python research/07_orb_broker_eval.py data/mt5/XAUUSD_M1_20210101_20261113.csv \
        --tz base_dst:120:Europe/London
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from xauscalp.backtest.orb_study import StudyResult, run_orb_walkforward
from xauscalp.calendar.events import load_events
from xauscalp.config import ROOT, CostModel, load_config
from xauscalp.parity import parse_tz
from xauscalp.pipeline import load_broker_research_data, md_table

SCENARIOS = {
    "A_demo_as_is": CostModel(0.00, 0.05, 0.0),
    "B_base": CostModel(0.15, 0.10, 7.0),
    "C_stress": CostModel(0.30, 0.30, 7.0),
}
RUNS = [("B_base", True), ("A_demo_as_is", True), ("C_stress", True), ("B_base", False)]
PRIMARY = ("B_base", True)
MIN_TRADES = 100


def fmt(d: dict) -> str:
    def conv(v):
        if isinstance(v, float):
            return round(v, 4)
        if isinstance(v, tuple):
            return tuple(round(x, 4) for x in v)
        return v
    return "```\n" + json.dumps({k: conv(v) for k, v in d.items()}, indent=1, default=str) + "\n```"


def verdict(prim: StudyResult, stress: StudyResult) -> tuple[bool, list[str]]:
    s, b = prim.summary, prim.bench
    ci = s.get("expectancy_r_ci95_weekblock", (float("nan"), float("nan")))
    checks = {
        "validable (folds suficientes)": prim.validatable,
        f"n_trades >= {MIN_TRADES}": s.get("n_trades", 0) >= MIN_TRADES,
        "IC95 (bloques semanales) de la expectativa > 0": ci[0] > 0,
        "p vs dirección aleatoria < 0,05": b.get("p_value_vs_random_dir", 1.0) < 0.05,
        "expectativa > 0 también en C (estrés)": stress.summary.get("expectancy_r", -1) > 0,
    }
    return all(checks.values()), [f"{'✅' if ok else '❌'} {k}" for k, ok in checks.items()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("m1_csv")
    ap.add_argument("--tz", required=True)
    a = ap.parse_args()
    cfg = load_config()
    rd = load_broker_research_data(cfg, Path(a.m1_csv), parse_tz(a.tz))
    ev = load_events(ROOT / "config" / "events.csv")
    print(f"broker M1 {rd.m1.index[0]} -> {rd.m1.index[-1]} ({len(rd.m1):,} bars) "
          f"coverage {rd.coverage.coverage_pct:.1f}%  events={len(ev)}")
    res: dict[tuple[str, bool], StudyResult] = {}
    for name, news in RUNS:
        res[(name, news)] = run_orb_walkforward(rd, cfg, SCENARIOS[name], ev if news else None)
        r = res[(name, news)]
        print(name, "news" if news else "no-news", "folds", r.n_valid_folds, r.summary.get("n_trades"),
              r.summary.get("expectancy_r"))
    edge, lines = verdict(res[PRIMARY], res[("C_stress", True)])
    prim = res[PRIMARY]
    v = cfg.validation
    md = ["# Estudio 7 — ORB sobre el histórico del bróker (walk-forward, costes realistas)", "",
          ("> Nivel de evidencia 1 (velas M1 del feed de MetaQuotes-Demo; Ask = Bid + spread mínimo de la vela). "
          "No es un bróker real ni ticks reales. Periodo reservado (≥ "
          f"{v['holdout_start']}) **no leído**. Escenarios y regla de veredicto fijados antes de ejecutar."), "",
          f"**Veredicto: {'EVIDENCIA DE VENTAJA NETA' if edge else 'SIN EVIDENCIA DE VENTAJA NETA'}**", ""]
    md += [f"- {x}" for x in lines]
    md += ["", (f"Datos: {rd.m1.index[0]:%Y-%m-%d} → {rd.m1.index[-1]:%Y-%m-%d}, {len(rd.m1):,} barras, "
           f"cobertura {rd.coverage.coverage_pct:.1f} % ({rd.coverage.usable_days}/{rd.coverage.expected_days} días). "
           f"Folds válidos: {prim.n_valid_folds}. Configuraciones evaluadas por escenario: {prim.n_combos} "
           f"(selección walk-forward por sesión). Señales retiradas por noticias (primario): "
           f"{prim.n_signals_blackout_removed}."), "",
           "## Escenarios de coste (fijados antes)",
           md_table(pd.DataFrame({n: {"spread extra": c.extra_spread_usd, "slippage": c.slippage_usd,
                                      "comisión USD/lote RT": c.commission_per_lot_usd}
                                  for n, c in SCENARIOS.items()}).T.rename_axis("escenario")), ""]
    summ = {f"{n}{'' if news else ' (sin noticias)'}": {
        "n": r.summary.get("n_trades"), "exp_R": r.summary.get("expectancy_r"),
        "IC95_bloques": r.summary.get("expectancy_r_ci95_weekblock"),
        "PF": r.summary.get("profit_factor"), "win": r.summary.get("win_rate"),
        "p_vs_random": r.bench.get("p_value_vs_random_dir"),
        "exp_R_coste_cero": r.bench.get("zero_cost_exp_r"),
        "exp_R_dirección_invertida": r.bench.get("faded_direction_exp_r")}
        for (n, news), r in res.items()}
    md += ["## Comparación de escenarios (resultado OOS conjunto)", "```", json.dumps(summ, indent=1, default=str), "```", ""]
    md += ["## Primario (B_base + noticias): detalle", fmt(prim.summary), "### Benchmarks", fmt(prim.bench),
           "### Monte Carlo de drawdown (R)", fmt(prim.mc) if prim.mc else "_n/a_", "### Selección por fold",
           md_table(prim.folds), ""]
    for t, df in (("año", prim.by_year), ("sesión", prim.by_session)):
        md += [f"### OOS por {t}", md_table(df), ""]
    ct = prim.combos_table.sort_values("exp_r", ascending=False)
    md += ["## Las 36 combinaciones en todo el periodo (descriptivo, escenario B; NO se usa para elegir)",
           (f"Con {len(ct)} combinaciones el mejor valor está sesgado al alza por azar: no se interpreta. "
           f"Combinaciones con expectativa > 0: {(ct.exp_r > 0).sum()} de {len(ct)}."),
           md_table(ct), ""]
    out = ROOT / "reports"
    (out / "07_orb_broker_eval.md").write_text("\n".join(md))
    if len(prim.oos):
        prim.oos.to_csv(out / "07_orb_broker_oos_trades.csv", index=False)
    print("\n".join(md[:14]))


if __name__ == "__main__":
    main()
