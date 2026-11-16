"""Verify the MT5 server timezone empirically (needed before any broker-data study).

Matches the broker's M1 Bid closes (exported with XAU_ExportHistory.mq5, naive SERVER
time) against Dukascopy M1 Bid closes (UTC) week by week and reports the offset that
best aligns 1-minute returns. Only dates BEFORE the holdout are used on both sides.

    uv run python research/04_verify_server_tz.py <path/to/XAUUSD_M1_....csv>

Output: reports/04_server_tz.md with one row per week (offset, correlation, margin,
confidence) and a verdict from data.server_time.fit_server_rule: CONSISTENT (one rule,
with the EA inputs and the --tz spec to use), AMBIGUOUS, INCONSISTENT or INSUFFICIENT.
Declare the rule in the EA ONLY when the verdict is CONSISTENT; otherwise keep TZ_UNKNOWN.
"""

from __future__ import annotations

import sys
from datetime import date

import pandas as pd

from xauscalp.config import ROOT, load_config
from xauscalp.data.dukascopy import load_m1
from xauscalp.data.server_time import fit_server_rule, infer_weekly_offsets
from xauscalp.mt5_report import read_mt5_rates_raw
from xauscalp.pipeline import md_table, research_max_date


def main(path: str) -> None:
    cfg = load_config()
    max_d = research_max_date(cfg)
    broker, meta = read_mt5_rates_raw(path, max_date=max_d)
    broker = broker[broker.index < pd.Timestamp(max_d) + pd.Timedelta(days=1)]
    if broker.empty:
        sys.exit("broker export has no bars before the holdout; export older history")
    start = (broker.index.min() - pd.Timedelta(days=1)).date()
    ref = load_m1(
        cfg.data["symbol"],
        max(start, date(2000, 1, 1)),
        max_d,
        ROOT / cfg.data.get("dir", "data"),
        max_date=max_d,
    )["bid_c"]
    tab = infer_weekly_offsets(broker["close"], ref)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    v = fit_server_rule(tab)
    conf = v.n_confident
    md = [
        "# Estudio 4 — Zona horaria del servidor MT5 (verificación empírica)",
        "",
        (
            f"Servidor: {meta.get('server', '?')} · offset al exportar: "
            f"{meta.get('server_minus_gmt_seconds_at_export', '?')} s · semanas: {len(tab)}, "
            f"confiables: {conf}"
        ),
        "",
        f"## Veredicto: **{v.status}**",
        "",
        f"- Base (min) de cada regla que explica TODAS las semanas confiables: {v.fits}",
        f"- Semanas que separan regla de EE. UU. y de la UE: {v.n_us_eu_discriminating}",
        f"- Semanas a ambos lados de un cambio de hora: {v.n_dst_mixed}",
        (f"- **Declarar en el EA**: `{v.ea_inputs}` · **paridad/Python**: `--tz {v.cli_spec}`"
         if v.status == "CONSISTENT" else
         "- **No declares ninguna política**: mantén `TZ_UNKNOWN` (ver explicación)."),
        "",
        {"CONSISTENT": "Una única regla explica todas las semanas y los datos contienen las "
                       "semanas capaces de refutar las alternativas.",
         "AMBIGUOUS": "Varias reglas encajan: faltan semanas en las ventanas en que difieren "
                      "(marzo entre el 2.º y el último domingo; final de octubre/primeros de "
                      "noviembre). Exporta más historial o descarga esas semanas de Dukascopy.",
         "INCONSISTENT": "Ninguna regla simple explica todas las semanas: el servidor pudo "
                         "cambiar de política o hay semanas erróneas. Usa la política "
                         "`inferred` semana a semana o revisa la tabla.",
         "INSUFFICIENT": "Menos de 8 semanas confiables solapadas con la referencia."
         }[v.status],
        "",
        md_table(tab.set_index("week")),
        "",
    ]
    (out / "04_server_tz.md").write_text("\n".join(md))
    print("\n".join(md[:14]))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
