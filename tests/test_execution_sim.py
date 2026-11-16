"""Failure-injection tests of the Stage C policy on a mock broker (nothing is ever sent).

They verify the POLICY model in src/xauscalp/execution_sim.py (a mirror of ExecEngine.mqh, which is not published here);
see that module for what this does and does not prove."""
import random

import pytest

from xauscalp import execution_spec as sp
from xauscalp.execution_sim import Engine, MockBroker, Persist, SendScript

R = 5.0        # risk money for 0.01 lot
V = 0.01


def make(**kw):
    b = MockBroker()
    e = Engine(b, Persist(), **{"enabled": True, **kw})
    return b, e


def test_happy_path_one_fill_with_stop_and_errors_cleared():
    b, e = make()
    e.p.gv["errors"] = 2
    assert e.try_enter("london.d1", V, R) == "FILLED"
    assert len(b.positions) == 1 and e.errors == 0 and not e.inflight


def test_timeout_without_position_blocks_then_locks_and_never_resends():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=False)
    assert e.try_enter("london.d1", V, R).startswith("AMBIGUOUS")
    assert e.inflight and e.errors == 1
    for t in (1, 30, 100):                       # still within the wait: blocked, nothing sent
        e.now = t
        e.reconcile()
        assert e.try_enter("newyork.d1", V, R) == "ORDER_IN_FLIGHT"
    e.now = sp.RECONCILE_WAIT_S + 1
    e.reconcile()
    assert e.locked and len(b.entry_requests) == 1
    assert e.try_enter("london.d2", V, R) == "ENGINE_LOCKED"


def test_timeout_but_order_actually_executed_is_adopted_not_duplicated():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=True)
    e.try_enter("london.d1", V, R)
    e.now = 3
    e.reconcile()
    assert len(b.positions) == 1 and not e.inflight and not e.locked
    assert e.try_enter("newyork.d1", V, R) == "POSITION_OR_ORDER_EXISTS"
    assert len(b.entry_requests) == 1


def test_timeout_and_the_position_already_stopped_out_does_not_lock_forever():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_CONNECTION", opens_position=True, closes_fast=True)
    e.try_enter("london.d1", V, R)
    e.now = 10
    e.reconcile()
    assert not e.inflight and not e.locked and not b.positions


def test_definitive_rejection_clears_marker_counts_error_and_trading_unavailable_locks():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_REQUOTE", opens_position=False)
    assert e.try_enter("london.d1", V, R) == "REJECTED_TRADE_RETCODE_REQUOTE"
    assert not e.inflight and e.errors == 1 and not e.locked
    b.script = SendScript(retcode="TRADE_RETCODE_NO_MONEY", opens_position=False)
    e.try_enter("newyork.d1", V, R)
    assert e.locked


def test_three_rejections_across_bars_pause_the_engine_only_a_fill_clears_it():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_REJECT", opens_position=False)
    for i in range(3):
        e.now += 60
        e.reconcile()                              # per-bar housekeeping must NOT clear errors
        e.try_enter(f"s{i}.d", V, R)
    assert e.errors == 3
    assert e.try_enter("s9.d", V, R) == "PAUSED_AFTER_ERRORS"


def test_restart_between_marker_and_answer_keeps_blocking_even_if_gv_lost():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=False)
    e.try_enter("london.d1", V, R)
    e2 = e.restart(lose_gv=True)                   # crash: GlobalVariables gone, file marker stays
    assert e2.inflight
    assert e2.try_enter("newyork.d1", V, R) == "ORDER_IN_FLIGHT"           # marker file blocks
    assert e2.try_enter("london.d1", V, R) == "SESSION_ALREADY_TRADED"       # session mark survives
    e2.now = 500
    e2.reconcile()
    assert e2.locked and len(b.entry_requests) == 1


def test_restart_after_fill_adopts_the_position_and_does_not_reenter_the_session():
    b, e = make()
    e.try_enter("london.d1", V, R)
    e2 = e.restart()
    assert len(b.positions) == 1
    assert e2.try_enter("london.d1", V, R) == "SESSION_ALREADY_TRADED"
    e2.b.positions.clear()
    assert e2.try_enter("london.d1", V, R) == "SESSION_ALREADY_TRADED"


def test_position_without_stop_is_closed_or_engine_locks():
    b, e = make()
    b.script = SendScript(has_sl=False)
    assert e.try_enter("london.d1", V, R) == "FILLED_WITHOUT_SL_CLOSE_DEMANDED"
    assert not b.positions and e.locked
    b2, e2 = make()
    b2.script = SendScript(has_sl=False)
    b2.close_succeeds = False
    e2.try_enter("london.d1", V, R)
    assert b2.positions and e2.locked              # could not close: locked, human must act


def test_excess_risk_after_fill_closes_retries_and_locks_if_it_stays_open():
    b, e = make()
    b.script = SendScript(risk_factor=1.5)
    b.close_succeeds = False
    assert e.try_enter("london.d1", V, R) == "POST_FILL_RISK_CLOSE_DEMANDED"
    assert b.positions and not e.locked
    for t in (6, 12, 30):
        e.now = t
        e.reconcile()
        assert len(b.close_requests) >= 2          # retried
    e.now = sp.MUST_CLOSE_WAIT_S + 10
    e.reconcile()
    assert e.locked
    b.close_succeeds = True
    e.now += 10
    e.reconcile()                                  # closes it
    assert not b.positions
    e.reconcile()                                  # next pass clears the mark (as in the MQL5)
    assert not e.has("must_close") and e.locked    # the lock stays: only a human clears it


