"""B3 — SKILL.md ↔ CHECKS_MANIFEST drift and rules YAML schema."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from cataforge.core.paths import ProjectPaths

from .._types import Report

_CHECK_ID_ANCHOR_RE = re.compile(r"<!--\s*check_id:\s*([\w.-]+)\s*-->")
_DELEGATION_RE = re.compile(r"权威清单见.*?CHECKS_MANIFEST", re.DOTALL)

# Skill id → builtin module exposing CHECKS_MANIFEST. Only review-class
# skills whose builtin runs Layer 1 checks AND that ship a data-driven
# SKILL.md belong here — each entry's SKILL.md '## Layer 1 检查项' section is
# reconciled against the builtin manifest. A builtin-only engine with no
# SKILL.md (its prose folded into another skill's reference) is not listed.
# Integrity of this map vs the on-disk SKILL.md set is guarded by a test.
_BUILTIN_MAP = {
    "code-review": "cataforge.runtime.skill.builtins.code_review",
    "sprint-review": "cataforge.runtime.skill.builtins.sprint_review",
    "framework-review": "cataforge.runtime.skill.builtins.framework_review",
    "testing": "cataforge.runtime.skill.builtins.testing",
}
_REQUIRES_RE = re.compile(
    r"<!--\s*requires:\s*cataforge\s*>=\s*([0-9]+(?:\.[0-9]+){0,2})\s*-->"
)


def _parse_semver(value: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' (or 'X.Y' / 'X') to a comparable tuple, pad with 0."""
    parts = value.split(".")
    out: list[int] = []
    for p in parts[:3]:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def _detect_release_lag(section_text: str) -> str | None:
    """If section declares ``<!-- requires: cataforge>=X.Y.Z -->`` and the
    running cataforge package is older, return the required version string
    so the caller can downgrade orphan-anchor FAILs to INFO."""
    match = _REQUIRES_RE.search(section_text)
    if not match:
        return None
    required = match.group(1)
    try:
        from cataforge import __version__ as runtime_version
    except ImportError:
        return None
    if _parse_semver(runtime_version) < _parse_semver(required):
        return required
    return None


def check_b3_manifest_drift(root: Path, report: Report) -> None:
    """B3-α: SKILL.md '## Layer 1 检查项' ↔ CHECKS_MANIFEST.

    Two reconciliation strategies — every SKILL.md must use one or the
    other (no soft fallback):

    1. **Anchor mode** — section contains one or more
       ``<!-- check_id: xxx -->`` HTML comments. Every anchor must point at
       a real manifest entry, and every non-delegated manifest entry must
       have an anchor.
    2. **Delegation mode** — section contains the canonical phrase
       ``权威清单见 ...CHECKS_MANIFEST``. We verify the manifest exists but
       skip entry-by-entry comparison (the manifest itself is authoritative).

    A SKILL.md with a "## Layer 1 检查项" section but neither anchors nor
    delegation marker → FAIL.
    """
    for skill_id, module_name in _BUILTIN_MAP.items():
        skill_md = ProjectPaths(root).skill_dir(skill_id) / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"cannot read SKILL.md: {exc}",
            )
            continue

        section_match = re.search(
            r"^##\s+Layer 1 检查项[^\n]*\n(.*?)(?=^##\s|\Z)",
            text,
            re.DOTALL | re.MULTILINE,
        )
        if not section_match:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                "缺少 '## Layer 1 检查项' 段；builtin manifest 已存在",
            )
            continue

        section_text = section_match.group(1)

        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"cannot import {module_name}: {exc}",
            )
            continue

        manifest = getattr(module, "CHECKS_MANIFEST", None)
        if not manifest:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"{module_name}.CHECKS_MANIFEST 不存在或为空",
            )
            continue

        anchored_ids = set(_CHECK_ID_ANCHOR_RE.findall(section_text))
        delegated = bool(_DELEGATION_RE.search(section_text))
        release_lag = _detect_release_lag(section_text)

        if anchored_ids:
            _check_b3_anchors(
                skill_id, anchored_ids, manifest, delegated, release_lag, report
            )
            continue
        if delegated:
            continue
        report.add(
            "B3_manifest_drift",
            "FAIL",
            f"skills/{skill_id}",
            "'## Layer 1 检查项' 段缺 <!-- check_id: ... --> 锚点和"
            " '权威清单见 ...CHECKS_MANIFEST' 委托句；二者必居其一",
        )


def _check_b3_anchors(
    skill_id: str,
    anchored_ids: set[str],
    manifest: tuple[dict[str, str], ...],
    delegated: bool,
    release_lag: str | None,
    report: Report,
) -> None:
    """Bidirectional check_id anchor reconciliation.

    Two failure modes:

    * **Orphan anchor** — ``<!-- check_id: xxx -->`` references an ID that
      no manifest entry declares.
    * **Missing anchor** — a manifest entry has no anchor in the prose.
      Skipped when the section also has the delegation marker.

    When *release_lag* is set, orphan anchors are downgraded to INFO with
    a "release lag, not a real drift" explanation pointing the user at a
    cataforge upgrade.
    """
    manifest_ids = {str(entry.get("id", "")).strip() for entry in manifest}
    manifest_ids.discard("")

    orphan_severity = "INFO" if release_lag else "FAIL"
    for anchor_id in sorted(anchored_ids - manifest_ids):
        if release_lag:
            message = (
                f"check_id anchor {anchor_id!r} not in current manifest; "
                f"SKILL.md declares 'requires: cataforge>={release_lag}' but "
                "runtime is older — upgrade cataforge or pin SKILL.md to the "
                "release branch (release lag, not a real drift)"
            )
        else:
            message = (
                f"check_id anchor {anchor_id!r} has no matching manifest "
                "entry — was the check renamed in the builtin without "
                "updating the SKILL.md anchor?"
            )
        report.add(
            "B3_manifest_drift", orphan_severity, f"skills/{skill_id}", message
        )

    if delegated:
        return

    for missing_id in sorted(manifest_ids - anchored_ids):
        report.add(
            "B3_manifest_drift",
            "FAIL",
            f"skills/{skill_id}",
            f"manifest entry {missing_id!r} has no <!-- check_id: ... --> "
            "anchor in the SKILL.md prose — anchor mode requires every "
            "manifest entry to be surfaced (or add the delegation marker "
            "to opt out for less-important entries)",
        )


def check_b3_rules_schema(root: Path, report: Report) -> None:
    """B3-β: project-local skill rules YAMLs validate against the schema."""
    try:
        from cataforge.runtime.skill.rules.loader import RuleLoadError, validate_yaml_text
    except ImportError:
        return

    skills_dir = ProjectPaths(root).skills_dir
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        rules_dir = skill_dir / "rules"
        if not rules_dir.is_dir():
            continue
        for path in sorted(rules_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".yaml", ".yml"):
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                report.add(
                    "B3_rules_schema_compliance",
                    "FAIL",
                    rel,
                    f"cannot read rules YAML: {exc}",
                )
                continue
            try:
                validate_yaml_text(text, rel)
            except RuleLoadError as exc:
                report.add(
                    "B3_rules_schema_compliance",
                    "FAIL",
                    rel,
                    f"rules YAML validation failed: {exc}",
                )
