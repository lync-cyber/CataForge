"""Project-level rot probes (scan mode only, informational).

Each probe wraps one external tool per COMMON-RULES §统一问题分类体系
category (dead-code / complexity, plus Java duplication via PMD CPD). Probes
never gate: a missing tool emits WARN and is skipped, a signal becomes an
``info`` finding for Layer 2 severity aggregation. Signal detection is the
tool-agnostic heuristic (non-zero exit or non-empty output, per probe).

The multi-language duplication dimension is owned by the ``duplication``
check (built-in floor + jscpd augmentation), not a probe here — a built-in
measurement keeps that dimension reliable where a subprocess-launched
external tool is not.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import complexity
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.fs import resolved
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.utils.run_subprocess import run as run_proc

PROBE_TIMEOUT_SECS = 180
_OUTPUT_HEAD_LINES = 30


@dataclass(frozen=True)
class Probe:
    check_id: str
    name: str
    title: str
    category: str
    extensions: frozenset[str]
    detect: tuple[str, ...]
    build_cmd: Callable[[Path, Path | None], list[str]]
    fail_on_nonzero: bool


def _warn_cyclomatic(project_root: Path | None) -> int:
    """warn-level cyclomatic threshold from the project complexity.yaml."""
    thresholds = complexity.thresholds_for(project_root)
    return thresholds["cyclomatic"]["warn"] if thresholds else 10


PROBES: tuple[Probe, ...] = (
    Probe(
        # PMD CPD is the canonical Java duplication detector — better
        # tokenization than jscpd for Java's verbose syntax.
        check_id="code_review.probe_pmd_cpd",
        name="pmd-cpd",
        title="PMD CPD 重复代码探针 (.java)",
        category="duplication",
        extensions=frozenset({".java"}),
        detect=("pmd", "cpd", "--help"),
        build_cmd=lambda target, project_root: [
            "pmd",
            "cpd",
            "--minimum-tokens",
            "100",
            "--language",
            "java",
            "--dir",
            str(target),
        ],
        fail_on_nonzero=False,
    ),
    Probe(
        check_id="code_review.probe_vulture",
        name="vulture",
        title="vulture 死码探针 (.py)",
        category="dead-code",
        extensions=frozenset({".py"}),
        detect=("vulture", "--version"),
        build_cmd=lambda target, project_root: ["vulture", str(target), "--min-confidence", "70"],
        fail_on_nonzero=True,
    ),
    Probe(
        check_id="code_review.probe_ts_prune",
        name="ts-prune",
        title="ts-prune 未引用导出探针 (.ts/.tsx)",
        category="dead-code",
        extensions=frozenset({".ts", ".tsx"}),
        detect=("npx", "ts-prune", "--version"),
        build_cmd=lambda target, project_root: ["npx", "ts-prune", "--project", str(target)],
        fail_on_nonzero=False,
    ),
    Probe(
        # knip covers unused exports / files / dependencies across TS and
        # Svelte projects — the dimensions ts-prune leaves dark when it is
        # absent or the project has no single tsconfig entry point.
        check_id="code_review.probe_knip",
        name="knip",
        title="knip 未使用导出/文件/依赖探针 (.ts/.tsx/.svelte)",
        category="dead-code",
        extensions=frozenset({".ts", ".tsx", ".svelte"}),
        detect=("npx", "knip", "--version"),
        build_cmd=lambda target, project_root: ["npx", "knip", "--directory", str(target)],
        fail_on_nonzero=False,
    ),
    Probe(
        # cargo-machete detects unused dependencies declared in Cargo.toml —
        # the closest "dead-code" signal Rust's type-and-borrow checker
        # doesn't already catch.
        check_id="code_review.probe_cargo_machete",
        name="cargo-machete",
        title="cargo-machete 未使用依赖探针 (.rs)",
        category="dead-code",
        extensions=frozenset({".rs"}),
        detect=("cargo", "machete", "--help"),
        build_cmd=lambda target, project_root: ["cargo", "machete", str(target)],
        fail_on_nonzero=True,
    ),
    Probe(
        check_id="code_review.probe_radon",
        name="radon (cc)",
        title="radon 圈复杂度探针 (.py)",
        category="complexity",
        extensions=frozenset({".py"}),
        detect=("radon", "--version"),
        build_cmd=lambda target, project_root: [
            "radon",
            "cc",
            "-n",
            complexity.radon_rank(_warn_cyclomatic(project_root)),
            "-a",
            str(target),
        ],
        fail_on_nonzero=False,
    ),
    Probe(
        check_id="code_review.probe_gocyclo",
        name="gocyclo",
        title="gocyclo 圈复杂度探针 (.go)",
        category="complexity",
        extensions=frozenset({".go"}),
        detect=("gocyclo", "-?"),
        build_cmd=lambda target, project_root: [
            "gocyclo",
            "-over",
            str(_warn_cyclomatic(project_root)),
            str(target),
        ],
        fail_on_nonzero=False,
    ),
    Probe(
        # Rides the project's own eslint setup (parser/plugins resolve from
        # its config) and layers the core complexity rule on top — the only
        # cyclomatic-complexity signal for JS/TS/Svelte here.
        check_id="code_review.probe_eslint_complexity",
        name="eslint (complexity)",
        title="eslint complexity 规则探针 (.js/.jsx/.ts/.tsx/.svelte)",
        category="complexity",
        extensions=frozenset({".js", ".jsx", ".ts", ".tsx", ".svelte"}),
        detect=("npx", "eslint", "--version"),
        build_cmd=lambda target, project_root: [
            "npx",
            "eslint",
            "--rule",
            f'{{"complexity": ["warn", {_warn_cyclomatic(project_root)}]}}',
            str(target),
        ],
        fail_on_nonzero=False,
    ),
)


def _make_runner(probe: Probe) -> Callable[[CheckContext], list[Finding]]:
    def run(ctx: CheckContext) -> list[Finding]:
        if not (probe.extensions & ctx.present_extensions()):
            return []
        if not ctx.tool_available(probe.name, probe.detect):
            if ctx.first_missing_report(probe.name):
                # A supplementary probe being absent is a "could install X for a
                # sharper signal" notice, not a defect — info keeps it in the
                # truncatable section instead of the prominent warn list. Runtime
                # failures (timeout below) stay warn.
                return [
                    Finding(
                        check_id=probe.check_id,
                        severity="info",
                        category=probe.category,
                        detail=f"probe '{probe.name}' 未安装，跳过",
                    )
                ]
            return []
        cmd = probe.build_cmd(ctx.target, ctx.project_root)
        try:
            result = run_proc(resolved(cmd), timeout=PROBE_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            return [
                Finding(
                    check_id=probe.check_id,
                    severity="warn",
                    category=probe.category,
                    detail=f"probe '{probe.name}' 超时",
                )
            ]
        output = (result.stdout + "\n" + result.stderr).strip()
        signal = (probe.fail_on_nonzero and result.returncode != 0) or (
            not probe.fail_on_nonzero and bool(output)
        )
        if not signal:
            return []
        head = output.splitlines()[:_OUTPUT_HEAD_LINES]
        return [
            Finding(
                check_id=probe.check_id,
                severity="info",
                category=probe.category,
                detail="\n".join([probe.name, *head]),
            )
        ]

    return run


for _probe in PROBES:
    register_check(
        CheckSpec(
            id=_probe.check_id,
            title=_probe.title,
            severity="informational",
            category=_probe.category,
            modes=frozenset({"scan"}),
            run=_make_runner(_probe),
        )
    )
