"""Executable specification of the Stage C (DEMO) execution policy.

The MQL5 engine (mt5/Include/XauScalp/ExecEngine.mqh) cannot be unit-tested here, so the
decisions that matter for money safety are written down once, in Python, with tests; the
MQL5 source must contain the same constants and the same retcode tables
(in the development repository tests/test_execution_spec.py compared them textually; the MQL5 engine is not
published here, so that comparison is not part of this repository). This module sends nothing.

Policy (audit 2026-11-14 H1, H2, H3, M4, M7):
  * Before OrderSend an 'inflight' marker is persisted. It is cleared only when the outcome
    is KNOWN: a position exists (ADOPT), or the broker definitively refused (REJECTED).
  * Ambiguous outcomes (timeout, connection, placed...) keep the marker: no new entry is
    possible; the engine reconciles against positions/history, and after RECONCILE_WAIT_S
    without an answer it LOCKS (only a human clears it). Never an automatic resend.
  * The consecutive-error counter is persistent and cleared ONLY by a confirmed fill.
  * A signal is stale unless the decision bar and the current bar are contiguous, the
    current bar opened <= MAX_SIGNAL_AGE_S ago and the live price is within
    MAX_DRIFT_FRAC * SL distance of the decision bar's close.
  * After a fill (and after ADOPT on restart) the real risk is recomputed; above POST_FILL_TOL
    x the approved risk a close is DEMANDED: persisted mark, retried on every reconcile, and
    the engine LOCKS if the position is still open MUST_CLOSE_WAIT_S later (audit H-1).
  * A fast SL/TP exit leaves no position: an ENTRY deal in the history also resolves an
    in-flight attempt (audit M-1). The marker is mirrored in a file (audit M-4).
  * One entry per (session, day), persisted before the send (audit M-2).
"""

from __future__ import annotations

import math
from enum import StrEnum

MAX_SIGNAL_AGE_S = 65
BAR_SECONDS = 60
MAX_DRIFT_FRAC = 0.25
RECONCILE_WAIT_S = 120
POST_FILL_TOL = 1.10
MUST_CLOSE_WAIT_S = 60
AUTH_FILE = "xauscalp_auth\\EXEC_DEMO_AUTHORIZED"       # own folder: can be root-owned (security/)

# MQL5 TRADE_RETCODE_* names (official constants).
SUCCESS = ("TRADE_RETCODE_DONE", "TRADE_RETCODE_DONE_PARTIAL")
# Definitive refusals: the broker did NOT open a position.
REJECTED = ("TRADE_RETCODE_REQUOTE", "TRADE_RETCODE_REJECT", "TRADE_RETCODE_INVALID",
            "TRADE_RETCODE_INVALID_VOLUME", "TRADE_RETCODE_INVALID_PRICE",
            "TRADE_RETCODE_INVALID_STOPS", "TRADE_RETCODE_TRADE_DISABLED",
            "TRADE_RETCODE_MARKET_CLOSED", "TRADE_RETCODE_NO_MONEY",
            "TRADE_RETCODE_PRICE_CHANGED", "TRADE_RETCODE_PRICE_OFF",
            "TRADE_RETCODE_TOO_MANY_REQUESTS", "TRADE_RETCODE_SERVER_DISABLES_AT",
            "TRADE_RETCODE_CLIENT_DISABLES_AT", "TRADE_RETCODE_INVALID_FILL",
            "TRADE_RETCODE_ONLY_REAL", "TRADE_RETCODE_LIMIT_VOLUME",
            "TRADE_RETCODE_LIMIT_POSITIONS", "TRADE_RETCODE_LIMIT_ORDERS",
            "TRADE_RETCODE_LOCKED", "TRADE_RETCODE_FROZEN")
# Retcodes that mean "trading itself is unavailable": also engage the kill lock.
LOCKING = ("TRADE_RETCODE_NO_MONEY", "TRADE_RETCODE_TRADE_DISABLED",
           "TRADE_RETCODE_SERVER_DISABLES_AT", "TRADE_RETCODE_CLIENT_DISABLES_AT",
           "TRADE_RETCODE_ONLY_REAL")


