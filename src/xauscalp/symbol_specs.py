"""Reader and viability maths for the contract specifications exported by XAU_SymbolSpecs.mq5.

Answers, per instrument and WITHOUT any assumption about a strategy: can the minimum lot be sized
inside the risk budget for a given stop distance, what does the spread cost at the minimum lot, what
do swaps and margin look like. Money is in the ACCOUNT currency (tick_value is already converted by
the broker). Commission is not exposed by MQL5: it must be added by hand from the firm's contract page.

    uv run python -m xauscalp.symbol_specs data/mt5/xauscalp/symbol_specs_mqdemo.csv \
        --capital 1000 --risk-pct 0.5 --sl XAUUSD=12,EURUSD=0.0030
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

NUMERIC = ["digits", "point", "contract_size", "volume_min", "volume_step", "volume_max", "tick_size",
           "tick_value", "spread_points", "swap_long", "swap_short", "margin_1lot"]


class SpecsError(ValueError):
    """A specs file is malformed or has implausible values."""


@dataclass
class Specs:
    meta: dict[str, str]
    df: pd.DataFrame


def load_specs(path: str | Path) -> Specs:
    meta: dict[str, str] = {}
    rows = []
    header = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(",")
        if line.startswith("#"):
            meta[parts[0][1:]] = ",".join(parts[1:])
        elif header is None:
            header = parts
        else:
            rows.append(parts + [""] * (len(header) - len(parts)))
    if header is None or "symbol" not in header:
        raise SpecsError("no header row with 'symbol'")
    df = pd.DataFrame(rows, columns=header)
    df["found"] = df["found"].astype(int)
    for c in NUMERIC + ["tick_value_loss", "tick_value_profit", "bid", "ask"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    ok = df[df["found"] == 1]
    for c in ("contract_size", "volume_min", "volume_step", "tick_size", "tick_value", "point"):
        bad = ok[~ok[c].map(lambda v: isinstance(v, float) and math.isfinite(v) and v > 0)]
        if len(bad):
            raise SpecsError(f"{c} missing or non-positive for {list(bad['symbol'])}")
    return Specs(meta, df.set_index("symbol"))


def _tv_loss(r) -> float:
    v = r.get("tick_value_loss")
    return float(v) if isinstance(v, float) and math.isfinite(v) and v > 0 else float(r["tick_value"])


def risk_at_min_lot(r, sl_dist: float) -> float:
    """Loss at the stop (account currency) with the minimum lot, no slippage."""
    if not (math.isfinite(sl_dist) and sl_dist > 0):
        raise SpecsError("sl_dist must be positive and finite")
    return float(r["volume_min"]) * sl_dist / float(r["tick_size"]) * _tv_loss(r)


def spread_cost_min_lot(r) -> float:
    """Entry spread in account currency at the minimum lot (the exit pays it again through the bid/ask)."""
    return float(r["volume_min"]) * float(r["spread_points"]) * float(r["point"]) / float(r["tick_size"]) * float(r["tick_value"])


def viability_table(specs: Specs, capital: float, risk_pct: float, sl_dist: dict[str, float]) -> pd.DataFrame:
    if not (capital > 0 and 0 < risk_pct <= 1.0):
        raise SpecsError("capital > 0 and 0 < risk_pct <= 1.0 (the project's hard ceiling)")
    budget = capital * risk_pct / 100
    out = []
    for sym, r in specs.df.iterrows():
        if r["found"] != 1:
            out.append({"symbol": sym, "found": False})
            continue
        sl = sl_dist.get(sym)
        row = {"symbol": sym, "found": True, "contract": r["contract_size"], "vol_min": r["volume_min"],
               "vol_step": r["volume_step"], "spread_cost_min_lot": spread_cost_min_lot(r),
               "swap_long": r["swap_long"], "swap_short": r["swap_short"], "margin_min_lot": r["margin_1lot"] * r["volume_min"]}
        if sl:
            risk = risk_at_min_lot(r, sl)
            row.update(sl_dist=sl, risk_at_min_lot=risk, budget=budget, sizeable=risk <= budget,
                       min_capital_for_risk_pct=risk / (risk_pct / 100),
                       spread_cost_pct_of_risk=100 * spread_cost_min_lot(r) / risk)
        out.append(row)
    return pd.DataFrame(out).set_index("symbol")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--capital", type=float, required=True)
    ap.add_argument("--risk-pct", type=float, default=0.5)
    ap.add_argument("--sl", default="", help="SYMBOL=price distance,... (e.g. XAUUSD=12,EURUSD=0.003)")
    a = ap.parse_args(argv)
    sl = {k: float(v) for k, v in (kv.split("=") for kv in a.sl.split(",") if kv)}
    s = load_specs(a.csv)
    print({k: v for k, v in s.meta.items() if k in ("company", "server", "account_currency", "leverage", "time_server")})
    print(viability_table(s, a.capital, a.risk_pct, sl).round(4).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
