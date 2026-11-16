"""Audit findings H1 (holdout access) and DL1 (downloader etiquette)."""
import lzma
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from xauscalp.data import dukascopy as dk
from xauscalp.data.dukascopy import (
    RECORD,
    HoldoutAccessError,
    HttpResult,
    Throttle,
    cache_path,
    download_range,
    load_m1,
    validate_body,
    verify_cache,
)

ROOT = Path(__file__).parents[1]


def day_body(price=2000.0, n=30):
    rec = np.zeros(n, dtype=RECORD)
    rec["t"] = np.arange(n) * 60 + 8 * 3600
    rec["o"] = rec["c"] = rec["l"] = rec["h"] = int(price * 1000)
    rec["h"] += 100
    rec["l"] -= 100
    rec["v"] = 1.0
    return lzma.compress(rec.tobytes())


def write_day(cache, d, price=2000.0):
    for s in ("BID", "ASK"):
        p = cache_path(cache, "XAUUSD", d, s)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(day_body(price + (0.3 if s == "ASK" else 0)))


# ------------------------------------------------------------------ holdout
def test_load_m1_refuses_past_max_date_before_reading(tmp_path):
    with pytest.raises(HoldoutAccessError):
        load_m1("XAUUSD", date(2025, 10, 1), date(2025, 11, 3), tmp_path,
                max_date=date(2025, 10, 31))


def test_research_loader_never_decodes_holdout_files(tmp_path, monkeypatch):
    write_day(tmp_path, date(2025, 10, 30))
    write_day(tmp_path, date(2025, 10, 31))
    write_day(tmp_path, date(2025, 11, 3), price=9999)         # holdout file in the cache
    decoded = []
    real = dk.decode_day
    monkeypatch.setattr(dk, "decode_day", lambda raw, d, s: decoded.append(d) or real(raw, d, s))
    raw = yaml.safe_load((ROOT / "config/default.yaml").read_text())
    raw["data"].update(dir=str(tmp_path), start="2025-10-30", end="2026-10-31")
    cfgp = tmp_path / "c.yaml"
    cfgp.write_text(yaml.safe_dump(raw))
    from xauscalp.config import load_config
    from xauscalp.pipeline import load_research_data
    rd = load_research_data(load_config(cfgp))
    assert max(decoded) < date(2025, 11, 1)
    assert rd.m1.index.max().date() < date(2025, 11, 1)
    assert rd.requested_end == date(2025, 10, 31)


def test_every_load_m1_call_declares_max_date():
    """Static guard: research/ and src/ may not call load_m1 without max_date."""
    for f in list((ROOT / "src").rglob("*.py")) + list((ROOT / "research").rglob("*.py")):
        text = f.read_text()
        for m in re.finditer(r"load_m1\(", text):
            depth, i = 1, m.end()
            while depth and i < len(text):
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                i += 1
            call = text[m.end():i]
            if text[max(0, m.start() - 4):m.start()] == "def ":
                continue                   # the definition itself
            assert "max_date=" in call, f"{f}: load_m1 without max_date"


# ------------------------------------------------------------------ downloader
class FakeClock:
    def __init__(self):
        self.now, self.slept, self.cooldowns = 0.0, 0.0, []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept += s
        self.now += s


def make_throttle(fc, interval=1.0):
    th = Throttle(interval, clock=fc.clock, sleep=fc.sleep)
    real = th.cooldown

    def cd(s):
        fc.cooldowns.append(s)
        real(s)
    th.cooldown = cd
    return th


RANGE = (date(2025, 3, 3), date(2025, 3, 7))     # 5 weekdays -> 10 files


def test_retry_after_is_honoured_and_files_cached(tmp_path):
    fc, calls = FakeClock(), []

    def fetch(url):
        calls.append(url)
        return HttpResult(429, retry_after_s=42.0) if len(calls) == 1 else HttpResult(200, day_body())
    rep = download_range("XAUUSD", *RANGE, tmp_path, workers=1, fetch=fetch,
                         throttle=make_throttle(fc), verbose=False)
    assert 42.0 in fc.cooldowns and rep.rate_limited == 1
    assert rep.ok == 10 and rep.stopped_reason == "completed"


def test_circuit_breaker_stops_request_storm(tmp_path):
    fc, calls = FakeClock(), []

    def fetch(url):
        calls.append(url)
        return HttpResult(429)
    rep = download_range("XAUUSD", date(2025, 1, 1), date(2025, 12, 31), tmp_path, workers=1,
                         fetch=fetch, throttle=make_throttle(fc), max_consecutive_failures=5,
                         verbose=False)
    assert len(calls) <= 5 and "circuit breaker" in rep.stopped_reason
    assert fc.cooldowns[:3] == [60.0, 120.0, 240.0]          # exponential global pause
    assert not list(tmp_path.rglob("*.bi5"))                  # nothing bogus cached


def test_circuit_breaker_with_pending_jobs_does_not_raise_cancelled_error(tmp_path, monkeypatch):
    """Regression: when the breaker trips, the queued jobs are cancelled; reading a cancelled future's
    result raised CancelledError (found when a different test order exposed it). Deterministic here: the
    single worker is held inside job 2 while the main thread cancels everything still queued."""
    import time
    fc, fetched, urls = FakeClock(), [], []
    real_url = dk.day_url

    def slow_second_job(*a, **k):
        urls.append(1)
        if len(urls) == 2:
            time.sleep(0.5)                       # job 2 is running; jobs 3.. are queued and get cancelled
        return real_url(*a, **k)

    def fetch(url):
        fetched.append(url)
        return HttpResult(429)
    monkeypatch.setattr(dk, "day_url", slow_second_job)
    rep = download_range("XAUUSD", date(2025, 1, 1), date(2025, 1, 31), tmp_path, workers=1,
                         fetch=fetch, throttle=make_throttle(fc), max_consecutive_failures=1,
                         verbose=False)
    assert len(fetched) == 1 and "circuit breaker" in rep.stopped_reason
    assert rep.ok == 0 and rep.empty == 0


