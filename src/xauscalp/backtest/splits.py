"""Time splits, walk-forward folds and the HOLDOUT LOCKBOX.

The holdout (data on/after validation.holdout_start) must not be used for research,
parameter selection or strategy choice. Opening it is a deliberate, one-shot, logged act
that requires the user's explicit environment flag.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

UNLOCK_ENV = "XAU_UNLOCK_HOLDOUT"
UNLOCK_VALUE = "I_ACCEPT_ONE_SHOT_EVALUATION"


class HoldoutLocked(RuntimeError):
    pass


def research_slice(df: pd.DataFrame, holdout_start: str) -> pd.DataFrame:
    """Everything strictly before the holdout. Use this for ALL research."""
    cut = pd.Timestamp(holdout_start, tz="UTC")
    return df[df.index < cut]


def holdout_slice(df: pd.DataFrame, holdout_start: str, strategy_id: str,
                  log_path: Path) -> pd.DataFrame:
    """Return holdout data only with explicit user authorisation; log every opening."""
    if os.environ.get(UNLOCK_ENV) != UNLOCK_VALUE:
        raise HoldoutLocked(
            f"Holdout is locked. The USER must set {UNLOCK_ENV}={UNLOCK_VALUE} "
            "for a single, final evaluation of a frozen strategy."
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prior = log_path.read_text() if log_path.exists() else ""
    if f"| {strategy_id} |" in prior:
        raise HoldoutLocked(f"holdout already used for {strategy_id}: results are final")
    with log_path.open("a") as fh:
        if not prior:
            fh.write("| opened_utc | strategy_id |\n|---|---|\n")
        fh.write(f"| {datetime.now(UTC).isoformat()} | {strategy_id} |\n")
    cut = pd.Timestamp(holdout_start, tz="UTC")
    return df[df.index >= cut]


def walk_forward_folds(start: pd.Timestamp, end: pd.Timestamp, train_months: int,
                       test_months: int) -> list[tuple[pd.Timestamp, ...]]:
    """Rolling folds: [train_start, train_end) then [train_end, test_end)."""
    folds, ts = [], start
    while True:
        tr_end = ts + pd.DateOffset(months=train_months)
        te_end = tr_end + pd.DateOffset(months=test_months)
        if te_end > end:
            break
        folds.append((ts, tr_end, tr_end, te_end))
        ts = ts + pd.DateOffset(months=test_months)
    return folds
