"""Study 6 - Broker tick export: coverage, completeness, real spreads vs. the ORB assumptions.

    uv run python research/06_tick_quality.py <XAUUSD_ticks_*.csv> <XAUUSD_M1_*.csv> --tz base_dst:120:Europe/London

Only data BEFORE the holdout is read (the readers stop at the research limit). Three claims
are kept apart in the report:
  1. ticks were exported;
  2. the history is complete enough for a cost study (agrees with the server's own M1 bars);
  3. a strategy is validated  -> never concluded here.
"""

from __future__ import annotations

import argparse
import itertools
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from xauscalp.backtest.engine import CostModel
from xauscalp.config import ROOT, load_config
from xauscalp.data import tick_quality as tq
from xauscalp.data.dukascopy import load_m1
from xauscalp.data.sources import MT5BrokerM1Source, read_mt5_ticks_raw
from xauscalp.features.core import build_features
from xauscalp.features.sessions import local_anchor_utc
from xauscalp.mt5_report import read_mt5_rates_raw
from xauscalp.parity import parse_tz
from xauscalp.pipeline import md_table, research_max_date
from xauscalp.strategies.orb import ORBParams, orb_scan


def kv(d: dict, name: str = "valor") -> pd.DataFrame:
    return pd.DataFrame({name: pd.Series(d, dtype=object)})


def f3(x) -> str:
    return f"{x:.3f}" if isinstance(x, float | np.floating) else str(x)


def load_ticks_utc(path: Path, policy, cfg) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    max_d = research_max_date(cfg)
    raw, meta = read_mt5_ticks_raw(path, max_date=max_d)
    utc = policy.to_utc(raw.index)
    ok = ~utc.isna()
    t = raw[ok].copy()
    t.index = pd.DatetimeIndex(utc[ok], name="time")
    t = t[t.index < pd.Timestamp(str(cfg.validation["holdout_start"]), tz="UTC")]
    return raw, t, {"undetermined_time": int((~ok).sum()), **meta}


def load_bars_utc(path: Path, policy, cfg) -> pd.DataFrame:
    df, _ = read_mt5_rates_raw(path, max_date=research_max_date(cfg))
    utc = policy.to_utc(df.index)
    ok = ~utc.isna()
    out = df[ok].copy()
    out.index = pd.DatetimeIndex(utc[ok], name="time")
    return out


def orb_breakouts(m1: pd.DataFrame, cfg) -> pd.DataFrame:
    """Every ORB breakout on broker bars, WITHOUT spread/cost filters (they are applied below
    with three different spread definitions on the SAME breakouts)."""
    sc = cfg.strategy["orb"]
    costs = CostModel(0.0, cfg.costs.slippage_usd, 0.0)
    feats = build_features(m1)
    frames = []
    for (sess, s), orm, sla in itertools.product(sc["sessions"].items(), sc["grid"]["or_minutes"],
                                                 sc["grid"]["sl_atr"]):
        p = ORBParams(session=sess, tz=s["tz"], open_hhmm=s["open"], or_minutes=orm, sl_atr=sla,
                      tp_r=1.5, entry_window_min=sc["entry_window_min"],
                      max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                      max_cost_frac=1e9)
        rows = [r for r in orb_scan(m1, feats, p, costs, None) if r.decision_idx >= 0]
        df = pd.DataFrame([r.__dict__ for r in rows])
        if df.empty:
            continue
        df["session"], df["or_minutes"], df["sl_atr"] = sess, orm, sla
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["t"] = pd.to_datetime(out["decision_time"], utc=True)
    return out


