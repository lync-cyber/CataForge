"""Loader for skill-level rules YAML files (schema v2).

Resolution order, highest priority first:

1. ``<project_root>/.cataforge/skills/{skill_id}/rules/*.yaml``
   — project-local override; replaces a default for the same
   ``(rule_type, language)`` pair, or adds a new language.
2. ``cataforge.runtime.skill.builtins.{skill_dir}.rules.*.yaml`` — the
   default rule set shipped with the framework.

Every rules YAML declares a ``scope``:

* ``scope: language`` — language-bound patterns; ``language`` required,
  ``extensions`` lists the file suffixes the rules apply to.
* ``scope: project`` — one language-agnostic model per rule_type (e.g.
  an architecture layer model); ``language`` / ``extensions`` are
  forbidden. Keyed as ``(rule_type, "")``.

The loader returns :class:`RuleSpec` entries; downstream callers
(code-review wiring scan, testing e2e scan) translate each spec into
their internal compiled-pattern form. Schema validation lives here so
``framework-review`` can re-use :func:`validate_yaml_text` to gate
project YAMLs without duplicating the parsing logic. A rule_type may
register an ``extra_validator`` for structural keys beyond the pattern
lists; rule_types without one reject unknown top-level keys (typo
guard).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

CURRENT_SCHEMA_VERSION = 2

SCOPES = ("language", "project")

_V1_MIGRATION_HINT = (
    "schema_version 1 已废弃，迁移到 2: 添加 scope: language（语言绑定规则）或 "
    "scope: project（项目级模型，language/extensions 移除）；wiring 规则删除 "
    "placeholder_pragma 键，文件级豁免改用统一注释 "
    'cataforge: allow(<check-id>, reason="...")（见 .cataforge/references/pragma-grammar.md）'
)

SUPPORTED_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "UNICODE": re.UNICODE,
    "VERBOSE": re.VERBOSE,
}

YAML_SUFFIXES = (".yaml", ".yml")

_BASE_KEYS = frozenset({"schema_version", "rule_type", "scope", "language", "extensions"})


class RuleLoadError(ValueError):
    """Raised when a rules YAML fails schema or regex validation."""


@dataclass(frozen=True)
class RuleSpec:
    """One parsed rules YAML file.

    ``raw`` carries the original mapping so each rule_type's downstream
    consumer can read the type-specific keys (``empty_handler_patterns``,
    ``backdoor_patterns``, etc.) without the loader needing to know
    every rule_type schema upfront. ``language`` is ``""`` for
    project-scope specs.
    """

    schema_version: int
    rule_type: str
    scope: str
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


ExtraValidator = Callable[[dict[str, Any], str], None]


@dataclass(frozen=True)
class RuleTypeSchema:
    """Per-rule_type contract.

    ``list_pattern_keys`` / ``single_pattern_keys`` are ``(key, require_label)``
    tuples naming the YAML keys whose entries are validated as pattern objects
    (``{regex, flags?, label?}``). ``extra_validator`` (optional) validates
    the rule_type's structural keys beyond the pattern lists; when absent,
    unknown top-level keys are rejected so a typo'd key fails loudly instead
    of silently deactivating a rule.
    """

    list_pattern_keys: tuple[tuple[str, bool], ...]
    single_pattern_keys: tuple[tuple[str, bool], ...] = ()
    extra_validator: ExtraValidator | None = None

    def pattern_keys(self) -> frozenset[str]:
        return frozenset(k for k, _ in self.list_pattern_keys + self.single_pattern_keys)


RULE_TYPE_SCHEMAS: dict[str, RuleTypeSchema] = {}


def register_rule_type(
    name: str,
    *,
    list_pattern_keys: list[tuple[str, bool]],
    single_pattern_keys: list[tuple[str, bool]] | None = None,
    extra_validator: ExtraValidator | None = None,
) -> None:
    """Register a rule_type so :func:`validate_yaml_text` accepts its YAMLs.

    The extension point that lets new skill rule families (and project /
    plugin overrides) plug into the same loader without editing it.
    """
    RULE_TYPE_SCHEMAS[name] = RuleTypeSchema(
        tuple(list_pattern_keys),
        tuple(single_pattern_keys or ()),
        extra_validator,
    )


_ARCH_PROJECT_KEYS = frozenset({"enforce", "layers", "rules"})
_ARCH_LAYER_KEYS = frozenset({"name", "paths", "modules"})
_ARCH_ENFORCE_VALUES = ("warn", "fail")


def _validate_arch_layers(layers_raw: Any, source: str) -> list[str]:
    """Validate the project-scope ``layers`` list; return declared names."""
    if not isinstance(layers_raw, list) or not layers_raw:
        raise RuleLoadError(f"{source}: 'layers' must be a non-empty list")
    names: list[str] = []
    for idx, layer in enumerate(layers_raw):
        where = f"{source}:layers[{idx}]"
        if not isinstance(layer, dict):
            raise RuleLoadError(f"{where}: layer entry must be a mapping")
        unknown = set(layer) - _ARCH_LAYER_KEYS
        if unknown:
            raise RuleLoadError(f"{where}: unknown key(s) {sorted(unknown)}")
        name = layer.get("name")
        if not isinstance(name, str) or not name:
            raise RuleLoadError(f"{where}: 'name' required and must be non-empty")
        if name in names:
            raise RuleLoadError(f"{where}: duplicate layer name {name!r}")
        paths = layer.get("paths")
        if (
            not isinstance(paths, list)
            or not paths
            or not all(isinstance(p, str) and p for p in paths)
        ):
            raise RuleLoadError(f"{where}: 'paths' must be a non-empty list of glob strings")
        modules = layer.get("modules") or []
        if not isinstance(modules, list) or not all(isinstance(m, str) and m for m in modules):
            raise RuleLoadError(f"{where}: 'modules' must be a list of module-prefix strings")
        names.append(name)
    return names


def _validate_arch_rules(rules_raw: Any, names: list[str], source: str) -> None:
    """Validate the direction matrix against the declared layer names."""
    if not isinstance(rules_raw, dict):
        raise RuleLoadError(f"{source}: 'rules' must be a mapping of layer -> allowed layers")
    unknown = set(rules_raw) - set(names)
    if unknown:
        raise RuleLoadError(f"{source}: 'rules' references undeclared layer(s) {sorted(unknown)}")
    missing = [n for n in names if n not in rules_raw]
    if missing:
        raise RuleLoadError(
            f"{source}: 'rules' missing direction entry for layer(s) {missing} "
            "(empty list = the layer may depend on itself only)"
        )
    for layer_name, allowed in rules_raw.items():
        where = f"{source}:rules[{layer_name}]"
        if not isinstance(allowed, list) or not all(isinstance(t, str) for t in allowed):
            raise RuleLoadError(f"{where}: must be a list of layer names")
        bad = [t for t in allowed if t not in names]
        if bad:
            raise RuleLoadError(f"{where}: undeclared layer(s) {bad}")


def _validate_arch(data: dict[str, Any], source: str) -> None:
    """arch structural contract, branched by scope.

    ``scope: language`` files carry only ``import_patterns`` (capture group
    1 = the imported module specifier). ``scope: project`` files carry the
    layer model: ``layers`` + ``rules`` direction matrix + optional
    ``enforce``.
    """
    if data.get("scope") == "language":
        unknown = set(data) - _BASE_KEYS - {"import_patterns"}
        if unknown:
            raise RuleLoadError(
                f"{source}: unknown key(s) {sorted(unknown)} for rule_type 'arch' (scope language)"
            )
        patterns = data.get("import_patterns")
        if not isinstance(patterns, list) or not patterns:
            raise RuleLoadError(f"{source}: scope 'language' requires non-empty 'import_patterns'")
        for idx, entry in enumerate(patterns):
            where = f"{source}:import_patterns[{idx}]"
            if re.compile(entry["regex"], _compile_flags(entry.get("flags"), where)).groups < 1:
                raise RuleLoadError(f"{where}: regex needs capture group 1 = imported module")
        return
    unknown = set(data) - _BASE_KEYS - _ARCH_PROJECT_KEYS
    if unknown:
        raise RuleLoadError(
            f"{source}: unknown key(s) {sorted(unknown)} for rule_type 'arch' (scope project)"
        )
    enforce = data.get("enforce", "fail")
    if enforce not in _ARCH_ENFORCE_VALUES:
        raise RuleLoadError(
            f"{source}: 'enforce' must be one of {list(_ARCH_ENFORCE_VALUES)} (got {enforce!r})"
        )
    names = _validate_arch_layers(data.get("layers"), source)
    _validate_arch_rules(data.get("rules"), names, source)


register_rule_type(
    "wiring",
    list_pattern_keys=[("empty_handler_patterns", False)],
)
register_rule_type(
    "arch",
    list_pattern_keys=[("import_patterns", True)],  # require label
    extra_validator=_validate_arch,
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


def _validate_scope_fields(
    data: dict[str, Any], scope: str, source: str
) -> tuple[str, frozenset[str]]:
    """Return ``(language, extensions)`` per the scope contract."""
    if scope == "project":
        for forbidden in ("language", "extensions"):
            if forbidden in data:
                raise RuleLoadError(
                    f"{source}: scope 'project' forbids {forbidden!r} "
                    "(project-scope specs are language-agnostic)"
                )
        return "", frozenset()

    language = data.get("language")
    if not isinstance(language, str) or not language:
        raise RuleLoadError(f"{source}: 'language' required for scope 'language'")
    exts_raw = data.get("extensions") or []
    if not isinstance(exts_raw, list):
        raise RuleLoadError(f"{source}: 'extensions' must be a list")
    exts: set[str] = set()
    for e in exts_raw:
        if not isinstance(e, str):
            raise RuleLoadError(f"{source}: extension entries must be strings")
        exts.add(e.lower())
    return language, frozenset(exts)


def _validate_header(data: dict[str, Any], source: str) -> tuple[int, str, str]:
    """Validate schema_version / rule_type / scope; return them."""
    sv = data.get("schema_version")
    if sv == 1:
        raise RuleLoadError(f"{source}: {_V1_MIGRATION_HINT}")
    if sv != CURRENT_SCHEMA_VERSION:
        raise RuleLoadError(
            f"{source}: unsupported schema_version {sv!r}; expected {CURRENT_SCHEMA_VERSION}"
        )

    rule_type = data.get("rule_type")
    if not isinstance(rule_type, str) or not rule_type:
        raise RuleLoadError(f"{source}: 'rule_type' required (got {rule_type!r})")
    if rule_type not in RULE_TYPE_SCHEMAS:
        raise RuleLoadError(
            f"{source}: unknown rule_type {rule_type!r}; supported: {sorted(RULE_TYPE_SCHEMAS)}"
        )

    scope = data.get("scope")
    if scope not in SCOPES:
        raise RuleLoadError(f"{source}: 'scope' required, one of {list(SCOPES)} (got {scope!r})")
    return sv, rule_type, scope


def validate_yaml_text(text: str, source: str) -> RuleSpec:
    """Parse + schema-validate a rules YAML body. Raises :class:`RuleLoadError`."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleLoadError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RuleLoadError(f"{source}: top-level must be a mapping")

    sv, rule_type, scope = _validate_header(data, source)
    language, exts = _validate_scope_fields(data, scope, source)

    schema = RULE_TYPE_SCHEMAS[rule_type]
    if schema.extra_validator is None:
        unknown = set(data) - _BASE_KEYS - schema.pattern_keys()
        if unknown:
            raise RuleLoadError(
                f"{source}: unknown key(s) {sorted(unknown)} for rule_type {rule_type!r}"
            )
    for key, require_label in schema.list_pattern_keys:
        items = data.get(key) or []
        if not isinstance(items, list):
            raise RuleLoadError(f"{source}: {key!r} must be a list")
        for idx, entry in enumerate(items):
            _validate_pattern_entry(entry, f"{source}:{key}[{idx}]", require_label=require_label)
    for key, require_label in schema.single_pattern_keys:
        entry = data.get(key)
        if entry is None:
            continue
        _validate_pattern_entry(entry, f"{source}:{key}", require_label=require_label)
    if schema.extra_validator is not None:
        schema.extra_validator(data, source)

    return RuleSpec(
        schema_version=sv,
        rule_type=rule_type,
        scope=scope,
        language=language,
        extensions=exts,
        source=source,
        raw=data,
    )


