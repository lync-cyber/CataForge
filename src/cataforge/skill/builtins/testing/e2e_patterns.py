"""Per-language e2e backdoor + real-input rules for the testing skill.

Thin wrapper over :mod:`cataforge.skill.rules.loader`: discovers the
shipped YAML files in ``cataforge.skill.builtins.testing.rules`` plus
any project overrides in ``.cataforge/skills/testing/rules/``, compiles
regexes once at import time, and exposes per-extension lookups the
e2e scanner calls for each file.

To extend coverage to a new language, drop a YAML file into either
location. No edits to this module needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.skill.rules.loader import RuleSpec, discover_rules

_BUILTIN_MODULE = "cataforge.skill.builtins.testing"
_SKILL_ID = "testing"


@dataclass(frozen=True)
class E2ELangRule:
    extensions: frozenset[str]
    backdoor_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    real_input_patterns: tuple[re.Pattern[str], ...]


def _compile_flags(flags_raw) -> int:
    from cataforge.skill.rules.loader import SUPPORTED_FLAGS

    if not flags_raw:
        return 0
    out = 0
    for f in flags_raw:
        out |= SUPPORTED_FLAGS.get(f, 0)
    return out


def _compile_e2e_rule(spec: RuleSpec) -> E2ELangRule:
    raw = spec.raw
    backdoors = tuple(
        (p["label"], re.compile(p["regex"], _compile_flags(p.get("flags"))))
        for p in (raw.get("backdoor_patterns") or [])
    )
    real_input = tuple(
        re.compile(p["regex"], _compile_flags(p.get("flags")))
        for p in (raw.get("real_input_patterns") or [])
    )
    return E2ELangRule(
        extensions=spec.extensions,
        backdoor_patterns=backdoors,
        real_input_patterns=real_input,
    )


def _load(project_root: Path | None) -> dict[str, E2ELangRule]:
    specs = discover_rules(
        _SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root
    )
    out: dict[str, E2ELangRule] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "e2e":
            continue
        out[language] = _compile_e2e_rule(spec)
    return out


LANGUAGE_RULES: dict[str, E2ELangRule] = _load(project_root=None)


def reload_for_project(project_root: Path | None) -> None:
    """Re-discover rules with a project root in scope (replaces in place)."""
    global LANGUAGE_RULES
    LANGUAGE_RULES = _load(project_root)


def all_extensions() -> frozenset[str]:
    out: set[str] = set()
    for rule in LANGUAGE_RULES.values():
        out.update(rule.extensions)
    return frozenset(out)


def rule_for_extension(ext: str) -> E2ELangRule | None:
    ext_lower = ext.lower()
    for rule in LANGUAGE_RULES.values():
        if ext_lower in rule.extensions:
            return rule
    return None
