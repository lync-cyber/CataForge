"""Skill-level rules plugin architecture.

Default rule sets ship inside the cataforge package at
``cataforge.skill.builtins.{skill_dir}.rules`` (YAML files). Projects
can override or extend by adding YAML files at
``<project_root>/.cataforge/skills/{skill_id}/rules/``. The loader
resolves project files first; files for the same ``(rule_type, language)``
key replace the package default. Adding a brand-new language is a single
project YAML, no cataforge fork required.
"""

from cataforge.skill.rules.loader import (
    CURRENT_SCHEMA_VERSION,
    RuleLoadError,
    RuleSpec,
    discover_rules,
    validate_yaml_text,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "RuleLoadError",
    "RuleSpec",
    "discover_rules",
    "validate_yaml_text",
]
