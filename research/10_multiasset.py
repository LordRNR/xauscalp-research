"""Study 10: multi-asset trend / momentum / FX reversion (PREREGISTERED in docs/08_hipotesis_multiactivo.md).

Hypotheses, the closed 18-configuration grid, costs relative to each symbol's spread, the basket
walk-forward, three controls and the acceptance criteria are fixed in that document and in
src/xauscalp/strategies/multi.py + src/xauscalp/multiasset.py BEFORE any real data was seen.
NOT RUN on real data yet: it needs the user's MT5 exports (see docs/08 and docs/10).

    uv run python research/10_multiasset.py --dir data/mt5 \
        --specs data/mt5/xauscalp/symbol_specs_mqdemo.csv --tz base_dst:120:Europe/London
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from pathlib import Path

import numpy as np

from xauscalp.backtest.family_study import trades_hash
from xauscalp.config import ROOT, SymbolSpec, load_config
from xauscalp.multiasset import cost_model_for, median_spread, run_basket
from xauscalp.parity import parse_tz
from xauscalp.pipeline import load_broker_research_data, md_table
from xauscalp.strategies.multi import GRID, N_CONFIGS, all_configs, multi_signals
from xauscalp.symbol_specs import load_specs, viability_table

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAGUSD"]
FX = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"}
MIN_SYMBOLS = 4
P_THRESHOLD = 0.05 / 3                      # Bonferroni over the three controls
_G: dict = {}


def _task(t):
    fam, scen, _again = t
    rds, specs, cfg = _G["rds"], _G["specs"], _G["cfg"]
    sym = [s for s in rds if fam != "m3_fx_reversion" or s in FX]
    costs = {s: cost_model_for(rds[s].m1, scen, _G["ccy"][s][0], _G["ccy"][s][1]) for s in sym}
    return t, run_basket({s: rds[s] for s in sym}, {s: specs[s] for s in sym}, costs, all_configs(True),
                         multi_signals, cfg, fam, n_controls=200)


def criteria(b, c, h2, by_year, by_sym, fold_r):
    s, bm = b.summary, b.bench
    ci = s.get("expectancy_r_ci95_weekblock", (np.nan, np.nan))
    fpos = float((fold_r["sum_r"] > 0).mean()) if len(fold_r) else 0.0
    ypos = int((by_year["total_r"] > 0).sum()) if len(by_year) else 0
    spos = float((by_sym["expectancy_r"] > 0).mean()) if len(by_sym) else 0.0
    act = bm.get("actual_exp_r", np.nan)
    return [
        ("1 ≥ 4 folds y ≥ 200 operaciones OOS", b.n_valid_folds >= 4 and s.get("n_trades", 0) >= 200, f"{b.n_valid_folds} folds, n={s.get('n_trades', 0)}"),
        ("2 IC95 bloques semanales > 0", bool(ci[0] > 0), f"[{ci[0]:.3f}, {ci[1]:.3f}]"),
        (f"3a p vs dirección aleatoria < {P_THRESHOLD:.4f}", bm.get("p_random_direction", 1) < P_THRESHOLD, f"p={bm.get('p_random_direction', float('nan')):.3f}"),
        (f"3b p vs tiempos de entrada aleatorios < {P_THRESHOLD:.4f}", bm.get("p_random_entry_times", 1) < P_THRESHOLD, f"p={bm.get('p_random_entry_times', float('nan')):.3f}"),
        ("3c supera a «siempre largo» con las mismas señales", bool(act > bm.get("always_long_exp_r", np.inf)), f"{act:.3f} vs {bm.get('always_long_exp_r', float('nan')):.3f}"),
        ("4 expectativa > 0 con costes C", c.summary.get("expectancy_r", -1) > 0, f"{c.summary.get('expectancy_r', float('nan')):.3f}"),
        ("5 ≥ 60 % folds, ≥ 3 años y ≥ 60 % de activos positivos", fpos >= 0.6 and ypos >= 3 and spos >= 0.6, f"folds {fpos:.0%}, años {ypos}, activos {spos:.0%}"),
        ("6 invertida < 0 y coste cero > con costes", bm.get("faded_direction_exp_r", 1) < 0 and bm.get("zero_cost_exp_r", -1) > act, f"{bm.get('faded_direction_exp_r', float('nan')):.3f} / {bm.get('zero_cost_exp_r', float('nan')):.3f}"),
        ("7 reproducible (mismo hash)", trades_hash(b.oos) == h2, h2),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--specs", required=True)
    ap.add_argument("--tz", required=True)
    a = ap.parse_args()
    d = Path(a.dir)
    files = {s: sorted(d.glob(f"{s}_M1_*.csv")) for s in SYMBOLS}
    have = [s for s in SYMBOLS if files[s]]
    if len(have) < MIN_SYMBOLS:
        raise SystemExit(f"need ≥ {MIN_SYMBOLS} exported symbols in {d}, found {have}. See docs/10_exportacion_multiactivo_y_ftmo.md")
    cfg = load_config()
    specs_file = load_specs(a.specs)
    rds, specs, ccy = {}, {}, {}
    for s in have:
        if s not in specs_file.df.index or specs_file.df.loc[s, "found"] != 1:
            raise SystemExit(f"{s} is missing from the specs file {a.specs}")
        r = specs_file.df.loc[s]
        rds[s] = load_broker_research_data(cfg, files[s][-1], parse_tz(a.tz))
        specs[s] = SymbolSpec(name=s, contract_size=float(r["contract_size"]), volume_min=float(r["volume_min"]),
                              volume_step=float(r["volume_step"]), volume_max=float(r["volume_max"]),
                              profit_currency=str(r["currency_profit"]))
        ccy[s] = (str(r["currency_profit"]), str(r["currency_base"]))
        print(s, f"{len(rds[s].m1):,} bars, coverage {rds[s].coverage.coverage_pct:.1f}%, median spread {median_spread(rds[s].m1):.6f}")
    _G.update(rds=rds, specs=specs, cfg=cfg, ccy=ccy)
    fams = list(GRID)
    tasks = [(f, sc, False) for f in fams for sc in ("A", "B", "C")] + [(f, "B", True) for f in fams]
    with mp.get_context("fork").Pool(min(10, len(tasks))) as pool:
        out = dict(pool.map(_task, tasks))
    md = ["# Estudio 10 — Cesta multiactivo (preregistrado)", "",
          ("> Hipótesis, rejilla (18 configuraciones), costes relativos al spread de cada símbolo, selección por cesta, tres controles y criterios fijados en "
          "`docs/08_hipotesis_multiactivo.md` antes de ver datos. Nivel de evidencia 1 (M1 de MetaQuotes-Demo; spreads de demo: no son de un bróker real). "
          f"Periodo reservado (≥ {cfg.validation['holdout_start']}) no leído. Símbolos: {', '.join(have)}."), ""]
    verdicts = {}
    for f in fams:
        b, c, h = out[(f, "B", False)], out[(f, "C", False)], trades_hash(out[(f, "B", True)].oos)
        cr = criteria(b, c, h, b.by_year, b.by_symbol, b.fold_r)
        verdicts[f] = all(ok for _, ok, _ in cr)
        md += [f"## {f}", "", "| criterio | cumple | dato |", "|---|---|---|"] + [f"| {n} | {'✅' if ok else '❌'} | {dd} |" for n, ok, dd in cr] + [""]
        if len(b.by_symbol):
            md += ["Por activo:", md_table(b.by_symbol, "{:.3f}"), ""]
        if len(b.by_year):
            md += ["Por año:", md_table(b.by_year, "{:.3f}"), ""]
    md.insert(3, f"**Veredicto global: {'AL MENOS UNA CESTA CUMPLE LOS CRITERIOS (candidata, NO autoriza ejecución)' if any(verdicts.values()) else 'SIN EVIDENCIA DE VENTAJA NETA'}**  (configuraciones: {N_CONFIGS})")
    # instrument viability (independent of any edge)
    sl = {}
    for s in have:
        sg = multi_signals(rds[s].m1, "m1_tsmom", GRID["m1_tsmom"][0])
        sl[s] = float(np.median([x.sl_dist for x in sg])) if sg else float("nan")
    for cap in (1000, 10000):
        md += [f"## Viabilidad por instrumento con {cap:,} (SL = mediana de 3×ATR diario, riesgo 0,5 %)",
               md_table(viability_table(specs_file, cap, 0.5, {k: v for k, v in sl.items() if np.isfinite(v)}).round(4), "{:.4f}"), ""]
    (ROOT / "reports" / "10_multiasset.md").write_text("\n".join(md))
    print("\n".join(md[:10]))


if __name__ == "__main__":
    main()
