"""Reference model of the Stage C engine + a MOCK broker, to test safety under failures.

WHAT THIS IS: a line-by-line Python mirror of the decision flow of
mt5/Include/XauScalp/ExecEngine.mqh (TryEnter, Reconcile, DemandClose, restart), built on the
tested policy functions of `execution_spec`, driven by a scripted broker that can time out,
answer ambiguously, refuse, fill partially, lose its memory (GlobalVariables) or crash between
steps. It sends nothing anywhere.

WHAT THIS IS NOT: the MQL5 binary. The Strategy Tester cannot produce timeouts or crashes
either, so the failure-handling of the real engine stays UNVERIFIED until a DEMO dry run with
real disconnections; this model verifies that the POLICY is consistent and that its invariants
hold under thousands of random failure sequences. in the development repository tests/test_execution_sim.py also
checked that the MQL5 source keeps the structure this model assumes; that source is not published here.

Invariants checked by the tests:
  I1 the broker never holds more than one position, nor receives two entries for one session;
  I2 while an attempt is unresolved (marker present) no second entry is ever sent;
  I3 an ambiguous result never causes an automatic resend;
  I4 a position without a stop loss, or above the post-fill risk tolerance, is closed or the
     engine locks;
  I5 nothing is sent when disabled, locked, killed, or when the account is not authorised.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xauscalp import execution_spec as sp


@dataclass
class Position:
    ticket: int
    magic: int
    volume: float
    sl: float
    risk: float
    opened_at: float


@dataclass
class SendScript:
    """What the broker does with the NEXT entry request."""
    retcode: str = "TRADE_RETCODE_DONE"
    opens_position: bool = True          # a position appears even if the answer is ambiguous
    fill_volume_ratio: float = 1.0
    has_sl: bool = True
    risk_factor: float = 1.0             # real risk / approved risk after the fill
    closes_fast: bool = False            # stopped out immediately: only a history deal remains


@dataclass
class MockBroker:
    positions: list[Position] = field(default_factory=list)
    entry_deals: list[tuple[float, int]] = field(default_factory=list)   # (time, magic)
    entry_requests: list[dict] = field(default_factory=list)
    close_requests: list[int] = field(default_factory=list)
    close_succeeds: bool = True
    script: SendScript = field(default_factory=SendScript)
    next_ticket: int = 1

    def send_entry(self, now: float, magic: int, volume: float, risk_per_lot: float,
                   session_key: str) -> str:
        self.entry_requests.append({"t": now, "session": session_key, "volume": volume})
        sc = self.script
        if sc.retcode in sp.SUCCESS or sc.opens_position:
            vol = volume * sc.fill_volume_ratio
            self.entry_deals.append((now, magic))
            if not sc.closes_fast:
                self.positions.append(Position(self.next_ticket, magic, vol,
                                               1.0 if sc.has_sl else 0.0,
                                               risk_per_lot * vol * sc.risk_factor, now))
                self.next_ticket += 1
        return sc.retcode

    def close(self, ticket: int) -> bool:
        self.close_requests.append(ticket)
        if self.close_succeeds:
            self.positions = [p for p in self.positions if p.ticket != ticket]
        return self.close_succeeds


@dataclass
class Persist:
    """What survives a restart. `gv_lost=True` models a crash that lost the GlobalVariables
    but not the flushed marker file."""
    gv: dict[str, float] = field(default_factory=dict)
    marker_file: bool = False
    lock_file: bool = False
    done_sessions: set[str] = field(default_factory=set)


class Engine:
    def __init__(self, broker: MockBroker, persist: Persist, *, enabled: bool, magic: int = 7,
                 tester: bool = False, demo: bool = True, authorized: bool = True,
                 max_errors: int = 3, max_hold_s: float = 5400.0) -> None:
        self.b, self.p = broker, persist
        self.enabled, self.magic, self.tester = enabled, magic, tester
        self.demo, self.authorized = demo, authorized
        self.max_errors, self.max_hold_s = max_errors, max_hold_s
        self.kill = False
        self.now = 0.0
        self.log: list[str] = []
        self.last_close_try = -1e9

    # --- persistent state helpers (GlobalVariables + marker file) ---------------------
    def gv(self, k: str, d: float = 0.0) -> float:
        return self.p.gv.get(k, d)

    def has(self, k: str) -> bool:
        return k in self.p.gv

    @property
    def errors(self) -> int:
        return int(self.gv("errors"))

    def add_error(self, why: str) -> None:
        self.p.gv["errors"] = self.errors + 1
        self.log.append(f"ERROR {why}")

    def lock(self, why: str) -> None:
        self.p.gv["lock"] = 1.0
        self.p.lock_file = True                        # Lock = GlobalVariable + FILE (audit M1)
        self.log.append(f"LOCKED {why}")

    @property
    def locked(self) -> bool:
        return self.has("lock") or self.p.lock_file

    @property
    def inflight(self) -> bool:
        return self.has("inflight") or self.p.marker_file

    def clear_inflight(self) -> None:
        for k in ("inflight", "inflight_t", "inflight_out", "inflight_rpl"):
            self.p.gv.pop(k, None)
        self.p.marker_file = False

    # --- gate (mirror of Gate/GateCommon) ------------------------------------------------
    def gate_common(self) -> str:
        if self.kill:
            return "KILL_SWITCH"
        if self.locked:
            return "ENGINE_LOCKED"
        if self.inflight:
            return "ORDER_IN_FLIGHT"
        if self.b.positions:
            return "POSITION_OR_ORDER_EXISTS"
        if self.errors >= self.max_errors:
            return "PAUSED_AFTER_ERRORS"
        return ""

    def gate(self) -> str:
        if not self.enabled:
            return "TRADING_DISABLED"
        if not self.tester and not (self.demo and self.authorized):
            return "NOT_DEMO_OR_NOT_AUTHORIZED"
        return self.gate_common()

    # --- entry (mirror of TryEnter) -------------------------------------------------------
    def try_enter(self, session_key: str, volume: float, risk_money: float) -> str:
        if session_key in self.p.done_sessions:
            return "SESSION_ALREADY_TRADED"
        g = self.gate()
        if g:
            return g
        g = self.gate()                                   # re-read right before the send
        if g:
            return g
        attempt = int(self.gv("attempt")) + 1
        self.p.done_sessions.add(session_key)
        self.p.gv.update({"attempt": attempt, "inflight": attempt, "inflight_t": self.now,
                          "inflight_out": float(sp_outcome_code(sp.Outcome.AMBIGUOUS)),
                          "inflight_rpl": risk_money / volume})
        self.p.marker_file = True
        rc = self.b.send_entry(self.now, self.magic, volume, risk_money / volume, session_key)
        out = sp.classify(rc)
        self.p.gv["inflight_out"] = float(sp_outcome_code(out))
        if out is sp.Outcome.REJECTED:
            self.clear_inflight()
            self.add_error(f"rejected {rc}")
            if rc in sp.LOCKING:
                self.lock(f"trading unavailable {rc}")
            return f"REJECTED_{rc}"
        if out is sp.Outcome.AMBIGUOUS:
            self.add_error(f"ambiguous {rc}")             # marker stays: no resend
            return f"AMBIGUOUS_{rc}"
        pos = self.our_position()
        if pos is None:
            return "FILLED_BUT_POSITION_NOT_VISIBLE"
        rpl = risk_money / volume
        self.clear_inflight()
        if not self.verify_protection(pos):
            return "FILLED_WITHOUT_SL_CLOSE_DEMANDED"
        if not sp.post_fill_ok(rpl * pos.volume, pos.risk):
            self.demand_close(pos, "POST_FILL_RISK")
            self.add_error("post-fill risk")
            return "POST_FILL_RISK_CLOSE_DEMANDED"
        self.p.gv["errors"] = 0                            # ONLY here
        return "FILLED"

    def our_position(self) -> Position | None:
        return next((p for p in self.b.positions if p.magic == self.magic), None)

    def verify_protection(self, pos: Position) -> bool:
        if pos.sl <= 0:
            self.demand_close(pos, "NO_SL")
            self.lock("position without stop loss")
            return False
        return True

    def close_position(self, pos: Position, why: str) -> bool:
        if self.now - self.last_close_try < 5:
            return False
        self.last_close_try = self.now
        if not self.enabled:
            self.log.append("CLOSE_SKIPPED_DISABLED")
            return False
        ok = self.b.close(pos.ticket)
        if not ok:
            self.add_error("close failed")
        return ok

    def demand_close(self, pos: Position, why: str) -> None:
        self.p.gv.setdefault("must_close", self.now)
        self.last_close_try = -1e9
        self.close_position(pos, why)

    # --- reconcile (mirror of Reconcile) ---------------------------------------------------
    def reconcile(self) -> None:
        pos = self.our_position()
        if not self.has("inflight") and self.p.marker_file:      # GV lost, file survived
            self.p.gv.update({"inflight": 0.0, "inflight_t": self.now,
                              "inflight_out": float(sp_outcome_code(sp.Outcome.AMBIGUOUS))})
        if self.inflight:
            sent = self.gv("inflight_t")
            age = self.now - sent
            out = sp_outcome_from_code(int(self.gv("inflight_out", 2)))
            deal = any(t >= sent - 60 and m == self.magic for t, m in self.b.entry_deals)
            action = sp.reconcile(inflight_age_s=age, position_found=pos is not None,
                                  outcome=out, entry_deal_in_history=deal)
            if action is sp.Reconcile.ADOPT:
                rpl = self.gv("inflight_rpl")
                self.clear_inflight()
                if not (rpl > 0) or not sp.post_fill_ok(rpl * pos.volume, pos.risk):
                    self.demand_close(pos, "ADOPT_RISK")
            elif action is sp.Reconcile.CLEAR:
                self.clear_inflight()
            elif action is sp.Reconcile.LOCK and not self.locked:
                self.lock("in-flight unresolved")
        pos = self.our_position()
        if pos is not None:
            if not self.verify_protection(pos):
                return
            if self.has("must_close"):
                act = sp.must_close_action(seconds_since_demand=self.now - self.gv("must_close"),
                                           still_open=True)
                if act == "LOCK" and not self.locked:
                    self.lock("must-close still open")
                self.close_position(pos, "MUST_CLOSE_RETRY")
                return
            if self.now - pos.opened_at >= self.max_hold_s:
                self.close_position(pos, "TIME_EXIT")
        elif self.has("must_close"):
            self.p.gv.pop("must_close")

    def human_reset(self) -> None:
        """The documented manual procedure: check the terminal, close what is open, delete the
        lock/errors/in-flight GVs and the marker file."""
        for k in ("lock", "errors", "inflight", "inflight_t", "inflight_out", "inflight_rpl",
                  "must_close"):
            self.p.gv.pop(k, None)
        self.p.marker_file = False
        self.p.lock_file = False
        self.b.positions.clear()                     # the human checks the terminal and closes it

    def restart(self, *, lose_gv: bool = False) -> Engine:
        """New process, same persistent state (optionally without the GlobalVariables)."""
        persist = Persist(gv={} if lose_gv else dict(self.p.gv), marker_file=self.p.marker_file,
                          lock_file=self.p.lock_file,
                          # the session mark is also a FILE and a history deal (audit M1)
                          done_sessions=set(self.p.done_sessions))
        e = Engine(self.b, persist, enabled=self.enabled, magic=self.magic, tester=self.tester,
                   demo=self.demo, authorized=self.authorized, max_errors=self.max_errors,
                   max_hold_s=self.max_hold_s)
        e.now = self.now
        e.kill = self.kill
        e.log = self.log                               # one audit trail across restarts
        e.reconcile()                                  # OnInit does this
        return e


def sp_outcome_code(o: sp.Outcome) -> int:
    return {sp.Outcome.SUCCESS: 0, sp.Outcome.REJECTED: 1, sp.Outcome.AMBIGUOUS: 2}[o]


def sp_outcome_from_code(c: int) -> sp.Outcome:
    return {0: sp.Outcome.SUCCESS, 1: sp.Outcome.REJECTED, 2: sp.Outcome.AMBIGUOUS}.get(
        c, sp.Outcome.AMBIGUOUS)
