"""SSOT parity between framework.json constants and COMMON-RULES, plus
migration-check hygiene.

These guard three drift classes that previously slipped through every gate:
the framework.json constant table and the COMMON-RULES index diverging, a
migration check masking a moved source path behind ``allow_missing``, and
stale skill names / change narrative leaking into migration-check
descriptions that surface in ``cataforge doctor``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_JSON = REPO_ROOT / ".cataforge" / "framework.json"
COMMON_RULES = REPO_ROOT / ".cataforge" / "rules" / "COMMON-RULES.md"

# Change-narrative patterns banned from long-lived assets (CLAUDE.md hard
# constraint 1). Migration-check descriptions render in doctor output.
_RESIDUE_PATTERNS = [
    re.compile(r"已废弃"),
    re.compile(r"已删除"),
    re.compile(r"取代"),
    re.compile(r"放宽至"),
    re.compile(r"无过渡期"),
    re.compile(r"自\s*v?[0-9]+\.[0-9]+(?:\.[0-9]+)?\s*起"),
]


def _framework() -> dict:
    return json.loads(FRAMEWORK_JSON.read_text(encoding="utf-8"))


def _common_rules_constant_names() -> set[str]:
    text = COMMON_RULES.read_text(encoding="utf-8")
    start = text.index("## 框架配置常量")
    end = text.index("## 执行模式矩阵")
    section = text[start:end]
    return set(re.findall(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|", section, re.M))


def test_every_framework_constant_documented_in_common_rules() -> None:
    """framework.json#/constants and the COMMON-RULES table must match exactly.

    Missing entries break discoverability ("直接引用常量名" is impossible);
    extra documented entries would point at constants that no longer exist.
    """
    declared = set(_framework()["constants"])
    documented = _common_rules_constant_names()
    assert declared == documented, (
        f"undocumented in COMMON-RULES: {sorted(declared - documented)}; "
        f"documented but absent from framework.json: {sorted(documented - declared)}"
    )


def test_no_migration_check_masks_a_drifted_source_path() -> None:
    """A migration check pointing at ``src/`` must reference a real file.

    ``allow_missing`` exists for downstream site-packages installs, but in the
    dogfood/editable tree a ``src/`` path that no longer exists means the
    check silently passes against nothing.
    """
    offenders = []
    for check in _framework()["migration_checks"]:
        path = str(check.get("path", ""))
        if path.startswith("src/") and not (REPO_ROOT / path).exists():
            offenders.append((check["id"], path))
    assert not offenders, f"migration checks point at missing src/ paths: {offenders}"


def test_migration_check_descriptions_are_current_state() -> None:
    """Descriptions carry neither stale skill names nor change narrative."""
    bad_names: list[str] = []
    residue: list[str] = []
    for check in _framework()["migration_checks"]:
        desc = check.get("description", "")
        if "doc-gen" in desc or "doc-nav" in desc:
            bad_names.append(check["id"])
        if any(p.search(desc) for p in _RESIDUE_PATTERNS):
            residue.append(check["id"])
    assert not bad_names, f"migration descriptions reference renamed skills: {bad_names}"
    assert not residue, f"migration descriptions carry change narrative: {residue}"
