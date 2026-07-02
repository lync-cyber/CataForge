"""Public API surface snapshot diff — code-review probe.

``rule_type: api_surface`` language YAMLs declare ``export_patterns``
(capture group 1 = exported symbol). The surface —
``{rel_path::symbol}`` — snapshots to
``.cataforge/baselines/api-surface.json`` (tamper-guarded by
framework-review B3-γ like every baseline).

Scan: first run establishes the snapshot; later runs report added /
removed exports as informational findings, then refresh. Review: a
no-op unless the project ships an ``api-surface.yaml`` (``scope:
project``) with ``gating: true`` — then exports present in the snapshot
but missing from the working tree FAIL (a public contract shrank
without a scan acknowledging it); review never refreshes the snapshot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.baseline import (
    baseline_path,
    load_baseline,
    save_baseline,
)
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.builtins.code_review.engine.xref import (
    Occurrence,
    collect_occurrences,
)
from cataforge.runtime.skill.rules.loader import compile_flags, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"

CHECK_ID = "code_review.api_surface"
SNAPSHOT_NAME = "api-surface.json"


@dataclass(frozen=True)
class ApiLang:
    extensions: frozenset[str]
    export_patterns: tuple[re.Pattern[str], ...]


def load_api_rules(project_root: Path | None = None) -> tuple[bool, dict[str, ApiLang]]:
    """``(gating, per-language export patterns)`` for *project_root*."""
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    gating = False
    langs: dict[str, ApiLang] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "api_surface":
            continue
        if spec.scope == "project":
            gating = bool(spec.raw.get("gating", False))
        else:
            langs[language] = ApiLang(
                extensions=spec.extensions,
                export_patterns=tuple(
                    re.compile(p["regex"], compile_flags(p.get("flags")))
                    for p in spec.raw["export_patterns"]
                ),
            )
    return gating, langs


def _surface(ctx: CheckContext, langs: dict[str, ApiLang]) -> dict[str, Occurrence]:
    """Current export surface: ``{"<rel_path>::<symbol>": occurrence}``."""
    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    all_exts: frozenset[str] = frozenset().union(*(al.extensions for al in langs.values()))
    surface: dict[str, Occurrence] = {}
    for path in ctx.files(all_exts):
        lang = next((al for al in langs.values() if path.suffix.lower() in al.extensions), None)
        if lang is None:
            continue
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
            text = path.read_text(errors="replace")
        except (ValueError, OSError):
            continue
        for occ in collect_occurrences(str(path), text, lang.export_patterns):
            surface.setdefault(f"{rel}::{occ.key}", occ)
    return surface


def _scan(ctx: CheckContext, surface: dict[str, Occurrence]) -> list[Finding]:
    if ctx.project_root is None:
        return []
    findings: list[Finding] = []
    established = baseline_path(ctx.project_root, SNAPSHOT_NAME).is_file()
    if not established:
        findings.append(
            Finding(
                check_id=CHECK_ID,
                severity="info",
                category="consistency",
                detail=f"API 面快照已建立：{len(surface)} 个导出",
            )
        )
    else:
        old = set(load_baseline(ctx.project_root, SNAPSHOT_NAME))
        for fp in sorted(set(surface) - old):
            occ = surface[fp]
            findings.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="info",
                    category="consistency",
                    detail=f"API 新增导出：{fp}",
                    file=occ.file,
                    line=occ.line,
                )
            )
        for fp in sorted(old - set(surface)):
            findings.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="info",
                    category="consistency",
                    detail=f"API 导出移除：{fp}（确认是否破坏性变更）",
                )
            )
    save_baseline(
        ctx.project_root,
        SNAPSHOT_NAME,
        {fp: {"line": occ.line} for fp, occ in surface.items()},
    )
    return findings


def _review_gate(ctx: CheckContext, surface: dict[str, Occurrence]) -> list[Finding]:
    if ctx.project_root is None or not baseline_path(ctx.project_root, SNAPSHOT_NAME).is_file():
        return []
    old = set(load_baseline(ctx.project_root, SNAPSHOT_NAME))
    return [
        Finding(
            check_id=CHECK_ID,
            severity="fail",
            category="consistency",
            detail=(
                f"API 导出移除：{fp}（api-surface.yaml gating: true — 破坏性变更须先由 "
                "scan 刷新快照并出 CODE-SCAN 报告确认）"
            ),
        )
        for fp in sorted(old - set(surface))
    ]


def run(ctx: CheckContext) -> list[Finding]:
    """Scan diffs + refreshes the snapshot; review gates only with gating: true."""
    gating, langs = load_api_rules(ctx.project_root)
    if not langs:
        return []
    surface = _surface(ctx, langs)
    if ctx.mode == "scan":
        return _scan(ctx, surface)
    if not gating:
        return []
    return _review_gate(ctx, surface)


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "API 面快照探针（rules/api-surface-{lang}.yaml 的 export_patterns 驱动）— scan 对比 "
            ".cataforge/baselines/api-surface.json 报告新增/移除导出（INFO）并刷新快照；项目级 "
            "api-surface.yaml 声明 gating: true 时 review 对快照内消失的导出 FAIL"
            "（review 不刷新快照）"
        ),
        severity="informational",
        category="consistency",
        modes=frozenset({"review", "scan"}),
        run=run,
    )
)
