"""Shared research pipeline: load -> integrity -> coverage -> features.

Holdout protection (audit finding H1): the requested end date is clipped to the day
before `validation.holdout_start` BEFORE any file is read, and load_m1 enforces it again
via `max_date`. Cached holdout files may exist on disk; research code never decodes them.
This is a guard against accidents, not a cryptographic guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from xauscalp.backtest.splits import research_slice
from xauscalp.config import ROOT, Config
from xauscalp.data.coverage import CoverageReport, coverage_report
from xauscalp.data.dukascopy import load_m1
from xauscalp.data.quality import check_m1
from xauscalp.features.core import build_features
from xauscalp.features.sessions import session_labels
from xauscalp.regime import trend_regime, vol_regime


@dataclass
class ResearchData:
    m1: pd.DataFrame
    feats: pd.DataFrame
    quality: dict
    coverage: CoverageReport
    requested_start: date
    requested_end: date


def research_max_date(cfg: Config) -> date:
    return date.fromisoformat(str(cfg.validation["holdout_start"])) - timedelta(days=1)


def load_research_data(cfg: Config, symbol: str | None = None) -> ResearchData:
    """Loads ONLY data before the holdout. The holdout never enters research code."""
    d = cfg.data
    cache = ROOT / d.get("dir", "data")
    max_date = research_max_date(cfg)
    start = _to_date(d["start"])
    end = min(_to_date(d["end"]), max_date)
    m1 = load_m1(symbol or d["symbol"], start, end, Path(cache), max_date=max_date)
    m1 = research_slice(m1, str(cfg.validation["holdout_start"]))  # belt and braces
    q = check_m1(m1)
    cov = coverage_report(m1, start, end)
    feats = build_features(m1)
    feats["session"] = session_labels(m1.index)
    feats["vol_regime"] = vol_regime(feats["atr_m5_pct"])
    feats["trend_regime"] = trend_regime(feats["er_h1"])
    return ResearchData(m1=m1, feats=feats, quality=q, coverage=cov,
                        requested_start=start, requested_end=end)


def load_broker_research_data(cfg: Config, csv_path: Path, policy) -> ResearchData:
    """Same as load_research_data but from the broker's M1 export (MT5BrokerM1Source).

    The readers stop at the research limit, so the export's holdout-period rows are never
    decoded. `policy` must be a verified ServerTimePolicy (see research/04)."""
    from xauscalp.data.sources import MT5BrokerM1Source
    max_date = research_max_date(cfg)
    start = _to_date(cfg.data["start"])
    end = min(_to_date(cfg.data["end"]), max_date)
    md = MT5BrokerM1Source(Path(csv_path), policy).load(start, end, max_date=max_date)
    m1 = research_slice(md.m1, str(cfg.validation["holdout_start"]))
    feats = build_features(m1)
    feats["session"] = session_labels(m1.index)
    feats["vol_regime"] = vol_regime(feats["atr_m5_pct"])
    feats["trend_regime"] = trend_regime(feats["er_h1"])
    return ResearchData(m1=m1, feats=feats, quality=check_m1(m1),
                        coverage=coverage_report(m1, start, end),
                        requested_start=start, requested_end=end)


def _to_date(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    """Tiny markdown table writer (avoids an extra dependency)."""
    if df is None or df.empty:
        return "_(vacío)_"
    cols = [df.index.name or ""] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        cells = [str(idx)] + [
            floatfmt.format(v) if isinstance(v, float) else str(v) for v in row.tolist()
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
