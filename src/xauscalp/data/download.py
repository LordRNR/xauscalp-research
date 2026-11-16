"""CLI: polite, resumable, bounded download of research data.

    uv run python -m xauscalp.data.download                 # research period only
    uv run python -m xauscalp.data.download --max-requests 600
    uv run python -m xauscalp.data.download --include-holdout   # cache only, still locked

Dukascopy rate-limits aggressively (HTTP 429 / dropped connections). The run stops by
itself (circuit breaker / request budget) instead of hammering the server; just re-run
later. Cached files are verified first and never fetched twice.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from xauscalp.config import ROOT, load_config
from xauscalp.data.dukascopy import download_range, verify_cache


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default=cfg.data["symbol"])
    ap.add_argument("--start", default=str(cfg.data["start"]))
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-requests", type=int, default=1500)
    ap.add_argument("--min-interval", type=float, default=1.5)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--include-holdout", action="store_true",
                    help="also cache holdout-period files (research code still cannot read them)")
    a = ap.parse_args(argv)
    cache = ROOT / cfg.data.get("dir", "data")
    hold = date.fromisoformat(str(cfg.validation["holdout_start"]))
    end = date.fromisoformat(a.end) if a.end else date.fromisoformat(str(cfg.data["end"]))
    if not a.include_holdout:
        end = min(end, hold - timedelta(days=1))
    print("verify cache:", verify_cache(cache, a.symbol))
    rep = download_range(a.symbol, date.fromisoformat(a.start), end, cache,
                         workers=a.workers, min_interval_s=a.min_interval,
                         max_requests=a.max_requests)
    print(f"{a.symbol}: {rep}")
    return 0 if rep.stopped_reason in ("completed", "nothing to do") else 3


if __name__ == "__main__":
    raise SystemExit(main())
