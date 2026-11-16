"""Study 3: WHY does the ORB (not) trade?  Funnel diagnostics, no parameter changes.

For every (day, session) of the research slice it records the outcome of each rule:
  NO_DATA / OR_INCOMPLETE / NO_ATR       -> data problems (no evaluation possible)
  NO_BREAKOUT                            -> NO technical signal
  DATA_GAP_AT_SIGNAL / REJECT_SPREAD /
  REJECT_COST                            -> technical signal exists but NOT tradable
  SIGNAL                                 -> passes the strategy's own filters
Then, for SIGNAL records, it asks the Risk Manager whether the trade would be possible
at several account sizes (USD account to avoid assuming an FX rate; 23 USD ~ 20 EUR) and
which rule blocks it (minimum volume vs. risk, margin, spread...).
Nothing here selects parameters; results are descriptive and carry the data coverage.

    uv run python research/03_orb_diagnostics.py
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import run_backtest
from xauscalp.config import ROOT, load_config
from xauscalp.pipeline import load_research_data, md_table
from xauscalp.risk.manager import AccountState, MarketState, RiskManager, TradeProposal
from xauscalp.strategies.orb import (
    STATUSES,
    TECHNICAL_SIGNAL,
    ORBParams,
    orb_scan,
    records_frame,
    records_to_signals,
)

EQUITY_LEVELS_USD = (23, 500, 1_000, 10_000, 100_000)


def capital_check(rec, m1, cfg, equity: float) -> tuple[bool, tuple[str, ...], float]:
    half = cfg.costs.extra_spread_usd / 2
    i = rec.decision_idx
    bid, ask = m1["bid_c"].iat[i] - half, m1["ask_c"].iat[i] + half
    entry = ask if rec.direction == 1 else bid
    sl = entry - rec.direction * rec.sl_dist
    rm = RiskManager(cfg.risk, cfg.symbol, profit_to_account_rate=1.0,
                     leverage=float(cfg.account.get("leverage", 20)))
    acct = AccountState(equity=equity, free_margin=equity, day_start_equity=equity,
                        week_start_equity=equity, peak_equity=equity, open_positions=0,
                        trades_today=0)
    d = rm.evaluate(TradeProposal(rec.direction, entry, sl, None, "orb"),
                    acct, MarketState(bid=bid, ask=ask, data_age_s=0.0))
    return d.approved, d.reasons, float(d.details.get("min_volume_risk") or np.nan)


def main() -> None:
    cfg = load_config()
    sc = cfg.strategy["orb"]
    rd = load_research_data(cfg)
    m1, feats, cov = rd.m1, rd.feats, rd.coverage
    funnel_rows, tech_rows, cap_rows, trade_rows, all_recs = [], [], [], [], []
    for (sess, scfg), orm, sla in itertools.product(sc["sessions"].items(),
                                                    sc["grid"]["or_minutes"],
                                                    sc["grid"]["sl_atr"]):
        p = ORBParams(session=sess, tz=scfg["tz"], open_hhmm=scfg["open"], or_minutes=orm,
                      sl_atr=sla, tp_r=1.5, entry_window_min=sc["entry_window_min"],
                      max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                      max_cost_frac=sc["max_cost_frac"])
        recs = orb_scan(m1, feats, p, cfg.costs, cfg.risk.max_spread_usd)
        df = records_frame(recs)
        df["or_minutes"], df["sl_atr"] = orm, sla
        all_recs.append(df)
        counts = df["status"].value_counts()
        key = f"{sess} or{orm} sl{sla}"
        funnel_rows.append({"config": key, **{s: int(counts.get(s, 0)) for s in STATUSES}})
        tech = df[df["status"].isin(TECHNICAL_SIGNAL)]
        if len(tech):
            tech_rows.append({
                "config": key, "breakouts": len(tech),
                "tradable": int((tech["status"] == "SIGNAL").sum()),
                "cost_frac_p25": tech["cost_frac"].quantile(0.25),
                "cost_frac_med": tech["cost_frac"].median(),
                "cost_frac_p75": tech["cost_frac"].quantile(0.75),
                "spread_med": tech["spread"].median(), "atr_med": tech["atr"].median(),
                "sl_usd_med": tech["sl_dist"].median(),
            })
        sig_recs = [r for r in recs if r.status == "SIGNAL"]
        if sig_recs:
            tr = run_backtest(m1, records_to_signals(recs, p), cfg.costs, cfg.symbol)
            trade_rows.append({"config": key, "signals": len(sig_recs),
                               "simulated": len(tr), "valid": int(tr["valid"].sum()),
                               "invalid_data_gap": int((~tr["valid"]).sum())})
            for eq in EQUITY_LEVELS_USD:
                res = [capital_check(r, m1, cfg, eq) for r in sig_recs]
                reasons = pd.Series([x for _, rs, _ in res for x in rs]).value_counts()
                cap_rows.append({"config": key, "equity_usd": eq, "signals": len(res),
                                 "approved": sum(a for a, _, _ in res),
                                 "MIN_VOLUME_EXCEEDS_RISK": int(reasons.get("MIN_VOLUME_EXCEEDS_RISK", 0)),
                                 "INSUFFICIENT_MARGIN": int(reasons.get("INSUFFICIENT_MARGIN", 0)),
                                 "other": int(reasons.drop(["MIN_VOLUME_EXCEEDS_RISK", "INSUFFICIENT_MARGIN"], errors="ignore").sum())})

    recs_df = pd.concat(all_recs, ignore_index=True)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    recs_df.to_csv(out / "03_orb_day_records.csv", index=False)
    funnel = pd.DataFrame(funnel_rows).set_index("config")
    data_issue = funnel[["NO_DATA", "OR_INCOMPLETE", "NO_ATR"]].sum(axis=1)
    evaluable = funnel.sum(axis=1) - data_issue
    summary = pd.DataFrame({
        "días-sesión": funnel.sum(axis=1), "sin datos/ATR": data_issue,
        "evaluables": evaluable, "sin señal técnica": funnel["NO_BREAKOUT"],
        "señal técnica": funnel[["DATA_GAP_AT_SIGNAL", "REJECT_SPREAD", "REJECT_COST",
                                 "SIGNAL"]].sum(axis=1),
        "rechazo spread": funnel["REJECT_SPREAD"], "rechazo coste/SL": funnel["REJECT_COST"],
        "operables": funnel["SIGNAL"],
    })
    seg_note = cov.segments.to_string()
    md = [
        "# Estudio 3 — Diagnóstico ORB: ¿por qué (no) opera?",
        "",
        (f"> Cobertura del tramo de investigación: **{cov.coverage_pct:.1f} %** "
        f"({cov.usable_days}/{cov.expected_days} días utilizables). Con esta cobertura el "
        "estudio es **descriptivo** de los segmentos disponibles; no estima rentabilidad."),
        "",
        "Segmentos de datos usados:",
        "```", seg_note, "```",
        ("Reglas sin cambios (filtro coste/SL = "
        f"{sc['max_cost_frac']:.0%}, spread máx. = {cfg.risk.max_spread_usd} $ incl. "
        f"{cfg.costs.extra_spread_usd} $ extra de bróker)."),
        "",
        "## Embudo por configuración",
        md_table(summary.astype(int), "{:.0f}"),
        "",
        "## Breakouts técnicos: ¿cuánto pesa el coste frente al stop?",
        ("`cost_frac` = (spread + 2×slippage) / distancia del SL. El filtro exige ≤ "
        f"{sc['max_cost_frac']:.2f}."),
        md_table(pd.DataFrame(tech_rows).set_index("config")) if tech_rows else "_sin breakouts_",
        "",
        "## Simulación de las señales operables (solo recuento)",
        md_table(pd.DataFrame(trade_rows).set_index("config"), "{:.0f}") if trade_rows
        else "_ninguna señal operable → nada que simular_",
        "",
        ("## ¿Sería posible con este capital? (Risk Manager, cuenta en USD, apalancamiento "
        f"{cfg.account.get('leverage', 20)}:1, contrato {cfg.symbol.contract_size:g} oz, "
        f"mínimo {cfg.symbol.volume_min} lotes — valores de configuración, NO del bróker)"),
        md_table(pd.DataFrame(cap_rows).set_index("config"), "{:.0f}") if cap_rows
        else "_sin señales operables_",
        "",
    ]
    (out / "03_orb_diagnostics.md").write_text("\n".join(md))
    print("\n".join(md[:30]))


if __name__ == "__main__":
    main()
