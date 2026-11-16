"""Cost calibration from a tick export of ANOTHER server (e.g. a prop-firm Free Trial). SPREADS ONLY.

This tool deliberately computes nothing about price direction or returns: it reports quote integrity
and the distribution of ask - bid (overall and by UTC hour) plus the tick rate. That is why it may
read any recent dates (the research holdout protects strategy EVALUATION, and no strategy is
evaluated here). It never feeds the research pipeline and never touches orders.

    uv run python research/11_cost_calibration.py data/mt5/XAUUSD_ticks_<from>_<to>.csv --label ftmo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from xauscalp.config import ROOT
from xauscalp.data import tick_quality as tq
from xauscalp.data.sources import read_mt5_ticks_raw
from xauscalp.pipeline import md_table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticks_csv")
    ap.add_argument("--label", required=True, help="server label for the report name (e.g. ftmo)")
    a = ap.parse_args()
    raw, meta = read_mt5_ticks_raw(Path(a.ticks_csv), max_date=None)     # spreads only: see docstring
    ticks, dropped = tq.clean_quotes(raw)
    st = tq.spread_stats(ticks)
    by_hour = tq.spread_by_hour(ticks)
    span_days = (ticks.index[-1] - ticks.index[0]).total_seconds() / 86400
    md = [f"# Calibración de costes — servidor `{a.label}` (solo spreads)", "",
          ("> Esta herramienta no calcula rentabilidad ni usa precios para ninguna señal; por eso puede leer fechas recientes. "
          "El spread de una **Free Trial** es de una cuenta de prueba: contrástalo con la primera cuenta real antes de fiarte."), "",
          f"- Símbolo/metadatos: {meta}", f"- Ticks válidos: {len(ticks):,} (descartados: {dropped}); periodo {ticks.index[0]} → {ticks.index[-1]} ({span_days:.1f} días)", "",
          "## Spread (ask − bid, unidades de precio)", md_table(pd.DataFrame({"valor": pd.Series(st, dtype=object)})), "",
          "## Por hora UTC", md_table(by_hour, "{:.4f}"), "",
          "Siguiente paso: comparar con la mediana de MetaQuotes-Demo (0,17 $ en oct-2025) y con la comisión por lote y los swaps del contrato (a mano, en `config/propfirm_ftmo_2step.yaml` → `unverified`)."]
    out = ROOT / "reports" / f"11_cost_calibration_{a.label}.md"
    out.write_text("\n".join(md))
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
