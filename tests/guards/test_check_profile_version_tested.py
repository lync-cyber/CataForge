"""Self-test for ``scripts/checks/check_profile_version_tested.py``.

Exercises the pure staleness logic with injected commit dates so the guard's
threshold/skip behaviour is covered without depending on real git history.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_profile_version_tested.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vt_guard", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_find_stale_flags_only_old_profiles() -> None:
    mod = _load()
    old = (NOW - timedelta(days=400)).isoformat()
    fresh = (NOW - timedelta(days=10)).isoformat()
    stale = mod.find_stale({"codex": old, "cursor": fresh}, NOW, 180)
    assert [p for p, _ in stale] == ["codex"]


def test_find_stale_skips_untracked() -> None:
    mod = _load()
    assert mod.find_stale({"opencode": None}, NOW, 180) == []


def test_boundary_not_stale_at_threshold() -> None:
    mod = _load()
    exactly = (NOW - timedelta(days=180)).isoformat()
    assert mod.find_stale({"x": exactly}, NOW, 180) == []


def test_profile_age_days() -> None:
    mod = _load()
    iso = (NOW - timedelta(days=200)).isoformat()
    assert mod.profile_age_days(iso, NOW) == 200
