"""Hook configuration merging for platform adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cataforge.core.errors import CataforgeError, ConfigError
from cataforge.core.io import read_json
from cataforge.utils.atomic_write import atomic_write_text


def merge_json_key(path: Path, dotted_key: str, value: Any, *, dry_run: bool = False) -> list[str]:
    """Merge a value into a JSON file at a dotted key path."""
    if dry_run:
        return [f"would merge {dotted_key} → {path}"]

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        try:
            data = read_json(path)
        except ConfigError as exc:
            raise CataforgeError(
                f"existing config corrupted (cannot merge): {path} ({exc}). "
                f"Fix or remove the file and retry."
            ) from exc
        except OSError as exc:
            raise CataforgeError(f"cannot read existing config: {path} ({exc}).") from exc
    else:
        data = {}

    keys = dotted_key.split(".")
    obj = data
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value

    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return [f"merged {dotted_key} → {path}"]


def merge_json_list(
    path: Path, dotted_key: str, items: list[str], *, dry_run: bool = False
) -> list[str]:
    """Union-merge string *items* into a JSON list at *dotted_key* (order-preserving).

    Existing entries the user added are kept; only genuinely new items are
    appended. The file/key is created when absent. A no-op (every item already
    present) writes nothing.
    """
    if dry_run:
        return [f"would enable {','.join(items)} in {path}"]

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = read_json(path)
        except ConfigError as exc:
            raise CataforgeError(
                f"existing config corrupted (cannot merge): {path} ({exc}). "
                f"Fix or remove the file and retry."
            ) from exc
    else:
        data = {}

    keys = dotted_key.split(".")
    obj = data
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    current = obj.get(keys[-1])
    merged = list(current) if isinstance(current, list) else []
    added = [it for it in items if it not in merged]
    if not added:
        return []
    merged.extend(added)
    obj[keys[-1]] = merged

    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return [f"enabled {','.join(added)} in {path}"]


def seed_settings_defaults(data: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Set-if-absent seed of framework default settings into a settings dict.

    Top-level ``dict`` values merge per leaf key (only missing keys are added);
    scalar values use ``setdefault``. A key the user already set is never
    overwritten, so a deliberate override survives every redeploy.
    """
    for key, value in defaults.items():
        if isinstance(value, dict):
            target = data.setdefault(key, {})
            if isinstance(target, dict):
                for leaf, leaf_value in value.items():
                    target.setdefault(leaf, leaf_value)
        else:
            data.setdefault(key, value)


# Marker substrings identifying CataForge-generated hook commands regardless
# of the interpreter spelling in front of them (bare ``python``, any quoted
# absolute path, the current ``sys.executable``).
OWNED_HOOK_MARKERS: tuple[str, ...] = (
    "-m cataforge.runtime.hook.scripts.",
    ".cataforge/hooks/custom/",
)


def _is_owned_hook_entry(entry: Any, owned_markers: tuple[str, ...]) -> bool:
    """True iff every command in *entry* contains a CataForge-owned marker."""
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        return False
    commands = [h.get("command", "") for h in hooks if isinstance(h, dict)]
    if not commands:
        return False
    return all(any(marker in cmd for marker in owned_markers) for cmd in commands)


def merge_hooks_config(
    existing_hooks: Any,
    generated_hooks: Any,
    owned_markers: tuple[str, ...] = OWNED_HOOK_MARKERS,
) -> dict[str, Any]:
    """Splice freshly generated hook entries into an existing ``hooks`` map.

    CataForge owns the entries whose command contains one of
    ``owned_markers``; those are dropped and replaced by ``generated_hooks``.
    Substring (not prefix) matching keeps ownership detection independent of
    the interpreter a previous deploy wrote in front of the marker. Foreign
    entries (user- or other-tool-authored, e.g. a hand-written
    ``SessionStart`` bootstrap) are preserved verbatim, so a deploy never
    silently removes hooks CataForge did not write. Events that exist only in
    the prior map survive with their foreign entries intact.
    """
    existing = existing_hooks if isinstance(existing_hooks, dict) else {}
    generated = generated_hooks if isinstance(generated_hooks, dict) else {}

    merged: dict[str, Any] = {}
    events = list(existing.keys()) + [e for e in generated if e not in existing]
    for event in events:
        prior = existing.get(event, [])
        preserved = [
            entry
            for entry in (prior if isinstance(prior, list) else [])
            if not _is_owned_hook_entry(entry, owned_markers)
        ]
        combined = preserved + list(generated.get(event, []))
        if combined:
            merged[event] = combined
    return merged