def _is_placeholder_yaml(text: str) -> bool:
    """Comment-only / empty YAML — a shipped template, not a rule file.

    Skipped by :func:`discover_rules` so a fully commented-out model
    template (e.g. the builtin ``arch.yaml``) equals "no model declared".
    """
    try:
        return yaml.safe_load(text) is None
    except yaml.YAMLError:
        return False  # let validate_yaml_text raise a proper error


def _iter_package_rule_files(builtin_module: str) -> Iterator[tuple[str, str]]:
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
            text = entry.read_text()
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
        paths.override_layer(layer) / "skills" / skill_id / "rules" for layer in OVERRIDE_LAYERS
    ]
    return dirs


def _iter_project_rule_files(
    project_root: Path | None, skill_id: str
) -> Iterator[tuple[Path, str]]:
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
                text = path.read_text()
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

    Returns ``{(rule_type, language): RuleSpec}`` (project-scope specs use
    ``""`` as the language key — one model per rule_type). Project entries
    replace package entries with the same key. A malformed default
    raises immediately (the framework ships broken rules); a malformed
    project file also raises so the user notices instead of silently
    falling back. ``framework-review`` should call
    :func:`validate_yaml_text` directly on project files for surfacing
    validation problems as audit findings rather than runtime errors.
    """
    found: dict[tuple[str, str], RuleSpec] = {}

    for name, text in _iter_package_rule_files(builtin_module):
        if _is_placeholder_yaml(text):
            continue
        spec = validate_yaml_text(text, f"package:{name}")
        found[(spec.rule_type, spec.language)] = spec

    for path, text in _iter_project_rule_files(project_root, skill_id):
        if _is_placeholder_yaml(text):
            continue
        spec = validate_yaml_text(text, str(path))
        found[(spec.rule_type, spec.language)] = spec

    return found
