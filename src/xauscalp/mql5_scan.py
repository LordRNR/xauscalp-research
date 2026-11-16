"""Single source of truth for 'which MQL5 files may contain order-sending code'.

Audit M1 (2026-11-14): the scanner was duplicated (build tool + tests), its regex missed
PositionOpen / TRADE_ACTION_MODIFY / MqlTradeRequest / .Buy( / .Sell(, its comment
stripper treated "//" inside a string as a comment (so `"//"; OrderSend(...)` was
invisible) and Stage C needs an explicit, narrow exception instead of loosening the rule.

Policy:
  * Only the files in EXEC_ALLOWED may contain trading calls.
  * Every other .mq5/.mqh (read-only EA, shared includes, scripts) must contain none and
    must not #include an Exec* file, so trading code can never leak into them.
  * XAU_FeasibilityReport builds a request ONLY for OrderCheck (server-side validation):
    its TRADE_ACTION_DEAL / MqlTradeRequest tokens are exempt, OrderSend is not.
"""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"\b(OrderSend|OrderSendAsync|CTrade|CPositionInfo|PositionOpen|PositionClose|"
    r"PositionClosePartial|PositionModify|OrderOpen|OrderModify|OrderDelete|"
    r"TRADE_ACTION_DEAL|TRADE_ACTION_PENDING|TRADE_ACTION_SLTP|TRADE_ACTION_MODIFY|"
    r"TRADE_ACTION_REMOVE|TRADE_ACTION_CLOSE_BY|MqlTradeRequest)\b"
    r"|Trade\.mqh|#import|\.\s*(Buy|Sell|BuyLimit|SellLimit|BuyStop|SellStop)\s*\(")
FEASIBILITY_EXEMPT = ("TRADE_ACTION_DEAL", "MqlTradeRequest")
EXEC_ALLOWED = ("Experts/XauScalp_Exec.mq5", "Include/XauScalp/ExecEngine.mqh")
EXEC_INCLUDE = re.compile(r'#\s*include\s*[<"][^>"]*Exec[^>"]*[>"]', re.IGNORECASE)   # Wine ignores case


def strip_comments(src: str) -> str:
    """Remove // and /* */ comments but NOT text inside string or char literals."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def is_exec_file(rel: str | Path) -> bool:
    return Path(rel).as_posix() in EXEC_ALLOWED


def violations(files: list[Path], root: Path) -> list[str]:
    """Repo-relative names of files that break the policy (empty list = ok)."""
    bad = []
    for rel in files:
        rel_posix = Path(rel).as_posix()
        src = strip_comments((root / rel).read_text(encoding="utf-8"))
        if is_exec_file(rel_posix):
            continue
        if rel_posix.endswith("XAU_FeasibilityReport.mq5"):
            for tok in FEASIBILITY_EXEMPT:
                src = src.replace(tok, "")
        if FORBIDDEN.search(src) or EXEC_INCLUDE.search(src):
            bad.append(rel_posix)
    return bad
