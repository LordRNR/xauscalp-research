"""Broker feasibility profile (study 5), server-time rule verdict (study 4) and the MQL5
build tool. No Wine/MT5 needed: the build tool is tested on its pure parts."""
import math
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from xauscalp import mt5_build
from xauscalp.config import load_config
from xauscalp.data.server_time import fit_server_rule
from xauscalp.mt5_report import (
    BrokerReportError,
    broker_profile,
    compare_with_config,
    read_feasibility,
)

# Values from the user's real MetaQuotes-Demo report (2026-11-12), no account login.
REPORT = {
    "report_version": "0.10", "generated_gmt": "2026.11.12 23:33:24",
    "server_minus_gmt_seconds": "7200", "account_trade_mode": "ACCOUNT_TRADE_MODE_DEMO",
    "account_is_demo": "true", "account_company": "MetaQuotes Ltd.",
    "account_server": "MetaQuotes-Demo", "account_currency": "EUR", "account_leverage": "100",
    "account_margin_mode": "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", "account_balance": "1000.00",
    "account_equity": "1000.00", "account_margin_so_call": "50.00",
    "account_margin_so_so": "30.00", "terminal_trade_allowed": "false", "symbol": "XAUUSD",
    "symbol_calc_mode": "SYMBOL_CALC_MODE_CFDLEVERAGE", "symbol_trade_mode": "SYMBOL_TRADE_MODE_FULL",
    "currency_profit": "USD", "digits": "2", "point": "0.01", "contract_size": "100.0",
    "volume_min": "0.01", "volume_max": "100.0", "volume_step": "0.01", "tick_size": "0.01",
    "tick_value": "0.1", "stops_level_points": "0", "freeze_level_points": "0",
    "spread_float": "true", "spread_now_points": "21", "swap_mode": "SYMBOL_SWAP_MODE_POINTS",
    "swap_long": "-12.6", "swap_short": "-4.6", "bid": "3877.00", "ask": "3877.21",
    "spread_now_price": "0.21", "margin_for_0.010_lots": "35.08",
    "profit_per_1usd_move_0.010_lots": "0.9000", "profit_per_1usd_move_1.000_lots": "90.4700",
    "ordercheck_retcode": "10027", "ordercheck_comment": "AutoTrading disabled by client",
    "spread_sample_m1_bars": "29334", "spread_m1_p50_price": "0.18",
    "spread_m1_p90_price": "0.33", "spread_m1_p99_price": "0.42",
    "session_MONDAY": "00:00-23:00 ", "spread_mean_server_hour_10": "0.19",
}


def test_real_report_parses_and_is_consistent(tmp_path):
    f = tmp_path / "xau_feasibility.csv"
    f.write_text("".join(f"{k},{v}\r\n" for k, v in REPORT.items()))
    p = broker_profile(read_feasibility(f))
    assert p.is_demo and p.hedging and p.leverage == 100
    assert math.isclose(p.profit_to_account_rate, 0.9047)
    assert p.spec.contract_size == 100 and p.spec.volume_min == 0.01
    assert p.sessions["MONDAY"] == "00:00-23:00"
    assert p.spread_by_server_hour[10] == 0.19


@pytest.mark.parametrize("field,value,match", [
    ("contract_size", None, "missing"),
    ("bid", "nan", "non-finite"),
    ("ask", "abc", "non-numeric"),
    ("ask", "3876.00", "implausible"),               # ask < bid
    ("spread_m1_p90_price", "0.10", "implausible"),  # p90 < p50
    ("margin_for_0.010_lots", "3.50", "inconsistent"),
    ("report_version", "9.99", "unsupported"),
    ("currency_profit", "EUR", "implausible"),
    ("account_leverage", "0", "implausible"),
])
def test_bad_reports_are_rejected(field, value, match):
    rep = dict(REPORT)
    if value is None:
        rep.pop(field)
    else:
        rep[field] = value
    with pytest.raises(BrokerReportError, match=match):
        broker_profile(rep)


