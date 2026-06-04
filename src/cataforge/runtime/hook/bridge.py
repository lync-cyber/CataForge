"""Hook bridge — generate platform hook configs from hooks.yaml + adapter.

Bridges CataForge's canonical hook spec (``hooks.yaml``) to each platform's
native hook config, collecting *warnings* for any hook entry that could not
be materialised natively (missing event mapping, missing matcher mapping).
Callers (``deploy`` / ``doctor``) are expected to surface those warnings to
the user so silent functional loss becomes observable.

Degradation strategies (used when a platform marks a canonical hook as
``degraded`` rather than ``native``) are materialised by
:func:`apply_degradation`. The implemented strategy set is the module-level
:data:`KNOWN_DEGRADATION_STRATEGIES`; any other value found in a degradation
template emits a ``WARN: …`` action line so the deploy log surfaces the gap
instead of silently dropping the hook.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.core.paths import ProjectPaths
from cataforge.runtime.hook.hooks_schema import HooksSpec
from cataforge.utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)


# Highest schema version this release understands.  Older hooks.yaml files
# are treated as v1 (missing/optional fields default to "no filter").
SUPPORTED_SCHEMA_VERSION = 2

# Degradation strategies materialised by :func:`apply_degradation`.
#
#  - ``rules_injection``    — accumulate safety rule text into
#                             ``auto-safety-degradation.md``
#  - ``prompt_instruction`` — accumulate agent instructions (e.g. audit-log
#                             commands) into ``auto-prompt-instructions.md``
#  - ``prompt_checklist``   — accumulate self-check checklists into
#                             ``auto-prompt-checklists.md``
#  - ``skip``               — emit a ``SKIP: …`` line; no file written
#
# Any other value found in a ``degradation_templates`` entry emits a
# ``WARN: …`` action so the deploy log surfaces the unrecognised strategy
# instead of silently dropping the hook.
KNOWN_DEGRADATION_STRATEGIES = frozenset(
    {"rules_injection", "prompt_instruction", "prompt_checklist", "skip"}
)

# Per-strategy aggregate output file. Strategies not listed here either do
# not produce a file (``skip``) or are unknown (handled separately as WARN).
_AGGREGATE_OUTPUTS: tuple[tuple[str, str, str], ...] = (
    (
        "rules_injection",
        "auto-safety-degradation.md",
        "Auto-generated Safety Rules (Hook Degradation)",
    ),
    (
        "prompt_instruction",
        "auto-prompt-instructions.md",
        "Auto-generated Agent Instructions (Hook Degradation)",
    ),
    (
        "prompt_checklist",
        "auto-prompt-checklists.md",
        "Auto-generated Self-check Checklists (Hook Degradation)",
    ),
)


class HookGenerationResult(NamedTuple):
    """Return value of :func:`generate_platform_hooks`.

    Using a NamedTuple keeps old positional-unpacking call sites working while
    attaching a second, named field for warnings.
    """

    hooks: dict[str, Any]
    warnings: list[str]


def load_hooks_spec(hooks_yaml: Path | None = None) -> dict[str, Any]:
    """Load and validate the canonical hook specification from hooks.yaml.

    A structurally malformed spec (wrong ``schema_version`` type, ``hooks``
    that is not an event→entry-list mapping, a hook entry missing ``script`` …)
    fails here with a ``pydantic.ValidationError`` naming the offending field
    rather than as a ``KeyError`` deep in the platform bridge. The validated
    mapping is returned unchanged so the downstream dict pipeline is untouched.
    """
    if hooks_yaml is None:
        hooks_yaml = ProjectPaths().hooks_spec

    with open(hooks_yaml) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"hooks.yaml must be a mapping, got {type(data).__name__}")
    HooksSpec.model_validate(data)
    return data


def check_schema_version(spec: dict[str, Any]) -> str | None:
    """Validate ``schema_version`` against this release.

    Returns ``None`` when the version is supported (including the implicit
    v1 for files authored before the field existed), otherwise a warning
    string ready to show the user.
    """
    raw = spec.get("schema_version", 1)
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return f"hooks.yaml: schema_version must be an integer, got {raw!r}. Treating as v1."
    if version > SUPPORTED_SCHEMA_VERSION:
        return (
            f"hooks.yaml: schema_version={version} is newer than this "
            f"cataforge release understands (max v{SUPPORTED_SCHEMA_VERSION}). "
            "Consider upgrading the package."
        )
    return None


def generate_platform_hooks(adapter: PlatformAdapter) -> HookGenerationResult:
    """Generate platform-native hook configuration.

    Returns ``(hooks, warnings)``.  ``hooks`` is suitable for writing into
    the platform's hook config file; ``warnings`` enumerates every canonical
    hook that could not be emitted natively so the caller can surface it.
    """
    spec = load_hooks_spec()
    warnings: list[str] = []

    version_warning = check_schema_version(spec)
    if version_warning:
        warnings.append(version_warning)

    _merge_plugin_hooks(spec)

    event_map = adapter.hook_event_map
    degradation = adapter.hook_degradation
    tool_map = adapter.get_tool_map()
    hook_tool_overrides = getattr(adapter, "hook_tool_overrides", {}) or {}
    command_template = adapter.get_hook_command_template()

    platform_hooks: dict[str, list[dict[str, Any]]] = {}

    for event_name, hook_list in spec.get("hooks", {}).items():
        platform_event = event_map.get(event_name)
        if platform_event is None:
            for hook_entry in hook_list:
                script_name = _script_to_hook_name(hook_entry.get("script", "?"))
                warnings.append(
                    f"{adapter.platform_id}: event {event_name!r} has no platform "
                    f"mapping — hook {script_name!r} will not fire."
                )
            continue

        translated: list[dict[str, Any]] = []
        for hook_entry in hook_list:
            capability = hook_entry.get("matcher_capability", "")
            hook_name = _script_to_hook_name(hook_entry.get("script", ""))

            status = degradation.get(hook_name, "native")
            if status != "native":
                # Degraded/skipped hooks are handled by apply_degradation; we
                # still surface the loss of the native code path here so the
                # user understands that runtime blocking/observing is gone.
                warnings.append(
                    f"{adapter.platform_id}: hook {hook_name!r} is {status!r} "
                    f"(not native) — runtime behaviour replaced by a degradation "
                    "strategy (see `hook list`)."
                )
                continue

            if capability:
                native_tool = hook_tool_overrides.get(capability) or tool_map.get(capability)
                if native_tool is None:
                    warnings.append(
                        f"{adapter.platform_id}: matcher_capability "
                        f"{capability!r} has no tool mapping — hook "
                        f"{hook_name!r} on event {event_name} skipped."
                    )
                    continue
                platform_matcher = native_tool
            else:
                platform_matcher = ""

            module_name = _script_to_hook_name(hook_entry.get("script", ""))
            command = _resolve_command(command_template, module_name)

            # Emit the platform-native hook entry type (typically "command" for
            # JSON-config platforms like Claude Code / Cursor / Codex). The
            # internal "block" / "observe" in hooks.yaml is a CataForge-side
            # semantic tag used for CLI display and future policy — it must
            # not leak into platform configs, where it would be rejected or
            # silently ignored by the host IDE.
            platform_entry_type = adapter.hook_entry_type or hook_entry.get("type", "command")

            translated.append(
                {
                    "matcher": platform_matcher,
                    "hooks": [
                        {
                            "type": platform_entry_type,
                            "command": command,
                        }
                    ],
                }
            )

        if translated:
            platform_hooks[platform_event] = translated

    return HookGenerationResult(platform_hooks, warnings)


def _merge_plugin_hooks(spec: dict[str, Any]) -> None:
    """Fold plugin ``provides.hooks`` entries into *spec*'s event table.

    Each plugin hook dict carries an ``event`` key naming the canonical event;
    the remaining keys (``script`` / ``matcher_capability`` / ``type`` …) form
    a hook entry appended to that event's list, so plugin hooks translate
    through the same per-platform pipeline as built-in ones.
    """
    from cataforge.runtime.plugin.loader import PluginLoader

    try:
        plugin_hooks = PluginLoader().provided_hooks()
    except Exception as exc:  # plugin discovery must never break a deploy
        logger.warning("plugin hook discovery failed: %s", exc)
        return
    if not plugin_hooks:
        return
    hooks = spec.setdefault("hooks", {})
    for hook in plugin_hooks:
        event = hook.get("event")
        if not event:
            logger.warning("plugin hook missing 'event' key, skipped: %r", hook)
            continue
        entry = {k: v for k, v in hook.items() if k != "event"}
        hooks.setdefault(event, []).append(entry)


def _resolve_command(template: str, script_name: str) -> str:
    """Resolve a hook command line.

    Built-in scripts live in ``cataforge.runtime.hook.scripts.<name>`` and use the
    adapter's ``{module}`` template.  User-authored scripts are referenced
    with a ``custom:`` prefix (``script: custom:my_hook``) and are invoked
    directly from ``.cataforge/hooks/custom/<name>.py`` — this lets a project
    ship its own hooks without needing a plugin mechanism.
    """
    if script_name.startswith("custom:"):
        custom_name = script_name.removeprefix("custom:")
        # Path is relative to the project root, which every supported IDE
        # uses as the hook process's cwd.
        return f"python .cataforge/hooks/custom/{custom_name}.py"
    return template.format(module=script_name)


def get_degraded_hooks(adapter: PlatformAdapter) -> list[dict[str, Any]]:
    """Get hooks that need degradation and their fallback strategies."""
    spec = load_hooks_spec()
    degradation = adapter.hook_degradation
    templates = spec.get("degradation_templates", {})

    result: list[dict[str, Any]] = []
    for hook_name, status in degradation.items():
        if status == "degraded" and hook_name in templates:
            template = templates[hook_name]
            result.append(
                {
                    "name": hook_name,
                    "strategy": template.get("strategy", "skip"),
                    "content": template.get("content", ""),
                    "reason": template.get("reason", ""),
                }
            )
    return result


def apply_degradation(
    adapter: PlatformAdapter, project_root: Path, *, dry_run: bool = False
) -> list[str]:
    """Materialize degradation strategies into file changes.

    Each strategy in :data:`KNOWN_DEGRADATION_STRATEGIES` is handled
    explicitly; ``skip`` emits a single log line and the three
    file-producing strategies aggregate per-hook content into one Markdown
    file per strategy under ``.cataforge/platforms/{platform}/overrides/
    rules/``. Whether the platform adapter automatically picks those files
    up (Cursor scans ``overrides/rules/`` for ``.mdc`` wrapping; others may
    leave them for manual review) is platform-specific — by writing them
    unconditionally the bridge guarantees that no degraded hook is silently
    dropped.

    Unrecognised strategies emit a ``WARN: …`` action so the deploy log
    surfaces the gap.
    """
    degraded = get_degraded_hooks(adapter)
    actions: list[str] = []

    # Plugin-style platforms (OpenCode) materialise their hooks via a
    # generated plugin file in addition to whatever per-hook degradation
    # strategies still apply for events the plugin host cannot represent.
    plugin_actions = _emit_plugin_hooks(adapter, project_root, dry_run=dry_run)
    if plugin_actions is not None:
        actions.extend(plugin_actions)

    # Per-strategy accumulator. Each entry is ``(hook_name, content)`` so
    # the aggregated file labels every fragment with its source hook.
    aggregates: dict[str, list[tuple[str, str]]] = {item[0]: [] for item in _AGGREGATE_OUTPUTS}

    for entry in degraded:
        strategy = entry["strategy"]
        name = entry["name"]
        content = entry["content"]

        if strategy in aggregates:
            aggregates[strategy].append((name, content))
        elif strategy == "skip":
            actions.append(f"SKIP: {name} — {entry.get('reason', '')}")
        else:
            actions.append(
                f"WARN: {name} — unrecognised degradation strategy "
                f"{strategy!r}; nothing emitted. Known strategies: "
                f"{sorted(KNOWN_DEGRADATION_STRATEGIES)}"
            )

    auto_rules_dir = (
        project_root / ".cataforge" / "platforms" / adapter.platform_id / "overrides" / "rules"
    )

    for strategy, filename, heading in _AGGREGATE_OUTPUTS:
        fragments = aggregates[strategy]
        if not fragments:
            continue
        out_path = auto_rules_dir / filename
        if dry_run:
            actions.append(f"would write {strategy} → {out_path} ({len(fragments)} fragment(s))")
            continue
        auto_rules_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out_path, _render_aggregate(heading, fragments))
        actions.append(f"{strategy} → {out_path}")

    return actions


def _render_aggregate(heading: str, fragments: list[tuple[str, str]]) -> str:
    """Render aggregated degradation content with per-hook section headers."""
    parts = [f"# {heading}\n"]
    for hook_name, content in fragments:
        parts.append(f"\n## {hook_name}\n\n{content.strip()}\n")
    return "".join(parts)


def _emit_plugin_hooks(
    adapter: PlatformAdapter, project_root: Path, *, dry_run: bool = False
) -> list[str] | None:
    """Call the adapter's ``emit_plugin_hooks`` hook if defined.

    Platforms that use plugin files instead of JSON hook configs (OpenCode)
    implement this method to generate the plugin wrapper in one go.  Returns
    ``None`` when the adapter has no plugin surface — in that case the
    caller falls back to per-hook rules injection / skip.
    """
    fn = getattr(adapter, "emit_plugin_hooks", None)
    if fn is None:
        return None
    return list(fn(project_root, dry_run=dry_run))


def _script_to_hook_name(script: str) -> str:
    return script.replace(".py", "")
