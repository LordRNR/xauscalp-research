"""Regression tests for the independent risk-auditor findings (2026-11-12)."""
import hashlib
from pathlib import Path

import pytest
import yaml

from xauscalp import modes
from xauscalp.config import HARD_LIMITS, ConfigError, RiskConfig, SymbolSpec
from xauscalp.risk.manager import AccountState, MarketState, RiskManager, TradeProposal
from xauscalp.risk.sizing import size_position

ROOT = Path(__file__).parents[1]
RM = RiskManager(RiskConfig(), SymbolSpec(), leverage=20)
BIG = AccountState(100_000, 100_000, 100_000, 100_000, 100_000, 0, 0)
MKT = MarketState(bid=3999.6, ask=4000.0, data_age_s=1)
SLIP = RiskConfig().expected_slippage_usd


# ---- H1: size from the worst of proposal entry and live quote -----------------------
def test_h1_stale_low_entry_cannot_oversize():
    """Auditor repro: entry 3996.1 while ask is 4000 -> previously 1.38 lots, real loss
    ~1035 (1.03% > 1% hard ceiling)."""
    d = RM.evaluate(TradeProposal(1, 3996.1, 3992.6, None, "t"), BIG, MKT)
    assert d.approved
    real_loss = d.volume * 100 * (4000.0 - 3992.6 + SLIP)
    assert real_loss <= 100_000 * 0.005 + 1e-6


def test_h1_sell_uses_bid():
    d = RM.evaluate(TradeProposal(-1, 4003.0, 4007.0, None, "t"), BIG, MKT)
    assert d.approved
    assert d.volume * 100 * (4007.0 - 3999.6 + SLIP) <= 500 + 1e-6


@pytest.mark.parametrize("direction,entry,sl", [
    (1, 4000.0, 3999.8),    # buy SL between bid and ask: triggers immediately
    (1, 3996.1, 4000.4),    # buy SL above the ask
    (-1, 3999.6, 3999.9),   # sell SL between bid and ask
    (-1, 3999.6, 3999.0),   # sell SL below the bid
])
def test_h1_stop_on_wrong_side_of_live_market_rejected(direction, entry, sl):
    d = RM.evaluate(TradeProposal(direction, entry, sl, None, "t"), BIG, MKT)
    assert not d.approved
    assert {"SL_WRONG_SIDE", "SL_WRONG_SIDE_OF_MARKET"} & set(d.reasons)


# ---- L2: stale peak below equity must not loosen the drawdown allowance --------------
def test_l2_peak_below_equity_uses_equity():
    acct = AccountState(1000, 1000, 1000, 1000, 900, 0, 0)
    assert RM.remaining_loss_budget(acct) <= 1000 * 0.02 + 1e-9


# ---- L1: no overflow on absurd inputs ------------------------------------------------
def test_l1_tiny_stop_huge_budget_no_exception():
    assert size_position(1e10, 5e-324, SymbolSpec()).volume <= SymbolSpec().volume_max


# ---- M2: sanity bounds --------------------------------------------------------------
@pytest.mark.parametrize("kw", [dict(max_spread_usd=1e9), dict(max_data_age_s=1e9),
                                dict(max_consecutive_errors=10**9),
                                dict(expected_slippage_usd=0.0)])
def test_m2_unbounded_fields_rejected(kw):
    with pytest.raises(ConfigError):
        RiskConfig(**kw)


# ---- tripwires: values only the USER may change --------------------------------------
# sha256 of src/xauscalp/modes.py, unchanged since commit 94b74bf (verified 2026-11-12).
# A legitimate change by the user must update this pin in the same reviewed commit.
MODES_SHA256 = "7836f5548c2fb6cd89bb740a3dbe6a44d69ca41534586d0b585835b0cfcd475e"


def test_tripwire_live_lock_file_unchanged():
    assert modes.LIVE_PHASE_UNLOCKED is False
    digest = hashlib.sha256((ROOT / "src/xauscalp/modes.py").read_bytes()).hexdigest()
    assert digest == MODES_SHA256, "modes.py changed: the LIVE lock must be reviewed by the user"


def test_tripwire_hard_limits_unchanged():
    assert HARD_LIMITS == {"risk_per_trade_pct": 1.0, "daily_loss_limit_pct": 3.0,
                           "weekly_loss_limit_pct": 6.0, "max_drawdown_pct": 10.0,
                           "max_open_positions": 1, "max_trades_per_day": 10,
                           "max_margin_usage_pct": 50.0}


def test_tripwire_holdout_start_pinned():
    raw = yaml.safe_load((ROOT / "config/default.yaml").read_text())
    assert str(raw["validation"]["holdout_start"]) == "2025-11-01"
