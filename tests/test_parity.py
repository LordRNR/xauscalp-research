"""Stage B parity tool: must detect real differences and never declare equivalence lightly."""
import numpy as np
import pandas as pd
import pytest

from xauscalp.config import CostModel
from xauscalp.parity import compare, python_records
from xauscalp.strategies.orb import ORBParams

P = [ORBParams("london", "Europe/London", "08:00", 15, 1.5, 1.5),
     ORBParams("newyork", "America/New_York", "08:20", 15, 1.5, 1.5)]


def market(days=30, seed=3):
    idx = pd.date_range("2025-01-06", periods=days * 1440, freq="1min", tz="UTC")
    idx = idx[idx.day_of_week < 5]
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 0.5, len(idx)))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"bid_o": o, "bid_h": np.maximum(o, c) + 0.2,
                       "bid_l": np.minimum(o, c) - 0.2, "bid_c": c}, index=idx)
    for x in "ohlc":
        df[f"ask_{x}"] = df[f"bid_{x}"] + 0.2
    df["volume"] = 1.0
    return df


def fake_ea_log(py: pd.DataFrame) -> pd.DataFrame:
    """What a faithful EA would log for the same data."""
    ea = pd.DataFrame({
        "day": py["day"], "session": py["session"], "status": py["status"],
        "direction": py["direction"], "or_high": py["or_high"], "or_low": py["or_low"],
        "atr_m5": py["atr_py"] * (1 + 1e-6), "sl_dist": py["sl_dist"] * (1 + 1e-6),
        "spread_now": py["spread_py"], "spread_bar": py["spread_py"],
        "bar_utc": pd.to_datetime(py["decision_time"].replace("", np.nan), utc=True)})
    return ea


def setup():
    py = python_records(market(), P, CostModel(0.0, 0.05, 0.0), max_spread=0.6)
    return py, fake_ea_log(py)


def test_faithful_ea_is_equivalent():
    py, ea = setup()
    rep = compare(ea, py)
    assert rep.compared >= 20 and rep.hard_mismatches == 0 and rep.equivalent, rep.verdict()


def test_direction_or_atr_errors_are_caught():
    py, ea = setup()
    i = ea.index[ea["status"] == "SIGNAL"][0]
    ea.loc[i, "direction"] *= -1
    j = ea.index[ea["status"].isin(["SIGNAL", "REJECT_COST", "REJECT_SPREAD"])][1]
    ea.loc[j, "atr_m5"] *= 1.01
    rep = compare(ea, py)
    assert not rep.equivalent and rep.hard_mismatches >= 2
    assert set(rep.detail.query("result == 'MISMATCH'")["why"].str.split(",").sum()) >= {"direction", "atr"}


def test_spread_only_difference_is_reported_not_hidden():
    py, ea = setup()
    i = ea.index[ea["status"] == "SIGNAL"][0]
    ea.loc[i, "status"] = "REJECT_SPREAD"
    rep = compare(ea, py)
    assert rep.spread_sensitive == 1 and rep.hard_mismatches == 0


def test_missing_rows_prevent_equivalence():
    py, ea = setup()
    rep = compare(ea.iloc[1:], py)
    assert rep.only_in_python == 1 and not rep.equivalent


def test_too_few_rows_is_not_proof():
    py, ea = setup()
    rep = compare(ea.iloc[:5], py.iloc[:5], min_compared=20)
    assert rep.hard_mismatches == 0 and not rep.equivalent


def test_duplicate_rows_from_appended_runs_are_rejected(tmp_path):
    from xauscalp.parity import DuplicateDecisionsError, read_ea_log
    f = tmp_path / "decisions_parity.csv"
    row = "2025.10.01 10:00:00,TESTER,x,london,2025-10-01,2025.10.01 08:15:00\n"
    f.write_text("logged_server,mode,tz_policy,session,day,bar_utc\n" + row + row)
    with pytest.raises(DuplicateDecisionsError, match="InpLogTag"):
        read_ea_log(f)


def test_restrict_days_is_inclusive_and_isolates_the_tester_window():
    from xauscalp.parity import restrict_days
    df = pd.DataFrame({"day": ["2025-08-29", "2025-09-01", "2025-10-31", "2025-11-03"],
                       "x": range(4)})
    assert list(restrict_days(df, "2025-09-01", "2025-10-31")["x"]) == [1, 2]


