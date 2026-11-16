"""Spec of the DEMO execution policy (the MQL5 engine it describes is not published here)."""
import math
from pathlib import Path

import pytest

from xauscalp import execution_spec as sp

MT5 = Path(__file__).parents[1] / "mt5"


def test_retcode_classification_is_fail_closed():
    assert sp.classify("TRADE_RETCODE_DONE") is sp.Outcome.SUCCESS
    assert sp.classify("TRADE_RETCODE_DONE_PARTIAL") is sp.Outcome.SUCCESS
    assert sp.classify("TRADE_RETCODE_REJECT") is sp.Outcome.REJECTED
    for amb in ("TRADE_RETCODE_TIMEOUT", "TRADE_RETCODE_CONNECTION", "TRADE_RETCODE_PLACED",
                "TRADE_RETCODE_ERROR", "TRADE_RETCODE_CANCEL", "SOMETHING_NEW", ""):
        assert sp.classify(amb) is sp.Outcome.AMBIGUOUS
    assert set(sp.SUCCESS).isdisjoint(sp.REJECTED) and set(sp.LOCKING) <= set(sp.REJECTED)


def test_timeout_never_allows_a_second_entry():
    """Audit H1: timeout + no deal in history yet must keep blocking, then lock; never resend."""
    amb = sp.Outcome.AMBIGUOUS
    assert sp.reconcile(inflight_age_s=1, position_found=False, outcome=amb) is sp.Reconcile.WAIT
    assert sp.reconcile(inflight_age_s=sp.RECONCILE_WAIT_S - 1, position_found=False,
                        outcome=amb) is sp.Reconcile.WAIT
    assert sp.reconcile(inflight_age_s=sp.RECONCILE_WAIT_S, position_found=False,
                        outcome=amb) is sp.Reconcile.LOCK
    assert sp.reconcile(inflight_age_s=5, position_found=True, outcome=amb) is sp.Reconcile.ADOPT
    assert sp.reconcile(inflight_age_s=5, position_found=False,
                        outcome=sp.Outcome.REJECTED) is sp.Reconcile.CLEAR
    for bad in (math.nan, math.inf, -1.0):
        assert sp.reconcile(inflight_age_s=bad, position_found=False, outcome=amb) is sp.Reconcile.LOCK
    # while the marker exists the pre-send gate refuses, whatever else is fine
    ok = dict(enabled=True, authorized=True, demo=True, tester=False, locked=False, inflight=False,
              positions=0, pending_orders=0, kill_switch=False, errors=0, max_errors=3)
    assert sp.entries_allowed(**ok) == (True, "")
    assert sp.entries_allowed(**{**ok, "inflight": True}) == (False, "ORDER_IN_FLIGHT")


@pytest.mark.parametrize("change,reason", [
    ({"enabled": False}, "TRADING_DISABLED"),
    ({"authorized": False}, "NOT_DEMO_OR_NOT_AUTHORIZED"),
    ({"demo": False}, "NOT_DEMO_OR_NOT_AUTHORIZED"),
    ({"kill_switch": True}, "KILL_SWITCH"), ({"locked": True}, "ENGINE_LOCKED"),
    ({"positions": 1}, "POSITION_OR_ORDER_EXISTS"), ({"pending_orders": 1}, "POSITION_OR_ORDER_EXISTS"),
    ({"errors": 3}, "PAUSED_AFTER_ERRORS")])
def test_every_gate_blocks(change, reason):
    ok = dict(enabled=True, authorized=True, demo=True, tester=False, locked=False, inflight=False,
              positions=0, pending_orders=0, kill_switch=False, errors=0, max_errors=3)
    assert sp.entries_allowed(**{**ok, **change}) == (False, reason)


def test_tester_needs_no_authorization_file_but_real_accounts_never_pass():
    base = dict(enabled=True, authorized=False, demo=False, tester=True, locked=False,
                inflight=False, positions=0, pending_orders=0, kill_switch=False, errors=0,
                max_errors=3)
    assert sp.entries_allowed(**base)[0] is True            # simulated orders only
    assert sp.entries_allowed(**{**base, "tester": False})[0] is False
    assert sp.entries_allowed(**{**base, "tester": False, "demo": False,
                                 "authorized": True})[0] is False


def test_signal_freshness_rejects_gaps_age_and_drift():
    kw = dict(bar_gap_s=60, bar_age_s=2, price=2000.0, decision_close=2000.1, sl_dist=4.0)
    assert sp.signal_fresh(**kw) == (True, "")
    assert sp.signal_fresh(**{**kw, "bar_gap_s": 180}) == (False, "BAR_GAP")        # H2
    assert sp.signal_fresh(**{**kw, "bar_age_s": 66}) == (False, "SIGNAL_STALE")
    assert sp.signal_fresh(**{**kw, "price": 2001.2}) == (False, "PRICE_DRIFT")     # 1.1 > 1.0
    for bad in (math.nan, math.inf):
        assert sp.signal_fresh(**{**kw, "price": bad}) == (False, "INVALID_INPUT")
    assert sp.signal_fresh(**{**kw, "sl_dist": 0.0}) == (False, "INVALID_INPUT")


def test_post_fill_risk_check():
    assert sp.post_fill_ok(5.0, 5.5)
    assert not sp.post_fill_ok(5.0, 5.6) and not sp.post_fill_ok(5.0, math.nan)
    assert not sp.post_fill_ok(0.0, 1.0) and not sp.post_fill_ok(5.0, 0.0)


def test_fast_exit_resolves_an_inflight_attempt_without_locking():
    """Audit M-1: filled and stopped out within the wait -> history shows the entry deal."""
    amb = sp.Outcome.AMBIGUOUS
    assert sp.reconcile(inflight_age_s=130, position_found=False, outcome=amb,
                        entry_deal_in_history=True) is sp.Reconcile.CLEAR
    assert sp.reconcile(inflight_age_s=130, position_found=False, outcome=amb) is sp.Reconcile.LOCK


def test_failed_post_fill_close_is_retried_then_locks():
    assert sp.must_close_action(seconds_since_demand=5, still_open=True) == "RETRY"
    assert sp.must_close_action(seconds_since_demand=sp.MUST_CLOSE_WAIT_S, still_open=True) == "LOCK"
    assert sp.must_close_action(seconds_since_demand=999, still_open=False) == "DONE"
    assert sp.must_close_action(seconds_since_demand=math.nan, still_open=True) == "LOCK"


def test_one_entry_per_session_and_day():
    assert sp.session_allows_entry(set(), "london.2025-10-13")
    assert not sp.session_allows_entry({"london.2025-10-13"}, "london.2025-10-13")
    assert sp.session_allows_entry({"london.2025-10-13"}, "newyork.2025-10-13")
    assert not sp.session_allows_entry(set(), "")


def test_terminal_not_ready_refuses_live_entries_without_blocking_the_tester():
    ok = dict(enabled=True, authorized=True, demo=True, tester=False, locked=False, inflight=False,
              positions=0, pending_orders=0, kill_switch=False, errors=0, max_errors=3)
    assert sp.entries_allowed(**ok, terminal_ready=False) == (False, "TERMINAL_NOT_READY")
    assert sp.entries_allowed(**{**ok, "tester": True, "demo": False, "authorized": False},
                              terminal_ready=False)[0] is True
