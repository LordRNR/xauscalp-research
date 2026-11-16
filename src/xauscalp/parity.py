"""Stage B: Python <-> MQL5 signal parity.

Compares the EA's decision log (Common/Files/xauscalp/decisions_<tag>.csv, produced in
the Strategy Tester or live DEMO read-only) with orb_scan() run in Python on the SAME
broker data (MT5BrokerM1Source + a verified ServerTimePolicy).

Matching key: (day, session). Per row we compare:
  status, direction, decision bar time (exact), OR high/low (|diff| <= price_tol),
  ATR M5 (relative <= atr_rel_tol), SL distance (relative <= atr_rel_tol),
  decision-bar spread (EA `spread_bar` vs Python `spread_py`: same bar, same data, so it
  must be identical to 1e-6).
Documented, explainable differences:
  * The EA ALSO logs `spread_now` = quote at its first tick of the NEXT bar (execution
    moment); Python only has the decision bar's spread. They are different quantities, so
    they are not compared as a pass/fail; `spread_next_py` (Python's spread of bar i+1,
    equal to `spread_now` in the Tester's "1 minute OHLC" mode) is shown beside them.
  * SPREAD_SENSITIVE: statuses differ only among REJECT_SPREAD / REJECT_COST / SIGNAL
    and the spreads used by each side differ. Reported separately, never silently counted
    as a match.
Equivalence is declared ONLY if there are zero hard mismatches and at least
`min_compared` day-sessions were compared. Anything else is "NOT EQUIVALENT / NOT PROVEN".

Tolerances (justification):
  price_tol   = 1 tick (the EA reads the same broker bars; only float formatting differs)
  atr_rel_tol = 1e-3 (Wilder seeds differ: Python seeds at segment start, the EA seeds
                10 calendar days back and refuses < 300 M5 bars -> (13/14)^300 ~ 5e-10.
                A 502-bar CALENDAR window (first version) held ~110 bars on Monday
                mornings and gave 1.0-1.3e-3, i.e. the tolerance caught a real defect;
                do NOT loosen it to hide such differences)

    uv run python -m xauscalp.parity --ea decisions_ro.csv --broker-m1 XAUUSD_M1.csv \
        --tz base_dst:120:America/New_York
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from xauscalp.config import CostModel, load_config
from xauscalp.data.server_time import ServerTimePolicy
from xauscalp.features.core import build_features
from xauscalp.strategies.orb import ORBParams, orb_scan, records_frame

FLEX = {"REJECT_SPREAD", "REJECT_COST", "SIGNAL"}


@dataclass
class ParityReport:
    compared: int
    hard_mismatches: int
    spread_sensitive: int
    only_in_ea: int
    only_in_python: int
    equivalent: bool
    detail: pd.DataFrame = field(repr=False)

    def verdict(self) -> str:
        if self.equivalent:
            return f"EQUIVALENT on {self.compared} day-sessions (tolerances documented)"
        return (f"NOT EQUIVALENT / NOT PROVEN: compared={self.compared}, "
                f"hard_mismatches={self.hard_mismatches}, spread_sensitive="
                f"{self.spread_sensitive}, only_in_ea={self.only_in_ea}, "
                f"only_in_python={self.only_in_python}")


class DuplicateDecisionsError(ValueError):
    """The EA log holds more than one row per (day, session): it appends across runs."""


def read_ea_log(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    dup = df.duplicated(["day", "session"], keep=False)
    if dup.any():
        raise DuplicateDecisionsError(
            f"{int(dup.sum())} rows share a (day, session) in {path}: the EA appends to its log "
            "across runs. Delete the file or use a new InpLogTag for each tester run.")
    df["bar_utc"] = pd.to_datetime(df["bar_utc"], format="%Y.%m.%d %H:%M:%S", utc=True)
    return df


def compare(ea: pd.DataFrame, py: pd.DataFrame, *, price_tol: float = 0.01,
            atr_rel_tol: float = 1e-3, min_compared: int = 20) -> ParityReport:
    py = py.copy()
    py["decision_time"] = pd.to_datetime(py["decision_time"].replace("", np.nan), utc=True)
    key = ["day", "session"]
    m = ea.merge(py, on=key, how="outer", suffixes=("_ea", "_py"), indicator=True)
    rows = []
    for _, r in m.iterrows():
        if r["_merge"] != "both":
            rows.append({**{k: r[k] for k in key}, "result": r["_merge"], "why": ""})
            continue
        why = []
        s_ea, s_py = r["status_ea"], r["status_py"]
        tech = s_py in FLEX | {"DATA_GAP_AT_SIGNAL"} and s_ea in FLEX | {"DATA_GAP_AT_SIGNAL"}
        if s_ea != s_py and not (s_ea in FLEX and s_py in FLEX):
            why.append(f"status {s_ea}!={s_py}")
        if np.isfinite(r.get("or_high_py", np.nan)) and np.isfinite(r.get("or_high_ea", np.nan)):
            if abs(r["or_high_ea"] - r["or_high_py"]) > price_tol + 1e-9:
                why.append("or_high")
            if abs(r["or_low_ea"] - r["or_low_py"]) > price_tol + 1e-9:
                why.append("or_low")
        if tech:
            sb_ea, sb_py = r.get("spread_bar"), r.get("spread_py")
            if not (np.isfinite(sb_ea) and np.isfinite(sb_py)) or abs(sb_ea - sb_py) > 1e-6:
                why.append("spread_bar")
            if int(r["direction_ea"]) != int(r["direction_py"]):
                why.append("direction")
            if r["bar_utc"] != r["decision_time"]:
                why.append("decision_time")
            if abs(r["atr_m5"] / r["atr_py"] - 1) > atr_rel_tol:
                why.append("atr")
            if abs(r["sl_dist_ea"] / r["sl_dist_py"] - 1) > atr_rel_tol:
                why.append("sl_dist")
        if why:
            result = "MISMATCH"
        elif s_ea != s_py:
            result = "SPREAD_SENSITIVE"
        else:
            result = "MATCH"
        rows.append({**{k: r[k] for k in key}, "result": result, "why": ",".join(why),
                     "status_ea": s_ea, "status_py": s_py,
                     "spread_bar_ea": r.get("spread_bar"), "spread_py": r.get("spread_py"),
                     "spread_now_ea": r.get("spread_now"),
                     "spread_next_py": r.get("spread_next_py", np.nan)})
    d = pd.DataFrame(rows)
    cnt = d["result"].value_counts()
    compared = int(cnt.get("MATCH", 0) + cnt.get("MISMATCH", 0) + cnt.get("SPREAD_SENSITIVE", 0))
    hard = int(cnt.get("MISMATCH", 0))
    rep = ParityReport(compared=compared, hard_mismatches=hard,
                       spread_sensitive=int(cnt.get("SPREAD_SENSITIVE", 0)),
                       only_in_ea=int(cnt.get("left_only", 0)),
                       only_in_python=int(cnt.get("right_only", 0)),
                       equivalent=False, detail=d)
    rep.equivalent = (hard == 0 and rep.only_in_ea == 0 and rep.only_in_python == 0
                      and compared >= min_compared)
    return rep


def python_records(m1: pd.DataFrame, params: list[ORBParams], costs: CostModel,
                   max_spread: float) -> pd.DataFrame:
    feats = build_features(m1)
    frames = [records_frame(orb_scan(m1, feats, p, costs, max_spread)) for p in params]
    py = pd.concat(frames, ignore_index=True).rename(
        columns={"atr": "atr_py", "spread": "spread_py"})
    # Spread of the bar AFTER the decision bar = what the Tester's "1 minute OHLC" mode quotes
    # at the EA's first tick of bar i+1 (the EA's `spread_now`). Informational only.
    dt = pd.to_datetime(py["decision_time"].replace("", np.nan), utc=True)
    nxt = (dt + pd.Timedelta(minutes=1)).dt.as_unit("ns")
    spr = (m1["ask_c"] - m1["bid_c"]).astype("float64")
    py["spread_next_py"] = spr.reindex(pd.DatetimeIndex(nxt)).to_numpy()
    return py


def restrict_days(df: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    """Keep rows whose ISO `day` is within [lo, hi] (string order == date order)."""
    return df[(df["day"] >= lo) & (df["day"] <= hi)]


def parse_tz(spec: str) -> ServerTimePolicy:
    kind, *rest = spec.split(":")
    if kind == "fixed":
        return ServerTimePolicy(kind="fixed", offset_min=int(rest[0]), source="cli")
    if kind == "iana":
        return ServerTimePolicy(kind="iana", zone=rest[0], source="cli")
    if kind == "base_dst":
        return ServerTimePolicy(kind="base_dst", base_min=int(rest[0]), dst_of=rest[1],
                                source="cli")
    raise ValueError("tz spec: fixed:<min> | iana:<zone> | base_dst:<min>:<zone>")


def main(argv: list[str] | None = None) -> int:
    from xauscalp.data.sources import MT5BrokerM1Source
    from xauscalp.pipeline import research_max_date
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ea", help="EA decision log; omit to only write Python's expected records")
    ap.add_argument("--broker-m1", required=True)
    ap.add_argument("--tz", required=True)
    ap.add_argument("--from", dest="d_from", required=True,
                    help="first day compared (YYYY-MM-DD) = the tester's start date")
    ap.add_argument("--to", dest="d_to", required=True,
                    help="last day compared (YYYY-MM-DD) = the tester's end date")
    ap.add_argument("--expected-out", help="write Python's expected day-session records (CSV)")
    ap.add_argument("--or-minutes", type=int, default=15)
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-r", type=float, default=1.5)
    ap.add_argument("--include-holdout-period", action="store_true",
                    help="also compare decisions on dates >= holdout_start. Parity compares "
                         "SIGNAL DECISIONS only (no P&L is computed), but by default the "
                         "lockbox is respected (audit M6).")
    a = ap.parse_args(argv)
    if not a.ea and not a.expected_out:
        ap.error("give --ea (compare) and/or --expected-out (write Python's expectations)")
    lo, hi = date.fromisoformat(a.d_from), date.fromisoformat(a.d_to)
    if lo > hi:
        ap.error("--from is after --to")
    cfg = load_config()
    max_d = None if a.include_holdout_period else research_max_date(cfg)
    if max_d is not None and hi > max_d:
        ap.error(f"--to {hi} is inside the holdout period (research ends {max_d}); "
                 "pass --include-holdout-period only if YOU unlocked it")
    if max_d is None:
        print("NOTE: holdout-period dates included; decisions only, no performance computed.")
    sc = cfg.strategy["orb"]
    md = MT5BrokerM1Source(Path(a.broker_m1), parse_tz(a.tz)).load(
        lo - timedelta(days=30), hi, max_date=max_d)       # 30 days of warm-up before --from
    params = [ORBParams(session=s, tz=v["tz"], open_hhmm=v["open"], or_minutes=a.or_minutes,
                        sl_atr=a.sl_atr, tp_r=a.tp_r, entry_window_min=sc["entry_window_min"],
                        max_hold_min=sc["max_hold_min"], buffer_atr=sc["buffer_atr"],
                        max_cost_frac=sc["max_cost_frac"])
              for s, v in sc["sessions"].items()]
    costs = CostModel(0.0, cfg.costs.slippage_usd, cfg.costs.commission_per_lot_usd)
    py = restrict_days(python_records(md.m1, params, costs, cfg.risk.max_spread_usd),
                       a.d_from, a.d_to)
    print(f"Python expects {len(py)} day-sessions in {a.d_from} .. {a.d_to}: "
          + ", ".join(f"{k}={v}" for k, v in py["status"].value_counts().items()))
    if a.expected_out:
        py.to_csv(a.expected_out, index=False)
        print("wrote", a.expected_out)
    if not a.ea:
        return 0
    ea = restrict_days(read_ea_log(a.ea), a.d_from, a.d_to)
    rep = compare(ea, py)
    print(rep.verdict())
    d = rep.detail[rep.detail["result"] != "right_only"]
    both = d.dropna(subset=["spread_now_ea", "spread_next_py"])
    if len(both):
        same = int(np.isclose(both["spread_now_ea"], both["spread_next_py"]).sum())
        print(f"info: EA spread_now == Python spread of the NEXT bar in {same}/{len(both)} "
              "compared sessions (expected in ' 1 minute OHLC' mode; not a pass/fail check)")
    print(rep.detail[rep.detail["result"] != "MATCH"].to_string())
    return 0 if rep.equivalent else 1


if __name__ == "__main__":
    raise SystemExit(main())
