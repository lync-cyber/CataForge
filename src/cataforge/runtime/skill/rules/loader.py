"""Loader for skill-level rules YAML files.

Resolution order, highest priority first:

1. ``<project_root>/.cataforge/skills/{skill_id}/rules/*.yaml``
   — project-local override; replaces a default for the same
   ``(rule_type, language)`` pair, or adds a new language.
2. ``cataforge.runtime.skill.builtins.{skill_dir}.rules.*.yaml`` — the
   default rule set shipped with the framework.

The loader returns a flat list of :class:`RuleSpec`; downstream callers
(code-review wiring scan, testing e2e scan) translate each spec into
their internal compiled-pattern form. Schema validation lives here so
``framework-review`` can re-use :func:`validate_yaml_text` to gate
project YAMLs without duplicating the parsing logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

CURRENT_SCHEMA_VERSION = 1

SUPPORTED_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "UNICODE": re.UNICODE,
    "VERBOSE": re.VERBOSE,
}

YAML_SUFFIXES = (".yaml", ".yml")


class RuleLoadError(ValueError):
    """Raised when a rules YAML fails schema or regex validation."""


@dataclass(frozen=True)
class RuleSpec:
    """One parsed rules YAML file.

    ``raw`` carries the original mapping so each rule_type's downstream
    consumer can read the type-specific keys (``empty_handler_patterns``,
    ``backdoor_patterns``, etc.) without the loader needing to know
    every rule_type schema upfront.
    """

    schema_version: int
    rule_type: str
    language: str
    extensions: frozenset[str]
    source: str
    raw: dict[str, Any] = field(repr=False)


def _compile_flags(flags_raw: Any, where: str) -> int:
    if flags_raw is None:
        return 0
    if not isinstance(flags_raw, list):
        raise RuleLoadError(f"{where}: 'flags' must be a list, got {type(flags_raw).__name__}")
    out = 0
    for f in flags_raw:
        if not isinstance(f, str):
            raise RuleLoadError(f"{where}: flag entries must be strings")
        if f not in SUPPORTED_FLAGS:
            raise RuleLoadError(
                f"{where}: unknown flag {f!r}; supported: {sorted(SUPPORTED_FLAGS)}"
            )
        out |= SUPPORTED_FLAGS[f]
    return out


def _validate_pattern_entry(entry: Any, where: str, *, require_label: bool = False) -> None:
    if not isinstance(entry, dict):
        raise RuleLoadError(f"{where}: pattern entry must be a mapping")
    regex = entry.get("regex")
    if not isinstance(regex, str) or not regex:
        raise RuleLoadError(f"{where}: missing or empty 'regex' field")
    flags = _compile_flags(entry.get("flags"), where)
    try:
        re.compile(regex, flags)
    except re.error as exc:
        raise RuleLoadError(f"{where}: invalid regex {regex!r}: {exc}") from exc
    if require_label:
        label = entry.get("label")
        if not isinstance(label, str) or not label:
            raise RuleLoadError(f"{where}: 'label' field required and must be non-empty")


@dataclass(frozen=True)
class RuleTypeSchema:
    """Per-rule_type pattern-key contract.

    ``list_pattern_keys`` / ``single_pattern_keys`` are ``(key, require_label)``
    tuples naming the YAML keys whose entries are validated as pattern objects
    (``{regex, flags?, label?}``). ``require_label`` forces a non-empty
    ``label`` (used where downstream consumers need a human tag per pattern).
    """

    list_pattern_keys: tuple[tuple[str, bool], ...]
    single_pattern_keys: tuple[tuple[str, bool], ...] = ()


RULE_TYPE_SCHEMAS: dict[str, RuleTypeSchema] = {}


def register_rule_type(
    name: str,
    *,
    list_pattern_keys: list[tuple[str, bool]],
    single_pattern_keys: list[tuple[str, bool]] | None = None,
) -> None:
    """Register a rule_type so :func:`validate_yaml_text` accepts its YAMLs.

    The extension point that lets new skill rule families (and project /
    plugin overrides) plug into the same loader without editing it.
    """
    RULE_TYPE_SCHEMAS[name] = RuleTypeSchema(
        tuple(list_pattern_keys), tuple(single_pattern_keys or ())
    )


register_rule_type(
    "wiring",
    list_pattern_keys=[("empty_handler_patterns", False)],
    single_pattern_keys=[("placeholder_pragma", False)],
)
register_rule_type(
    "e2e",
    list_pattern_keys=[
        ("backdoor_patterns", True),  # require label
        ("real_input_patterns", False),
    ],
)
register_rule_type(
    "doc_terms",
    list_pattern_keys=[("forbidden_terms", True)],  # doc-review term checks
)


def validate_yaml_text(text: str, source: str) -> RuleSpec:
    """Parse + schema-validate a rules YAML body. Raises :class:`RuleLoadError`."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleLoadError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RuleLoadError(f"{source}: top-level must be a mapping")

    sv = data.get("schema_version")
    if sv != CURRENT_SCHEMA_VERSION:
        raise RuleLoadError(
            f"{source}: unsupported schema_version {sv!r}; "
            f"expected {CURRENT_SCHEMA_VERSION}"
        )

    rule_type = data.get("rule_type")
    if not isinstance(rule_type, str) or not rule_type:
        raise RuleLoadError(f"{source}: 'rule_type' required (got {rule_type!r})")
    if rule_type not in RULE_TYPE_SCHEMAS:
        raise RuleLoadError(
            f"{source}: unknown rule_type {rule_type!r}; "
            f"supported: {sorted(RULE_TYPE_SCHEMAS)}"
        )

    language = data.get("language")
    if not isinstance(language, str) or not language:
        raise RuleLoadError(f"{source}: 'language' required (got {language!r})")

    exts_raw = data.get("extensions") or []
    if not isinstance(exts_raw, list):
        raise RuleLoadError(f"{source}: 'extensions' must be a list")
    exts: set[str] = set()
    for e in exts_raw:
        if not isinstance(e, str):
            raise RuleLoadError(f"{source}: extension entries must be strings")
        exts.add(e.lower())

    schema = RULE_TYPE_SCHEMAS[rule_type]
    for key, require_label in schema.list_pattern_keys:
        items = data.get(key) or []
        if not isinstance(items, list):
            raise RuleLoadError(f"{source}: {key!r} must be a list")
        for idx, entry in enumerate(items):
            _validate_pattern_entry(
                entry, f"{source}:{key}[{idx}]", require_label=require_label
            )
    for key, require_label in schema.single_pattern_keys:
        entry = data.get(key)
        if entry is None:
            continue
        _validate_pattern_entry(entry, f"{source}:{key}", require_label=require_label)

    return RuleSpec(
        schema_version=sv,
        rule_type=rule_type,
        language=language,
        extensions=frozenset(exts),
        source=source,
        raw=data,
    )