def test_comparison_flags_and_never_adopts_cheaper_costs():
    cfg = load_config()
    before = (cfg.costs, cfg.risk, cfg.symbol)
    by_area = {f.area: f for f in compare_with_config(broker_profile(REPORT), cfg)}
    assert by_area["account mode"].status == "MATCH"
    assert by_area["leverage"].status == "CONFIG_MORE_CONSERVATIVE"
    assert by_area["research cost model"].status == "UNKNOWN"
    assert by_area["commission (per lot, round turn)"].status == "UNKNOWN"
    assert (cfg.costs, cfg.risk, cfg.symbol) == before          # read-only comparison
    live = dict(REPORT, account_trade_mode="ACCOUNT_TRADE_MODE_REAL", account_is_demo="false")
    assert {f.area: f for f in compare_with_config(broker_profile(live), cfg)}[
        "account mode"].status == "BROKER_WORSE"


# ---------------------------------------------------------------- server-time rule verdict
def weekly_table(start: str, end: str, offset_of) -> pd.DataFrame:
    ws = pd.date_range(start + " 12:00", end, freq="7D")      # Saturdays, like WEEK_ANCHOR
    assert (ws.day_of_week == 5).all()
    mid = (ws + pd.Timedelta(days=3)).tz_localize("UTC")
    return pd.DataFrame({"week": range(len(ws)), "week_start_server": ws,
                         "offset_min": [offset_of(t) for t in mid], "confident": True})


def dst(zone):
    return lambda t: t.tz_convert(ZoneInfo(zone)).dst() != pd.Timedelta(0)


US, EU = dst("America/New_York"), dst("Europe/London")


def test_us_rule_identified_when_discriminating_weeks_exist():
    tab = weekly_table("2025-02-01", "2025-04-30", lambda t: 120 + 60 * US(t))
    v = fit_server_rule(tab)
    assert v.status == "CONSISTENT" and v.rule == "base+US_DST" and v.base_min == 120
    assert v.n_us_eu_discriminating >= 2
    assert v.cli_spec == "base_dst:120:America/New_York"
    assert v.ea_inputs == "InpTzPolicy=TZ_BASE_PLUS_US_DST, InpTzBaseMinutes=120"
    assert v.policy.kind == "base_dst"


def test_eu_rule_identified():
    v = fit_server_rule(weekly_table("2025-02-01", "2025-04-30", lambda t: 120 + 60 * EU(t)))
    assert (v.status, v.rule, v.base_min) == ("CONSISTENT", "base+EU_DST", 120)


def test_fixed_rule_identified_only_across_a_dst_switch():
    v = fit_server_rule(weekly_table("2025-02-01", "2025-04-30", lambda t: 0))
    assert (v.status, v.rule, v.base_min) == ("CONSISTENT", "fixed", 0)
    summer = fit_server_rule(weekly_table("2025-05-03", "2025-08-30", lambda t: 0))
    assert summer.status == "AMBIGUOUS"            # fixed vs DST rules not separable


def test_ambiguous_without_us_eu_discriminating_weeks():
    # Sep -> 18 Oct 2025: both zones on DST every week -> fixed/US/EU all fit
    v = fit_server_rule(weekly_table("2025-08-02", "2025-10-18", lambda t: 120 + 60 * US(t)))
    assert v.status == "AMBIGUOUS" and v.ea_inputs is None and v.policy is None


def test_late_october_week_separates_us_from_eu():
    v = fit_server_rule(weekly_table("2025-08-02", "2025-10-31", lambda t: 120 + 60 * US(t)),
                        min_confident=8)
    assert v.n_us_eu_discriminating == 1
    # one week fits US only, but DST-vs-fixed needs both regimes for US: still ambiguous
    assert v.status == "AMBIGUOUS"
    v2 = fit_server_rule(weekly_table("2024-08-03", "2025-10-31",
                                      lambda t: 120 + 60 * US(t)))
    assert (v2.status, v2.rule) == ("CONSISTENT", "base+US_DST")


def test_inconsistent_and_insufficient():
    tab = weekly_table("2025-02-01", "2025-04-30", lambda t: 120 + 60 * US(t))
    tab.loc[3, "offset_min"] = 0
    assert fit_server_rule(tab).status == "INCONSISTENT"
    assert fit_server_rule(tab.head(5)).status == "INSUFFICIENT"
    tab.loc[3, "confident"] = False                     # non-confident weeks are ignored
    assert fit_server_rule(tab).status == "CONSISTENT"


