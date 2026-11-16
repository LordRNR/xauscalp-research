"""Static guarantees on MQL5 sources (no compiler on macOS yet, so these are text checks).

- Stage A EA + includes + scripts contain NO trading calls.
- The EA refuses non-demo accounts.
- Hard ceilings in RiskGuard.mqh equal HARD_LIMITS in Python.
- Every MQL5 file declares its compile status honestly.
"""
import re
from pathlib import Path

import pytest

from xauscalp.config import HARD_LIMITS

MT5 = Path(__file__).parents[1] / "mt5"
from xauscalp.mql5_scan import FORBIDDEN, strip_comments, violations

READ_ONLY_FILES = sorted([*MT5.glob("Experts/XauScalp_ReadOnly.mq5"),
                          *MT5.glob("Include/XauScalp/*.mqh"), *MT5.glob("Scripts/*.mq5")])


@pytest.mark.parametrize("path", READ_ONLY_FILES, ids=lambda p: p.name)
def test_no_trading_calls(path):
    assert violations([path.relative_to(MT5)], MT5) == [], f"trading call in {path}"


@pytest.mark.parametrize("path", READ_ONLY_FILES, ids=lambda p: p.name)
def test_compile_status_declared(path):
    assert "STATUS: NOT YET COMPILED" in path.read_text() or "STATUS: COMPILED" in path.read_text()


def test_feasibility_uses_ordercheck_only():
    src = strip_comments((MT5 / "Scripts/XAU_FeasibilityReport.mq5").read_text())
    assert "OrderCheck(" in src and "OrderSend" not in src


def test_ea_refuses_non_demo_accounts():
    src = strip_comments((MT5 / "Experts/XauScalp_ReadOnly.mq5").read_text())
    assert "ACCOUNT_TRADE_MODE_DEMO" in src and "INIT_FAILED" in src


def test_mql5_hard_ceilings_match_python():
    src = (MT5 / "Include/XauScalp/RiskGuard.mqh").read_text()
    defs = {k: float(v) for k, v in re.findall(r"#define (HARD_\w+)\s+([\d.]+)", src)}
    mapping = {"risk_per_trade_pct": "HARD_MAX_RISK_PCT",
               "daily_loss_limit_pct": "HARD_MAX_DAILY_LOSS_PCT",
               "weekly_loss_limit_pct": "HARD_MAX_WEEKLY_LOSS_PCT",
               "max_drawdown_pct": "HARD_MAX_DRAWDOWN_PCT",
               "max_open_positions": "HARD_MAX_POSITIONS",
               "max_trades_per_day": "HARD_MAX_TRADES_PER_DAY",
               "max_margin_usage_pct": "HARD_MAX_MARGIN_USAGE"}
    for py, mq in mapping.items():
        assert defs[mq] == HARD_LIMITS[py], (py, defs[mq], HARD_LIMITS[py])


def test_orb_statuses_match_python():
    from xauscalp.strategies.orb import STATUSES
    src = (MT5 / "Include/XauScalp/OrbSignal.mqh").read_text()
    for s in STATUSES:
        assert f'"{s}"' in src, s


def test_mql5_sanity_bounds_match_python():
    from xauscalp.config import SANITY_BOUNDS
    src = (MT5 / "Include/XauScalp/RiskGuard.mqh").read_text()
    d = {k: float(v) for k, v in re.findall(r"#define (SANE_\w+)\s+([\d.]+)", src)}
    assert (d["SANE_MIN_SPREAD"], d["SANE_MAX_SPREAD"]) == SANITY_BOUNDS["max_spread_usd"]
    assert (d["SANE_MIN_AGE_S"], d["SANE_MAX_AGE_S"]) == SANITY_BOUNDS["max_data_age_s"]
    assert (d["SANE_MIN_ERRORS"], d["SANE_MAX_ERRORS"]) == SANITY_BOUNDS["max_consecutive_errors"]
    assert (d["SANE_MIN_SLIP"], d["SANE_MAX_SLIP"]) == SANITY_BOUNDS["expected_slippage_usd"]


def test_riskguard_uses_live_quote_and_levels():
    src = strip_comments((MT5 / "Include/XauScalp/RiskGuard.mqh").read_text())
    for token in ("SL_WRONG_SIDE_OF_MARKET", "worst_entry", "SYMBOL_TRADE_FREEZE_LEVEL",
                  "TimeTradeServer() - tk.time", "NEWS_CALENDAR_MISSING", "DEAL_ENTRY_INOUT"):
        assert token in src, token


# --- EA defaults must mirror config/default.yaml (a mismatch silently breaks parity:
#     2026-11-14 the ORB cost filter used the risk slippage 0.10 instead of 0.05) ---
def ea_input_defaults() -> dict[str, str]:
    src = strip_comments((MT5 / "Experts/XauScalp_ReadOnly.mq5").read_text())
    return {m.group(1): m.group(2).strip().strip('"')
            for m in re.finditer(r"^input\s+\w+\s+(\w+)\s*=\s*([^;]+);", src, re.MULTILINE)}


