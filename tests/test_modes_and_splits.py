import itertools

import pandas as pd
import pytest

from xauscalp import modes
from xauscalp.backtest.splits import (
    UNLOCK_ENV,
    UNLOCK_VALUE,
    HoldoutLocked,
    holdout_slice,
    research_slice,
    walk_forward_folds,
)
from xauscalp.modes import Mode, ModeViolation, check_mode


def test_demo_refuses_real_account():
    with pytest.raises(ModeViolation):
        check_mode(Mode.DEMO, account_is_demo=False)
    check_mode(Mode.DEMO, account_is_demo=True)


def test_research_refuses_any_account():
    with pytest.raises(ModeViolation):
        check_mode(Mode.RESEARCH, account_is_demo=True)


def test_live_disabled_in_this_phase(tmp_path):
    assert modes.LIVE_PHASE_UNLOCKED is False
    auth = tmp_path / "LIVE_AUTHORIZATION"
    auth.write_text("login=123")
    with pytest.raises(ModeViolation):
        check_mode(Mode.LIVE, account_is_demo=False, account_login=123, authorization_file=auth)


def _df():
    idx = pd.date_range("2025-10-01", "2025-11-30", freq="1D", tz="UTC")
    return pd.DataFrame({"x": range(len(idx))}, index=idx)


def test_research_slice_excludes_holdout():
    r = research_slice(_df(), "2025-11-01")
    assert r.index.max() < pd.Timestamp("2025-11-01", tz="UTC")


def test_holdout_locked_without_user_flag(monkeypatch, tmp_path):
    monkeypatch.delenv(UNLOCK_ENV, raising=False)
    with pytest.raises(HoldoutLocked):
        holdout_slice(_df(), "2025-11-01", "s1", tmp_path / "log.md")


def test_holdout_is_one_shot(monkeypatch, tmp_path):
    monkeypatch.setenv(UNLOCK_ENV, UNLOCK_VALUE)
    log = tmp_path / "log.md"
    assert len(holdout_slice(_df(), "2025-11-01", "s1", log)) == 30
    with pytest.raises(HoldoutLocked):
        holdout_slice(_df(), "2025-11-01", "s1", log)


def test_walk_forward_folds_do_not_overlap_and_stay_in_range():
    s, e = pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC")
    folds = walk_forward_folds(s, e, 12, 3)
    assert folds
    for tr0, tr1, te0, te1 in folds:
        assert tr0 < tr1 == te0 < te1 <= e
    tests = [(f[2], f[3]) for f in folds]
    for (a0, a1), (b0, b1) in itertools.pairwise(tests):
        assert a1 <= b0
