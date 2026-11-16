"""Pluggable market-data sources with a single canonical output.

Every source returns MarketData:
  m1        canonical M1 frame, UTC index, columns bid_o..bid_c, ask_o..ask_c, volume
  meta      SourceMetadata (provider, granularity, how Ask is obtained, timezone status,
            spread semantics, licence/cost, evidence notes)
  coverage  CoverageReport;  quality  dict from check_m1
Strategies and the backtester only see the canonical frame, so sources can be swapped
without touching strategy code. Differences in data QUALITY are carried in `meta` and
must be reported next to any result (e.g. derived Ask from MT5 bar spread is optimistic).

Sources:
  DukascopyM1Source      free, M1 Bid+Ask OHLC, UTC, long history; NOT your broker's quotes
  MT5BrokerM1Source      your broker's M1 Bid OHLC + per-bar spread field (Ask DERIVED),
                         server time -> UTC only with a ServerTimePolicy
  MT5BrokerTicksSource   your broker's real Bid/Ask ticks (CopyTicksRange export),
                         aggregated to exact M1 Bid and Ask OHLC; tick depth is limited
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from xauscalp.data.coverage import CoverageReport, coverage_report
from xauscalp.data.dukascopy import load_m1
from xauscalp.data.quality import check_m1
from xauscalp.data.server_time import ServerTimePolicy
from xauscalp.mt5_report import read_csv_until, read_mt5_rates_raw, server_cut

CANONICAL = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]


@dataclass(frozen=True)
class SourceMetadata:
    name: str
    provider: str
    granularity: str            # "M1" | "tick->M1"
    ask_source: str             # "real ask OHLC" | "derived: bid + bar spread field"
    timezone: str               # e.g. "UTC (provider)" or "server time via policy=base_dst"
    timezone_verified: bool
    spread_semantics: str
    cost: str
    licence_note: str
    use_extra_spread: bool      # True if a broker-spread markup should be added (not broker data)
    notes: str = ""


@dataclass
class MarketData:
    m1: pd.DataFrame
    meta: SourceMetadata
    coverage: CoverageReport
    quality: dict


class DataSource(Protocol):
    meta: SourceMetadata

    def load(self, start: date, end: date, *, max_date: date | None) -> MarketData: ...


def _finish(m1: pd.DataFrame, meta: SourceMetadata, start: date, end: date) -> MarketData:
    m1 = m1[CANONICAL].sort_index()
    m1.index = m1.index.as_unit("ns")
    q = check_m1(m1)
    return MarketData(m1=m1, meta=meta, coverage=coverage_report(m1, start, end), quality=q)


def _preclip_server(raw: pd.DataFrame, max_date: date | None) -> pd.DataFrame:
    """Second line of defence (the raw readers already stop at server_cut(max_date))."""
    cut = server_cut(max_date)
    return raw if cut is None else raw[raw.index < cut]


def _clip(df: pd.DataFrame, start: date, end: date, max_date: date | None) -> pd.DataFrame:
    if max_date is not None:
        end = min(end, max_date)
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    return df[(df.index >= lo) & (df.index < hi)]


class DukascopyM1Source:
    def __init__(self, cache_dir: Path, symbol: str = "XAUUSD"):
        self.cache_dir, self.symbol = Path(cache_dir), symbol
        self.meta = SourceMetadata(
            name="dukascopy_m1", provider="Dukascopy public datafeed", granularity="M1",
            ask_source="real ask OHLC", timezone="UTC (provider)", timezone_verified=True,
            spread_semantics="ask_c - bid_c at bar close (ECN-like; tighter than retail CFD)",
            cost="free (rate-limited)",
            licence_note="free for personal use; do not redistribute raw data",
            use_extra_spread=True,
            notes="Not the broker's price feed: add extra spread; levels may differ slightly.")

    def load(self, start: date, end: date, *, max_date: date | None) -> MarketData:
        e = min(end, max_date) if max_date else end
        m1 = load_m1(self.symbol, start, e, self.cache_dir, max_date=max_date)
        return _finish(m1, self.meta, start, e)


class MT5BrokerM1Source:
    def __init__(self, csv_path: Path, policy: ServerTimePolicy):
        self.path, self.policy = Path(csv_path), policy
        self.meta = SourceMetadata(
            name="mt5_broker_m1", provider="MT5 broker server (XAU_ExportHistory.mq5)",
            granularity="M1", ask_source="derived: bid + bar spread field",
            timezone=f"server time via policy={policy.kind} ({policy.source})",
            timezone_verified=policy.kind == "inferred",
            spread_semantics="MqlRates.spread (points); on many servers the bar MINIMUM -> "
                             "derived Ask is OPTIMISTIC",
            cost="free", licence_note="your broker's data, personal use",
            use_extra_spread=False,
            notes="Bid OHLC are the broker's; Ask high/low are approximations.")

    def load(self, start: date, end: date, *, max_date: date | None) -> MarketData:
        raw, _ = read_mt5_rates_raw(self.path, max_date=max_date)
        raw = _preclip_server(raw, max_date)
        utc = self.policy.to_utc(raw.index)
        raw = raw[~utc.isna()]
        raw.index = pd.DatetimeIndex(utc[~utc.isna()], name="time")
        m1 = pd.DataFrame(index=raw.index)
        for src, dst in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")):
            m1[f"bid_{dst}"] = raw[src]
            m1[f"ask_{dst}"] = raw[src] + raw["spread"]
        m1["volume"] = raw["tick_volume"].astype(float)
        e = min(end, max_date) if max_date else end
        return _finish(_clip(m1, start, end, max_date), self.meta, start, e)


def read_mt5_ticks_raw(path: Path, *, max_date: date | None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Tick export (server-time epoch ms). Stops reading at server_cut(max_date)."""
    cut = server_cut(max_date)
    limit = None if cut is None else int(cut.value // 1_000_000)   # .value is ALWAYS ns
    df, meta = read_csv_until(path, lambda ln: int(ln.split(",", 1)[0]), limit)
    ms = df.pop("time_msc_server").astype("int64")
    df.index = pd.DatetimeIndex(pd.to_datetime(ms, unit="ms"), name="time_server").as_unit("ns")
    return df, meta


class MT5BrokerTicksSource:
    def __init__(self, csv_path: Path, policy: ServerTimePolicy):
        self.path, self.policy = Path(csv_path), policy
        self.meta = SourceMetadata(
            name="mt5_broker_ticks", provider="MT5 broker server (XAU_ExportTicks.mq5)",
            granularity="tick->M1", ask_source="real ask OHLC (from ticks)",
            timezone=f"server time via policy={policy.kind} ({policy.source})",
            timezone_verified=policy.kind == "inferred",
            spread_semantics="exact bid/ask of every quote", cost="free",
            licence_note="your broker's data, personal use", use_extra_spread=False,
            notes="Tick history depth on the server is limited; aggregated to M1 here. "
                  "Intrabar order is still lost in the M1 engine (use ticks for level 2).")

    def ticks(self, max_date: date | None = None) -> pd.DataFrame:
        raw, _ = read_mt5_ticks_raw(self.path, max_date=max_date)
        raw = _preclip_server(raw, max_date)
        bad = ~(np.isfinite(raw["bid"]) & np.isfinite(raw["ask"]) & (raw["bid"] > 0)
                & (raw["ask"] >= raw["bid"]))
        raw = raw[~bad]
        utc = self.policy.to_utc(raw.index)
        raw = raw[~utc.isna()]
        raw.index = pd.DatetimeIndex(utc[~utc.isna()], name="time")
        raw.attrs["invalid_ticks_dropped"] = int(bad.sum())
        return raw

    def load(self, start: date, end: date, *, max_date: date | None) -> MarketData:
        t = self.ticks(max_date)
        g = t.resample("1min", label="left", closed="left")
        m1 = pd.concat([g["bid"].ohlc().add_prefix("bid_"), g["ask"].ohlc().add_prefix("ask_")],
                       axis=1)
        m1.columns = [c.replace("open", "o").replace("high", "h").replace("low", "l")
                      .replace("close", "c") for c in m1.columns]
        m1["volume"] = g["bid"].count().astype(float)
        m1 = m1.dropna()
        e = min(end, max_date) if max_date else end
        return _finish(_clip(m1, start, end, max_date), self.meta, start, e)
