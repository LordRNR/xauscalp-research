import pytest

from xauscalp.config import ConfigError, RiskConfig, SymbolSpec, load_config
from xauscalp.risk.manager import AccountState, MarketState, RiskManager, TradeProposal
from xauscalp.risk.sizing import size_position

SPEC = SymbolSpec(contract_size=100, volume_min=0.01, volume_step=0.01, volume_max=50)


# ---------- sizing ----------
def test_volume_is_floored_never_rounded_up():
    # budget 5 USD, SL 2 USD -> loss/lot 200 -> raw 0.025 lots -> must be 0.02, not 0.03
    s = size_position(5.0, 2.0, SPEC)
    assert s.volume == 0.02
    assert s.risk_money <= 5.0


def test_min_volume_exceeding_risk_is_rejected():
    # 20 EUR account, 0.5% = 0.10 budget; 0.01 lot with 3 USD stop risks 3 USD
    s = size_position(0.10, 3.0, SPEC)
    assert s.volume == 0.0
    assert s.reason == "MIN_VOLUME_EXCEEDS_RISK"
    assert s.risk_money == pytest.approx(3.0)


def test_slippage_commission_and_fx_reduce_volume():
    base = size_position(10.0, 2.0, SPEC)
    worse = size_position(10.0, 2.0, SPEC, slippage=0.5, commission_per_lot=7.0,
                          profit_to_account_rate=1 / 1.10)
    assert worse.volume <= base.volume
    assert worse.risk_money <= 10.0


@pytest.mark.parametrize("budget", [0.3, 1.99, 2.0, 2.01, 7.77, 123.45])
def test_risk_never_exceeds_budget(budget):
    s = size_position(budget, 1.0, SPEC)
    assert s.volume == 0 or s.risk_money <= budget + 1e-9


def test_volume_capped_at_max():
    assert size_position(1e9, 1.0, SPEC).volume == SPEC.volume_max


# ---------- config hard limits ----------
def test_config_cannot_exceed_hard_ceiling():
    with pytest.raises(ConfigError):
        RiskConfig(risk_per_trade_pct=2.0)
    with pytest.raises(ConfigError):
        RiskConfig(max_open_positions=2)


def test_default_config_loads_and_is_not_live():
    cfg = load_config()
    assert cfg.mode != "LIVE"
    assert cfg.risk.risk_per_trade_pct <= 0.5


# ---------- risk manager ----------
def _acct(**kw):
    base = dict(equity=1000, free_margin=1000, day_start_equity=1000, week_start_equity=1000,
                peak_equity=1000, open_positions=0, trades_today=0)
    base.update(kw)
    return AccountState(**base)


MKT = MarketState(bid=2000.0, ask=2000.3, data_age_s=1)
RM = RiskManager(RiskConfig(expected_slippage_usd=0.01), SPEC, leverage=20)


def _buy(sl=1997.3, tp=2006.3):
    return TradeProposal(direction=1, entry_price=2000.3, sl_price=sl, tp_price=tp, strategy="t")


def test_happy_path_approved_and_within_budget():
    d = RM.evaluate(_buy(), _acct(), MKT)
    assert d.approved, d.reasons
    assert d.risk_money <= 1000 * 0.005 + 1e-9


def test_missing_or_wrong_side_sl_rejected():
    assert "SL_MISSING" in RM.evaluate(_buy(sl=None), _acct(), MKT).reasons
    assert "SL_WRONG_SIDE" in RM.evaluate(_buy(sl=2001), _acct(), MKT).reasons


def test_small_account_rejected_not_forced():
    d = RM.evaluate(_buy(), _acct(equity=20, free_margin=20, day_start_equity=20,
                                  week_start_equity=20, peak_equity=20), MKT)
    assert not d.approved
    assert "MIN_VOLUME_EXCEEDS_RISK" in d.reasons


@pytest.mark.parametrize("kw,code", [
    (dict(kill_switch=True), "KILL_SWITCH"),
    (dict(open_positions=1), "MAX_OPEN_POSITIONS"),
    (dict(trades_today=3), "MAX_TRADES_PER_DAY"),
    (dict(equity=979, day_start_equity=1000), "DAILY_LOSS_LIMIT"),
    (dict(equity=949, week_start_equity=1000, day_start_equity=949), "WEEKLY_LOSS_LIMIT"),
    (dict(equity=919, peak_equity=1000, week_start_equity=919, day_start_equity=919),
     "MAX_DRAWDOWN"),
    (dict(consecutive_errors=3), "PAUSED_AFTER_ERRORS"),
    (dict(drawdown_lock=True), "DRAWDOWN_LOCK"),
])
def test_blocking_conditions(kw, code):
    d = RM.evaluate(_buy(), _acct(**kw), MKT)
    assert not d.approved and code in d.reasons


def test_market_conditions_block():
    wide = MarketState(bid=2000, ask=2001, data_age_s=1)
    stale = MarketState(bid=2000, ask=2000.3, data_age_s=60)
    assert "SPREAD_TOO_WIDE" in RM.evaluate(_buy(), _acct(), wide).reasons
    assert "STALE_DATA" in RM.evaluate(_buy(), _acct(), stale).reasons
    news = MarketState(bid=2000, ask=2000.3, data_age_s=1, news_blackout=True)
    assert "NEWS_BLACKOUT" in RM.evaluate(_buy(), _acct(), news).reasons


def test_remaining_daily_budget_caps_trade_risk():
    # down 1.9% today: only 0.1% left (1 EUR) -> trade must be sized to <= 1 EUR or rejected
    acct = _acct(equity=981, day_start_equity=1000, peak_equity=1000, week_start_equity=1000)
    d = RM.evaluate(_buy(), acct, MKT)
    assert (not d.approved) or d.risk_money <= 1.0 + 1e-9


def test_all_reasons_reported_not_short_circuited():
    d = RM.evaluate(_buy(sl=None), _acct(kill_switch=True, open_positions=1), MKT)
    assert {"KILL_SWITCH", "MAX_OPEN_POSITIONS", "SL_MISSING"} <= set(d.reasons)


def test_margin_check():
    d = RM.evaluate(_buy(), _acct(free_margin=50), MKT)
    assert "INSUFFICIENT_MARGIN" in d.reasons
