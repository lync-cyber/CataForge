"""Per-language e2e backdoor + real-input rules for the testing skill.

Thin wrapper over :mod:`cataforge.runtime.skill.rules.loader`: discovers the
shipped YAML files in ``cataforge.runtime.skill.builtins.testing.rules`` plus
any project overrides in ``.cataforge/skills/testing/rules/``, compiles
their regexes, and exposes per-extension lookups the e2e scanner calls
for each file.

Rules are resolved per *project_root* at scan time (the runner injects
``CATAFORGE_PROJECT_ROOT``), so a project's override YAML takes effect at
runtime rather than only the package defaults.

To extend coverage to a new language, drop a YAML file into either
location. No edits to this module needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.rules.loader import RuleSpec, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.testing"
_SKILL_ID = "testing"


@dataclass(frozen=True)
class E2ELangRule:
    extensions: frozenset[str]
    backdoor_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    real_input_patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class E2ERuleSet:
    """Compiled e2e rules for one project_root, keyed by language."""

    by_language: dict[str, E2ELangRule]

    def rule_for_extension(self, ext: str) -> E2ELangRule | None:
        ext_lower = ext.lower()
        for rule in self.by_language.values():
            if ext_lower in rule.extensions:
                return rule
        return None

    def all_extensions(self) -> frozenset[str]:
        out: set[str] = set()
        for rule in self.by_language.values():
            out.update(rule.extensions)
        return frozenset(out)


def _compile_flags(flags_raw) -> int:
    from cataforge.runtime.skill.rules.loader import SUPPORTED_FLAGS

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


def load_e2e_rules(project_root: Path | None = None) -> E2ERuleSet:
    """Discover + compile e2e rules for *project_root* (None → defaults only)."""
    by_language: dict[str, E2ELangRule] = {}
    specs = discover_rules(
        _SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root
    )
    for (rule_type, language), spec in specs.items():
        if rule_type == "e2e":
            by_language[language] = _compile_e2e_rule(spec)
    return E2ERuleSet(by_language)