def test_ea_defaults_mirror_config():
    from xauscalp.config import load_config
    from xauscalp.mt5_build import ea_inputs
    cfg = load_config()
    expected = ea_inputs(cfg, "fixed:0")                 # tz values are run-specific
    ea = ea_input_defaults()
    skip = {"InpTzPolicy", "InpTzBaseMinutes", "InpLogTag", "InpSymbol"}
    for k, v in expected.items():
        if k in skip:
            continue
        assert k in ea, f"EA lacks input {k}"
        try:
            assert float(ea[k]) == float(v), (k, ea[k], v)
        except ValueError:
            assert ea[k] == v, (k, ea[k], v)


def test_preset_covers_every_strategy_and_risk_input():
    from xauscalp.config import load_config
    from xauscalp.mt5_build import ea_inputs
    ea = set(ea_input_defaults())
    preset = set(ea_inputs(load_config(), "base_dst:120:America/New_York"))
    assert preset <= ea, preset - ea
    assert ea - preset == {"InpMagic", "InpNewsFile", "InpNewsBeforeMin", "InpNewsAfterMin",
                           "InpTesterStopUtc"}


def test_preset_rejects_unverifiable_tz_and_off_grid_params():
    from xauscalp.config import load_config
    from xauscalp.mt5_build import ea_inputs, tz_spec_to_ea
    assert tz_spec_to_ea("base_dst:120:America/New_York") == (3, 120)
    assert tz_spec_to_ea("base_dst:120:Europe/London") == (4, 120)
    assert tz_spec_to_ea("fixed:0") == (2, 0)
    for bad in ("iana:Europe/Athens", "base_dst:120:Asia/Tokyo", "unknown"):
        with pytest.raises(ValueError):
            tz_spec_to_ea(bad)
    with pytest.raises(ValueError, match="grid"):
        ea_inputs(load_config(), "fixed:0", sl_atr=1.25)


def test_export_defaults_stay_before_holdout():
    src = (MT5 / "Scripts/XAU_ExportTicks.mq5").read_text()
    to = re.search(r"InpTo\s*=\s*D'(\d{4})\.(\d{2})\.(\d{2})", src).groups()
    assert "-".join(to) <= "2025-11-01"


def test_atr_window_is_calendar_days_with_a_minimum_bar_count():
    """Regression (parity 2025-10-13/20): never size the ATR window as N bars * 300 s."""
    src = (MT5 / "Include/XauScalp/OrbSignal.mqh").read_text()
    days = int(re.search(r"#define\s+ATR_LOOKBACK_DAYS\s+(\d+)", src).group(1))
    min_bars = int(re.search(r"#define\s+ATR_MIN_BARS\s+(\d+)", src).group(1))
    assert days >= 7 and min_bars >= 300 and (13 / 14) ** min_bars < 1e-8
    assert "* 300," not in src.split("double AtrM5Wilder")[1].split("class COrbSession")[0]


def test_tester_stops_before_the_research_holdout():
    from xauscalp.config import load_config
    src = (MT5 / "Experts/XauScalp_ReadOnly.mq5").read_text()
    d = re.search(r"InpTesterStopUtc\s*=\s*D'(\d{4})\.(\d{2})\.(\d{2})", src).groups()
    assert "-".join(d) == str(load_config().validation["holdout_start"])
    assert "TesterStop()" in src


def test_scanner_sees_through_string_comment_tricks(tmp_path):
    """Audit M1: '//' inside a string must not hide the call that follows it."""
    for i, body in enumerate(('string s = "//"; OrderSend(r, res);',
                              "CTrade t; t.Buy(0.01);",
                              "MqlTradeRequest r; r.action = TRADE_ACTION_MODIFY;",
                              "PositionOpen(_Symbol, ORDER_TYPE_BUY, 0.01, 1, 0, 0);",
                              '#include <XauScalp/ExecEngine.mqh>')):
        f = tmp_path / f"E{i}.mq5"
        f.write_text(body)
        assert violations([Path(f.name)], tmp_path) == [f.name], body
    ok = tmp_path / "ok.mq5"
    ok.write_text("// OrderSend( in a comment\n/* CTrade */ int x = 1; // \"quoted\"")
    assert violations([Path("ok.mq5")], tmp_path) == []
    ok.write_text('string s = "OrderSend";')     # strings are scanned on purpose (conservative)
    assert violations([Path("ok.mq5")], tmp_path) == ["ok.mq5"]


def test_only_the_exec_files_may_trade_and_nothing_includes_them():
    from xauscalp.mql5_scan import EXEC_ALLOWED, EXEC_INCLUDE
    for rel in (*MT5.glob("Include/XauScalp/*.mqh"), *MT5.glob("Experts/*.mq5"),
                *MT5.glob("Scripts/*.mq5")):
        r = rel.relative_to(MT5).as_posix()
        src = strip_comments(rel.read_text())
        if r in EXEC_ALLOWED:
            continue
        assert not EXEC_INCLUDE.search(src), f"{r} includes execution code"
        assert not FORBIDDEN.search(src.replace("TRADE_ACTION_DEAL", "").replace(
            "MqlTradeRequest", "") if "Feasibility" in r else src), r
