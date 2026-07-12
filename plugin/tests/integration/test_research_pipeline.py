"""Pure-Python logic checks for the research pipeline orchestration rules."""
from __future__ import annotations

ROUND_CAP_DEFAULT = 2
ROUND_CAP_DEEP = 3


def _should_loop(need_more: bool, rounds_done: int, deep: bool) -> bool:
    """Mirror the round-2 gate documented in research/SKILL.md."""
    cap = ROUND_CAP_DEEP if deep else ROUND_CAP_DEFAULT
    return need_more and rounds_done < cap


def test_no_need_more_stops():
    assert _should_loop(need_more=False, rounds_done=1, deep=False) is False


def test_need_more_within_cap_loops():
    assert _should_loop(need_more=True, rounds_done=1, deep=False) is True


def test_need_more_at_cap_stops():
    assert _should_loop(need_more=True, rounds_done=2, deep=False) is False


def test_deep_allows_extra_round():
    assert _should_loop(need_more=True, rounds_done=2, deep=True) is True


def test_capture_snapshots_is_deleted():
    from pathlib import Path
    root = Path(__file__).parent.parent.parent
    assert not (root / "scripts/capture_snapshots.py").exists()
