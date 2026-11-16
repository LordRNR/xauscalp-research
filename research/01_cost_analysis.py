"""Study 1: are scalping costs small relative to gold's short-term movement?

Descriptive market study (research slice only). For each UTC hour / session it compares
the round-trip cost (spread + extra broker spread + 2 x slippage) with the typical
15-minute absolute move and M5 ATR. A forward-looking move is fine HERE because it
describes the market; it is never used as a feature.

    uv run python research/01_cost_analysis.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from xauscalp.config import ROOT, load_config
from xauscalp.pipeline import load_research_data, md_table


def main() -> None:
    cfg = load_config()
    rd = load_research_data(cfg)
    m1, f = rd.m1, rd.feats
    c = cfg.costs
    mid = (m1["bid_c"] + m1["ask_c"]) / 2
    # move15 by TIME (exactly +15 min), never by row shift: no crossing of gaps/weekends
    fut = mid.reindex(m1.index + pd.Timedelta(minutes=15)).to_numpy()
    df = pd.DataFrame({
        "spread": f["spread"],
        "cost_rt": f["spread"] + c.extra_spread_usd + 2 * c.slippage_usd,
        "atr_m5": f["atr_m5"],
        "move15": np.abs(fut - mid.to_numpy()),   # descriptive only (forward-looking)
        "price": mid,
        "session": f["session"],
        "hour_utc": m1.index.hour,
        "year": m1.index.year,
    }).dropna()
    df["cost_over_move15"] = df["cost_rt"] / df["move15"].replace(0, np.nan)

    by_hour = df.groupby("hour_utc").agg(
        spread_med=("spread", "median"), cost_rt_med=("cost_rt", "median"),
        atr_m5_med=("atr_m5", "median"), move15_med=("move15", "median"),
    )
    by_hour["cost_pct_of_move15"] = 100 * by_hour["cost_rt_med"] / by_hour["move15_med"]
    by_sess = df.groupby("session").agg(
        bars=("spread", "size"), spread_med=("spread", "median"),
        spread_p90=("spread", lambda s: s.quantile(0.9)), cost_rt_med=("cost_rt", "median"),
        atr_m5_med=("atr_m5", "median"), move15_med=("move15", "median"),
    )
    by_sess["cost_pct_of_move15"] = 100 * by_sess["cost_rt_med"] / by_sess["move15_med"]
    by_year = df.groupby("year").agg(
        price_med=("price", "median"), spread_med=("spread", "median"),
        atr_m5_med=("atr_m5", "median"), move15_med=("move15", "median"),
    )
    by_year["cost_pct_of_move15"] = 100 * (by_year["spread_med"] + c.extra_spread_usd
                                           + 2 * c.slippage_usd) / by_year["move15_med"]

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    by_hour.to_csv(out / "01_cost_by_hour_utc.csv")
    by_sess.to_csv(out / "01_cost_by_session.csv")
    cov = rd.coverage
    enough = cov.coverage_pct >= 80
    md = [
        "# Estudio 1 — Costes de scalping frente al movimiento del oro",
        "",
        f"> **Cobertura del histórico: {cov.coverage_pct:.1f} %** de las barras esperadas "
        f"({cov.usable_days}/{cov.expected_days} días utilizables). "
        + ("" if enough else "**Insuficiente: estudio DESCRIPTIVO de los segmentos disponibles, "
           "no representativo del periodo completo.**"),
        "",
        (f"Datos: Dukascopy M1 bid/ask, {rd.quality['start']} → {rd.quality['end']} "
        f"(solo tramo de investigación; holdout ≥ {cfg.validation['holdout_start']} intacto)."),
        f"Integridad: `{json.dumps(rd.quality)}`",
        "",
        (f"Modelo de costes: spread Dukascopy + extra {c.extra_spread_usd} $ + 2×slippage "
        f"{c.slippage_usd} $. Unidades: USD por onza (= USD por 0,01 lotes en un contrato de 100 oz)."),
        "",
        "## Cobertura y calidad",
        cov.to_markdown(),
        "",
        "## Por sesión",
        md_table(by_sess),
        "",
        "## Por año (el nivel de precio cambia mucho → parámetros en unidades de ATR, no en $)",
        md_table(by_year),
        "",
        "## Por hora UTC",
        md_table(by_hour),
        "",
        ("_`move15` = movimiento absoluto mediano en 15 min (descriptivo, mira al futuro; "
        "nunca se usa como variable predictiva)._"),
    ]
    (out / "01_cost_analysis.md").write_text("\n".join(md))
    print("\n".join(md[:30]))


if __name__ == "__main__":
    main()
