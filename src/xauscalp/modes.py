"""Operating-mode guard: RESEARCH / DEMO / LIVE.

LIVE is hard-disabled during development: LIVE_PHASE_UNLOCKED is a code constant that
only the user may change, after Phase 8 is approved. Even then LIVE additionally needs a
user-written authorisation file bound to a specific account login (git-ignored).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

LIVE_PHASE_UNLOCKED = False  # USER-ONLY. AI agents must never change this (see CLAUDE.md).


class Mode(str, Enum):
    RESEARCH = "RESEARCH"
    DEMO = "DEMO"
    LIVE = "LIVE"


class ModeViolation(RuntimeError):
    pass


def check_mode(
    mode: Mode,
    *,
    account_is_demo: bool | None,
    account_login: int | None = None,
    authorization_file: Path | None = None,
) -> None:
    """Raise ModeViolation unless the (mode, account) combination is safe.

    - RESEARCH: must not be connected to any trading account.
    - DEMO: account must be a demo account (rejects accidental real-account connection).
    - LIVE: requires LIVE_PHASE_UNLOCKED and an authorisation file naming this login.
    """
    if mode is Mode.RESEARCH:
        if account_is_demo is not None:
            raise ModeViolation("RESEARCH mode must not connect to a trading account")
        return
    if account_is_demo is None:
        raise ModeViolation(f"{mode.value} mode requires a known account type")
    if mode is Mode.DEMO:
        if not account_is_demo:
            raise ModeViolation("DEMO mode connected to a REAL account: refusing to run")
        return
    # LIVE
    if not LIVE_PHASE_UNLOCKED:
        raise ModeViolation("LIVE is disabled in this development phase")
    if account_is_demo:
        raise ModeViolation("LIVE mode connected to a demo account")
    if authorization_file is None or not authorization_file.exists():
        raise ModeViolation("LIVE requires a user-written authorisation file")
    text = authorization_file.read_text()
    if account_login is None or f"login={account_login}" not in text:
        raise ModeViolation("authorisation file does not name this account login")
