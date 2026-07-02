"""Per-language wiring rules + the empty-handler scan (Layer 1 grep).

Thin wrapper over :mod:`cataforge.runtime.skill.rules.loader`: discovers the
shipped YAML files in ``cataforge.runtime.skill.builtins.code_review.rules``
plus any project overrides in ``.cataforge/skills/code-review/rules/``,
compiles their regexes, and scans every file whose extension has at least
one pattern. Rules are resolved per project root at run time (the runner
injects ``CATAFORGE_PROJECT_ROOT``), so a project's override YAML takes
effect at runtime rather than only the package defaults.

To extend coverage to a new language, drop a YAML file into either
location (see ``cataforge.runtime.skill.builtins.code_review.rules`` for
shipped examples). No edits to this module needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.rules.loader import SUPPORTED_FLAGS, RuleSpec, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"
_LINE_HEAD_CHARS = 80

CHECK_ID = "code_review.wiring_empty_handler"


@dataclass(frozen=True)
class LangRule:
    extensions: frozenset[str]
    empty_handler_patterns: tuple[re.Pattern[str], ...]
    placeholder_pragma: re.Pattern[str] | None


@dataclass(frozen=True)
class WiringRuleSet:
    """Compiled wiring rules for one project_root, keyed by language."""

    by_language: dict[str, LangRule]

    def rule_for_extension(self, ext: str) -> LangRule | None:
        ext_lower = ext.lower()
        for rule in self.by_language.values():
            if ext_lower in rule.extensions:
                return rule
        return None

    def scanned_extensions(self) -> frozenset[str]:
        """Extensions for which at least one empty-handler pattern is wired."""
        out: set[str] = set()
        for rule in self.by_language.values():
            if rule.empty_handler_patterns:
                out.update(rule.extensions)
        return frozenset(out)


def _compile_flags(flags_raw: list[str] | None) -> int:
    if not flags_raw:
        return 0
    out = 0
    for f in flags_raw:
        out |= SUPPORTED_FLAGS.get(f, 0)
    return out


def _compile_lang_rule(spec: RuleSpec) -> LangRule:
    raw = spec.raw
    handlers = tuple(
        re.compile(p["regex"], _compile_flags(p.get("flags")))
        for p in (raw.get("empty_handler_patterns") or [])
    )
    pragma_raw = raw.get("placeholder_pragma")
    pragma = (
        re.compile(pragma_raw["regex"], _compile_flags(pragma_raw.get("flags")))
        if isinstance(pragma_raw, dict) and pragma_raw.get("regex")
        else None
    )
    return LangRule(
        extensions=spec.extensions,
        empty_handler_patterns=handlers,
        placeholder_pragma=pragma,
    )


def load_wiring_rules(project_root: Path | None = None) -> WiringRuleSet:
    """Discover + compile wiring rules for *project_root* (None → defaults only)."""
    by_language: dict[str, LangRule] = {}
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    for (rule_type, language), spec in specs.items():
        if rule_type == "wiring":
            by_language[language] = _compile_lang_rule(spec)
    return WiringRuleSet(by_language)


def _scan_file(path: Path, rule: LangRule) -> list[Finding]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    if rule.placeholder_pragma is not None and rule.placeholder_pragma.search(text):
        return []
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in rule.empty_handler_patterns:
            if pattern.search(line):
                findings.append(
                    Finding(
                        check_id=CHECK_ID,
                        severity="warn",
                        category="integration-wiring",
                        detail=line.strip()[:_LINE_HEAD_CHARS],
                        file=str(path),
                        line=lineno,
                    )
                )
                break
    return findings


def run(ctx: CheckContext) -> list[Finding]:
    """Flag empty-handler prop wiring as WARN (never gates).

    Skipped in fix mode (nothing to fix mechanically) and for files
    declaring the placeholder pragma (whole-file opt-out for tasks
    legitimately stubbing handlers).
    """
    if ctx.fix:
        return []
    rules = load_wiring_rules(ctx.project_root)
    exts = rules.scanned_extensions()
    if not exts:
        return []
    findings: list[Finding] = []
    for path in ctx.files(exts):
        rule = rules.rule_for_extension(path.suffix)
        if rule is None or not rule.empty_handler_patterns:
            continue
        findings.extend(_scan_file(path, rule))
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "wiring 空 handler 正则扫描（rules/wiring-{lang}.yaml 驱动）— 空函数 prop "
            "命中即 WARN（豁免：任务卡 wiring_placeholder: true / 文件级 pragma）"
        ),
        severity="warn",
        category="integration-wiring",
        modes=frozenset({"review", "scan"}),
        run=run,
    )
)
