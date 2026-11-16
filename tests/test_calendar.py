import pandas as pd

from xauscalp.calendar.events import blackout_mask, load_events
from xauscalp.config import ROOT


def test_blackout_window(tmp_path):
    p = tmp_path / "ev.csv"
    p.write_text("utc_time,event,impact\n2025-01-10T13:30:00Z,NFP,high\n"
                 "2025-01-10T15:00:00Z,minor,low\n")
    idx = pd.date_range("2025-01-10 12:00", "2025-01-10 16:00", freq="1min", tz="UTC")
    m = blackout_mask(idx, load_events(p), 30, 30)
    on = idx[m]
    assert on.min() == pd.Timestamp("2025-01-10 13:00", tz="UTC")
    assert on.max() == pd.Timestamp("2025-01-10 14:00", tz="UTC")
    assert m.sum() == 61                       # low-impact event ignored


def test_committed_calendar_is_exactly_the_generated_official_one():
    """config/events.csv must come from xauscalp.calendar.official (no hand-typed dates)."""
    from xauscalp.calendar.official import build_events, to_csv_text
    assert (ROOT / "config" / "events.csv").read_text() == to_csv_text(build_events())


def test_official_calendar_is_structurally_valid_and_dst_aware():
    from xauscalp.calendar.official import build_events, validate
    df = build_events()
    assert validate(df) == []
    t = {(r.event, r.utc_time.strftime("%Y-%m-%d")): r.utc_time.strftime("%H:%M")
         for r in df.itertuples()}
    assert t[("CPI", "2025-10-24")] == "12:30"                       # EDT
    assert t[("CPI", "2025-12-18")] == "13:30"                       # EST
    assert t[("Employment Situation (NFP)", "2026-11-06")] == "13:30"
    assert t[("FOMC statement", "2025-12-10")] == "19:00"
    assert t[("FOMC statement", "2025-10-29")] == "18:00"
    # the documented 2025 shutdown gap is present as a gap, not filled with invented dates
    nov25 = df[(df.utc_time >= "2025-11-01") & (df.utc_time < "2025-12-01")]
    assert "CPI" not in set(nov25.event)


def test_validation_catches_a_typo(monkeypatch):
    from xauscalp.calendar import official
    bad = dict(official.CPI)
    bad[2024] = bad[2024][:-1]
    monkeypatch.setattr(official, "CPI", bad)
    assert any("CPI 2024" in m for m in official.validate(official.build_events()))
    monkeypatch.setattr(official, "CPI", {**official.CPI, 2024: ["01-13"] + official.CPI[2024][1:]})
    # 2024-01-13 is a Saturday
    assert any("weekend" in m for m in official.validate(official.build_events()))
