"""Study 5 - Real account conditions (MT5 feasibility report) vs. ORB assumptions.

    uv run python research/05_broker_conditions.py [data/mt5/xau_feasibility.csv]

1. Validated broker profile and assumption-by-assumption comparison (xauscalp.mt5_report).
2. Capital: with the REAL symbol spec, account currency and leverage, which share of the
   ORB breakouts seen in the most recent pre-holdout segment could be sized at all
   (RiskManager, unchanged limits)? Also at the ESMA retail leverage (20:1) a real EU
   account would have.
3. What-if (NOT adopted): how the ORB cost filters would behave with this feed's spreads.

Integrity notes:
- Stop distances come from research data (< holdout_start). The broker's spread statistics
  come from its recent bars (holdout-era dates): they are treated as current market-structure
  planning data, never used to choose strategy parameters, and never make the cost model
  cheaper (MetaQuotes-Demo does not execute real orders).
- Bar spreads (MqlRates.spread) are typically the bar MINIMUM: optimistic.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

from xauscalp.config import ROOT, load_config
from xauscalp.mt5_report import (
    DEFAULT_FEASIBILITY_CSV,
    compare_with_config,
    findings_frame,
    load_broker_profile,
)
from xauscalp.pipeline import load_research_data, md_table
from xauscalp.risk.manager import AccountState, MarketState, RiskManager, TradeProposal
from xauscalp.strategies.orb import TECHNICAL_SIGNAL, ORBParams, orb_scan, records_frame

EQUITY_EUR = (20, 500, 1_000, 2_000, 5_000)
RECENT_FROM = pd.Timestamp("2025-01-01", tz="UTC")   # gold ~3,300-4,300 USD, like today


def capital_table(tech: pd.DataFrame, m1: pd.DataFrame, cfg, prof, spread: float,
                  leverage: float) -> pd.DataFrame:
    rows = []
    for eq in EQUITY_EUR:
        rm = RiskManager(cfg.risk, prof.spec, profit_to_account_rate=prof.profit_to_account_rate,
                         leverage=leverage)
        acct = AccountState(equity=eq, free_margin=eq, day_start_equity=eq,
                            week_start_equity=eq, peak_equity=eq, open_positions=0,
                            trades_today=0)
        approved, reasons = 0, []
        for r in tech.itertuples():
            mid = (m1["bid_c"].iat[r.decision_idx] + m1["ask_c"].iat[r.decision_idx]) / 2
            bid, ask = mid - spread / 2, mid + spread / 2
            entry = ask if r.direction == 1 else bid
            d = rm.evaluate(TradeProposal(int(r.direction), entry,
                                          entry - r.direction * r.sl_dist, None, "orb"),
                            acct, MarketState(bid=bid, ask=ask, data_age_s=0.0))
            approved += d.approved
            reasons += list(d.reasons)
        rc = pd.Series(reasons, dtype=object).value_counts()
        rows.append({"equity_EUR": eq, "breakouts": len(tech), "sizeable": approved,
                     "pct": 100 * approved / max(len(tech), 1),
                     "MIN_VOLUME_EXCEEDS_RISK": int(rc.get("MIN_VOLUME_EXCEEDS_RISK", 0)),
                     "INSUFFICIENT_MARGIN": int(rc.get("INSUFFICIENT_MARGIN", 0)),
                     "other": int(rc.drop(["MIN_VOLUME_EXCEEDS_RISK", "INSUFFICIENT_MARGIN"],
                                          errors="ignore").sum())})
    return pd.DataFrame(rows).set_index("equity_EUR")


def main(path: str | Path = DEFAULT_FEASIBILITY_CSV) -> None:
    cfg = load_config()
    prof = load_broker_profile(path)
    cur = prof.raw["account_currency"]
    fnd = findings_frame(compare_with_config(prof, cfg))

    rd = load_research_data(cfg)
    m1, feats = rd.m1, rd.feats
    sc = cfg.strategy["orb"]
    frames = []
    for (sess, s), orm, sla in itertools.product(sc["sessions"].items(),
                                                 sc["grid"]["or_minutes"],
                                                 sc["grid"]["sl_atr"]):
        p = ORBParams(session=sess, tz=s["tz"], open_hhmm=s["open"], or_minutes=orm,
                      sl_atr=sla, tp_r=1.5, entry_window_min=sc["entry_window_min"],
                      max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                      max_cost_frac=sc["max_cost_frac"])
        df = records_frame(orb_scan(m1, feats, p, cfg.costs, cfg.risk.max_spread_usd))
        df["or_minutes"], df["sl_atr"] = orm, sla
        frames.append(df)
    rec = pd.concat(frames, ignore_index=True)
    rec = rec[rec["status"].isin(TECHNICAL_SIGNAL)].copy()
    rec["t"] = pd.to_datetime(rec["decision_time"], utc=True)
    recent = rec[rec["t"] >= RECENT_FROM]
    if recent.empty:
        sys.exit("no breakouts in the recent research segment: download more data first")
    period = f"{recent['t'].min():%Y-%m-%d} → {recent['t'].max():%Y-%m-%d}"
    price = float(m1.loc[m1.index >= RECENT_FROM, "bid_c"].median())

    sl = (recent.groupby("sl_atr")["sl_dist"]
          .describe(percentiles=[0.25, 0.5, 0.75, 0.9])[["count", "25%", "50%", "75%", "90%"]])
    loss_per_usd = prof.num("profit_per_1usd_move_0.010_lots")
    sl["count"] = sl["count"].astype(int)
    sl = sl.astype(object)
    sl["loss_0.01lot_p50_" + cur] = sl["50%"] * loss_per_usd
    sl["equity_for_0.5pct_p50_" + cur] = (sl["50%"] + cfg.risk.expected_slippage_usd) \
        * loss_per_usd / (cfg.risk.risk_per_trade_pct / 100)

    p90 = prof.num("spread_m1_p90_price")
    cap = {}
    for lev, label in ((prof.leverage, f"cuenta demo 1:{prof.leverage:g}"),
                       (float(cfg.account.get("leverage", 20)), "cuenta real UE (ESMA) 1:20")):
        cap[label] = {k: capital_table(recent[recent["sl_atr"] == k], m1, cfg, prof, p90, lev)
                      for k in sorted(recent["sl_atr"].unique())}

    # what-if: cost filters with this feed's spreads (NOT adopted)
    slip2 = 2 * cfg.costs.slippage_usd
    wi = []
    for label, spr in (("Dukascopy + extra (modelo actual)", None),
                       ("bróker p50", prof.num("spread_m1_p50_price")),
                       ("bróker p90", p90), ("bróker p99", prof.num("spread_m1_p99_price"))):
        s_ = recent["spread"] if spr is None else pd.Series(spr, index=recent.index)
        cf = (s_ + slip2) / recent["sl_dist"]
        ok = (s_ <= cfg.risk.max_spread_usd) & (cf <= sc["max_cost_frac"])
        wi.append({"spread usado": label, "spread_med": float(s_.median()),
                   "cost_frac_med": float(cf.median()),
                   "pasan spread": int((s_ <= cfg.risk.max_spread_usd).sum()),
                   "pasan ambos filtros": int(ok.sum()), "breakouts": len(recent)})
    hours = prof.spread_by_server_hour

    off_h = prof.num("server_minus_gmt_seconds") / 3600
    md = [
        "# Estudio 5 — Condiciones reales de la cuenta MT5 frente a los supuestos de la ORB",
        "",
        (f"Fuente: `xau_feasibility.csv` generado {prof.raw['generated_gmt']} GMT en "
         f"**{prof.raw['account_server']}** ({prof.raw['account_company']}). "
         "MetaQuotes-Demo es el servidor de demostración del fabricante de MT5, **no un bróker "
         "que ejecute órdenes reales**: sus spreads y su apalancamiento no prueban nada sobre "
         "el coste real de operar."),
        "",
        "## 1. Supuesto a supuesto",
        md_table(fnd.set_index("area")),
        "",
        ("Estados: MATCH = coincide · CONFIG_MORE_CONSERVATIVE = la configuración es más "
        "prudente (se mantiene) · BROKER_WORSE = el bróker es peor que lo supuesto (requiere "
        "acción) · UNKNOWN = no medible todavía · INFO = dato a tener en cuenta."),
        "",
        ("**Cambios en `config/default.yaml`: ninguno numérico.** Los valores de símbolo "
        "coinciden; apalancamiento y volumen máximo de la configuración son más prudentes; "
        "comisión y deslizamiento siguen sin medir; el modelo de costes no se abarata con "
        "datos de una demo."),
        "",
        "## 2. ¿Con qué capital se podrían dimensionar las rupturas ORB?",
        (f"Rupturas técnicas (antes de filtros de coste) del tramo reciente de investigación "
         f"({period}, oro mediano {price:,.0f} $; hoy {prof.num('bid'):,.0f} $). Distancia del "
         f"SL en $ por onza; 0,01 lotes pierden **{loss_per_usd:g} {cur} por cada 1 $** de "
         "recorrido (OrderCalcProfit del bróker)."),
        md_table(sl, "{:.2f}"),
        "",
        (f"Gestor de riesgo **sin cambios** (riesgo {cfg.risk.risk_per_trade_pct} %, margen "
         f"máx. {cfg.risk.max_margin_usage_pct:g} % del libre, slippage "
         f"{cfg.risk.expected_slippage_usd} $), especificación real del símbolo, tipo "
         f"USD→{cur} = {prof.profit_to_account_rate:.4f} y spread fijado en el p90 del "
         f"bróker ({p90:g} $) para aislar la pregunta de capital."),
        "",
    ]
    for label, tabs in cap.items():
        for k, t in tabs.items():
            md += [f"### {label} — SL = {k:g}×ATR(M5)", md_table(t, "{:.0f}"), ""]
    md += [
        "## 3. *What-if* de filtros de coste con los spreads de este servidor (NO adoptado)",
        (f"Filtros sin cambios: spread ≤ {cfg.risk.max_spread_usd} $ y (spread + "
         f"2×{cfg.costs.slippage_usd}) / SL ≤ {sc['max_cost_frac']:.2f}. Solo ilustra qué "
         "filtro dejaría de ser el cuello de botella **si** un bróker real ofreciera estos "
         "spreads en esas mismas fechas. Fechas distintas y spreads mínimos de barra: no es "
         "evidencia."),
        md_table(pd.DataFrame(wi).set_index("spread usado").astype(object), "{:.2f}"),
        "",
        "## 4. Spread medio por hora del servidor (muestra reciente del bróker)",
        (f"Desfase actual servidor−GMT: {off_h:+g} h (solo para la fecha del informe). "
         "Con ese desfase, la apertura de Londres (08:00 Londres) cae a las 10:00 servidor y "
         "COMEX (08:20 Nueva York) a las 15:20 servidor en horario de invierno."),
        md_table(hours.rename_axis("hora servidor").to_frame(), "{:.2f}"),
        "",
        "## Conclusiones",
        ("- La especificación del símbolo coincide con la configuración: el sizing de "
        "investigación ya usaba contrato 100 oz y mínimo 0,01."),
        (f"- **20 € no alcanzan ni el margen de 0,01 lotes** ({prof.raw['margin_for_0.010_lots']}"
        f" {cur} a 1:{prof.leverage:g}; ×5 a 1:20)."),
        "- La capacidad de dimensionar depende del SL en dólares: ver tablas del apartado 2.",
        "- Ninguna cifra de este estudio es evidencia de rentabilidad.",
        "",
    ]
    out = ROOT / "reports" / "05_broker_conditions.md"
    out.write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FEASIBILITY_CSV)
