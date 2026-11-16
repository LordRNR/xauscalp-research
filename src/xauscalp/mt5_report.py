"""Readers for files produced by the MQL5 scripts in mt5/Scripts.

    uv run python -m xauscalp.mt5_report [data/mt5/xau_feasibility.csv]
prints the validated broker profile and how it compares with config/default.yaml.
The full study (capital feasibility on real ORB stop distances) is
research/05_broker_conditions.py.
"""

from __future__ import annotations

import csv
import io
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from xauscalp.config import ROOT, Config, SymbolSpec
from xauscalp.data.server_time import ServerTimePolicy

DEFAULT_FEASIBILITY_CSV = ROOT / "data" / "mt5" / "xau_feasibility.csv"
SUPPORTED_REPORT_VERSIONS = {"0.10"}


def read_feasibility(path: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, newline="", encoding="latin-1") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2:
                out[row[0].strip()] = row[1].strip()
    return out


def spec_from_report(rep: dict[str, str]) -> SymbolSpec:
    return SymbolSpec(
        name=rep["symbol"],
        contract_size=float(rep["contract_size"]),
        volume_min=float(rep["volume_min"]),
        volume_step=float(rep["volume_step"]),
        volume_max=float(rep["volume_max"]),
        profit_currency=rep.get("currency_profit", "USD"),
    )


class UnsortedExportError(ValueError):
    """Export rows are not in chronological order, so reading cannot stop at the limit."""


def server_cut(max_date: date | None) -> pd.Timestamp | None:
    """First SERVER-time instant that can no longer belong to a UTC date <= max_date.

    Server time is at most UTC+14h, so anything at or after max_date + 1 day + 14 h is
    certainly after the research window. The exact UTC cut is made later (sources._clip)."""
    if max_date is None:
        return None
    return pd.Timestamp(max_date) + pd.Timedelta(days=1, hours=14)