def test_partial_ea_run_is_not_equivalent_when_window_is_explicit():
    """An EA that stopped halfway must not pass just because we compare what it logged."""
    from xauscalp.parity import restrict_days
    py, ea = setup()
    window = (py["day"].min(), py["day"].max())
    half = ea[ea["day"] <= sorted(ea["day"].unique())[len(ea["day"].unique()) // 2]]
    assert compare(restrict_days(ea, *window), restrict_days(py, *window)).equivalent
    rep = compare(restrict_days(half, *window), restrict_days(py, *window))
    assert not rep.equivalent and rep.only_in_python > 0


def test_cli_rejects_a_window_inside_the_holdout(tmp_path):
    from xauscalp.parity import main
    f = tmp_path / "m1.csv"
    f.write_text("#point,0.01\ntime_server,open,high,low,close,tick_volume,spread_points\n")
    with pytest.raises(SystemExit):
        main(["--broker-m1", str(f), "--tz", "fixed:120", "--from", "2025-10-01",
              "--to", "2025-11-05", "--expected-out", str(tmp_path / "o.csv")])


def test_decision_bar_spread_difference_is_a_hard_mismatch():
    py, ea = setup()
    j = ea.index[ea["status"].isin(["SIGNAL", "REJECT_COST", "REJECT_SPREAD"])][0]
    ea.loc[j, "spread_bar"] += 0.05
    rep = compare(ea, py)
    assert not rep.equivalent
    assert "spread_bar" in rep.detail.loc[rep.detail["result"] == "MISMATCH", "why"].iloc[0]


def test_missing_spread_bar_is_not_silently_accepted():
    py, ea = setup()
    j = ea.index[ea["status"] == "SIGNAL"][0]
    ea.loc[j, "spread_bar"] = np.nan
    assert not compare(ea, py).equivalent


def test_spread_at_next_quote_is_informational_not_a_mismatch():
    """EA spread_now (quote at the first tick of bar i+1) differs from the decision bar's
    spread by design (2025-10-20: 0.06 vs 0.17). It must neither fail nor hide."""
    py, ea = setup()
    ea["spread_now"] = ea["spread_now"] * 0.3
    rep = compare(ea, py)
    assert rep.equivalent and rep.hard_mismatches == 0
    assert (rep.detail["spread_now_ea"] != rep.detail["spread_bar_ea"]).any()


def _ea_atr(m5: pd.DataFrame, decision: pd.Timestamp, *, window_s: int, min_bars: int):
    """Python mirror of AtrM5Wilder(): calendar window, closed bars only, seeded at the
    window's first bar, refuses fewer than `min_bars` bars."""
    from xauscalp.features.core import wilder_atr
    w = m5[(m5.index >= decision - pd.Timedelta(seconds=window_s))
           & (m5.index + pd.Timedelta(minutes=5) <= decision)]
    if len(w) < min_bars:
        return np.nan
    return float(wilder_atr(w["h"], w["l"], w["c"]).iloc[-1])


def test_atr_window_must_hold_enough_bars_on_monday_mornings():
    """Regression 2025-10-13/20: a 502-bar *calendar* window (41.8 h) holds ~110 M5 bars on
    Monday London because the market is closed at the weekend; the seed error
    (13/14)^110 gave 1.0-1.3e-3. A 10-day window with >=300 bars is exact to ~1e-9."""
    from xauscalp.features.core import resample_ohlc, wilder_atr
    m1 = market(days=40, seed=11)
    wild = (m1.index.day_of_week == 0) & (m1.index.hour == 0) & (m1.index.minute < 25)
    m1.loc[wild, "bid_h"] += 15.0                     # a violent Monday open, like a gap
    m1.loc[wild, "bid_l"] -= 15.0
    m5 = resample_ohlc(m1, "5min")
    full = wilder_atr(m5["h"], m5["l"], m5["c"])
    monday = pd.Timestamp("2025-02-03 07:20", tz="UTC")
    exact = float(full.loc[:monday - pd.Timedelta(minutes=5)].iloc[-1])
    short = _ea_atr(m5, monday, window_s=502 * 300, min_bars=14)
    good = _ea_atr(m5, monday, window_s=10 * 86400, min_bars=300)
    assert abs(good / exact - 1) < 1e-6
    assert abs(short / exact - 1) > 1e-6         # the old window really was inexact here
    assert np.isnan(_ea_atr(m5, monday, window_s=502 * 300, min_bars=300))   # fails closed
