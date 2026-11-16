"""Official macro-event calendar (FOMC, CPI, Employment Situation) -> config/events.csv.

Every date below was read on 2026-11-14 from an OFFICIAL page and is NOT invented:
  FOMC  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  (2021-2027)
  CPI   https://www.bls.gov/schedule/<year>/home.htm (2021-2026) and
        https://www.bls.gov/schedule/news_release/cpi.htm (Nov-2026 .. Dec-2027)
  NFP   same pages, "Employment Situation"
CAVEATS (kept visible on purpose):
  * The pages were read through a summarising fetch tool, not parsed from raw HTML. The
    structural checks in `validate()` (12 releases a year, working days, cross-check of the
    two BLS pages for Nov/Dec-2026) catch typos but cannot prove every date: the user must
    spot-check against the official pages before trusting the calendar for DEMO trading.
  * 2025: the BLS page lists NO CPI for Oct-2025 data and NO Employment Situation for
    Oct-2025 data (government shutdown); Sept-2025 CPI/NFP appear on 24-Oct and 20-Nov.
  * 2027 FOMC dates are "tentative until confirmed" per the Fed page.
  * Only these three event families are covered (the template's scope). Other high-impact
    releases (PPI, PCE, GDP, retail sales, ISM, claims, central-bank speeches, unscheduled
    FOMC notation votes such as 2025-08-22) are NOT in the file: the spread/volatility gates
    remain the protection for them.
Times: BLS 08:30 America/New_York; FOMC statement 14:00 America/New_York on the 2nd day.
The FOMC press conference (usually 14:30 ET) is inside the default 30-min after-window.

    uv run python -m xauscalp.calendar.official write [--install]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
RETRIEVED = "2026-11-14"

# FOMC: statement day (second day of each two-day meeting).
FOMC_STATEMENT_DAYS = [
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22",
    "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21",
    "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20",
    "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18",
    "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17",
    "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
    "2026-10-28", "2026-12-09",
]
FOMC_TENTATIVE_2027 = ["2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28",
                       "2027-09-15", "2027-10-27", "2027-11-17"]

CPI = {
    2021: ["01-13", "02-10", "03-10", "04-13", "05-12", "06-10", "07-13", "08-11", "09-14",
           "10-13", "11-10", "12-10"],
    2022: ["01-12", "02-10", "03-10", "04-12", "05-11", "06-10", "07-13", "08-10", "09-13",
           "10-13", "11-10", "12-13"],
    2023: ["01-12", "02-14", "03-14", "04-12", "05-10", "06-13", "07-12", "08-10", "09-13",
           "10-12", "11-14", "12-12"],
    2024: ["01-11", "02-13", "03-12", "04-10", "05-15", "06-12", "07-11", "08-14", "09-11",
           "10-10", "11-13", "12-11"],
    2025: ["01-15", "02-12", "03-12", "04-10", "05-13", "06-11", "07-15", "08-12", "09-11",
           "10-24", "12-18"],                       # no Oct-2025 data release (see caveats)
    2026: ["01-13", "02-13", "03-11", "04-10", "05-12", "06-10", "07-14", "08-12", "09-11",
           "10-14", "11-10", "12-10"],
    2027: ["01-13", "02-11", "03-10", "04-13", "05-12", "06-10", "07-14", "08-11", "09-14",
           "10-14", "11-10", "12-10"],
}
NFP = {
    2021: ["01-08", "02-05", "03-05", "04-02", "05-07", "06-04", "07-02", "08-06", "09-03",
           "10-08", "11-05", "12-03"],
    2022: ["01-07", "02-04", "03-04", "04-01", "05-06", "06-03", "07-08", "08-05", "09-02",
           "10-07", "11-04", "12-02"],
    2023: ["01-06", "02-03", "03-10", "04-07", "05-05", "06-02", "07-07", "08-04", "09-01",
           "10-06", "11-03", "12-08"],
    2024: ["01-05", "02-02", "03-08", "04-05", "05-03", "06-07", "07-05", "08-02", "09-06",
           "10-04", "11-01", "12-06"],
    2025: ["01-10", "02-07", "03-07", "04-04", "05-02", "06-06", "07-03", "08-01", "09-05",
           "11-20", "12-16"],                       # no Oct-2025 data release (see caveats)
    2026: ["01-09", "02-11", "03-06", "04-03", "05-08", "06-05", "07-02", "08-07", "09-04",
           "10-02", "11-06", "12-04"],
    2027: ["01-08", "02-05", "03-05", "04-02", "05-07", "06-04", "07-02", "08-06", "09-03",
           "10-08", "11-05", "12-03"],
}
EXPECTED_SHORT_YEARS = {2025: 11}                    # documented gap, not a typo


def _utc(day: str, hh: int, mm: int) -> pd.Timestamp:
    d = date.fromisoformat(day)
    loc = datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY)
    return pd.Timestamp(loc).tz_convert("UTC")


def build_events() -> pd.DataFrame:
    rows: list[tuple[pd.Timestamp, str, str]] = []
    for d in FOMC_STATEMENT_DAYS:
        rows.append((_utc(d, 14, 0), "FOMC statement", "high"))
    for d in FOMC_TENTATIVE_2027:
        rows.append((_utc(d, 14, 0), "FOMC statement (tentative)", "high"))
    for y, ds in CPI.items():
        rows += [(_utc(f"{y}-{md}", 8, 30), "CPI", "high") for md in ds]
    for y, ds in NFP.items():
        rows += [(_utc(f"{y}-{md}", 8, 30), "Employment Situation (NFP)", "high") for md in ds]
    df = pd.DataFrame(rows, columns=["utc_time", "event", "impact"])
    return df.sort_values("utc_time").reset_index(drop=True)


def validate(df: pd.DataFrame) -> list[str]:
    """Structural problems (empty list = none). These catch typos, not every wrong date."""
    bad: list[str] = []
    if df["utc_time"].duplicated().any():
        bad.append("duplicate timestamps")
    ny = df["utc_time"].dt.tz_convert(NY)
    if (ny.dt.day_of_week >= 5).any():
        bad.append("event on a weekend")
    for name, tab in (("CPI", CPI), ("NFP", NFP)):
        for y, ds in tab.items():
            want = EXPECTED_SHORT_YEARS.get(y, 12)
            if len(ds) != want or sorted(ds) != ds or len(set(ds)) != len(ds):
                bad.append(f"{name} {y}: {len(ds)} releases (expected {want}) or unsorted")
    fomc = {y: sum(1 for d in FOMC_STATEMENT_DAYS if d.startswith(str(y))) for y in range(2021, 2027)}
    if any(n != 8 for n in fomc.values()):
        bad.append(f"FOMC scheduled meetings per year != 8: {fomc}")
    # ET->UTC must follow DST: 08:30 ET is 12:30Z in summer and 13:30Z in winter.
    for ts, ev in zip(df["utc_time"], df["event"], strict=True):
        if ev.startswith(("CPI", "Employment")):
            expect = 12 if ts.tz_convert(NY).utcoffset().total_seconds() == -4 * 3600 else 13
            if ts.hour != expect or ts.minute != 30:
                bad.append(f"{ev} {ts}: ET->UTC conversion inconsistent")
    return bad


def to_csv_text(df: pd.DataFrame) -> str:
    head = ("# High-impact USD events (blackout). UTC. GENERATED by xauscalp.calendar.official\n"
            f"# from the OFFICIAL Fed / BLS pages read on {RETRIEVED}. See that module's caveats:\n"
            "# FOMC+CPI+NFP only; spot-check against the official pages before DEMO use.\n"
            "utc_time,event,impact\n")
    body = "".join(f"{t.strftime('%Y-%m-%dT%H:%M:%SZ')},{e},{i}\n"
                   for t, e, i in zip(df["utc_time"], df["event"], df["impact"], strict=True))
    return head + body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("action", choices=["write"])
    ap.add_argument("--out", default="config/events.csv")
    ap.add_argument("--install", action="store_true",
                    help="also copy to MT5 Common/Files/xauscalp/events.csv (what the EA reads)")
    a = ap.parse_args(argv)
    df = build_events()
    problems = validate(df)
    if problems:
        print("VALIDATION FAILED:", *problems, sep="\n  ")
        return 1
    Path(a.out).write_text(to_csv_text(df))
    print(f"wrote {a.out}: {len(df)} events {df.utc_time.min():%Y-%m-%d}..{df.utc_time.max():%Y-%m-%d}")
    if a.install:
        import os

        from xauscalp.mt5_build import DEFAULT_PREFIX, common_files
        dst = common_files(Path(os.environ.get("XAU_MT5_PREFIX", DEFAULT_PREFIX))) / "xauscalp" / "events.csv"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(to_csv_text(df))
        print("installed", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
