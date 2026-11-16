"""Free historical M1 bid/ask candles from Dukascopy's public datafeed.

File format (verified 2026-11-12 by decoding live files, see docs/decisiones.md):
  URL   {BASE}/{SYMBOL}/{YYYY}/{MM0}/{DD}/{BID|ASK}_candles_min_1.bi5   (MM0 = month - 1)
  body  LZMA-compressed, 24-byte big-endian records:
        int32 seconds since UTC midnight, int32 open, close, low, high (price * scale),
        float32 volume.
  Closed-market minutes are served as flat "filler" candles with volume 0; we drop them.
Timezone: UTC (Dukascopy documents GMT; consistent with the session structure observed).

Dukascopy quotes are NOT your broker's quotes. Spreads are usually tighter than a retail
CFD broker, which is why the cost model adds a configurable extra spread on top.

Download etiquette (the free service rate-limits with HTTP 429 / dropped connections):
  * one global throttle shared by all workers (min interval between requests);
  * HTTP 429 honours Retry-After, otherwise an exponential GLOBAL cooldown;
  * circuit breaker: after N consecutive failures the run stops (no request storms);
  * a per-run request budget; bounded retries per file;
  * every body is validated (LZMA + record layout) before an atomic write;
  * Ctrl-C / SIGTERM stops gracefully; completed files are never fetched again.
"""

from __future__ import annotations

import email.utils
import lzma
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
PRICE_SCALE = {"XAUUSD": 1000.0, "XAGUSD": 1000.0, "EURUSD": 100000.0}
SIDES = ("BID", "ASK")
RECORD = np.dtype(
    [("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")]
)
# Generic client name on purpose: no personal data is ever sent to external services.
USER_AGENT = "Mozilla/5.0 (compatible; research-downloader)"


class HoldoutAccessError(RuntimeError):
    """Raised when research code tries to load data past its allowed date."""


# --------------------------------------------------------------------------- paths
def day_url(symbol: str, day: date, side: str) -> str:
    return (
        f"{BASE_URL}/{symbol}/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/"
        f"{side}_candles_min_1.bi5"
    )


def cache_path(cache_dir: Path, symbol: str, day: date, side: str) -> Path:
    return (
        Path(cache_dir) / "raw" / "dukascopy" / symbol / f"{day:%Y}" / f"{day:%m}"
        / f"{day:%d}_{side}.bi5"
    )


def trading_days(start: date, end: date) -> list[date]:
    """Calendar days in [start, end] except Saturdays (gold CFD market is closed)."""
    out, d = [], start
    while d <= end:
        if d.weekday() != 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# --------------------------------------------------------------------------- validation
def validate_body(body: bytes) -> str | None:
    """None if `body` is a valid day file (or empty = no data), else a problem string."""
    if not body:
        return None
    try:
        raw = lzma.decompress(body)
    except (lzma.LZMAError, EOFError) as exc:
        return f"lzma: {exc}"
    if len(raw) % RECORD.itemsize:
        return f"length {len(raw)} not a multiple of {RECORD.itemsize}"
    rec = np.frombuffer(raw, dtype=RECORD)
    if len(rec) > 1440:
        return f"{len(rec)} records > 1440 minutes"
    t = rec["t"].astype(np.int64)
    if len(t) and (t.min() < 0 or t.max() >= 86400 or (np.diff(t) <= 0).any()):
        return "timestamps out of range or not increasing"
    return None


def verify_cache(cache_dir: Path, symbol: str, quarantine: bool = True) -> dict[str, int]:
    """Check every cached file; move corrupt ones to a quarantine folder (re-downloadable)."""
    root = Path(cache_dir) / "raw" / "dukascopy" / symbol
    stats = {"files": 0, "empty": 0, "corrupt": 0}
    for p in sorted(root.rglob("*.bi5")):
        stats["files"] += 1
        body = p.read_bytes()
        stats["empty"] += not body
        if validate_body(body):
            stats["corrupt"] += 1
            if quarantine:
                q = Path(cache_dir) / "raw" / "quarantine" / p.relative_to(root.parent)
                q.parent.mkdir(parents=True, exist_ok=True)
                p.replace(q)
    for tmp in root.rglob("*.tmp"):
        tmp.unlink()
    return stats


