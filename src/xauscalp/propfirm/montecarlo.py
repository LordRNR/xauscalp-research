"""Reproducible Monte Carlo of a two-step challenge, with statistical uncertainty.

INPUT: a trade list with net R per trade (costs already inside R), its maximum adverse
excursion in R (for the floating-loss test) and the entry time. R is converted to money with a
fixed-fractional risk of `risk_pct` of the INITIAL capital per trade (1R = risk_pct % of it).

Two levels of resampling:
  outer: bootstrap the calendar WEEKS of the sample (weeks without trades kept: frequency and
         clustering are preserved) -> a plausible "true" distribution; this carries the
         statistical uncertainty about the edge into the answer;
  inner: paths drawn from that outer dataset (week blocks) simulate the phases.
A NULL control (same weeks, mean net R shifted to 0 per outer draw) shows how often a strategy
WITHOUT edge, but with the same variance and clustering, passes: a pass rate that is not clearly
above the null says nothing about skill.

Simplifications (conservative or documented): equity test uses entry balance minus the trade's
MAE (worst intratrade point); one balance, no swaps; lots assumed sizeable (>= 0.01 at the chosen
capital); no news restriction in challenge/verification (per the firm's FAQ).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from xauscalp.propfirm.rules import PropRules


@dataclass(frozen=True)
class McConfig:
    initial: float = 10_000.0
    risk_pct: float = 0.5                 # % of INITIAL capital risked per trade (1R)
    max_weeks_per_phase: int = 52
    funded_weeks: int = 13
    outer: int = 100
    inner: int = 200
    seed: int = 20261115
    fee: float = 89.0                     # EUR, account assumed in EUR
    reward_ratio: float = 0.80


def weeks_from_trades(trades: pd.DataFrame, r: np.ndarray, mae_r: np.ndarray):
    """list over calendar weeks of arrays [[dow, r, mae], ...] (empty weeks included)."""
    t = pd.DatetimeIndex(trades["entry_time"])
    wk = t.tz_convert("UTC").tz_localize(None).to_period("W").to_timestamp()
    df = pd.DataFrame({"wk": wk, "dow": t.day_of_week, "r": r, "mae": mae_r})
    allw = pd.date_range(df["wk"].min(), df["wk"].max(), freq="W-MON")
    groups = {k: g[["dow", "r", "mae"]].to_numpy() for k, g in df.groupby("wk")}
    return [groups.get(w, np.empty((0, 3))) for w in allw]


def _phase(rng, weeks, cfg: McConfig, rules: PropRules, target_pct, min_days, max_weeks) -> tuple[str, int, float]:
    """One phase. Returns (PASSED|FAILED|UNRESOLVED, weeks used, final balance ratio)."""
    f, ini = cfg.risk_pct / 100, cfg.initial
    r_money = f * ini
    bal = ini
    tot_limit = ini * (1 - rules.max_loss_pct / 100)
    n = len(weeks)
    days: set[int] = set()
    day_start = bal
    cur_day = -1
    for w in range(max_weeks):
        wk = weeks[rng.integers(n)]
        for dow, r, mae in wk:
            day = w * 7 + int(dow)
            if day != cur_day:
                cur_day, day_start = day, bal
            days.add(day)
            limit = max(day_start - rules.max_daily_loss_pct / 100 * ini, tot_limit)
            if bal - mae * r_money <= limit:
                return "FAILED", w + 1, bal / ini
            bal += r * r_money
            if bal <= limit:
                return "FAILED", w + 1, bal / ini
            if target_pct is not None and bal >= ini * (1 + target_pct / 100) and len(days) >= min_days:
                return "PASSED", w + 1, bal / ini
    return "UNRESOLVED", max_weeks, bal / ini


def simulate_path(rng, weeks, cfg: McConfig, rules: PropRules) -> dict:
    c = rules.phases["challenge"]
    st1, w1, _ = _phase(rng, weeks, cfg, rules, c.profit_target_pct, c.min_trading_days, cfg.max_weeks_per_phase)
    out = {"c": st1, "v": None, "funded": None, "weeks": w1, "profit_ratio": 0.0}
    if st1 != "PASSED":
        return out
    v = rules.phases["verification"]
    st2, w2, _ = _phase(rng, weeks, cfg, rules, v.profit_target_pct, v.min_trading_days, cfg.max_weeks_per_phase)
    out.update(v=st2, weeks=w1 + w2)
    if st2 != "PASSED":
        return out
    fp = rules.phases["funded"]
    st3, w3, ratio = _phase(rng, weeks, cfg, rules, None, fp.min_trading_days, cfg.funded_weeks)
    out.update(funded="SURVIVED" if st3 == "UNRESOLVED" else "FAILED", weeks=w1 + w2 + w3,
               profit_ratio=max(0.0, ratio - 1.0) if st3 == "UNRESOLVED" else 0.0)
    return out


def run_mc(weeks_all: list[np.ndarray], cfg: McConfig, rules: PropRules, *, null: bool = False) -> dict:
    """Outer bootstrap x inner paths. Returns per-outer-draw probabilities and summaries."""
    rng = np.random.default_rng(cfg.seed + (7919 if null else 0))
    nw = len(weeks_all)
    rows = []
    for _ in range(cfg.outer):
        idx = rng.integers(nw, size=nw)
        weeks = [weeks_all[i] for i in idx]
        if null:                                 # zero net edge, same variance and clustering
            allr = np.concatenate([w[:, 1] for w in weeks if len(w)]) if any(len(w) for w in weeks) else np.array([0.0])
            mu = allr.mean()
            weeks = [np.column_stack([w[:, 0], w[:, 1] - mu, w[:, 2]]) if len(w) else w for w in weeks]
        res = [simulate_path(rng, weeks, cfg, rules) for _ in range(cfg.inner)]
        n = len(res)
        c_pass = sum(r["c"] == "PASSED" for r in res) / n
        both = sum(r["v"] == "PASSED" for r in res) / n
        fail = sum(r["c"] == "FAILED" or r["v"] == "FAILED" for r in res) / n
        unres = sum(r["c"] == "UNRESOLVED" or r["v"] == "UNRESOLVED" for r in res) / n
        surv = [r for r in res if r["funded"] == "SURVIVED"]
        payout = sum(r["profit_ratio"] * cfg.initial * cfg.reward_ratio for r in surv) / n
        refund = sum(1 for r in surv if r["profit_ratio"] > 0) / n * cfg.fee
        wk = [r["weeks"] for r in res if r["v"] == "PASSED"]
        rows.append({"p_challenge": c_pass, "p_both": both, "p_fail": fail, "p_unresolved": unres,
                     "ev_eur": payout + refund - cfg.fee,
                     "median_weeks_to_funded": float(np.median(wk)) if wk else float("nan")})
    df = pd.DataFrame(rows)
    q = lambda c: (float(df[c].quantile(0.05)), float(df[c].median()), float(df[c].quantile(0.95)))
    return {"p_challenge": q("p_challenge"), "p_both": q("p_both"), "p_fail": q("p_fail"),
            "p_unresolved": q("p_unresolved"), "ev_eur": q("ev_eur"),
            "median_weeks_to_funded": float(df["median_weeks_to_funded"].median()),
            "draws": df}
