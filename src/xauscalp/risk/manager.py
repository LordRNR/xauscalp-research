"""Risk Manager: the only component allowed to approve a trade.

Strategies/models only PROPOSE. Every proposal goes through evaluate(), which runs ALL
checks (no short-circuit) so the decision log explains every reason for a rejection.
The same rules are mirrored in the MQL5 EA (last line of defence inside the terminal).

Fail-closed design: any non-finite, missing or out-of-range input produces a rejection
with an INVALID_* reason. Boolean safety flags are only considered "safe" when they are
exactly True/False as expected (e.g. kill_switch=None blocks trading).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from xauscalp.config import RiskConfig, SymbolSpec
from xauscalp.risk.sizing import is_nonneg, is_pos, size_position, spec_problem

# Max allowed distance between the proposal's entry and the live quote, as a fraction of
# price, before we assume the proposal was built on stale or wrong prices.
MAX_ENTRY_DEVIATION_FRAC = 0.001


@dataclass(frozen=True)
class TradeProposal:
    direction: int            # +1 buy, -1 sell
    entry_price: float        # expected fill (ask for buy, bid for sell)
    sl_price: float | None
    tp_price: float | None
    strategy: str
    rationale: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AccountState:
    equity: float
    free_margin: float
    day_start_equity: float
    week_start_equity: float
    peak_equity: float
    open_positions: int
    trades_today: int
    consecutive_errors: int = 0
    kill_switch: bool = False
    drawdown_lock: bool = False      # set once max DD is hit; only a human resets it


@dataclass(frozen=True)
class MarketState:
    bid: float
    ask: float
    data_age_s: float
    market_open: bool = True
    news_blackout: bool = False


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    volume: float
    risk_money: float
    reasons: tuple[str, ...]          # rejection codes (empty if approved)
    details: dict

    def explain(self) -> str:
        if self.approved:
            return f"APPROVED vol={self.volume} risk={self.risk_money:.2f}"
        return "REJECTED: " + ", ".join(self.reasons)


def _is_count(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


class RiskManager:
    def __init__(
        self,
        cfg: RiskConfig,
        spec: SymbolSpec,
        *,
        profit_to_account_rate: float = 1.0,
        leverage: float = 20.0,
    ) -> None:
        self.cfg = cfg
        self.spec = spec
        self.fx = profit_to_account_rate
        self.leverage = leverage

    # --- helpers -------------------------------------------------------------
    def remaining_loss_budget(self, acct: AccountState) -> float:
        """Smallest remaining allowance among daily, weekly and drawdown limits."""
        c = self.cfg
        daily = acct.day_start_equity * c.daily_loss_limit_pct / 100 - (
            acct.day_start_equity - acct.equity
        )
        weekly = acct.week_start_equity * c.weekly_loss_limit_pct / 100 - (
            acct.week_start_equity - acct.equity
        )
        peak = max(acct.peak_equity, acct.equity)   # a stale peak must not loosen the limit
        dd = peak * c.max_drawdown_pct / 100 - (peak - acct.equity)
        out = min(daily, weekly, dd)
        return max(0.0, out) if math.isfinite(out) else 0.0

    def margin_required(self, volume: float, price: float) -> float:
        """Approximation (research only). Live code must use OrderCalcMargin."""
        return volume * self.spec.contract_size * price / self.leverage * self.fx

    def _invalid_inputs(self, p: TradeProposal, a: AccountState, m: MarketState) -> list[str]:
        bad = []
        for name in ("equity", "day_start_equity", "week_start_equity", "peak_equity"):
            if not is_pos(getattr(a, name)):
                bad.append(f"INVALID_ACCOUNT:{name}")
        if not is_nonneg(a.free_margin):
            bad.append("INVALID_ACCOUNT:free_margin")
        for name in ("open_positions", "trades_today", "consecutive_errors"):
            if not _is_count(getattr(a, name)):
                bad.append(f"INVALID_ACCOUNT:{name}")
        if not is_pos(m.bid) or not is_pos(m.ask):
            bad.append("INVALID_QUOTE")
        if not is_nonneg(m.data_age_s):
            bad.append("STALE_DATA")          # unknown age is treated as stale
        if not is_pos(p.entry_price):
            bad.append("INVALID_INPUT:entry_price")
        if p.sl_price is not None and not is_pos(p.sl_price):
            bad.append("INVALID_INPUT:sl_price")
        if p.tp_price is not None and not is_pos(p.tp_price):
            bad.append("INVALID_INPUT:tp_price")
        if not is_pos(self.fx):
            bad.append("INVALID_FX_RATE")
        if not is_pos(self.leverage):
            bad.append("INVALID_LEVERAGE")
        if (sp := spec_problem(self.spec)) is not None:
            bad.append(sp)
        return bad

    # --- main entry point ----------------------------------------------------
    def evaluate(self, p: TradeProposal, acct: AccountState, mkt: MarketState) -> RiskDecision:
        c, d = self.cfg, {}
        reasons: list[str] = self._invalid_inputs(p, acct, mkt)
        invalid = bool(reasons)

        # safety flags: anything other than the exact "safe" value blocks
        if acct.kill_switch is not False:
            reasons.append("KILL_SWITCH")
        if acct.drawdown_lock is not False:
            reasons.append("DRAWDOWN_LOCK")
        if mkt.market_open is not True:
            reasons.append("MARKET_CLOSED")
        if mkt.news_blackout is not False:
            reasons.append("NEWS_BLACKOUT")
        if _is_count(acct.consecutive_errors) and acct.consecutive_errors >= c.max_consecutive_errors:
            reasons.append("PAUSED_AFTER_ERRORS")
        if is_nonneg(mkt.data_age_s) and mkt.data_age_s > c.max_data_age_s:
            reasons.append("STALE_DATA")

        if is_pos(mkt.bid) and is_pos(mkt.ask):
            spread = mkt.ask - mkt.bid
            d["spread"] = spread
            if spread <= 0:
                reasons.append("INVALID_QUOTE")
            elif spread > c.max_spread_usd:
                reasons.append("SPREAD_TOO_WIDE")
            if p.direction in (1, -1) and is_pos(p.entry_price):
                ref = mkt.ask if p.direction == 1 else mkt.bid
                if abs(p.entry_price - ref) > MAX_ENTRY_DEVIATION_FRAC * ref:
                    reasons.append("ENTRY_PRICE_MISMATCH")
        if _is_count(acct.open_positions) and acct.open_positions >= c.max_open_positions:
            reasons.append("MAX_OPEN_POSITIONS")
        if _is_count(acct.trades_today) and acct.trades_today >= c.max_trades_per_day:
            reasons.append("MAX_TRADES_PER_DAY")

        # loss limits (only computable with valid equity figures)
        if not any(r.startswith("INVALID_ACCOUNT:") and "equity" in r for r in reasons):
            day_pnl_pct = (acct.equity / acct.day_start_equity - 1) * 100
            week_pnl_pct = (acct.equity / acct.week_start_equity - 1) * 100
            dd_pct = (1 - acct.equity / max(acct.peak_equity, acct.equity)) * 100
            d.update(day_pnl_pct=day_pnl_pct, week_pnl_pct=week_pnl_pct, drawdown_pct=dd_pct)
            if day_pnl_pct <= -c.daily_loss_limit_pct:
                reasons.append("DAILY_LOSS_LIMIT")
            if week_pnl_pct <= -c.weekly_loss_limit_pct:
                reasons.append("WEEKLY_LOSS_LIMIT")
            if dd_pct >= c.max_drawdown_pct:
                reasons.append("MAX_DRAWDOWN")

        # stop loss is mandatory and must be on the correct side
        sl_dist = None
        if p.direction not in (1, -1) or isinstance(p.direction, bool):
            reasons.append("INVALID_DIRECTION")
        elif p.sl_price is None:
            reasons.append("SL_MISSING")
        elif is_pos(p.sl_price) and is_pos(p.entry_price):
            sl_dist = (p.entry_price - p.sl_price) * p.direction
            if sl_dist <= 0:
                reasons.append("SL_WRONG_SIDE")
                sl_dist = None
            elif is_pos(mkt.bid) and is_pos(mkt.ask) and mkt.ask > mkt.bid:
                # Audit H1: size from the WORST of the proposal entry and the live quote
                # (a buy fills at >= ask, a sell at <= bid), and the stop must be beyond
                # the price that triggers it (buy SL triggers on bid, sell SL on ask).
                if p.direction == 1:
                    worst_entry, trigger = max(p.entry_price, mkt.ask), mkt.bid
                else:
                    worst_entry, trigger = min(p.entry_price, mkt.bid), mkt.ask
                if (trigger - p.sl_price) * p.direction <= 0:
                    reasons.append("SL_WRONG_SIDE_OF_MARKET")
                    sl_dist = None
                else:
                    sl_dist = (worst_entry - p.sl_price) * p.direction
                    d["worst_entry"] = worst_entry
            else:
                sl_dist = None          # no valid live quote: cannot size safely
        if (p.tp_price is not None and is_pos(p.tp_price) and is_pos(p.entry_price)
                and p.direction in (1, -1)
                and (p.tp_price - p.entry_price) * p.direction <= 0):
            reasons.append("TP_WRONG_SIDE")

        # sizing: budget is the SMALLER of per-trade risk and remaining loss allowances
        volume, risk_money = 0.0, 0.0
        if sl_dist is not None and not invalid:
            budget = min(acct.equity * c.risk_per_trade_pct / 100,
                         self.remaining_loss_budget(acct))
            s = size_position(
                budget, sl_dist, self.spec,
                slippage=c.expected_slippage_usd,
                commission_per_lot=c.commission_per_lot,
                profit_to_account_rate=self.fx,
            )
            d.update(budget=budget, sl_distance=sl_dist, loss_per_lot=s.loss_per_lot,
                     sizing=s.reason, min_volume_risk=s.risk_money if s.volume == 0 else None)
            if s.reason != "OK":
                reasons.append(s.reason)
            else:
                volume, risk_money = s.volume, s.risk_money
                margin = self.margin_required(volume, p.entry_price)
                d["margin_required"] = margin
                if not is_pos(margin):
                    reasons.append("MARGIN_CALC_FAILED")
                elif margin > acct.free_margin * c.max_margin_usage_pct / 100:
                    reasons.append("INSUFFICIENT_MARGIN")

        approved = not reasons
        if approved and not (is_pos(volume) and is_pos(risk_money)):
            reasons.append("INTERNAL_INCONSISTENCY")      # belt and braces
            approved = False
        reasons = list(dict.fromkeys(reasons))            # de-duplicate, keep order
        return RiskDecision(
            approved=approved,
            volume=volume if approved else 0.0,
            risk_money=risk_money if approved else 0.0,
            reasons=tuple(reasons),
            details=d,
        )
