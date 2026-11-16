"""Data-integrity checks for M1 bid/ask bars. Hard errors raise; soft issues are counted."""

from __future__ import annotations

import pandas as pd


class DataIntegrityError(ValueError):
    pass


def check_m1(df: pd.DataFrame, max_spread: float = 5.0) -> dict:
    if df.index.tz is None:
        raise DataIntegrityError("index must be tz-aware UTC")
    if df.index.has_duplicates:
        raise DataIntegrityError(f"{df.index.duplicated().sum()} duplicated timestamps")
    if not df.index.is_monotonic_increasing:
        raise DataIntegrityError("timestamps not sorted")
    if (df[["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]] <= 0).any().any():
        raise DataIntegrityError("non-positive prices")
    if df.empty:
        return {"rows": 0, "start": None, "end": None}
    rep: dict = {"rows": len(df), "start": str(df.index[0]), "end": str(df.index[-1])}
    for side in ("bid", "ask"):
        o, h, l, c = (df[f"{side}_{x}"] for x in "ohlc")
        rep[f"{side}_bad_ohlc"] = int(((h < o.combine(c, max)) | (l > o.combine(c, min))).sum())
    spread = df["ask_c"] - df["bid_c"]
    rep["negative_spread"] = int((spread < 0).sum())
    rep["extreme_spread"] = int((spread > max_spread).sum())
    gaps = df.index.to_series().diff().dt.total_seconds().div(60)
    # gaps inside the trading week (ignore weekend and the daily 1h maintenance break)
    rep["gaps_2_to_59min"] = int(((gaps > 1) & (gaps < 60)).sum())
    rep["gaps_ge_60min"] = int((gaps >= 60).sum())
    if rep["bid_bad_ohlc"] or rep["ask_bad_ohlc"]:
        raise DataIntegrityError(f"inconsistent OHLC bars: {rep}")
    return rep
