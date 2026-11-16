from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signal:
    """A trade PROPOSAL. It has no authority: the Risk Manager approves or rejects it.

    decision_idx is the M1 row at whose CLOSE the decision is taken; execution happens at
    the OPEN of the next row. Distances are in price units (USD per oz) from the fill.
    """

    decision_idx: int
    direction: int            # +1 long, -1 short
    sl_dist: float
    tp_dist: float
    max_hold_min: int
    strategy: str
    session: str
    context: dict = field(default_factory=dict)
