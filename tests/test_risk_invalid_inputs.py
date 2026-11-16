"""Regression tests (audit 2026-11-12, finding R1): anomalous inputs must REJECT, never
approve and never raise. Before the fix NaN spread / NaN data age / NaN free margin /
kill_switch=None were APPROVED."""
import math
from pathlib import Path

import pytest
import yaml

from xauscalp.config import ConfigError, CostModel, RiskConfig, SymbolSpec, load_config
from xauscalp.risk.manager import AccountState, MarketState, RiskManager, TradeProposal
from xauscalp.risk.sizing import size_position

NAN, INF = math.nan, math.inf
SPEC = SymbolSpec()
CFG = RiskConfig(expected_slippage_usd=0.01)
ACCT = dict(equity=1000, free_margin=1000, day_start_equity=1000, week_start_equity=1000,
            peak_equity=1000, open_positions=0, trades_today=0)
MKT = dict(bid=2000.0, ask=2000.3, data_age_s=1.0)
PROP = dict(direction=1, entry_price=2000.3, sl_price=1997.3, tp_price=2006.3, strategy="t")


def evaluate(acct=None, mkt=None, prop=None, rm=None):
    rm = rm or RiskManager(CFG, SPEC)
    return rm.evaluate(TradeProposal(**{**PROP, **(prop or {})}),
                       AccountState(**{**ACCT, **(acct or {})}),
                       MarketState(**{**MKT, **(mkt or {})}))


def test_baseline_is_approved():
    assert evaluate().approved


BAD_ACCT = [("equity", NAN), ("equity", INF), ("equity", 0), ("equity", -5),
            ("free_margin", NAN), ("free_margin", -1), ("free_margin", INF),
            ("day_start_equity", NAN), ("week_start_equity", 0), ("peak_equity", -INF),
            ("open_positions", -1), ("open_positions", 0.5), ("trades_today", None),
            ("consecutive_errors", NAN), ("kill_switch", None), ("kill_switch", "false"),
            ("drawdown_lock", None)]


@pytest.mark.parametrize("field,value", BAD_ACCT)
def test_invalid_account_rejects(field, value):
    d = evaluate(acct={field: value})
    assert not d.approved and d.volume == 0 and d.reasons


BAD_MKT = [("bid", NAN), ("ask", NAN), ("ask", INF), ("bid", 0), ("ask", -1),
           ("ask", 1999.0),                   # negative spread (ask < bid)
           ("ask", 2000.0),                   # zero spread
           ("data_age_s", NAN), ("data_age_s", -1), ("data_age_s", INF),
           ("market_open", None), ("news_blackout", None)]


@pytest.mark.parametrize("field,value", BAD_MKT)
def test_invalid_market_rejects(field, value):
    d = evaluate(mkt={field: value})
    assert not d.approved and d.volume == 0


BAD_PROP = [("entry_price", NAN), ("entry_price", 0), ("sl_price", NAN), ("sl_price", -1),
            ("sl_price", INF), ("tp_price", NAN), ("direction", 0), ("direction", True),
            ("entry_price", 1500.0)]          # far from live quote -> ENTRY_PRICE_MISMATCH


@pytest.mark.parametrize("field,value", BAD_PROP)
def test_invalid_proposal_rejects(field, value):
    d = evaluate(prop={field: value})
    assert not d.approved and d.volume == 0


@pytest.mark.parametrize("kw", [dict(profit_to_account_rate=NAN),
                                dict(profit_to_account_rate=0),
                                dict(profit_to_account_rate=-1.1),
                                dict(leverage=0), dict(leverage=NAN)])
def test_invalid_fx_or_leverage_rejects(kw):
    assert not evaluate(rm=RiskManager(CFG, SPEC, **kw)).approved


@pytest.mark.parametrize("spec", [SymbolSpec(volume_step=0), SymbolSpec(volume_min=NAN),
                                  SymbolSpec(contract_size=-100),
                                  SymbolSpec(volume_min=1, volume_max=0.5)])
def test_invalid_spec_rejects_without_exception(spec):
    assert not evaluate(rm=RiskManager(CFG, spec)).approved


@pytest.mark.parametrize("args", [(NAN, 1.0), (INF, 1.0), (5.0, NAN), (5.0, 0), (5.0, -1)])
def test_sizing_invalid_inputs_return_zero_volume(args):
    s = size_position(*args, SPEC)
    assert s.volume == 0 and s.reason != "OK"


def test_sizing_volume_max_is_floored_to_step():
    s = size_position(1e9, 1.0, SymbolSpec(volume_step=0.03, volume_min=0.03, volume_max=1.0))
    assert s.volume == pytest.approx(0.99) and s.volume <= 1.0


# ---------------- config ----------------
@pytest.mark.parametrize("kw", [dict(risk_per_trade_pct=NAN), dict(daily_loss_limit_pct=INF),
                                dict(max_spread_usd=0), dict(max_trades_per_day=2.5),
                                dict(max_open_positions=True), dict(risk_per_trade_pct="0.5")])
def test_risk_config_rejects_bad_values(kw):
    with pytest.raises(ConfigError):
        RiskConfig(**kw)


def test_cost_model_rejects_nan():
    with pytest.raises(ConfigError):
        CostModel(slippage_usd=NAN)


def _write(tmp_path, mutate):
    raw = yaml.safe_load(Path("config/default.yaml").read_text())
    mutate(raw)
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(raw))
    return p


@pytest.mark.parametrize("mutate", [
    lambda r: r["risk"].pop("daily_loss_limit_pct"),       # incomplete -> no silent default
    lambda r: r["risk"].update(typo_limit=1),               # unknown key
    lambda r: r.pop("costs"),                               # missing section
    lambda r: r["symbol"].update(volume_step=0),            # invalid spec
    lambda r: r["validation"].pop("holdout_start"),         # lockbox date required
    lambda r: r.update(mode="PAPER"),
])
def test_incomplete_or_invalid_yaml_fails(tmp_path, mutate):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, mutate))