# --------------------------------------------------------------------------- HTTP
@dataclass
class HttpResult:
    status: int
    body: bytes = b""
    retry_after_s: float | None = None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    if value.strip().isdigit():
        return float(value.strip())
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return max(0.0, (dt - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def http_get(url: str, timeout: float = 30.0) -> HttpResult:
    """Real network fetch. Network errors are reported as status 0."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResult(resp.status, resp.read())
    except urllib.error.HTTPError as exc:
        return HttpResult(exc.code, b"", _parse_retry_after(exc.headers.get("Retry-After")))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return HttpResult(0)


class Throttle:
    """Global politeness: min interval between requests + shared cooldown after 429s."""

    def __init__(self, min_interval_s: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval = min_interval_s
        self.clock, self.sleep = clock, sleep
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            if self._next_at > now:
                self.sleep(self._next_at - now)
                now = self.clock()
            self._next_at = now + self.min_interval

    def cooldown(self, seconds: float) -> None:
        with self._lock:
            self._next_at = max(self._next_at, self.clock() + seconds)


@dataclass
class DownloadReport:
    requested: int = 0
    ok: int = 0
    empty: int = 0
    failed: int = 0
    requests_sent: int = 0
    rate_limited: int = 0
    stopped_reason: str = ""
    failures: list[str] = field(default_factory=list)


def download_range(
    symbol: str, start: date, end: date, cache_dir: Path, *,
    workers: int = 2, min_interval_s: float = 1.0, max_retries_per_file: int = 3,
    max_consecutive_failures: int = 6, max_requests: int = 3000,
    base_cooldown_s: float = 60.0, max_cooldown_s: float = 900.0,
    fetch: Callable[[str], HttpResult] = http_get,
    throttle: Throttle | None = None, verbose: bool = True,
) -> DownloadReport:
    """Download missing day files into the cache. Idempotent, resumable, polite."""
    today = datetime.now(UTC).date()
    end = min(end, today - timedelta(days=1))  # never cache a partial day
    tasks = [(d, s) for d in trading_days(start, end) for s in SIDES
             if not cache_path(cache_dir, symbol, d, s).exists()]
    rep = DownloadReport(requested=len(tasks))
    if not tasks:
        rep.stopped_reason = "nothing to do"
        return rep
    throttle = throttle or Throttle(min_interval_s)
    stop = threading.Event()
    lock = threading.Lock()
    state = {"consecutive_failures": 0, "consecutive_429": 0}

    def on_signal(signum, _frame):
        rep.stopped_reason = f"signal {signum}: stopped after in-flight requests"
        stop.set()

    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, on_signal)

    def record_failure(kind: str) -> None:
        with lock:
            state["consecutive_failures"] += 1
            if state["consecutive_failures"] >= max_consecutive_failures:
                rep.stopped_reason = (f"circuit breaker: {state['consecutive_failures']} "
                                      f"consecutive failures (last: {kind}). Provider is "
                                      "limiting access; resume later.")
                stop.set()

    def job(d: date, s: str) -> str:
        url = day_url(symbol, d, s)
        for attempt in range(max_retries_per_file):
            if stop.is_set():
                return "skipped"
            with lock:
                if rep.requests_sent >= max_requests:
                    rep.stopped_reason = f"request budget of {max_requests} reached"
                    stop.set()
                    return "skipped"
                rep.requests_sent += 1
            throttle.wait()
            r = fetch(url)
            if r.status == 429:
                with lock:
                    rep.rate_limited += 1
                    state["consecutive_429"] += 1
                    k = state["consecutive_429"]
                wait = r.retry_after_s if r.retry_after_s is not None else min(
                    max_cooldown_s, base_cooldown_s * 2 ** (k - 1))
                throttle.cooldown(wait)
                if verbose:
                    print(f"  429 rate-limited: global pause {wait:.0f}s", file=sys.stderr,
                          flush=True)
                record_failure("429")
                continue
            if r.status in (200, 404):
                body = r.body if r.status == 200 else b""
                if (problem := validate_body(body)) is not None:
                    record_failure(f"invalid body ({problem})")
                    continue
                p = cache_path(cache_dir, symbol, d, s)
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_bytes(body)
                tmp.replace(p)
                with lock:
                    state["consecutive_failures"] = 0
                    state["consecutive_429"] = 0
                return "ok" if body else "empty"
            record_failure(f"HTTP {r.status or 'network error'}")
            throttle.cooldown(min(max_cooldown_s, 5.0 * 2 ** attempt))
        return "failed"

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(job, d, s): (d, s) for d, s in tasks}
            for i, fut in enumerate(as_completed(futures), 1):
                if fut.cancelled():       # cancelled after the stop flag was set: nothing to record
                    continue
                res = fut.result()
                if res in ("ok", "empty"):
                    setattr(rep, res, getattr(rep, res) + 1)
                elif res == "failed":
                    rep.failed += 1
                    rep.failures.append(str(futures[fut]))
                if stop.is_set():
                    for f in futures:
                        f.cancel()
                if verbose and i % 100 == 0:
                    print(f"  {i}/{len(tasks)} done", file=sys.stderr, flush=True)
    finally:
        for sig, h in old_handlers.items():
            signal.signal(sig, h)
    if not rep.stopped_reason:
        rep.stopped_reason = "completed"
    return rep


# --------------------------------------------------------------------------- decoding
def decode_day(raw: bytes, day: date, scale: float) -> pd.DataFrame:
    """Decode one day file into a DataFrame indexed by bar-open time (UTC)."""
    cols = ["o", "h", "l", "c", "v"]
    if not raw:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    rec = np.frombuffer(lzma.decompress(raw), dtype=RECORD)
    idx = pd.Timestamp(day, tz="UTC") + pd.to_timedelta(rec["t"].astype(np.int64), unit="s")
    return pd.DataFrame(
        {
            "o": rec["o"] / scale,
            "h": rec["h"] / scale,
            "l": rec["l"] / scale,
            "c": rec["c"] / scale,
            "v": rec["v"].astype(np.float64),
        },
        index=pd.DatetimeIndex(idx, name="time"),
    )


def load_m1(symbol: str, start: date, end: date, cache_dir: Path, *,
            max_date: date | None) -> pd.DataFrame:
    """Load cached M1 bars. Columns: bid_o..bid_c, ask_o..ask_c, volume.

    `max_date` is REQUIRED (keyword) so every caller states the latest date it may read:
    research code passes the day before the holdout. Requesting a later `end` raises
    HoldoutAccessError before any file is decoded. Pass max_date=None only in the logged,
    user-authorised holdout evaluation path.
    Drops filler bars (zero volume) and keeps only minutes present on both sides.
    """
    if max_date is not None and end > max_date:
        raise HoldoutAccessError(f"{symbol}: requested end {end} > allowed {max_date}")
    scale = PRICE_SCALE[symbol]
    frames = []
    for d in trading_days(start, end):
        sides = {}
        for s in SIDES:
            p = cache_path(cache_dir, symbol, d, s)
            if not p.exists():
                continue
            df = decode_day(p.read_bytes(), d, scale)
            sides[s] = df[df["v"] > 0]
        if len(sides) != 2 or sides["BID"].empty or sides["ASK"].empty:
            continue
        b = sides["BID"].add_prefix("bid_")
        a = sides["ASK"].add_prefix("ask_")
        j = b.join(a, how="inner")
        j["volume"] = j.pop("bid_v")
        j = j.drop(columns="ask_v")
        frames.append(j)
    if not frames:
        raise FileNotFoundError(f"no cached data for {symbol} {start}..{end}; run download first")
    out = pd.concat(frames).sort_index()
    out.index = out.index.as_unit("ns")
    return out[["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]]
