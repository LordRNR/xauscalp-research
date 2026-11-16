"""Prop-firm rules, replay and Monte Carlo: rule semantics must be exact and fail-closed."""
import math

import numpy as np
import pandas as pd
import pytest

from xauscalp.propfirm.montecarlo import McConfig, run_mc, weeks_from_trades
from xauscalp.propfirm.replay import replay, trade_mae_r
from xauscalp.propfirm.rules import (
    Observation,
    Phase,
    PropChecker,
    RulesError,
    Status,
    load_rules,
    news_violations,
    news_windows,
    size_lots,
)

R = load_rules()
INI = 10_000.0


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_rules_file_matches_the_firms_published_numbers_and_flags_what_is_unverified():
    assert R.max_daily_loss_pct == 5 and R.max_loss_pct == 10 and R.tz == "Europe/Prague"
    assert R.phases["challenge"].profit_target_pct == 10 and R.phases["verification"].profit_target_pct == 5
    assert R.phases["challenge"].min_trading_days == 4 and R.phases["funded"].profit_target_pct is None
    assert R.news_window_min == 2 and R.news_phases == ("funded",)
    assert any("contract size" in u for u in R.unverified) and any("14 days" in u or "Free Trial" in u for u in R.unverified)


def test_loader_is_fail_closed(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("firm: X\n")
    with pytest.raises(RulesError):
        load_rules(p)
    bad = (load_rules.__globals__["DEFAULT_RULES"]).read_text().replace("max_daily_loss_pct: 5.0", "max_daily_loss_pct: 20.0")
    p.write_text(bad)
    with pytest.raises(RulesError):
        load_rules(p)


def test_floating_loss_counts_and_daily_limit_resets_at_prague_midnight():
    c = PropChecker(R, Phase.CHALLENGE, INI)
    # 2025-10-10 22:30 UTC = 00:30 CEST on the 11th: a NEW day starts with balance 10_000
    assert c.update(Observation(ts("2025-10-10 20:00"), INI, INI)) is Status.RUNNING
    assert c.update(Observation(ts("2025-10-10 21:00"), INI, INI - 480, positions_open=1)) is Status.RUNNING
    assert c.update(Observation(ts("2025-10-10 21:30"), INI, INI - 500, positions_open=1)) is Status.FAILED
    assert c.reason == "MAX_DAILY_LOSS"                       # floating loss, no closed trade needed
    c2 = PropChecker(R, Phase.CHALLENGE, INI)
    c2.update(Observation(ts("2025-10-10 20:00"), INI, INI))
    c2.update(Observation(ts("2025-10-10 21:30"), 9_600, 9_600))      # closed -400 on day 1
    # after the midnight reset the daily start balance is 9_600 -> limit 9_100 (not 9_500)
    assert c2.update(Observation(ts("2025-10-10 22:30"), 9_600, 9_200)) is Status.RUNNING
    assert c2.update(Observation(ts("2025-10-10 22:40"), 9_600, 9_100)) is Status.FAILED


def test_static_max_loss_and_nonfinite_values_fail_closed():
    c = PropChecker(R, Phase.CHALLENGE, INI)
    day = ts("2025-01-06 10:00")
    bal = INI
    for i in range(2):                                      # -4 % of the initial capital per day
        bal -= 400
        assert c.update(Observation(day + pd.Timedelta(days=i), bal, bal)) is Status.RUNNING
    assert c.update(Observation(day + pd.Timedelta(days=2), 9_201, 9_201)) is Status.RUNNING
    assert c.update(Observation(day + pd.Timedelta(days=2, hours=1), 9_201, 9_000)) is Status.FAILED
    assert c.reason == "MAX_LOSS"                           # static: initial capital minus 10 %
    c2 = PropChecker(R, Phase.CHALLENGE, INI)
    assert c2.update(Observation(ts("2025-01-06 10:00"), math.nan, INI)) is Status.FAILED
    assert c2.reason == "INVALID_ACCOUNT_VALUES"


def test_target_needs_flat_book_and_four_trading_days():
    c = PropChecker(R, Phase.CHALLENGE, INI)
    for i in range(3):
        c.update(Observation(ts("2025-01-06 10:00") + pd.Timedelta(days=i), INI, INI, opened_position=True))
    assert c.update(Observation(ts("2025-01-09 10:00"), 11_050, 11_050, positions_open=0)) is Status.RUNNING   # 3 days
    c.update(Observation(ts("2025-01-09 10:01"), 11_050, 11_050, positions_open=1, opened_position=True))        # 4th day
    assert c.update(Observation(ts("2025-01-09 12:00"), 11_050, 11_050, positions_open=1)) is Status.RUNNING   # not flat
    assert c.update(Observation(ts("2025-01-09 13:00"), 11_050, 11_050, positions_open=0)) is Status.PASSED


def test_news_windows_are_plus_minus_two_minutes_including_sl_tp_times():
    ev = pd.DataFrame({"utc_time": [ts("2025-10-24 12:30")], "event": ["CPI"], "impact": ["high"]})
    w = news_windows(ev, R)
    inside = pd.DatetimeIndex([ts("2025-10-24 12:28"), ts("2025-10-24 12:32")])
    outside = pd.DatetimeIndex([ts("2025-10-24 12:27:59"), ts("2025-10-24 12:32:01")])
    assert len(news_violations(inside, w)) == 2 and news_violations(outside, w) == []


def test_lot_sizing_floors_and_refuses_when_unsizeable():
    assert size_lots(50, 12.0) == 0.04                       # 50/(12*100)=0.0416 -> 0.04
    assert size_lots(5, 12.0) == 0.0                          # below 0.01 lot: cannot size
    for bad in (math.nan, 0, -1):
        assert size_lots(bad, 5) == 0.0 and size_lots(50, bad) == 0.0


def _m1(n=3000):
    idx = pd.date_range("2025-03-03 08:00", periods=n, freq="1min", tz="UTC")
    c = 2000 + np.zeros(n)
    df = pd.DataFrame({"bid_o": c, "bid_h": c + 0.1, "bid_l": c - 0.1, "bid_c": c, "ask_h": c + 0.3}, index=idx)
    return df


def test_replay_detects_an_intrabar_floating_breach_without_a_closed_loss():
    m1 = _m1()
    m1.loc[m1.index[100], "bid_l"] = 1980.0                   # a spike low inside the trade
    tr = pd.DataFrame({"entry_time": [m1.index[50]], "exit_time": [m1.index[200]], "direction": [1],
                       "entry": [2000.0], "sl_dist": [25.0], "pnl_price": [5.0]})
    # risk 1 % of 10k = 100 USD at 25 USD stop -> 0.04 lot; adverse 20 USD x 0.04 x 100 = 80 USD only
    ok = replay(tr, m1, R, Phase.CHALLENGE, INI, 1.0, commission_per_lot=0.0)
    assert ok["status"] == "RUNNING"
    m1.loc[m1.index[100], "bid_l"] = 1500.0
    bad = replay(tr, m1, R, Phase.CHALLENGE, INI, 1.0, commission_per_lot=0.0)
    assert bad["status"] == "FAILED" and bad["reason"] in ("MAX_DAILY_LOSS", "MAX_LOSS")
    assert bad["trades_taken"] == 0                            # it never even closed


def test_trade_mae_in_r():
    m1 = _m1()
    m1.loc[m1.index[100], "bid_l"] = 1990.0
    tr = pd.DataFrame({"entry_time": [m1.index[50]], "exit_time": [m1.index[200]], "direction": [1],
                       "entry": [2000.0], "sl_dist": [20.0]})
    assert trade_mae_r(tr, m1)[0] == pytest.approx(0.5)


def _weeks(mean_r, seed=1, n=104, per=4):
    rng = np.random.default_rng(seed)
    return [np.column_stack([np.sort(rng.integers(0, 5, per)), rng.normal(mean_r, 1.0, per),
                             np.abs(rng.normal(0.3, 0.2, per))]) for _ in range(n)]


def test_monte_carlo_is_reproducible_and_edge_raises_the_pass_probability():
    cfg = McConfig(outer=8, inner=60, risk_pct=0.5)
    a = run_mc(_weeks(0.3), cfg, R)
    b = run_mc(_weeks(0.3), cfg, R)
    assert a["p_both"] == b["p_both"] and a["ev_eur"] == b["ev_eur"]                  # reproducible
    none = run_mc(_weeks(0.0), cfg, R)
    assert a["p_challenge"][1] > none["p_challenge"][1]
    nul = run_mc(_weeks(0.3), cfg, R, null=True)
    assert nul["p_challenge"][1] < a["p_challenge"][1]                                  # the null control
    assert 0 <= a["p_fail"][1] <= 1 and a["p_challenge"][0] <= a["p_challenge"][2]


def test_weeks_from_trades_keeps_empty_weeks():
    t = pd.DataFrame({"entry_time": pd.to_datetime(["2025-01-06 10:00", "2025-01-27 10:00"], utc=True)})
    w = weeks_from_trades(t, np.array([1.0, -1.0]), np.array([0.2, 0.4]))
    assert len(w) == 4 and len(w[1]) == 0 and len(w[0]) == 1
