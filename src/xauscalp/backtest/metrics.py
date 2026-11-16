"""Performance metrics with uncertainty. Win rate is reported but never used for selection."""

from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(cum: np.ndarray) -> float:
    if len(cum) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    return float((peak[1:] - cum).max())


def longest_underwater(cum: np.ndarray) -> int:
    """Longest run of consecutive trades below the previous equity peak."""
    peak, best, run = 0.0, 0, 0
    for x in cum:
        if x < peak - 1e-12:
            run += 1
            best = max(best, run)
        else:
            peak, run = x, 0
    return best


def bootstrap_mean_ci(x: np.ndarray, n_boot: int, rng: np.random.Generator,
                      alpha: float = 0.05) -> tuple[float, float, float]:
    """IID bootstrap CI for the mean and one-sided P(mean <= 0)."""
    if len(x) < 2:
        return (np.nan, np.nan, np.nan)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi), float((means <= 0).mean())


def block_bootstrap_mean_ci(x: pd.Series, n_boot: int, rng: np.random.Generator,
                            alpha: float = 0.05) -> tuple[float, float]:
    """Bootstrap resampling whole ISO weeks (keeps intra-week dependence)."""
    if len(x) < 2:
        return (np.nan, np.nan)
    wk = x.index.to_period("W")
    groups = [g.to_numpy() for _, g in x.groupby(wk)]
    if len(groups) < 5:
        return (np.nan, np.nan)
    sums = np.array([g.sum() for g in groups])
    cnts = np.array([len(g) for g in groups])
    pick = rng.integers(0, len(groups), size=(n_boot, len(groups)))
    means = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def summarize(trades: pd.DataFrame, n_boot: int = 5000, seed: int = 0,
              period_days: float | None = None) -> dict:
    if trades.empty:
        return {"n_trades": 0}
    n_invalid = int((~trades["valid"]).sum()) if "valid" in trades else 0
    if "valid" in trades:
        trades = trades[trades["valid"]]
    if trades.empty:
        return {"n_trades": 0, "n_invalid_excluded": n_invalid}
    rng = np.random.default_rng(seed)
    r = trades["r"].to_numpy()
    usd = trades["pnl_usd_001"].to_numpy()
    wins, losses = r[r > 0], r[r <= 0]
    cum = np.cumsum(r)
    gross_win, gross_loss = wins.sum(), -losses.sum()
    lo, hi, p_le0 = bootstrap_mean_ci(r, n_boot, rng)
    rs = pd.Series(r, index=pd.DatetimeIndex(trades["entry_time"]))
    blo, bhi = block_bootstrap_mean_ci(rs, n_boot, rng)
    daily = rs.groupby(rs.index.normalize()).sum()
    sharpe = daily.mean() / daily.std(ddof=1) * np.sqrt(252) if len(daily) > 20 else np.nan
    downside = daily[daily < 0]
    sortino = (daily.mean() / np.sqrt((downside**2).mean()) * np.sqrt(252)
               if len(downside) > 5 else np.nan)
    out = {
        "n_trades": len(r),
        "win_rate": float((r > 0).mean()),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "expectancy_r": float(r.mean()),
        "expectancy_r_ci95_iid": (lo, hi),
        "expectancy_r_ci95_weekblock": (blo, bhi),
        "p_expectancy_le_0": p_le0,
        "expectancy_usd_per_001lot": float(usd.mean()),
        "avg_win_r": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_r": float(losses.mean()) if len(losses) else np.nan,
        "payoff_ratio": float(wins.mean() / -losses.mean())
        if len(wins) and len(losses) and losses.mean() < 0 else np.nan,
        "total_r": float(cum[-1]),
        "total_usd_per_001lot": float(usd.sum()),
        "max_drawdown_r": max_drawdown(cum),
        "longest_underwater_trades": longest_underwater(cum),
        "sharpe_daily_annualised": float(sharpe),
        "sortino_daily_annualised": float(sortino),
        "avg_cost_r": float(trades["cost_r"].mean()),
        "avg_cost_usd_per_001lot": float(trades["cost_usd_001"].mean()),
        "avg_hold_min": float(trades["hold_min"].mean()),
        "exit_reasons": trades["reason"].value_counts().to_dict(),
        "ambiguous_bar_frac": float(trades["ambiguous_bar"].mean()),
    }
    if period_days:
        out["exposure_frac"] = float(trades["hold_min"].sum() / (period_days * 24 * 60))
        out["trades_per_week"] = float(len(r) / (period_days / 7))
    return out


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    if trades.empty or by not in trades:
        return pd.DataFrame()
    g = trades.groupby(by)["r"]
    return pd.DataFrame({
        "n": g.size(), "expectancy_r": g.mean(), "win_rate": g.apply(lambda s: (s > 0).mean()),
        "total_r": g.sum(), "sem_r": g.std(ddof=1) / np.sqrt(g.size()),
    })


def monte_carlo_drawdown(r: np.ndarray, n_sims: int, rng: np.random.Generator,
                         thresholds_r: tuple[float, ...] = (8, 16, 20)) -> dict:
    """Resample the trade sequence (iid) and measure max drawdown in R.

    With 0.5% risk per trade, an 8% account drawdown is ~16R (ignoring compounding).
    """
    if len(r) < 10:
        return {}
    sims = rng.choice(r, size=(n_sims, len(r)), replace=True).cumsum(axis=1)
    dds = np.array([max_drawdown(s) for s in sims])
    res = {"dd_r_median": float(np.median(dds)), "dd_r_p95": float(np.quantile(dds, 0.95))}
    for th in thresholds_r:
        res[f"p_dd_ge_{th:g}R"] = float((dds >= th).mean())
    return res
