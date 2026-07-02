"""Dead config keys — code-review scan probe (informational, xref kernel).

``rule_type: config_keys`` YAMLs declare where config keys are
*declared* (``declare_patterns`` over files selected by
``extensions``/``filenames`` globs) and where they are *consumed*
(``consume_patterns``). A declared key with zero consumers anywhere in
the scanned tree is a rot signal — a config knob or feature flag nothing
reads. The builtin declaration side is the language-agnostic dotenv
convention (``scope: project`` ``config-keys.yaml``); consumption is
per-language (``config-keys-{lang}.yaml``, six languages). Projects
extend by dropping more YAMLs (settings files, flag registries).

Informational only (a key may be consumed by external infra the scan
cannot see); a declaration file can opt out via the file-level pragma
``cataforge: allow(config_dead_key, reason="...")``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import file_allowance
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.builtins.code_review.engine.xref import (
    Occurrence,
    collect_keys,
    collect_occurrences,
    dead_keys,
)
from cataforge.runtime.skill.rules.loader import compile_flags, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"

CHECK_ID = "code_review.config_dead_key"


@dataclass(frozen=True)
class ConfigLang:
    extensions: frozenset[str]
    filenames: tuple[str, ...]
    declare_patterns: tuple[re.Pattern[str], ...]
    consume_patterns: tuple[re.Pattern[str], ...]

    def matches(self, path: Path) -> bool:
        if path.suffix.lower() in self.extensions:
            return True
        return any(fnmatch(path.name, glob) for glob in self.filenames)


def load_config_rules(project_root: Path | None = None) -> dict[str, ConfigLang]:
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    out: dict[str, ConfigLang] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "config_keys":
            continue
        out[language] = ConfigLang(
            extensions=spec.extensions,
            filenames=tuple(spec.raw.get("filenames") or ()),
            declare_patterns=tuple(
                re.compile(p["regex"], compile_flags(p.get("flags")))
                for p in (spec.raw.get("declare_patterns") or [])
            ),
            consume_patterns=tuple(
                re.compile(p["regex"], compile_flags(p.get("flags")))
                for p in (spec.raw.get("consume_patterns") or [])
            ),
        )
    return out


def run(ctx: CheckContext) -> list[Finding]:
    """Declared-but-never-consumed config keys as informational findings."""
    langs = load_config_rules(ctx.project_root)
    if not langs:
        return []
    declared: list[Occurrence] = []
    consumed: set[str] = set()
    findings: list[Finding] = []
    for path in ctx.all_files():
        lang = next((lc for lc in langs.values() if lc.matches(path)), None)
        if lang is None:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if lang.consume_patterns:
            consumed |= collect_keys(text, lang.consume_patterns)
        if not lang.declare_patterns:
            continue
        allowance = file_allowance(text, CHECK_ID)
        if allowance is not None:
            if not allowance.reason:
                findings.append(
                    Finding(
                        check_id=CHECK_ID,
                        severity="warn",
                        category="dead-code",
                        detail="allow(config_dead_key) 缺 reason — 豁免生效但须补充理由",
                        file=str(path),
                        line=allowance.line,
                    )
                )
            continue
        declared.extend(collect_occurrences(str(path), text, lang.declare_patterns))
    findings.extend(
        Finding(
            check_id=CHECK_ID,
            severity="info",
            category="dead-code",
            detail=f"config key {occ.key} 声明后全库零消费（外部基础设施消费时用文件级豁免标注）",
            file=occ.file,
            line=occ.line,
        )
        for occ in dead_keys(declared, consumed)
    )
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "config 死键探针（项目级 config-keys.yaml 声明侧 + config-keys-{lang}.yaml 消费侧，"
            "xref 集合差）— 声明零消费的 config key / feature flag 记 INFO；声明文件可用文件级 "
            'cataforge: allow(config_dead_key, reason="...") 豁免'
        ),
        severity="informational",
        category="dead-code",
        modes=frozenset({"scan"}),
        run=run,
    )
)
