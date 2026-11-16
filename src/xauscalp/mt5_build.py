"""Sync the repo's MQL5 sources into the local MT5 data folder and compile them with
MetaEditor's command line (macOS: MetaTrader 5.app ships its own Wine).

This tool only COPIES source files and COMPILES them. It never starts the terminal, never
attaches an EA to a chart and never sends orders. Before copying, the read-only files are
scanned for trading calls and the sync is refused if any is found.

    uv run python -m xauscalp.mt5_build sync            # copy mt5/ -> <MT5>/MQL5 (no deletes)
    uv run python -m xauscalp.mt5_build compile         # compile the 4 programs, write logs
    uv run python -m xauscalp.mt5_build all             # sync + compile
    uv run python -m xauscalp.mt5_build preset --tz base_dst:120:America/New_York
                                    # EA inputs for the Strategy Tester, FROM config/default.yaml
    uv run python -m xauscalp.mt5_build fetch           # copy exports Common/Files -> data/mt5

Locations (override with env vars when your install differs):
    XAU_MT5_PREFIX  Wine prefix   (default ~/Library/Application Support/net.metaquotes.wine.metatrader5)
    XAU_MT5_WINE    wine binary   (default /Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine)
Logs: reports/mt5_build/<program>.log + reports/mt5_build/SUMMARY.md
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from xauscalp.mql5_scan import violations

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "mt5"
OUT = REPO / "reports" / "mt5_build"
DEFAULT_PREFIX = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5"
DEFAULT_WINE = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine")
TERMINAL_REL = Path("drive_c/Program Files/MetaTrader 5")
COMMON_GLOB = "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
DATA_MT5 = REPO / "data" / "mt5"
FETCH_PATTERNS = ["xau_feasibility.csv", "*_M1_*.csv", "*_ticks_*.csv",
                  "xauscalp/decisions_*.csv", "xauscalp/state_*.json",
                  "xauscalp/exec_*.csv", "xauscalp/symbol_specs_*.csv"]
PRESET_NAME = "XauScalp_ReadOnly_parity.set"
TZ_ENUM = {"TZ_UNKNOWN": 0, "TZ_LIVE_CLOCK": 1, "TZ_FIXED": 2, "TZ_BASE_PLUS_US_DST": 3,
           "TZ_BASE_PLUS_EU_DST": 4}

PROGRAMS = ["Scripts/XAU_FeasibilityReport.mq5", "Scripts/XAU_ExportHistory.mq5",
            "Scripts/XAU_ExportTicks.mq5", "Scripts/XAU_SymbolSpecs.mq5",
            "Experts/XauScalp_ReadOnly.mq5"]
EXEC_PROGRAMS = ["Experts/XauScalp_Exec.mq5"]
INCLUDES = "Include/XauScalp"

RESULT_RE = re.compile(r"Result:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?")
DIAG_RE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*"
                     r"(?P<kind>error|warning)\s+(?P<code>\d+):\s*(?P<msg>.*)$")


def source_files(with_exec: bool = False) -> list[Path]:
    """Repo-relative MQL5 files this project owns (unique names: nothing else is touched).

    Execution-capable files (mql5_scan.EXEC_ALLOWED) are included ONLY with with_exec=True
    (CLI --with-exec); the default build never copies them."""
    files = [Path(p) for p in PROGRAMS] + sorted(
        p.relative_to(SRC) for p in (SRC / INCLUDES).glob("*.mqh")
        if with_exec or not p.name.startswith("Exec"))
    if with_exec:
        files += [Path(p) for p in EXEC_PROGRAMS if (SRC / p).exists()]
    return files


def trading_call_violations(with_exec: bool = False) -> list[str]:
    return violations(source_files(with_exec), SRC)


def terminal_dir(prefix: Path | None = None) -> Path:
    prefix = prefix or Path(os.environ.get("XAU_MT5_PREFIX", DEFAULT_PREFIX))
    d = prefix / TERMINAL_REL
    if not (d / "metaeditor64.exe").exists():
        raise FileNotFoundError(f"metaeditor64.exe not found under {d} (set XAU_MT5_PREFIX)")
    return d


def sync(term: Path, with_exec: bool = False) -> list[tuple[str, str]]:
    """Copy repo sources into <term>/MQL5. Returns [(rel, NEW|UPDATED|SAME)]. Never deletes."""
    bad = trading_call_violations(with_exec)
    if bad:
        raise RuntimeError(f"refusing to sync: trading calls found in {bad}")
    out = []
    for rel in source_files(with_exec):
        src, dst = SRC / rel, term / "MQL5" / rel
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            out.append((str(rel), "SAME"))
            continue
        state = "UPDATED" if dst.exists() else "NEW"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        out.append((str(rel), state))
    return out


@dataclass
class CompileResult:
    program: str
    errors: int | None
    warnings: int | None
    diagnostics: list[dict] = field(default_factory=list)
    ex5_written: bool = False

    @property
    def ok(self) -> bool:
        return self.errors == 0 and self.ex5_written


def decode_log(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or raw[1:2] == b"\x00":
        return raw.decode("utf-16").replace("\r", "")
    return raw.decode("utf-8", errors="replace").replace("\r", "")


def parse_log(program: str, text: str) -> CompileResult:
    m = RESULT_RE.search(text)
    diags = [d.groupdict() for line in text.splitlines() if (d := DIAG_RE.match(line.strip()))]
    return CompileResult(program, int(m.group(1)) if m else None,
                         int(m.group(2)) if m else None, diags)


def compile_one(term: Path, program: str, wine: Path, prefix: Path,
                timeout_s: int = 180) -> tuple[CompileResult, str]:
    rel_win = "MQL5\\" + program.replace("/", "\\")
    src = term / "MQL5" / program
    log = src.with_suffix(".log")
    ex5 = src.with_suffix(".ex5")
    log.unlink(missing_ok=True)
    before = ex5.stat().st_mtime if ex5.exists() else None
    env = {**os.environ, "WINEPREFIX": str(prefix), "WINEDEBUG": "-all"}
    subprocess.run([str(wine), "metaeditor64.exe", "/portable", f"/compile:{rel_win}", "/log"],
                   cwd=term, env=env, timeout=timeout_s, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not log.exists():
        return CompileResult(program, None, None), ""
    text = decode_log(log.read_bytes())
    res = parse_log(program, text)
    res.ex5_written = ex5.exists() and (before is None or ex5.stat().st_mtime > before)
    return res, text


def write_summary(results: list[CompileResult]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# MQL5 compile summary ({now})", "",
             ("Compiled with MetaEditor's command line (`xauscalp.mt5_build`) inside the "
             "MetaTrader 5 for macOS Wine prefix. Compiling proves syntax and types only: it "
             "says nothing about runtime behaviour (that needs the Strategy Tester)."), "",
             "| Program | Errors | Warnings | .ex5 written | Verdict |", "|---|---|---|---|---|"]
    for r in results:
        verdict = "COMPILED" if r.ok else ("NO LOG" if r.errors is None else "FAILED")
        lines.append(f"| `{r.program}` | {r.errors} | {r.warnings} | {r.ex5_written} | {verdict} |")
    lines += ["", "## Diagnostics", ""]
    for r in results:
        for d in r.diagnostics:
            lines.append(f"- `{Path(d['file']).name}:{d['line']}` {d['kind']} {d['code']}: "
                         f"{d['msg']}")
    if not any(r.diagnostics for r in results):
        lines.append("None.")
    p = OUT / "SUMMARY.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def tz_spec_to_ea(spec: str) -> tuple[int, int]:
    """--tz spec (as used by xauscalp.parity) -> (InpTzPolicy enum value, InpTzBaseMinutes)."""
    kind, *rest = spec.split(":")
    if kind == "fixed" and len(rest) == 1:
        return TZ_ENUM["TZ_FIXED"], int(rest[0])
    if kind == "base_dst" and len(rest) == 2:
        zone = {"America/New_York": "TZ_BASE_PLUS_US_DST",
                "Europe/London": "TZ_BASE_PLUS_EU_DST"}.get(rest[1])
        if zone:
            return TZ_ENUM[zone], int(rest[0])
    raise ValueError(f"tz spec {spec!r} has no EA equivalent "
                     "(use fixed:<min> or base_dst:<min>:America/New_York|Europe/London)")


def ea_inputs(cfg, tz_spec: str, *, or_minutes: int = 15, sl_atr: float = 1.5,
              tp_r: float = 1.5, log_tag: str = "parity") -> dict[str, str]:
    """EA inputs derived from config/default.yaml, so the tester runs EXACTLY the rules
    Python runs. ORB grid point defaults = xauscalp.parity CLI defaults."""
    sc, r, c = cfg.strategy["orb"], cfg.risk, cfg.costs
    for name, v, grid in (("or_minutes", or_minutes, sc["grid"]["or_minutes"]),
                          ("sl_atr", sl_atr, sc["grid"]["sl_atr"]),
                          ("tp_r", tp_r, sc["grid"]["tp_r"])):
        if v not in grid:
            raise ValueError(f"{name}={v} is not in the pre-registered grid {grid}")
    pol, base = tz_spec_to_ea(tz_spec)
    vals = {
        "InpSymbol": "", "InpTzPolicy": pol, "InpTzBaseMinutes": base, "InpLogTag": log_tag,
        "InpLondonOpen": sc["sessions"]["london"]["open"],
        "InpComexOpen": sc["sessions"]["newyork"]["open"],
        "InpOrMinutes": or_minutes, "InpSlAtr": sl_atr, "InpTpR": tp_r,
        "InpEntryWindow": sc["entry_window_min"], "InpMaxHoldMin": sc["max_hold_min"],
        "InpBufferAtr": sc["buffer_atr"], "InpMaxCostFrac": sc["max_cost_frac"],
        "InpExtraSpread": 0.0, "InpCostSlippage": c.slippage_usd,
        "InpRiskPct": r.risk_per_trade_pct, "InpDailyLossPct": r.daily_loss_limit_pct,
        "InpWeeklyLossPct": r.weekly_loss_limit_pct, "InpMaxDdPct": r.max_drawdown_pct,
        "InpMaxTradesDay": r.max_trades_per_day, "InpMaxSpread": r.max_spread_usd,
        "InpMaxDataAgeS": r.max_data_age_s, "InpMaxConsecErr": r.max_consecutive_errors,
        "InpSlippage": r.expected_slippage_usd, "InpCommissionLot": r.commission_per_lot,
        "InpMaxMarginPct": r.max_margin_usage_pct,
    }
    return {k: (f"{v:g}" if isinstance(v, float) else str(v)) for k, v in vals.items()}


PRESET_DIRS = ("MQL5/Presets", "MQL5/Profiles/Tester")   # EA dialog / Strategy Tester dialog


def write_preset(term: Path, values: dict[str, str]) -> list[Path]:
    """MT5 .set preset (UTF-16LE with BOM, CRLF, name=value), loadable from the tester's
    Inputs tab (right click > Load). Only this project's preset NAME is ever written, into
    both folders the Load dialogs may open."""
    body = "".join(f"{k}={v}\r\n" for k, v in values.items())
    out = []
    for rel in PRESET_DIRS:
        dst = term / rel / PRESET_NAME
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))
        out.append(dst)
    return out


def common_files(prefix: Path) -> Path:
    hits = sorted(prefix.glob(COMMON_GLOB))
    if not hits:
        raise FileNotFoundError(f"MT5 Common/Files not found under {prefix}")
    return hits[0]


def fetch(prefix: Path, dest: Path = DATA_MT5) -> list[tuple[str, str]]:
    """Copy MT5 exports (Common/Files) into data/mt5 (git-ignored). Never deletes.
    Tester agents' own Files folders are searched too (-> data/mt5/agents/<agent>/...)."""
    src_root = common_files(prefix)
    found = [(f, f.relative_to(src_root)) for pat in FETCH_PATTERNS
             for f in sorted(src_root.glob(pat))]
    for agent in sorted((prefix / TERMINAL_REL / "Tester").glob("Agent-*/MQL5/Files")):
        name = agent.parents[1].name
        found += [(f, Path("agents") / name / f.relative_to(agent))
                  for f in sorted(agent.glob("xauscalp/decisions_*.csv"))]
    out = []
    for f, rel in found:
        d = dest / rel
        if d.exists() and d.stat().st_size == f.stat().st_size and \
                d.read_bytes() == f.read_bytes():
            out.append((str(rel), "SAME"))
            continue
        state = "UPDATED" if d.exists() else "NEW"
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, d)
        out.append((str(rel), state))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["sync", "compile", "all", "preset", "fetch"])
    ap.add_argument("programs", nargs="*", help=f"subset of {PROGRAMS}")
    ap.add_argument("--tz", help="preset: verified server rule, e.g. base_dst:120:America/New_York")
    ap.add_argument("--or-minutes", type=int, default=15)
    ap.add_argument("--sl-atr", type=float, default=1.5)
    ap.add_argument("--tp-r", type=float, default=1.5)
    ap.add_argument("--log-tag", default="parity")
    ap.add_argument("--with-exec", action="store_true",
                    help="also copy/compile the DEMO execution EA (disabled by default in code; "
                         "compiling never sends orders, the user attaches it)")
    a = ap.parse_args(argv)
    prefix = Path(os.environ.get("XAU_MT5_PREFIX", DEFAULT_PREFIX))
    wine = Path(os.environ.get("XAU_MT5_WINE", DEFAULT_WINE))
    if a.action == "fetch":
        for rel, state in fetch(prefix):
            print(f"{state:8s} data/mt5/{rel}")
        return 0
    term = terminal_dir(prefix)
    if a.action == "preset":
        if not a.tz:
            ap.error("preset needs --tz (the rule VERIFIED by research/04_verify_server_tz.py)")
        from xauscalp.config import load_config
        vals = ea_inputs(load_config(), a.tz, or_minutes=a.or_minutes, sl_atr=a.sl_atr,
                         tp_r=a.tp_r, log_tag=a.log_tag)
        for f in write_preset(term, vals):
            print("wrote", f)
        for k, v in vals.items():
            print(f"  {k} = {v}")
        return 0
    if a.action in ("sync", "all"):
        for rel, state in sync(term, a.with_exec):
            print(f"{state:8s} {rel}")
    if a.action in ("compile", "all"):
        if not wine.exists():
            raise FileNotFoundError(f"wine not found: {wine} (set XAU_MT5_WINE)")
        OUT.mkdir(parents=True, exist_ok=True)
        results = []
        for prog in a.programs or (PROGRAMS + (EXEC_PROGRAMS if a.with_exec else [])):
            res, text = compile_one(term, prog, wine, prefix)
            if text:
                (OUT / (Path(prog).stem + ".log")).write_text(
                    "\n".join(ln for ln in text.splitlines() if "generating code" not in ln)
                    + "\n", encoding="utf-8")
            results.append(res)
            print(f"{prog:40s} errors={res.errors} warnings={res.warnings} "
                  f"ex5={res.ex5_written}")
        print("summary:", write_summary(results))
        return 0 if all(r.ok for r in results) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