class Outcome(StrEnum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"


class Reconcile(StrEnum):
    ADOPT = "ADOPT"      # a position with our magic/comment exists: track it, clear marker
    CLEAR = "CLEAR"      # known: nothing was opened, clear marker
    WAIT = "WAIT"        # unknown yet, keep blocking entries
    LOCK = "LOCK"        # unknown for too long: block until a human intervenes


def classify(retcode_name: str) -> Outcome:
    if retcode_name in SUCCESS:
        return Outcome.SUCCESS
    if retcode_name in REJECTED:
        return Outcome.REJECTED
    return Outcome.AMBIGUOUS            # unknown codes are NEVER assumed harmless


def reconcile(*, inflight_age_s: float, position_found: bool, outcome: Outcome,
              entry_deal_in_history: bool = False) -> Reconcile:
    if not (math.isfinite(inflight_age_s) and inflight_age_s >= 0):
        return Reconcile.LOCK
    if position_found:
        return Reconcile.ADOPT
    if outcome is Outcome.REJECTED or entry_deal_in_history:
        return Reconcile.CLEAR
    return Reconcile.WAIT if inflight_age_s < RECONCILE_WAIT_S else Reconcile.LOCK


def signal_fresh(*, bar_gap_s: float, bar_age_s: float, price: float, decision_close: float,
                 sl_dist: float) -> tuple[bool, str]:
    vals = (bar_gap_s, bar_age_s, price, decision_close, sl_dist)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        return False, "INVALID_INPUT"
    if sl_dist <= 0 or price <= 0 or decision_close <= 0:
        return False, "INVALID_INPUT"
    if bar_gap_s != BAR_SECONDS:
        return False, "BAR_GAP"
    if bar_age_s < 0 or bar_age_s > MAX_SIGNAL_AGE_S:
        return False, "SIGNAL_STALE"
    if abs(price - decision_close) > MAX_DRIFT_FRAC * sl_dist:
        return False, "PRICE_DRIFT"
    return True, ""


def post_fill_ok(approved_risk: float, actual_risk: float) -> bool:
    """False -> close immediately. Any non-finite input is a failure (fail-closed)."""
    if not all(math.isfinite(v) for v in (approved_risk, actual_risk)):
        return False
    return approved_risk > 0 and 0 < actual_risk <= approved_risk * POST_FILL_TOL


def entries_allowed(*, enabled: bool, authorized: bool, demo: bool, tester: bool,
                    locked: bool, inflight: bool, positions: int, pending_orders: int,
                    kill_switch: bool, errors: int, max_errors: int,
                    terminal_ready: bool = True) -> tuple[bool, str]:
    """Pre-send gate, evaluated AFTER the RiskGuard approved and again right before OrderSend."""
    if not enabled:
        return False, "TRADING_DISABLED"
    if not tester and not (demo and authorized):
        return False, "NOT_DEMO_OR_NOT_AUTHORIZED"
    if not tester and not terminal_ready:      # transient: refuse WITHOUT counting an error (audit E1)
        return False, "TERMINAL_NOT_READY"
    if kill_switch:
        return False, "KILL_SWITCH"
    if locked:
        return False, "ENGINE_LOCKED"
    if inflight:
        return False, "ORDER_IN_FLIGHT"
    if positions > 0 or pending_orders > 0:
        return False, "POSITION_OR_ORDER_EXISTS"
    if errors >= max_errors:
        return False, "PAUSED_AFTER_ERRORS"
    return True, ""


def must_close_action(*, seconds_since_demand: float, still_open: bool) -> str:
    """RETRY while it may still work, LOCK when the close did not happen in time, DONE when closed."""
    if not still_open:
        return "DONE"
    if not (math.isfinite(seconds_since_demand) and seconds_since_demand >= 0):
        return "LOCK"
    return "LOCK" if seconds_since_demand >= MUST_CLOSE_WAIT_S else "RETRY"


def session_allows_entry(done_keys: set[str], key: str) -> bool:
    return bool(key) and key not in done_keys