def _iter_package_rule_files(builtin_module: str):
    """Yield ``(name, text)`` pairs from the package ``rules`` subdir.

    Returns nothing when the module doesn't ship a ``rules`` subdir (the
    skill simply doesn't use the plugin architecture).
    """
    try:
        pkg = resources.files(builtin_module).joinpath("rules")
    except (ModuleNotFoundError, TypeError):
        return
    if not pkg.is_dir():
        return
    for entry in pkg.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if not name.endswith(YAML_SUFFIXES):
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except OSError:
            continue
        yield name, text


def _project_rule_dirs(project_root: Path, skill_id: str) -> list[Path]:
    """Rule dirs for *skill_id*, LOW → HIGH priority.

    The scaffold ``skills/<id>/rules`` first, then the project and user
    override layers, so a later layer's YAML for the same ``(rule_type,
    language)`` replaces the earlier one.
    """
    from cataforge.core.layers import OVERRIDE_LAYERS
    from cataforge.core.paths import ProjectPaths

    paths = ProjectPaths(project_root)
    dirs = [paths.skills_dir / skill_id / "rules"]
    dirs += [
        paths.override_layer(layer) / "skills" / skill_id / "rules"
        for layer in OVERRIDE_LAYERS
    ]
    return dirs


def _iter_project_rule_files(project_root: Path | None, skill_id: str):
    if project_root is None:
        return
    for rules_dir in _project_rule_dirs(project_root, skill_id):
        if not rules_dir.is_dir():
            continue
        for path in sorted(rules_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in YAML_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            yield path, text


def discover_rules(
    skill_id: str,
    *,
    builtin_module: str,
    project_root: Path | None = None,
) -> dict[tuple[str, str], RuleSpec]:
    """Resolve rules for one skill: package defaults + project overrides.

    Returns ``{(rule_type, language): RuleSpec}``. Project entries
    replace package entries with the same key. A malformed default
    raises immediately (the framework ships broken rules); a malformed
    project file also raises so the user notices instead of silently
    falling back. ``framework-review`` should call
    :func:`validate_yaml_text` directly on project files for surfacing
    validation problems as audit findings rather than runtime errors.
    """
    found: dict[tuple[str, str], RuleSpec] = {}

    for name, text in _iter_package_rule_files(builtin_module):
        spec = validate_yaml_text(text, f"package:{name}")
        found[(spec.rule_type, spec.language)] = spec

    for path, text in _iter_project_rule_files(project_root, skill_id):
        spec = validate_yaml_text(text, str(path))
        found[(spec.rule_type, spec.language)] = spec

    return found
