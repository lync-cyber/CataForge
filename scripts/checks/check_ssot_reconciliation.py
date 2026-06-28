#!/usr/bin/env python3
"""Anti-rot guard: cross-asset SSOT relations that drift silently.

Some single-sources of truth live in one place but are mirrored as plain
data in another with no link between them — a feature flag enumerated in
Python and again in every platform schema, a self-audit check that emits an
id which must exist in its own manifest. Nothing fails when the two diverge
until a downstream consumer hits the gap. These probes reconcile such pairs
statically so the divergence fails in CI / pre-commit instead.

Probes:
  - platform-features: ``core.types.PLATFORM_FEATURES`` == the ``features``
    keys in ``platforms/_schema.yaml`` == the ``features`` keys in every
    ``platforms/<id>/profile.yaml``. Adding a flag in one place but not the
    others (the ``subagent_interactive`` gap audit found) now fails.
  - framework-review check ids: every literal id passed to ``report.add``
    in ``framework_review/checks/*.py`` is registered in ``CHECKS_MANIFEST``.
    An orphan id (a parse-error branch emitting ``B6_hook_consistency``,
    absent from the manifest) only fired on its error path; this surfaces it
    without having to trigger that path.
"""

from __future__ import annotations

import ast
import sys

import yaml
from _common import REPO_ROOT, ensure_utf8

ensure_utf8()

sys.path.insert(0, str(REPO_ROOT / "src"))

from cataforge.core.types import PLATFORM_FEATURES  # noqa: E402
from cataforge.runtime.skill.builtins.framework_review import CHECKS_MANIFEST  # noqa: E402

PLATFORMS_DIR = REPO_ROOT / ".cataforge" / "platforms"
CHECKS_DIR = (
    REPO_ROOT
    / "src"
    / "cataforge"
    / "runtime"
    / "skill"
    / "builtins"
    / "framework_review"
    / "checks"
)


def _yaml(path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _check_platform_features() -> list[str]:
    canonical = set(PLATFORM_FEATURES)
    errs: list[str] = []

    schema = _yaml(PLATFORMS_DIR / "_schema.yaml")
    schema_features = set((schema.get("optional_fields") or {}).get("features") or {})
    if schema_features != canonical:
        errs.append(
            "platforms/_schema.yaml features drift\n"
            f"  only in PLATFORM_FEATURES: {sorted(canonical - schema_features)}\n"
            f"  only in _schema.yaml: {sorted(schema_features - canonical)}"
        )

    for profile in sorted(PLATFORMS_DIR.glob("*/profile.yaml")):
        keys = set(_yaml(profile).get("features") or {})
        if keys != canonical:
            rel = profile.relative_to(REPO_ROOT)
            errs.append(
                f"{rel} features drift\n"
                f"  only in PLATFORM_FEATURES: {sorted(canonical - keys)}\n"
                f"  only in profile: {sorted(keys - canonical)}"
            )
    return errs


def _report_add_ids(tree: ast.Module) -> list[str]:
    """Literal first-arg ids of every ``report.add("...")`` call in a module."""
    ids: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "report"):
            continue
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            ids.append(node.args[0].value)
    return ids


def _check_framework_review_ids() -> list[str]:
    manifest_ids = {entry["id"] for entry in CHECKS_MANIFEST}
    errs: list[str] = []
    for path in sorted(CHECKS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for check_id in _report_add_ids(tree):
            if check_id not in manifest_ids:
                rel = path.relative_to(REPO_ROOT)
                errs.append(
                    f"{rel}: report.add id {check_id!r} not in CHECKS_MANIFEST — "
                    f"register it or fix the id to a manifest entry"
                )
    return errs


def main() -> int:
    errs = _check_platform_features() + _check_framework_review_ids()
    if errs:
        print("FAIL: SSOT reconciliation drift\n", file=sys.stderr)
        for e in errs:
            print(f"  - {e}\n", file=sys.stderr)
        print(
            "Fix: edit the diverging side so both agree (one is the SSOT, the "
            "other its mirror), then rerun.",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: SSOT reconciliation "
        f"({len(PLATFORM_FEATURES)} platform features, "
        f"{len(CHECKS_MANIFEST)} framework-review check ids)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