def test_request_budget_and_resume(tmp_path):
    fc = FakeClock()
    rep = download_range("XAUUSD", *RANGE, tmp_path, workers=1, max_requests=4,
                         fetch=lambda u: HttpResult(200, day_body()),
                         throttle=make_throttle(fc), verbose=False)
    assert rep.ok == 4 and "budget" in rep.stopped_reason
    seen = []
    rep2 = download_range("XAUUSD", *RANGE, tmp_path, workers=1,
                          fetch=lambda u: seen.append(u) or HttpResult(200, day_body()),
                          throttle=make_throttle(fc), verbose=False)
    assert rep2.requested == 6 and len(seen) == 6               # completed files not refetched


def test_invalid_body_never_cached_and_404_cached_empty(tmp_path):
    fc = FakeClock()
    bodies = iter([HttpResult(200, b"garbage")] * 3 + [HttpResult(404)] * 20)
    rep = download_range("XAUUSD", date(2025, 3, 3), date(2025, 3, 3), tmp_path, workers=1,
                         fetch=lambda u: next(bodies), throttle=make_throttle(fc),
                         verbose=False)
    files = sorted(tmp_path.rglob("*.bi5"))
    assert rep.failed == 1 and rep.empty == 1 and len(files) == 1
    assert files[0].read_bytes() == b""


def test_throttle_enforces_min_interval():
    fc = FakeClock()
    th = Throttle(2.0, clock=fc.clock, sleep=fc.sleep)
    for _ in range(4):
        th.wait()
    assert fc.slept == pytest.approx(6.0)


def test_validate_body_and_quarantine(tmp_path):
    assert validate_body(day_body()) is None and validate_body(b"") is None
    assert validate_body(b"xx") is not None
    bad = lzma.compress(b"\x00" * 25)
    assert validate_body(bad) is not None
    p = cache_path(tmp_path, "XAUUSD", date(2025, 3, 3), "BID")
    p.parent.mkdir(parents=True)
    p.write_bytes(bad)
    stats = verify_cache(tmp_path, "XAUUSD")
    assert stats["corrupt"] == 1 and not p.exists()
    assert list((tmp_path / "raw" / "quarantine").rglob("*.bi5"))


# ------------------------------------------------- broker exports (MT5 CSV) and the lockbox
def _m1_csv(path, rows):
    path.write_text("#server_minus_gmt_seconds_at_export,7200\n#point,0.01\n"
                    "time_server,open,high,low,close,tick_volume,spread_points\n"
                    + "".join(rows))


def test_m1_reader_never_parses_rows_past_the_research_window(tmp_path):
    from xauscalp.mt5_report import read_mt5_rates_raw
    p = tmp_path / "m1.csv"
    # the row after the limit is garbage: it would raise if it were parsed or kept
    _m1_csv(p, ["2025.10.31 10:00,1,2,0,1,5,20\n", "2025.10.31 20:59,1,2,0,1,5,20\n",
                "2025.11.02 23:00,GARBAGE,NOT,A,ROW\n", "2026.05.05 10:00,1,2,0,1,5,20\n"])
    df, _ = read_mt5_rates_raw(p, max_date=date(2025, 10, 31))
    assert len(df) == 2 and df.index.max() < pd.Timestamp("2025-11-02")


def test_tick_reader_stops_at_the_limit_and_rejects_unsorted_files(tmp_path):
    from xauscalp.data.sources import read_mt5_ticks_raw
    from xauscalp.mt5_report import UnsortedExportError
    ms = lambda s: int(pd.Timestamp(s).value // 10**6)
    p = tmp_path / "t.csv"
    head = "#point,0.01\ntime_msc_server,bid,ask,flags\n"
    p.write_text(head + f"{ms('2025-10-31 12:00')},1.0,1.2,134\n"
                 f"{ms('2025-11-03 00:00')},GARBAGE\n")
    df, _ = read_mt5_ticks_raw(p, max_date=date(2025, 10, 31))
    assert len(df) == 1
    p.write_text(head + f"{ms('2025-10-31 12:00')},1.0,1.2,134\n"
                 f"{ms('2025-10-30 12:00')},1.0,1.2,134\n")
    with pytest.raises(UnsortedExportError):
        read_mt5_ticks_raw(p, max_date=date(2025, 10, 31))


def test_every_broker_export_read_declares_max_date():
    """Static guard (like load_m1): the raw broker readers may not be called without it."""
    names = r"(read_mt5_rates_raw|read_mt5_ticks_raw|load_mt5_rates_csv)\("
    for f in list((ROOT / "src").rglob("*.py")) + list((ROOT / "research").rglob("*.py")):
        text = f.read_text()
        for m in re.finditer(names, text):
            if text[max(0, m.start() - 4):m.start()] == "def " or "def " in text[
                    max(0, m.start() - 12):m.start()]:
                continue
            depth, i = 1, m.end()
            while depth and i < len(text):
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                i += 1
            assert "max_date=" in text[m.end():i], f"{f}: {m.group(1)} without max_date"
