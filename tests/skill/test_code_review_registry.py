"""code-review check registry ↔ derived CHECKS_MANIFEST contract.

The manifest consumed by framework-review B3 is a projection of the
registry — these tests pin the projection's shape and the invariants
``register_check`` enforces, so a hand-written manifest entry or an
unregistered check can't silently reappear.
"""

from __future__ import annotations

import pytest

from cataforge.runtime.skill.builtins.code_review import CHECKS_MANIFEST
from cataforge.runtime.skill.builtins.code_review.checks import probes
from cataforge.runtime.skill.builtins.code_review.engine import registry
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    REGISTRY,
    CheckSpec,
    checks_for_mode,
    register_check,
)

_GATING_IDS = {
    "code_review.eslint",
    "code_review.prettier",
    "code_review.ruff",
    "code_review.dotnet_format",
    "code_review.golangci",
    "code_review.clippy",
    "code_review.ui_fidelity",
}


def test_manifest_is_registry_projection() -> None:
    assert len(CHECKS_MANIFEST) == len(REGISTRY)
    ids = [e["id"] for e in CHECKS_MANIFEST]
    assert ids == [s.id for s in REGISTRY]
    assert len(set(ids)) == len(ids)
    for entry in CHECKS_MANIFEST:
        assert set(entry) == {"id", "title", "severity", "modes"}
        assert entry["severity"] in registry.MANIFEST_SEVERITIES


def test_manifest_covers_gating_checks_and_wiring() -> None:
    by_id = {e["id"]: e for e in CHECKS_MANIFEST}
    for check_id in _GATING_IDS:
        assert by_id[check_id]["severity"] == "fail-on-error"
        assert by_id[check_id]["modes"] == "review+scan"
    assert by_id["code_review.wiring_empty_handler"]["severity"] == "warn"


def test_every_scan_probe_is_in_manifest_as_informational() -> None:
    by_id = {e["id"]: e for e in CHECKS_MANIFEST}
    for probe in probes.PROBES:
        entry = by_id[probe.check_id]
        assert entry["severity"] == "informational"
        assert entry["modes"] == "scan"


def test_mode_selection_orders_gating_before_informational() -> None:
    scan_checks = checks_for_mode("scan")
    ranks = [registry._SEVERITY_RANK[c.severity] for c in scan_checks]
    assert ranks == sorted(ranks)
    review_checks = checks_for_mode("review")
    assert all(c.severity != "informational" for c in review_checks)


def test_register_check_rejects_duplicates_and_bad_fields() -> None:
    def _noop(_ctx: object) -> list[object]:
        return []

    existing = REGISTRY[0]
    dup = CheckSpec(
        id=existing.id,
        title="dup",
        severity="warn",
        category="convention",
        modes=frozenset({"review"}),
        run=_noop,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="duplicate check id"):
        register_check(dup)

    bad_category = CheckSpec(
        id="code_review.__test_bad_category",
        title="t",
        severity="warn",
        category="not-a-category",
        modes=frozenset({"review"}),
        run=_noop,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="invalid category"):
        register_check(bad_category)

    bad_mode = CheckSpec(
        id="code_review.__test_bad_mode",
        title="t",
        severity="warn",
        category="convention",
        modes=frozenset({"deploy"}),
        run=_noop,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="invalid modes"):
        register_check(bad_mode)
