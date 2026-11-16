"""Configurable prop-firm rule model + checker (equity-based, floating losses, daily reset).

Rules come from a YAML file with provenance (config/propfirm_ftmo_2step.yaml). Loading is
fail-closed: missing or implausible values raise. The checker is a pure state machine fed
with (timestamp, balance, equity) observations, so it works for backtests, replays and for
live monitoring from an EA log.

FTMO semantics implemented (from the firm's pages, see the YAML):
  * daily limit = balance at 00:00 CE(S)T minus max_daily_loss_pct of INITIAL capital;
  * max loss is STATIC: initial capital minus max_loss_pct;
  * both are measured on EQUITY (floating P/L, commissions, swaps count);
  * a profit target counts only when the balance exceeds it with all positions closed and
    the minimum number of trading days (days with a position OPENED) is met;
  * the news restriction (+-N min, SL/TP/pending included) applies to the funded phase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from xauscalp.config import ROOT

DEFAULT_RULES = ROOT / "config" / "propfirm_ftmo_2step.yaml"


class Phase(StrEnum):
    CHALLENGE = "challenge"
    VERIFICATION = "verification"
    FUNDED = "funded"


class Status(StrEnum):
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class RulesError(ValueError):
    """The rules file is missing a value, malformed or implausible."""


@dataclass(frozen=True)
class PhaseRules:
    profit_target_pct: float | None
    min_trading_days: int


@dataclass(frozen=True)
class PropRules:
    firm: str
    program: str
    phases: dict[str, PhaseRules]
    max_daily_loss_pct: float
    max_loss_pct: float
    tz: str
    news_window_min: float
    news_phases: tuple[str, ...]
    fees_eur: dict[int, float]
    reward_ratio: float
    account_sizes: tuple[int, ...]
    unverified: tuple[str, ...]
    retrieved: str


def _num(x, name: str, lo: float, hi: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
        raise RulesError(f"{name}={x!r} outside [{lo}, {hi}]")
    return float(x)


def load_rules(path: str | Path = DEFAULT_RULES) -> PropRules:
    d = yaml.safe_load(Path(path).read_text())
    try:
        r, eco = d["rules"], d["economics"]
        phases = {}
        for name, p in r["phases"].items():
            tgt = p["profit_target_pct"]
            phases[name] = PhaseRules(None if tgt is None else _num(tgt, f"{name}.target", 0.1, 100),
                                      int(_num(p["min_trading_days"], f"{name}.min_days", 0, 60)))
        nr = r["news_restriction"]
        rules = PropRules(
            firm=str(d["firm"]), program=str(d["program"]), phases=phases,
            max_daily_loss_pct=_num(r["max_daily_loss_pct"], "max_daily_loss_pct", 0.1, 50),
            max_loss_pct=_num(r["max_loss_pct"], "max_loss_pct", 0.1, 90),
            tz=str(r["daily_reset_tz"]), news_window_min=_num(nr["window_min"], "news.window", 0, 60),
            news_phases=tuple(nr["applies_to_phases"]),
            fees_eur={int(k): _num(v, f"fee{k}", 1, 100000) for k, v in eco["fee_eur_2step"].items()},
            reward_ratio=_num(eco["reward_ratio_default"], "reward_ratio", 0.01, 1.0),
            account_sizes=tuple(int(x) for x in r["account_sizes"]),
            unverified=tuple(d.get("unverified", [])), retrieved=str(d["retrieved"]))
    except KeyError as exc:
        raise RulesError(f"missing key {exc}") from exc
    ZoneInfo(rules.tz)                                           # raises if unknown
    if rules.max_daily_loss_pct >= rules.max_loss_pct:
        raise RulesError("daily loss limit must be below the maximum loss")
    if set(rules.phases) != {"challenge", "verification", "funded"}:
        raise RulesError("phases must be challenge, verification, funded")
    return rules


@dataclass
class Observation:
    ts: pd.Timestamp
    balance: float
    equity: float
    positions_open: int = 0
    opened_position: bool = False


@dataclass
class PropChecker:
    rules: PropRules
    phase: Phase
    initial: float
    status: Status = Status.RUNNING
    reason: str = ""
    breach_ts: pd.Timestamp | None = None
    pass_ts: pd.Timestamp | None = None
    trading_days: set[date] = field(default_factory=set)
    min_daily_margin: float = math.inf       # smallest (equity - daily limit) / initial seen
    min_total_margin: float = math.inf
    _day: date | None = None
    _day_start_balance: float = math.nan

    def daily_limit(self) -> float:
        return self._day_start_balance - self.rules.max_daily_loss_pct / 100 * self.initial

    def total_limit(self) -> float:
        return self.initial * (1 - self.rules.max_loss_pct / 100)

    def _local_day(self, ts: pd.Timestamp) -> date:
        return ts.tz_convert(self.rules.tz).date()

    def update(self, o: Observation) -> Status:
        if self.status is not Status.RUNNING:
            return self.status
        vals = (o.balance, o.equity)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
            return self._fail(o.ts, "INVALID_ACCOUNT_VALUES")        # fail-closed
        day = self._local_day(o.ts)
        if day != self._day:                                          # 00:00 CE(S)T reset
            self._day, self._day_start_balance = day, o.balance
        if o.opened_position:
            self.trading_days.add(day)
        self.min_daily_margin = min(self.min_daily_margin, (o.equity - self.daily_limit()) / self.initial)
        self.min_total_margin = min(self.min_total_margin, (o.equity - self.total_limit()) / self.initial)
        if o.equity <= self.daily_limit():
            return self._fail(o.ts, "MAX_DAILY_LOSS")
        if o.equity <= self.total_limit():
            return self._fail(o.ts, "MAX_LOSS")
        tgt = self.rules.phases[self.phase.value].profit_target_pct
        if (tgt is not None and o.positions_open == 0
                and o.balance >= self.initial * (1 + tgt / 100)
                and len(self.trading_days) >= self.rules.phases[self.phase.value].min_trading_days):
            self.status, self.pass_ts, self.reason = Status.PASSED, o.ts, "TARGET_REACHED"
        return self.status

    def _fail(self, ts: pd.Timestamp, why: str) -> Status:
        self.status, self.breach_ts, self.reason = Status.FAILED, ts, why
        return self.status


def news_windows(events: pd.DataFrame, rules: PropRules) -> pd.DataFrame:
    """[start, end] of every high-impact event restriction window (funded accounts)."""
    ev = events[events["impact"].isin(["high"])]
    w = pd.Timedelta(minutes=rules.news_window_min)
    return pd.DataFrame({"start": ev["utc_time"] - w, "end": ev["utc_time"] + w})


def news_violations(order_times: pd.DatetimeIndex, windows: pd.DataFrame) -> list[pd.Timestamp]:
    """Order executions (opens, SL/TP hits, closes) inside a restriction window."""
    bad = []
    for t in order_times:
        if ((windows["start"] <= t) & (t <= windows["end"])).any():
            bad.append(t)
    return bad


def size_lots(risk_money: float, sl_dist: float, *, contract_size: float = 100.0,
              lot_step: float = 0.01, lot_min: float = 0.01, lot_max: float = 50.0) -> float:
    """Lots whose loss at the stop does not exceed risk_money (floored; 0 = cannot size)."""
    if not all(math.isfinite(v) and v > 0 for v in (risk_money, sl_dist, contract_size, lot_step)):
        return 0.0
    steps = math.floor(risk_money / (sl_dist * contract_size) / lot_step + 1e-9)
    lots = round(steps * lot_step, 8)
    return 0.0 if lots < lot_min - 1e-12 else min(lots, lot_max)
