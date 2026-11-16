"""Study 9: could the strategies tested so far pass an FTMO-style 2-step challenge?

Inputs: the OUT-OF-SAMPLE trade lists of studies 7 and 8 (broker M1, costs scenario B already
inside R) and the rules in config/propfirm_ftmo_2step.yaml. NOTHING here proves an edge: the
point is to turn the measured (and uncertain) edge into pass probabilities and to compare with
a NULL strategy (same variance and clustering, zero net edge).

    uv run python research/09_propfirm_feasibility.py data/mt5/XAUUSD_M1_20210101_20261113.csv \
        --tz base_dst:120:Europe/London
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import pandas as pd

from xauscalp.config import ROOT, load_config
from xauscalp.parity import parse_tz
from xauscalp.pipeline import load_broker_research_data, md_table
from xauscalp.propfirm.montecarlo import McConfig, run_mc, weeks_from_trades
from xauscalp.propfirm.replay import replay, trade_mae_r
from xauscalp.propfirm.rules import Phase, load_rules

SETS = {"ORB (estudio 7)": "07_orb_broker_oos_trades.csv",
        "tendencia Donchian": "08_oos_trades_trend_donchian.csv",
        "pullback": "08_oos_trades_pullback.csv", "momentum": "08_oos_trades_momentum_tsmom.csv"}
MAIN_RISKS = (0.25, 0.5)          # operational: config risk 0.5 %/trade (hard ceiling 1.0 %)
SENS_RISKS = (1.0,)               # sensitivity ONLY, not an operational setting
RISKS = MAIN_RISKS + SENS_RISKS
HORIZON_WEEKS = 104               # the firm has no time limit: two years per phase
INITIAL, FEE = 10_000.0, 89.0                 # smallest size: loss at risk is the fee, not the capital
_G: dict = {}


def _task(t):
    name, risk, null = t
    cfg = McConfig(initial=INITIAL, risk_pct=risk, fee=FEE, max_weeks_per_phase=HORIZON_WEEKS)
    return t, run_mc(_G["weeks"][name], cfg, _G["rules"], null=null)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("m1_csv")
    ap.add_argument("--tz", required=True)
    a = ap.parse_args()
    cfg = load_config()
    rules = load_rules()
    rd = load_broker_research_data(cfg, Path(a.m1_csv), parse_tz(a.tz))
    m1 = rd.m1
    weeks, trades_by, stats = {}, {}, []
    for name, f in SETS.items():
        tr = pd.read_csv(ROOT / "reports" / f, parse_dates=["entry_time", "exit_time"])
        tr = tr[tr["valid"]].reset_index(drop=True)
        mae = trade_mae_r(tr, m1, extra_spread=0.15)
        weeks[name] = weeks_from_trades(tr, tr["r"].to_numpy(), mae)
        trades_by[name] = tr
        stats.append({"estrategia": name, "n": len(tr), "R medio": tr["r"].mean(),
                      "R desv": tr["r"].std(), "MAE medio (R)": mae.mean(),
                      "semanas": len(weeks[name]), "op/semana": len(tr) / len(weeks[name])})
    _G.update(weeks=weeks, rules=rules)
    tasks = [(n, r, nl) for n in SETS for r in RISKS for nl in (False, True)]
    with mp.get_context("fork").Pool(10) as pool:
        res = dict(pool.map(_task, tasks))
    def table(risks):
        rows = []
        for n in SETS:
            for r in risks:
                a_, z = res[(n, r, False)], res[(n, r, True)]
                f = lambda q: f"{q[1]:.1%} [{q[0]:.1%}–{q[2]:.1%}]"
                rows.append({"estrategia": n, "riesgo %/op": r, "P(Challenge)": f(a_["p_challenge"]),
                             "P(Challenge+Verif.)": f(a_["p_both"]), "P(suspender)": f(a_["p_fail"]),
                             f"sin resolver {HORIZON_WEEKS} sem": f(a_["p_unresolved"]),
                             "NULO P(Ch.+Ver.)": f(z["p_both"]),
                             "EV € (mediana)": a_["ev_eur"][1], "EV nulo €": z["ev_eur"][1]})
        return md_table(pd.DataFrame(rows).set_index("estrategia"), "{:.2f}")

    # historical replay: every 4th week as a start date, phase 1 only, exact floating equity
    rep_rows = []
    for n, tr in trades_by.items():
        t0 = tr["entry_time"].min().normalize()
        outcomes = []
        for k in range(int((tr["entry_time"].max() - t0).days // 28)):
            start = t0 + pd.Timedelta(days=28 * k)
            sub = tr[tr["entry_time"] >= start]
            if len(sub) < 5:
                break
            r = replay(sub, m1, rules, Phase.CHALLENGE, INITIAL, 0.5, extra_spread=0.15)
            outcomes.append(r["status"] if r["status"] != "RUNNING" else "SIN RESOLVER")
        rep_rows.append({"estrategia": n, "inicios (cada 4 sem.)": len(outcomes),
                         "PASSED": outcomes.count("PASSED"), "FAILED": outcomes.count("FAILED"),
                         "sin resolver": outcomes.count("SIN RESOLVER")})
    md = ["# Estudio 9 — Viabilidad frente a un challenge de prop firm (simulación)", "",
          ("> Entradas: operaciones OOS de los estudios 7 y 8 (M1 del bróker, costes B incluidos en R). Reglas: "
          f"`config/propfirm_ftmo_2step.yaml` (leídas el {rules.retrieved}; **lo no verificado está listado en el fichero**). "
          f"Cuenta simulada {INITIAL:,.0f}, cuota {FEE:.0f} €, riesgo fijo por operación sobre el capital inicial. "
          "Incertidumbre: bootstrap por semanas (100 re-muestreos × 200 trayectorias; entre corchetes percentiles 5–95 %). "
          "**Control nulo**: mismas semanas con la expectativa neta desplazada a 0."), "",
          "## Datos de entrada", md_table(pd.DataFrame(stats).set_index("estrategia"), "{:.3f}"), "",
          "## Evaluación PRINCIPAL: riesgo operativo del proyecto (0,5 % por operación; también 0,25 %)",
          f"Horizonte {HORIZON_WEEKS} semanas por fase (FTMO no tiene límite de tiempo).", table(MAIN_RISKS), "",
          "## Sensibilidad separada: 1 % por operación (techo duro del proyecto; NO es la configuración operativa)",
          "Solo para ver cuánto cambia el resultado con más riesgo; no se usa para decidir nada.", table(SENS_RISKS), "",
          "## Reproducción histórica exacta (fase 1, riesgo 0,5 %, equity flotante M1)",
          md_table(pd.DataFrame(rep_rows).set_index("estrategia")), "",
          ("**Ninguna de estas probabilidades valida una estrategia.** En particular la tendencia Donchian NO queda validada por aprobar el challenge simulado: su ventaja no es "
          "estadísticamente significativa (estudio 8) y proviene de operaciones largas en un mercado alcista; la tasa de aprobación hereda esa incertidumbre. "
          "Lectura: si P(Challenge+Verif.) de una estrategia **no supera claramente** la del control nulo, el resultado de un challenge sería "
          "suerte; el valor esperado es la cuota perdida menos/más los pagos. Una estrategia sin ventaja demostrada **no justifica pagar**.")]
    (ROOT / "reports" / "09_propfirm_feasibility.md").write_text("\n".join(md))
    print("\n".join(md[:30]))


if __name__ == "__main__":
    main()
