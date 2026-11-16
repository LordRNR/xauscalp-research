"""Position sizing. Volume is ALWAYS floored to the broker step, never rounded up.

If the broker's minimum volume would risk more than the allowed budget, the trade is
rejected: that is the correct outcome for an account that is too small.
Every input is validated: anything non-finite or out of range yields a rejection
(volume 0 and an INVALID_* reason), never an exception and never an approval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from xauscalp.config import SymbolSpec


@dataclass(frozen=True)
class SizingResult:
    volume: float            # 0.0 when rejected
    risk_money: float        # estimated loss at SL incl. slippage and commission (acct ccy)
    loss_per_lot: float      # acct ccy
    budget: float            # acct ccy
    reason: str              # "OK" or a rejection code


def is_pos(x) -> bool:
    """Finite real number strictly greater than zero (bools rejected)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def is_nonneg(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def spec_problem(spec: SymbolSpec) -> str | None:
    for name in ("contract_size", "volume_min", "volume_step", "volume_max"):
        if not is_pos(getattr(spec, name)):
            return f"INVALID_SPEC:{name}"
    if spec.volume_max < spec.volume_min:
        return "INVALID_SPEC:volume_max<volume_min"
    return None


def _step_decimals(step: float) -> int:
    s = f"{step:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def loss_per_lot(
    sl_distance: float,
    spec: SymbolSpec,
    slippage: float,
    commission_per_lot: float,
    profit_to_account_rate: float,
) -> float:
    """Money lost by 1.00 lot if the stop is hit (account currency).

    sl_distance is measured from the expected FILL price (ask for buys, bid for sells),
    so the spread paid on entry is already inside it. Stops can slip: `slippage` is added.
    profit_to_account_rate converts profit currency (USD) to account currency
    (e.g. 1/EURUSD for an EUR account). Live code uses OrderCalcProfit instead.
    """
    if not is_pos(sl_distance):
        raise ValueError("sl_distance must be a finite number > 0")
    price_loss = (sl_distance + slippage) * spec.contract_size
    return price_loss * profit_to_account_rate + commission_per_lot


def size_position(
    budget: float,
    sl_distance: float,
    spec: SymbolSpec,
    *,
    slippage: float = 0.0,
    commission_per_lot: float = 0.0,
    profit_to_account_rate: float = 1.0,
) -> SizingResult:
    nan = float("nan")

    def reject(reason: str) -> SizingResult:
        return SizingResult(0.0, nan, nan, budget, reason)

    if (p := spec_problem(spec)) is not None:
        return reject(p)
    if not is_pos(sl_distance):
        return reject("INVALID_INPUT:sl_distance")
    if not is_nonneg(slippage):
        return reject("INVALID_INPUT:slippage")
    if not is_nonneg(commission_per_lot):
        return reject("INVALID_INPUT:commission")
    if not is_pos(profit_to_account_rate):
        return reject("INVALID_FX_RATE")
    if not (isinstance(budget, (int, float)) and math.isfinite(budget)):
        return reject("INVALID_INPUT:budget")
    if budget <= 0:
        return reject("NO_RISK_BUDGET")
    lpl = loss_per_lot(sl_distance, spec, slippage, commission_per_lot, profit_to_account_rate)
    if not is_pos(lpl):
        return reject("INVALID_LOSS_PER_LOT")
    raw_steps = budget / lpl / spec.volume_step
    max_steps = spec.volume_max / spec.volume_step + 1
    if not math.isfinite(raw_steps) or raw_steps > max_steps:   # audit L1: no overflow
        raw_steps = max_steps
    steps = math.floor(raw_steps + 1e-9)
    # guard against float artefacts: never exceed the budget
    while steps > 0 and steps * spec.volume_step * lpl > budget * (1 + 1e-12):
        steps -= 1
    volume = round(steps * spec.volume_step, _step_decimals(spec.volume_step))
    if volume > spec.volume_max:  # floor the cap to the step grid as well
        volume = round(math.floor(spec.volume_max / spec.volume_step + 1e-9) * spec.volume_step,
                       _step_decimals(spec.volume_step))
    if volume + 1e-12 < spec.volume_min:
        return SizingResult(0.0, spec.volume_min * lpl, lpl, budget, "MIN_VOLUME_EXCEEDS_RISK")
    return SizingResult(volume, volume * lpl, lpl, budget, "OK")