def read_csv_until(path: str | Path, key_of: Callable[[str], object],
                   limit: object | None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read an MT5 export, STOPPING at the first row whose key >= limit.

    Rows past the limit are never parsed or kept (audit H1 applied to broker exports:
    the holdout period must not even be decoded). Exports are written in chronological
    order; that is verified on the rows read and a violation raises, because early
    stopping would otherwise be unsafe."""
    meta: dict[str, str] = {}
    header, kept, prev = None, [], None
    with open(path, encoding="latin-1", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if header is None:
                if line.startswith("#"):
                    k, v = line[1:].split(",", 1)
                    meta[k.strip()] = v.strip()
                else:
                    header = line
                continue
            if not line:
                continue
            key = key_of(line)
            if prev is not None and key < prev:
                raise UnsortedExportError(f"{path}: row key {key!r} after {prev!r}")
            if limit is not None and key >= limit:
                break
            prev = key
            kept.append(line)
    if header is None:
        raise ValueError(f"{path}: no column header found")
    return pd.read_csv(io.StringIO("\n".join([header, *kept]))), meta


def read_mt5_rates_raw(path: str | Path, *, max_date: date | None
                       ) -> tuple[pd.DataFrame, dict[str, str]]:
    """Broker M1 export with its NAIVE server-time index (no timezone assumption).

    `max_date` is REQUIRED (None = no limit, only for the user-unlocked holdout flow):
    rows after server_cut(max_date) are not read at all."""
    cut = server_cut(max_date)
    limit = None if cut is None else cut.strftime("%Y.%m.%d %H:%M")
    df, meta = read_csv_until(path, lambda ln: ln.split(",", 1)[0], limit)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("time_server"), format="%Y.%m.%d %H:%M"),
                                name="time_server").as_unit("ns")
    df["spread"] = df.pop("spread_points") * float(meta["point"])
    return df, meta


def load_mt5_rates_csv(path: str | Path, policy: ServerTimePolicy, *,
                       max_date: date | None) -> pd.DataFrame:
    """Broker M1 export -> UTC-indexed Bid bars + spread in price units.

    Requires an explicit ServerTimePolicy. The offset written at export time
    (`server_minus_gmt_seconds_at_export`) is metadata only and is NEVER applied to the
    whole history (it is wrong for dates in the other DST regime: audit finding T1).
    Rows whose UTC time cannot be determined are dropped and counted in df.attrs.
    """
    df, meta = read_mt5_rates_raw(path, max_date=max_date)
    utc = policy.to_utc(df.index)  # raises TimezoneUnknown for the default policy
    keep = ~utc.isna()
    out = df[keep].copy()
    out.index = pd.DatetimeIndex(utc[keep], name="time")
    out.attrs.update(meta=meta, tz_policy=policy.kind, tz_source=policy.source,
                     dropped_undetermined_time=int((~keep).sum()))
    return out


class BrokerReportError(ValueError):
    """The feasibility report is missing a field, malformed, or implausible."""


_NUM = ["account_leverage", "account_balance", "account_equity", "account_margin_so_call",
        "account_margin_so_so", "contract_size", "volume_min", "volume_max", "volume_step",
        "tick_size", "tick_value", "point", "stops_level_points", "freeze_level_points",
        "spread_now_points", "swap_long", "swap_short", "server_minus_gmt_seconds", "bid", "ask",
        "spread_now_price", "spread_m1_p50_price", "spread_m1_p90_price", "spread_m1_p99_price",
        "spread_sample_m1_bars", "margin_for_0.010_lots", "profit_per_1usd_move_0.010_lots",
        "profit_per_1usd_move_1.000_lots", "digits"]
_STR = ["report_version", "generated_gmt", "account_trade_mode", "account_is_demo",
        "account_company", "account_server", "account_currency", "account_margin_mode",
        "symbol", "symbol_calc_mode", "symbol_trade_mode", "currency_profit", "spread_float",
        "swap_mode", "terminal_trade_allowed", "ordercheck_retcode", "ordercheck_comment"]


@dataclass(frozen=True)
class BrokerProfile:
    """Typed, validated view of xau_feasibility.csv (one terminal, one moment)."""

    raw: dict[str, str]

    def num(self, k: str) -> float:
        return float(self.raw[k])

    @property
    def is_demo(self) -> bool:
        return (self.raw["account_is_demo"] == "true"
                and self.raw["account_trade_mode"] == "ACCOUNT_TRADE_MODE_DEMO")

    @property
    def hedging(self) -> bool:
        return "HEDGING" in self.raw["account_margin_mode"]

    @property
    def leverage(self) -> float:
        return self.num("account_leverage")

    @property
    def profit_to_account_rate(self) -> float:
        """Account-currency value of 1 unit of profit currency (USD), from OrderCalcProfit
        on 1.00 lot: profit for a 1 USD move on 1 lot is contract_size USD."""
        return self.num("profit_per_1usd_move_1.000_lots") / self.num("contract_size")

    @property
    def spec(self) -> SymbolSpec:
        return spec_from_report(self.raw)

    @property
    def sessions(self) -> dict[str, str]:
        return {k.removeprefix("session_"): v.strip() for k, v in self.raw.items()
                if k.startswith("session_")}

    @property
    def spread_by_server_hour(self) -> pd.Series:
        d = {int(k.rsplit("_", 1)[1]): float(v) for k, v in self.raw.items()
             if k.startswith("spread_mean_server_hour_")}
        return pd.Series(d, name="spread_mean").sort_index()


def broker_profile(rep: dict[str, str]) -> BrokerProfile:
    """Validate a parsed report. Fail-closed: anything missing or implausible raises."""
    missing = [k for k in _NUM + _STR if k not in rep or rep[k] == ""]
    if missing:
        raise BrokerReportError(f"missing fields: {missing}")
    if rep["report_version"] not in SUPPORTED_REPORT_VERSIONS:
        raise BrokerReportError(f"unsupported report_version {rep['report_version']}")
    bad = []
    for k in _NUM:
        try:
            v = float(rep[k])
        except ValueError:
            bad.append(k)
            continue
        if not math.isfinite(v):
            bad.append(k)
    if bad:
        raise BrokerReportError(f"non-numeric or non-finite fields: {bad}")
    p = BrokerProfile(dict(rep))
    checks = {
        "contract_size > 0": p.num("contract_size") > 0,
        "0 < volume_min <= volume_max": 0 < p.num("volume_min") <= p.num("volume_max"),
        "volume_step > 0": p.num("volume_step") > 0,
        "leverage >= 1": p.leverage >= 1,
        "0 < bid < ask": 0 < p.num("bid") < p.num("ask"),
        "spread_now_price == ask - bid": abs(p.num("ask") - p.num("bid")
                                             - p.num("spread_now_price")) < 1e-6,
        "spread quantiles ordered": (0 <= p.num("spread_m1_p50_price") <= p.num("spread_m1_p90_price")
                                     <= p.num("spread_m1_p99_price")),
        "profit/1USD/lot > 0": p.num("profit_per_1usd_move_1.000_lots") > 0,
        "profit currency USD": rep["currency_profit"] == "USD",
        "server offset within +-14h": abs(p.num("server_minus_gmt_seconds")) <= 14 * 3600,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        raise BrokerReportError(f"implausible values: {failed}")
    # internal consistency: margin of 0.01 lot vs. price/leverage/fx (CFD leverage mode)
    if rep["symbol_calc_mode"] == "SYMBOL_CALC_MODE_CFDLEVERAGE":
        expect = (0.01 * p.num("contract_size") * p.num("ask") / p.leverage
                  * p.profit_to_account_rate)
        if abs(expect - p.num("margin_for_0.010_lots")) > 0.05 * expect:
            raise BrokerReportError(
                f"margin_for_0.010_lots {rep['margin_for_0.010_lots']} inconsistent with "
                f"price/leverage/fx ({expect:.2f})")
    return p


def load_broker_profile(path: str | Path = DEFAULT_FEASIBILITY_CSV) -> BrokerProfile:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run mt5/Scripts/XAU_FeasibilityReport in MT5, then "
            "`uv run python -m xauscalp.mt5_build fetch` (copies it from Common/Files).")
    return broker_profile(read_feasibility(path))


@dataclass(frozen=True)
class Finding:
    area: str
    config_value: str
    broker_value: str
    status: str   # MATCH | CONFIG_MORE_CONSERVATIVE | BROKER_WORSE | UNKNOWN | INFO
    note: str


def compare_with_config(p: BrokerProfile, cfg: Config) -> list[Finding]:
    """What the real account says about each research/risk assumption. Never edits config:
    a broker that looks CHEAPER than assumed is reported, not adopted (MetaQuotes-Demo is
    not a broker that executes real orders)."""
    f: list[Finding] = []
    s, r, c = cfg.symbol, cfg.risk, cfg.costs

    def same(area: str, cv: float, bv: float, note: str = "") -> None:
        f.append(Finding(area, f"{cv:g}", f"{bv:g}", "MATCH" if cv == bv else "INFO", note))

    f.append(Finding("account mode", "DEMO required", p.raw["account_trade_mode"],
                     "MATCH" if p.is_demo else "BROKER_WORSE",
                     "the EA refuses non-demo accounts"))
    same("contract_size (oz/lot)", s.contract_size, p.num("contract_size"))
    same("volume_min (lots)", s.volume_min, p.num("volume_min"))
    same("volume_step (lots)", s.volume_step, p.num("volume_step"))
    f.append(Finding("volume_max (lots)", f"{s.volume_max:g}", f"{p.num('volume_max'):g}",
                     "CONFIG_MORE_CONSERVATIVE" if s.volume_max <= p.num("volume_max")
                     else "BROKER_WORSE", "cap only; risk % decides the size"))
    f.append(Finding("account currency", cfg.account.get("currency", "?"),
                     p.raw["account_currency"],
                     "MATCH" if cfg.account.get("currency") == p.raw["account_currency"]
                     else "INFO", "P&L converted with OrderCalcProfit"))
    lev = float(cfg.account.get("leverage", 20))
    f.append(Finding("leverage", f"{lev:g}", f"{p.leverage:g}",
                     "CONFIG_MORE_CONSERVATIVE" if lev <= p.leverage else "BROKER_WORSE",
                     "config keeps the ESMA retail cap for gold (20:1) for planning a real "
                     "EU account; margin at the demo's leverage is lower"))
    f.append(Finding("margin mode", "1 position (enforced by us)", p.raw["account_margin_mode"],
                     "INFO", "hedging allows several positions: the risk guard counts ANY "
                     "position on the symbol" if p.hedging else "netting"))
    f.append(Finding("stops/freeze level (points)", "checked by the EA",
                     f"{p.num('stops_level_points'):g}/{p.num('freeze_level_points'):g}",
                     "MATCH", "0 = no minimum distance today (can change; checked live)"))
    p50, p90, p99 = (p.num(f"spread_m1_{q}_price") for q in ("p50", "p90", "p99"))
    f.append(Finding("max_spread_usd filter", f"{r.max_spread_usd:g}",
                     f"bar p50 {p50:g} / p90 {p90:g} / p99 {p99:g}",
                     "INFO" if p99 < r.max_spread_usd else "BROKER_WORSE",
                     "bar spread is usually the bar MINIMUM (optimistic); confirm with ticks"))
    f.append(Finding("research cost model", f"Dukascopy spread + {c.extra_spread_usd:g}",
                     f"bar p50 {p50:g}", "UNKNOWN",
                     "not comparable yet: different dates and bar-min spreads. Calibrate "
                     "with broker M1/tick exports on the SAME pre-holdout dates. A cheaper "
                     "demo is never adopted as the cost model"))
    f.append(Finding("commission (per lot, round turn)", f"{r.commission_per_lot:g}",
                     "not exposed by SymbolInfo", "UNKNOWN",
                     "read DEAL_COMMISSION of a real broker's demo fill before Stage C"))
    f.append(Finding("slippage", f"risk {r.expected_slippage_usd:g} / backtest {c.slippage_usd:g}",
                     "unknown (no fills yet)", "UNKNOWN", "measure in DEMO (Stage C)"))
    f.append(Finding("swap (points/lot/night)", "not modelled (intraday)",
                     f"long {p.num('swap_long'):g} / short {p.num('swap_short'):g}", "INFO",
                     "ORB exits <= 150 min after the session open, far from the rollover"))
    f.append(Finding("server - GMT now (s)", "never assumed",
                     f"{p.num('server_minus_gmt_seconds'):g}", "INFO",
                     "one moment only; historical rule must be verified (study 04)"))
    f.append(Finding("OrderCheck", "must pass before Stage C",
                     f"{p.raw['ordercheck_retcode']} {p.raw['ordercheck_comment']}", "INFO",
                     "10027 = AutoTrading disabled in the terminal (deliberate)"))
    return f


def findings_frame(fs: list[Finding]) -> pd.DataFrame:
    return pd.DataFrame([f.__dict__ for f in fs])


def main(argv: list[str]) -> int:
    from xauscalp.config import load_config
    p = load_broker_profile(argv[1] if len(argv) > 1 else DEFAULT_FEASIBILITY_CSV)
    print(f"{p.raw['account_server']} ({p.raw['account_company']}), "
          f"{p.raw['account_currency']}, 1:{p.leverage:g}, demo={p.is_demo}, "
          f"{p.raw['account_margin_mode']}")
    print(f"{p.raw['symbol']} contract {p.num('contract_size'):g} oz, min {p.num('volume_min')} "
          f"step {p.num('volume_step')}, margin 0.01 lot = {p.raw['margin_for_0.010_lots']} "
          f"{p.raw['account_currency']}, 1 USD move on 0.01 lot = "
          f"{p.num('profit_per_1usd_move_0.010_lots'):g} {p.raw['account_currency']}")
    print(findings_frame(compare_with_config(p, load_config())).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