def test_partial_fill_budget_scales_and_rest_is_never_resent():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_DONE_PARTIAL", fill_volume_ratio=0.5)
    assert e.try_enter("london.d1", V, R) == "FILLED"
    assert b.positions[0].volume == pytest.approx(V * 0.5) and len(b.entry_requests) == 1


def test_adopted_position_with_unknown_or_excess_risk_is_closed():
    b, e = make()
    b.script = SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=True, risk_factor=2.0)
    e.try_enter("london.d1", V, R)
    e.now = 2
    e.reconcile()
    assert not b.positions                         # adopted, risk checked, closed


@pytest.mark.parametrize("kw,expect", [({"enabled": False}, "TRADING_DISABLED"),
                                       ({"demo": False}, "NOT_DEMO_OR_NOT_AUTHORIZED"),
                                       ({"authorized": False}, "NOT_DEMO_OR_NOT_AUTHORIZED")])
def test_nothing_is_sent_when_disabled_real_or_unauthorised(kw, expect):
    b, e = make(**kw)
    assert e.try_enter("london.d1", V, R) == expect and not b.entry_requests


def test_kill_switch_appearing_blocks_and_tester_needs_no_authorisation():
    b, e = make()
    e.kill = True
    assert e.try_enter("london.d1", V, R) == "KILL_SWITCH" and not b.entry_requests
    _b2, e2 = make(tester=True, demo=False, authorized=False)
    assert e2.try_enter("london.d1", V, R) == "FILLED"


def test_time_exit_closes_but_never_when_disabled():
    b, e = make()
    e.try_enter("london.d1", V, R)
    e.now = 5400 + 1
    e.reconcile()
    assert not b.positions
    b2, e2 = make()
    e2.try_enter("london.d1", V, R)
    e2.enabled = False
    e2.now = 6000
    e2.reconcile()
    assert b2.positions and not b2.close_requests


# ------------------------------------------------------------------------------------------
def run_fuzz(seed: int, steps: int = 400):
    rng = random.Random(seed)
    b, e = make()
    sessions = [f"{s}.d{d}" for d in range(6) for s in ("london", "newyork")]
    for _ in range(steps):
        e.now += rng.choice([1, 5, 20, 70, 130])
        act = rng.choices(["enter", "reconcile", "restart", "restart_lose", "kill", "fast_exit",
                           "human_reset"], [6, 6, 1, 1, 1, 1, 1])[0]
        if act == "enter":
            b.script = rng.choice([
                SendScript(), SendScript(), SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=False),
                SendScript(retcode="TRADE_RETCODE_TIMEOUT", opens_position=True),
                SendScript(retcode="TRADE_RETCODE_CONNECTION", opens_position=True, closes_fast=True),
                SendScript(retcode="TRADE_RETCODE_REJECT", opens_position=False),
                SendScript(retcode="TRADE_RETCODE_DONE_PARTIAL", fill_volume_ratio=0.5),
                SendScript(has_sl=False), SendScript(risk_factor=1.6), SendScript(retcode="BRAND_NEW_CODE")])
            b.close_succeeds = rng.random() < 0.7
            sent_before = len(b.entry_requests)
            blocked = (e.inflight, e.locked, e.kill, bool(b.positions), e.errors >= e.max_errors)
            key = rng.choice(sessions)
            done = key in e.p.done_sessions
            e.try_enter(key, V, R)
            if len(b.entry_requests) > sent_before:
                assert not any(blocked), f"seed {seed}: sent while blocked {blocked}"        # I2/I5
                assert not done, f"seed {seed}: session traded twice"                         # I1
        elif act == "reconcile":
            e.reconcile()
        elif act == "restart":
            e = e.restart()
        elif act == "restart_lose":
            # GlobalVariables lost at ANY moment: lock, in-flight marker and session marks are
            # also files / history deals now (audit M1), so the invariants must still hold.
            e = e.restart(lose_gv=True)
        elif act == "human_reset":
            e.human_reset()
        elif act == "kill":
            e.kill = not e.kill
        elif act == "fast_exit" and b.positions:
            b.positions.clear()
        assert len(b.positions) <= 1, f"seed {seed}: two positions"                           # I1
        for p in b.positions:
            if p.sl <= 0:
                assert e.locked, f"seed {seed}: unprotected position and not locked"          # I4
    return b, e


@pytest.mark.parametrize("seed", range(300))
def test_random_failure_sequences_keep_every_invariant(seed):
    run_fuzz(seed)


def test_fuzz_actually_exercises_the_failure_paths():
    """Guard against a vacuous fuzz: across seeds we must see locks, ambiguous attempts, rejections."""
    locks = ambiguous = rejected = filled = 0
    for seed in range(60):
        b, e = run_fuzz(seed)
        locks += any(line.startswith("LOCKED") for line in e.log)
        ambiguous += any("ambiguous" in line for line in e.log)
        rejected += any("rejected" in line for line in e.log)
        filled += len(b.entry_requests) > 0
    assert locks > 5 and ambiguous > 10 and rejected > 10 and filled > 30


def test_lock_survives_losing_the_global_variables():
    b, e = make()
    b.script = SendScript(has_sl=False)
    e.try_enter("london.d1", V, R)
    assert e.locked
    e2 = e.restart(lose_gv=True)
    assert e2.locked and e2.try_enter("newyork.d1", V, R) == "ENGINE_LOCKED"
    e2.human_reset()
    assert not e2.locked


def test_human_reset_does_not_rearm_sessions_already_traded():
    _b, e = make()
    e.try_enter("london.d1", V, R)
    e.human_reset()
    assert e.try_enter("london.d1", V, R) == "SESSION_ALREADY_TRADED"
