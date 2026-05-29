"""Per-language wiring rules for code-review Layer 1 grep.

Thin wrapper over :mod:`cataforge.runtime.skill.rules.loader`: discovers the
shipped YAML files in ``cataforge.runtime.skill.builtins.code_review.rules``
plus any project overrides in ``.cataforge/skills/code-review/rules/``,
compiles regexes once at import time, and exposes a per-extension
lookup the linter calls for each scanned file.

To extend coverage to a new language, drop a YAML file into either
location (see ``cataforge.runtime.skill.builtins.code_review.rules`` for
shipped examples). No edits to this module needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.rules.loader import RuleSpec, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"


@dataclass(frozen=True)
class LangRule:
    extensions: frozenset[str]
    empty_handler_patterns: tuple[re.Pattern[str], ...]
    placeholder_pragma: re.Pattern[str] | None


def _compile_flags(flags_raw) -> int:
    from cataforge.runtime.skill.rules.loader import SUPPORTED_FLAGS

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


def _load(project_root: Path | None) -> dict[str, LangRule]:
    specs = discover_rules(
        _SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root
    )
    out: dict[str, LangRule] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "wiring":
            continue
        out[language] = _compile_lang_rule(spec)
    return out


# Loaded at import time using the package defaults. Tests / runtime can
# call :func:`reload_for_project` to layer on a project override path
# (e.g. tests pointing at a synthetic project_root).
LANGUAGE_RULES: dict[str, LangRule] = _load(project_root=None)


def reload_for_project(project_root: Path | None) -> None:
    """Re-discover rules with a project root in scope (replaces in place)."""
    global LANGUAGE_RULES
    LANGUAGE_RULES = _load(project_root)


def rule_for_extension(ext: str) -> LangRule | None:
    ext_lower = ext.lower()
    for rule in LANGUAGE_RULES.values():
        if ext_lower in rule.extensions:
            return rule
    return None


def all_scanned_extensions() -> frozenset[str]:
    """Extensions for which at least one empty-handler pattern is wired."""
    out: set[str] = set()
    for rule in LANGUAGE_RULES.values():
        if rule.empty_handler_patterns:
            out.update(rule.extensions)
    return frozenset(out)