# ---------------------------------------------------------------------- MQL5 build tool
REAL_LOG = (
    "MQL5\\Experts\\XauScalp_ReadOnly.mq5 : information: compiling MQL5\\Experts\\XauScalp_ReadOnly.mq5\r\n"
    "MQL5\\Experts\\XauScalp_ReadOnly.mq5(21,11) : warning 68: version '0.10' is incompatible "
    "with MQL5 Market, must be xxx.yyy\r\n"
    "MQL5\\Experts\\x.mq5(5,3) : error 256: undeclared identifier\r\n"
    " : information: code generated\r\n"
    "Result: 1 errors, 1 warnings, 1120 ms elapsed, cpu='X64 Regular'\r\n")


def test_log_decoding_and_parsing():
    text = mt5_build.decode_log(b"\xff\xfe" + REAL_LOG.encode("utf-16-le"))
    r = mt5_build.parse_log("Experts/XauScalp_ReadOnly.mq5", text)
    assert (r.errors, r.warnings) == (1, 1)
    assert [d["kind"] for d in r.diagnostics] == ["warning", "error"]
    assert not r.ok
    assert mt5_build.parse_log("x", "no result line").errors is None


def test_repo_sources_have_no_trading_calls():
    assert mt5_build.trading_call_violations() == []


def test_sync_copies_new_files_never_deletes_and_refuses_trading_code(tmp_path, monkeypatch):
    src = tmp_path / "src"
    for rel in mt5_build.PROGRAMS + ["Include/XauScalp/A.mqh"]:
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("void OnStart(){}\n")
    term = tmp_path / "term"
    (term / "MQL5/Scripts").mkdir(parents=True)
    (term / "MQL5/Scripts/UserOwn.mq5").write_text("keep me")
    monkeypatch.setattr(mt5_build, "SRC", src)
    states = dict(mt5_build.sync(term))
    assert set(states.values()) == {"NEW"} and len(states) == len(mt5_build.PROGRAMS) + 1
    assert (term / "MQL5/Scripts/UserOwn.mq5").read_text() == "keep me"
    assert set(dict(mt5_build.sync(term)).values()) == {"SAME"}
    (src / "Include/XauScalp/A.mqh").write_text("// OrderSend in a comment is fine\n")
    assert dict(mt5_build.sync(term))["Include/XauScalp/A.mqh"] == "UPDATED"
    (src / "Include/XauScalp/A.mqh").write_text("void f(){ MqlTradeRequest r; OrderSend(r, x); }")
    with pytest.raises(RuntimeError, match="refusing to sync"):
        mt5_build.sync(term)


def test_fetch_copies_common_files_and_tester_agent_logs(tmp_path):
    prefix = tmp_path / "prefix"
    common = prefix / "drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    (common / "xauscalp").mkdir(parents=True)
    (common / "xau_feasibility.csv").write_text("a,b\n")
    (common / "xauscalp/decisions_parity1.csv").write_text("x\n")
    (common / "unrelated.txt").write_text("not ours")
    agent = prefix / mt5_build.TERMINAL_REL / "Tester/Agent-127.0.0.1-3000/MQL5/Files/xauscalp"
    agent.mkdir(parents=True)
    (agent / "decisions_parity2.csv").write_text("y\n")
    dest = tmp_path / "data"
    got = dict(mt5_build.fetch(prefix, dest))
    assert got == {"xau_feasibility.csv": "NEW", "xauscalp/decisions_parity1.csv": "NEW",
                   "agents/Agent-127.0.0.1-3000/xauscalp/decisions_parity2.csv": "NEW"}
    assert not (dest / "unrelated.txt").exists()
    assert set(dict(mt5_build.fetch(prefix, dest)).values()) == {"SAME"}


def test_preset_file_is_utf16_name_value_from_config(tmp_path):
    from xauscalp.config import load_config
    vals = mt5_build.ea_inputs(load_config(), "base_dst:120:America/New_York", log_tag="p1")
    files = mt5_build.write_preset(tmp_path, vals)
    assert len(files) == 2 and {f.parent.name for f in files} == {"Presets", "Tester"}
    f = files[0]
    assert all(g.name == mt5_build.PRESET_NAME and g.read_bytes() == f.read_bytes()
               for g in files) and f.read_bytes()[:2] == b"\xff\xfe"
    lines = dict(ln.split("=", 1) for ln in f.read_bytes().decode("utf-16").splitlines())
    assert lines["InpTzPolicy"] == "3" and lines["InpTzBaseMinutes"] == "120"
    assert lines["InpCostSlippage"] == "0.05" and lines["InpSlippage"] == "0.1"
    assert lines["InpLogTag"] == "p1"
