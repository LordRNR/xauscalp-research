import pytest

from xauscalp.symbol_specs import (
    SpecsError,
    load_specs,
    risk_at_min_lot,
    spread_cost_min_lot,
    viability_table,
)

HEAD = ("symbol,found,digits,point,contract_size,volume_min,volume_step,volume_max,volume_limit,tick_size,"
        "tick_value,tick_value_profit,tick_value_loss,currency_base,currency_profit,currency_margin,bid,ask,"
        "spread_points,stops_level,freeze_level,swap_long,swap_short,swap_mode,margin_1lot,trade_mode,calc_mode")
XAU = "XAUUSD,1,2,0.01,100,0.01,0.01,50,0,0.01,1.0,1.0,1.0,XAU,USD,XAU,2000,2000.2,20,0,0,-30,10,m,3500,FULL,CFD"
EUR = "EURUSD,1,5,0.00001,100000,0.01,0.01,50,0,0.00001,0.92,0.92,0.92,EUR,USD,EUR,1.1,1.10012,12,0,0,-5,2,m,11,FULL,FX"


def write(tmp_path, *rows, extra=""):
    p = tmp_path / "s.csv"
    p.write_text("#specs_version,1.0\n#company,Test\n#server,Demo\n#account_currency,EUR\n#leverage,100\n"
                 + HEAD + "\n" + "\n".join(rows) + "\n" + extra)
    return p


def test_load_and_money_maths(tmp_path):
    s = load_specs(write(tmp_path, XAU, EUR, "XYZ,0"))
    assert s.meta["account_currency"] == "EUR" and s.df.loc["XYZ", "found"] != 1
    xau = s.df.loc["XAUUSD"]
    # 0.01 lot = 1 oz; a 12 USD stop = 1200 ticks of 0.01 -> 1200 x 0.01 = 12 (account ccy as given)
    assert risk_at_min_lot(xau, 12.0) == pytest.approx(12.0)          # 0.01 lot x 1200 ticks x 1.0
    assert spread_cost_min_lot(xau) == pytest.approx(0.2)           # 0.01 lot x 20 ticks x 1.0
    eur = s.df.loc["EURUSD"]
    assert risk_at_min_lot(eur, 0.0030) == pytest.approx(0.01 * 300 * 0.92)


def test_viability_flags_unsizeable_stops_and_enforces_the_risk_ceiling(tmp_path):
    s = load_specs(write(tmp_path, XAU, EUR))
    t = viability_table(s, 1000, 0.5, {"XAUUSD": 12.0, "EURUSD": 0.0030})
    assert not t.loc["XAUUSD", "sizeable"] and t.loc["XAUUSD", "min_capital_for_risk_pct"] == pytest.approx(2400)
    assert t.loc["EURUSD", "sizeable"]
    with pytest.raises(SpecsError):
        viability_table(s, 1000, 2.0, {})                            # above the 1 % hard ceiling
    with pytest.raises(SpecsError):
        risk_at_min_lot(s.df.loc["XAUUSD"], float("nan"))


def test_malformed_specs_fail_closed(tmp_path):
    bad = XAU.replace(",100,0.01,", ",0,0.01,", 1)                  # contract size 0
    with pytest.raises(SpecsError):
        load_specs(write(tmp_path, bad))
    p = tmp_path / "x.csv"
    p.write_text("no,header\n")
    with pytest.raises(SpecsError):
        load_specs(p)