def window_profile(ticks: pd.DataFrame, cfg, days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    sc = cfg.strategy["orb"]
    span = int(sc["entry_window_min"]) + 15
    offs = [-10, 0, 5, 10, 15, 30, 45, 60, 75]
    prof, win = [], []
    sp = (ticks["ask"] - ticks["bid"]).to_numpy(float)
    w = tq.durations(ticks)
    ts = ticks.index.as_unit("ns").asi8
    for sess, s in sc["sessions"].items():
        anchors = pd.DatetimeIndex([local_anchor_utc(d, s["tz"], s["open"]) for d in days])
        for o in offs:
            v = tq.first_tick_spread_at(ticks, anchors + pd.Timedelta(minutes=o))
            v = v[np.isfinite(v)]
            prof.append({"session": sess, "min_from_open": o, "n": len(v),
                         "p50": float(np.median(v)) if len(v) else np.nan,
                         "p90": float(np.quantile(v, 0.9)) if len(v) else np.nan,
                         "max": float(v.max()) if len(v) else np.nan})
        m = np.zeros(len(ts), bool)
        for a in anchors:
            lo, hi = np.searchsorted(ts, a.value), np.searchsorted(
                ts, (a + pd.Timedelta(minutes=span)).value)
            m[lo:hi] = True
        q = tq.weighted_quantile(sp[m], w[m], [0.5, 0.9, 0.99])
        win.append({"session": sess, "ticks": int(m.sum()), "tw_p50": q[0], "tw_p90": q[1],
                    "tw_p99": q[2], "max": float(sp[m].max()),
                    "time>0.60": float(w[m & (sp > 0.60)].sum() / w[m].sum())})
    return pd.DataFrame(prof), pd.DataFrame(win).set_index("session")


def main(ticks_path: str, m1_path: str, tz: str) -> None:
    cfg = load_config()
    max_d = research_max_date(cfg)
    policy = parse_tz(tz)
    raw, t, meta = load_ticks_utc(Path(ticks_path), policy, cfg)
    integ = tq.integrity(t)
    t, _ = tq.clean_quotes(t)
    first, last = t.index.min(), t.index.max()
    bars = load_bars_utc(Path(m1_path), policy, cfg)
    cov = tq.daily_coverage(t, first, last)
    wk = cov[~cov["weekday"].isin(["Sat", "Sun"])]
    edge = wk[wk["ticks"] < 0.2 * wk["ticks"].median()]       # partial first/last UTC days
    wk_full = wk.drop(edge.index)
    server_days = pd.DatetimeIndex(raw.index.normalize().unique())
    srv_missing = [d for d in pd.date_range(server_days.min(), server_days.max(), freq="D")
                   if d not in server_days]
    gaps, _ = tq.gap_table(t)
    silences = tq.silences_vs_bars(t, bars)
    silences_all = tq.silences_vs_bars(t, bars, min_s=1800, max_s=6 * 3600)
    st = tq.spread_stats(t)
    minutes = tq.minute_frame(t)
    cmp_ = tq.compare_with_m1(minutes, bars)
    hours = tq.spread_by_hour(t)

    # ---- comparison with Dukascopy on the same minutes
    duka = load_m1(cfg.data["symbol"], (first - timedelta(days=1)).date(), max_d,
                   ROOT / cfg.data.get("dir", "data"), max_date=max_d)
    j = minutes.join(duka[["bid_c", "ask_c"]].rename(columns={"bid_c": "d_bid", "ask_c": "d_ask"}),
                     how="inner")
    j["d_sp"] = j["d_ask"] - j["d_bid"]
    dq = [0.5, 0.9, 0.99]
    spread_cmp = pd.DataFrame({
        "p50": [j["d_sp"].quantile(.5), j["d_sp"].add(cfg.costs.extra_spread_usd).quantile(.5),
                j["sp_last"].quantile(.5), j["sp_tw"].quantile(.5)],
        "p90": [j["d_sp"].quantile(.9), j["d_sp"].add(cfg.costs.extra_spread_usd).quantile(.9),
                j["sp_last"].quantile(.9), j["sp_tw"].quantile(.9)],
        "p99": [j["d_sp"].quantile(.99), j["d_sp"].add(cfg.costs.extra_spread_usd).quantile(.99),
                j["sp_last"].quantile(.99), j["sp_tw"].quantile(.99)],
    }, index=["Dukascopy ask_c-bid_c", f"Dukascopy + {cfg.costs.extra_spread_usd:g} (modelo)",
              "bróker: último tick del minuto", "bróker: media ponderada en el tiempo"])
    del dq
    pdiff = (j["bid_c"] - j["d_bid"])
    price = {"minutos comparados": len(j), "mediana (bróker − Dukascopy) $": pdiff.median(),
             "|dif| p95 $": pdiff.abs().quantile(.95), "|dif| p99 $": pdiff.abs().quantile(.99),
             "% minutos con |dif| ≤ 0,30 $": float((pdiff.abs() <= 0.30).mean() * 100),
             "correlación de retornos 1 min": float(
                 np.corrcoef(minutes.bid_c.diff().reindex(j.index).fillna(0),
                             j["d_bid"].diff().fillna(0))[0, 1])}

    # ---- ORB windows and filters
    days = pd.bdate_range(first.date(), last.date())
    span = pd.Timedelta(minutes=15 + int(cfg.strategy["orb"]["entry_window_min"]))
    windows = [(a, a + span) for s_ in cfg.strategy["orb"]["sessions"].values()
               for a in (local_anchor_utc(d, s_["tz"], s_["open"]) for d in days)]

    def hits_orb(start, end) -> bool:
        return any(start < w1 and end > w0 for w0, w1 in windows)

    holes_idx = minutes.index.difference(bars[(bars.index >= minutes.index.min())
                                              & (bars.index <= minutes.index.max())].index)
    holes = tq.contiguous_blocks(holes_idx)
    holes["toca ventana ORB"] = [hits_orb(a, b + pd.Timedelta(minutes=1))
                                 for a, b in zip(holes["start_utc"], holes["end_utc"], strict=True)]
    silences["toca ventana ORB"] = [hits_orb(a, b) for a, b in
                                    zip(silences["start_utc"], silences["end_utc"], strict=True)]
    # calendar expectation on the UTC grid: one daily break inside every Mon-Thu UTC day that
    # starts inside the window (a partial first day starts after its break), one weekly close
    # after every Friday that is not the last day of the window.
    lastday = cov.index[-1]
    nights = int(sum(1 for d in cov.index if cov.loc[d, "weekday"] in ("Mon", "Tue", "Wed", "Thu")
                     and cov.loc[d, "ticks"] > 0 and d not in set(edge.index)))
    weekends = int(sum(1 for d in cov.index if cov.loc[d, "weekday"] == "Fri"
                       and cov.loc[d, "ticks"] > 0 and d != lastday))
    brk = pd.DataFrame(silences_all)
    prof, win = window_profile(t, cfg, days)
    md1 = MT5BrokerM1Source(Path(m1_path), policy).load(date(2025, 9, 1), max_d, max_date=max_d)
    br = orb_breakouts(md1.m1, cfg)
    br = br[(br["t"] >= first) & (br["t"] <= last - pd.Timedelta(minutes=2))].copy()
    ref = pd.DatetimeIndex(br["t"])
    br["sp_tick"] = tq.first_tick_spread_at(t, ref + pd.Timedelta(minutes=1))
    br["sp_bar"] = br["spread"]
    dsp = (duka["ask_c"] - duka["bid_c"]).reindex(ref).to_numpy() + cfg.costs.extra_spread_usd
    br["sp_duka"] = dsp
    br = br.dropna(subset=["sp_tick", "sp_duka"])
    slip2 = 2 * cfg.costs.slippage_usd
    mx, mf = cfg.risk.max_spread_usd, cfg.strategy["orb"]["max_cost_frac"]
    models = {"Dukascopy + extra (supuesto actual)": "sp_duka",
              "bróker: spread de la vela (lo que ve Python)": "sp_bar",
              "bróker: primer tick de la vela siguiente (lo que ve el EA)": "sp_tick"}
    rows = []
    for sl, g in br.groupby("sl_atr"):
        row = {"SL×ATR": sl, "rupturas": len(g)}
        for name, col in models.items():
            ok = (g[col] <= mx) & ((g[col] + slip2) / g["sl_dist"] <= mf)
            row[name] = f"{int(ok.sum())} ({100 * ok.mean():.0f} %)"
        rows.append(row)
    funnel = pd.DataFrame(rows).set_index("SL×ATR")
    rej = {}
    for name, col in models.items():
        rs = int((br[col] > mx).sum())
        rc = int(((br[col] <= mx) & ((br[col] + slip2) / br["sl_dist"] > mf)).sum())
        rej[name] = {"rechaza spread": rs, "rechaza coste/SL": rc, "pasan": len(br) - rs - rc}
    rej_df = pd.DataFrame(rej).T
    agree = float(((br["sp_bar"] - br["sp_tick"]).abs() <= 0.005).mean())
    diff_q = (br["sp_tick"] - br["sp_bar"]).quantile([.05, .5, .95]).round(3).to_dict()

    # ---- verdict, criteria stated explicitly
    c = {
        "1. Ticks válidos (sin cruzados/no finitos) y en orden": integ["dropped"] == 0
        and integ["monotonic"],
        "2. Todos los días laborables tienen ticks": bool((wk["ticks"] > 0).all()),
        f"3. Pausas coherentes con el calendario ({nights} diarias, {weekends} semanales)":
            int(gaps.loc["30 min - 6 h (daily break)", "count"]) == nights
            and int(gaps.loc["> 6 h (weekly close)", "count"]) == weekends
            and bool(brk["seconds"].between(55 * 60, 65 * 60).all()),
        "4. Todo silencio > 5 min está también vacío en las velas del servidor "
        "(corte del servidor, no pérdida de la exportación)":
            bool((silences["server_bars_inside"] == 0).all()),
        "5. Toda vela M1 del servidor tiene ticks": cmp_["bars_without_ticks"] == 0,
        "6. OHLC (bid) de los ticks = OHLC de las velas del servidor (≥ 99 %)":
            all(cmp_.get(f"ohlc_{k}_equal", 0) >= 0.99 for k in ("open", "high", "low", "close")),
        "7. Ticks que cambian el bid = tick_volume del servidor (≥ 99,9 % de las velas)":
            cmp_.get("bidtick_equals_tickvolume_share", 0) >= 0.999,
    }
    complete = all(c.values())
    n_br = len(br[(br["or_minutes"] == 15) & (br["sl_atr"] == 1.5)])

    md = [
        "# Estudio 6 — Ticks del bróker: cobertura, completitud y spreads reales",
        "",
        (f"Fuente: `{Path(ticks_path).name}` (servidor {meta.get('server', '?')}, build "
         f"{meta.get('terminal_build', '?')}), regla horaria `{tz}` (verificada en el estudio 4). "
         f"Ventana leída: **{first:%Y-%m-%d %H:%M} → {last:%Y-%m-%d %H:%M} UTC**, "
         f"toda **anterior al periodo reservado** ({cfg.validation['holdout_start']}): los lectores "
         "se detienen en el límite y no leen más filas."),
        "",
        "## Tres cosas distintas",
        md_table(pd.DataFrame({"¿Cumplido?": [
            "**Sí**: " + f"{integ['n']:,} ticks exportados",
            ("**Sí, para este mes**" if complete else "**No / con reservas** (ver criterios)"),
            "**No**: nada de este informe valida una estrategia"]},
            index=["Ticks exportados", "Histórico suficientemente completo (coste/spread)",
                   "Estrategia validada y rentable"])),
        "",
        "## 1. Integridad",
        md_table(kv({k: v for k, v in integ.items() if k != "flags"})),
        "",
        ("Flags observados (`MqlTick.flags`): " + ", ".join(f"{k}: {v:,}" for k, v in
                                                          integ.get("flags", {}).items()) +
         ". La documentación oficial solo describe los bits BID/ASK/LAST/VOLUME/BUY/SELL; los "
         "bits 128 y 1024 aparecen en casi todos los ticks y **su significado no está "
         "verificado** (no afectan a la validez de bid/ask: todas las filas tienen ambos)."),
        "",
        "## 2. Cobertura por día",
        f"**Por día del servidor** (así lo cuenta el script de exportación): "
        f"{len(srv_missing)} días sin ticks: "
        + ", ".join(f"{d:%d-%b} ({d.day_name()[:3]})" for d in srv_missing) + ". ",
        f"**Por día UTC**: {len(cov)} días; laborables {len(wk)}, todos con ticks "
        f"({'sí' if bool((wk['ticks'] > 0).all()) else 'NO'}); sábados con ticks: "
        f"{int((cov[cov['weekday'] == 'Sat']['ticks'] > 0).sum())}; domingos con ticks: "
        f"{int((cov[cov['weekday'] == 'Sun']['ticks'] > 0).sum())} (es la apertura semanal del "
        "domingo por la tarde UTC). Días parciales en los bordes de la ventana: "
        + (", ".join(f"{d} ({int(n):,} ticks)" for d, n in edge["ticks"].items()) or "ninguno")
        + ". ",
        (f"Ticks por día laborable completo: mín {int(wk_full['ticks'].min()):,} · mediana "
        f"{int(wk_full['ticks'].median()):,} · máx {int(wk_full['ticks'].max()):,}."),
        "",
        "",
        "## 3. Silencios entre ticks",
        md_table(gaps.astype(object)),
        "",
        "Silencios > 5 min en horario de mercado y si las velas del servidor también faltan:",
        md_table(silences.assign(start_utc=silences["start_utc"].astype(str),
                                 end_utc=silences["end_utc"].astype(str)).astype(object),
                 "{:.0f}") if len(silences) else "_ninguno_",
        "",
        "## 4. ¿Reproducen los ticks las velas M1 del propio servidor?",
        ("Es la prueba de completitud que importa: si el servidor construyó sus velas con más "
         "ticks de los exportados, el histórico exportado está incompleto. `tick_volume` cuenta "
         "los ticks que cambian el **bid** (las velas son de bid): los ticks que solo cambian "
         "el ask (flag sin bit BID) explican la diferencia entre el total exportado y "
         "`tick_volume`, por eso la comparación válida es `bidtick_*`."),
        md_table(kv({k: (v if not isinstance(v, dict) else
                         {kk: round(vv, 4) for kk, vv in v.items()})
                     for k, v in cmp_.items()})),
        "",
        "### Velas que faltan en la exportación M1 (hay ticks, no hay vela)",
        md_table(holes.assign(start_utc=holes["start_utc"].astype(str),
                              end_utc=holes["end_utc"].astype(str)).astype(object))
        if len(holes) else "_ninguna_",
        "",
        ("Es un agujero de la **exportación M1**, no de los ticks. Si toca una ventana ORB, "
        "Python/EA trabajarían con velas incompletas ese día (usar la fuente de ticks)."),
        "",
        "## 5. Criterios de completitud (decisión explícita)",
        ("> Los criterios 3 y 4 se **refinaron tras ver la primera ejecución**: la versión "
         "inicial no distinguía la pausa diaria programada ni los cortes del servidor de una "
         "pérdida de la exportación. Son criterios de integridad de datos, no de estrategia."),
        md_table(pd.DataFrame({"cumple": ["sí" if v else "NO" for v in c.values()]},
                              index=list(c))),
        "",
        (f"**Veredicto: {'COMPLETO para este mes' if complete else 'INCOMPLETO o con reservas'}**"
        f" — con {len(silences)} cortes de cotización del servidor "
        f"({int(silences['seconds'].sum() / 60)} min en total) y {int(holes['minutes'].sum()) if len(holes) else 0}"
        " minutos sin vela en la exportación M1."),
        "",
        "## 6. Spread real (ask − bid) de los ticks",
        (f"Ponderado por tiempo (cada cotización pesa lo que duró, máx. {tq.CAP_S:g} s) frente a "
         "ponderado por tick (los momentos de mucha actividad pesan más)."),
        md_table(pd.DataFrame({
            "ponderado por tiempo": {f"p{int(q * 100)}": v for q, v in st["time_q"].items()},
            "ponderado por tick": {f"p{int(q * 100)}": v for q, v in st["tick_q"].items()}}),
            "{:.3f}"),
        "",
        f"Media por tiempo {st['time_mean']:.3f} $ · máximo {st['max']:.2f} $ · tiempo con spread > "
        + " · ".join(f"{k:g} $: {v * 100:.2f} %" for k, v in st["share_time_above"].items()) + ".",
        "",
        "Por hora UTC:",
        md_table(hours.astype(object).assign(**{c_: hours[c_].round(3) for c_ in hours.columns
                                                if c_ != "ticks"}), "{:.3f}"),
        "",
        "## 7. Spread en las ventanas de la ORB",
        (f"Ventana = apertura → +{15 + int(cfg.strategy['orb']['entry_window_min'])} min "
        "(rango de apertura de 15 min + 60 min de entrada)."),
        md_table(win, "{:.3f}"),
        "",
        "Primer tick de cada minuto relativo a la apertura (mediana/p90 entre días):",
        md_table(prof.set_index(["session", "min_from_open"]).astype(object), "{:.3f}"),
        "",
        "## 8. Bróker vs. Dukascopy (mismos minutos)",
        md_table(spread_cmp, "{:.3f}"),
        "",
        md_table(kv({k: (round(v, 4) if isinstance(v, float) else v) for k, v in price.items()})),
        "",
        "## 9. Efecto sobre los filtros de la ORB (mismas rupturas, solo cambia el spread)",
        (f"Rupturas ORB en las velas del bróker dentro de la ventana de ticks (todas las "
         f"combinaciones del grid, **sin filtros**, solo las que tienen además dato de Dukascopy en ese minuto: su octubre está incompleto); filtros sin cambios: spread ≤ {mx:g} $ y "
         f"(spread + 2×{cfg.costs.slippage_usd:g}) / SL ≤ {mf:.2f}. Con OR 15 / SL 1,5×ATR hay "
         f"**{n_br}** rupturas: lejos de las ≥ 200 operaciones que exige la fase 3."),
        md_table(funnel),
        "",
        md_table(rej_df.astype(object)),
        "",
        (f"El spread de la vela (Python) coincide con el del primer tick de la vela siguiente "
         f"(EA) en el **{agree * 100:.0f} %** de las rupturas; diferencia (tick − vela) "
         f"p5/p50/p95 = {diff_q}."),
        "",
        "## Qué NO se puede concluir",
        ("- **Un solo mes** (octubre de 2025) y un solo régimen (oro con subida fuerte): sirve "
        "para calibrar costes, no para validar nada."),
        ("- Es el feed de **MetaQuotes-Demo**, que no ejecuta órdenes reales: que su spread sea "
        "bajo y casi constante **no** implica que un bróker real lo ofrezca. Antes de cambiar "
        "`extra_spread_usd` o `max_spread_usd` hace falta el mismo análisis con la demo del "
        "bróker elegido y una comisión conocida."),
        "- Ninguna cifra de este informe es evidencia de rentabilidad.",
        "",
    ]
    out = ROOT / "reports" / "06_tick_quality.md"
    out.write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ticks")
    ap.add_argument("m1")
    ap.add_argument("--tz", required=True, help="verified rule, e.g. base_dst:120:Europe/London")
    a = ap.parse_args()
    main(a.ticks, a.m1, a.tz)
