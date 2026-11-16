"""Market-regime labels (causal). Used for reporting and, if validated, as filters."""

from __future__ import annotations

import numpy as np
import pandas as pd


def vol_regime(atr_pct: pd.Series) -> pd.Series:
    lab = np.select([atr_pct < 1 / 3, atr_pct > 2 / 3], ["low_vol", "high_vol"], "mid_vol")
    lab = np.where(atr_pct.isna(), "unknown", lab)
    return pd.Series(lab, index=atr_pct.index, name="vol_regime")


def trend_regime(er_h1: pd.Series, threshold: float = 0.30) -> pd.Series:
    lab = np.where(er_h1 >= threshold, "trend", "range")
    lab = np.where(er_h1.isna(), "unknown", lab)
    return pd.Series(lab, index=er_h1.index, name="trend_regime")
