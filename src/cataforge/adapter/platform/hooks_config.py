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


def _is_owned_hook_entry(entry: Any, owned_prefixes: tuple[str, ...]) -> bool:
    """True iff every command in *entry* starts with a CataForge-owned prefix."""
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        return False
    commands = [h.get("command", "") for h in hooks if isinstance(h, dict)]
    if not commands:
        return False
    return all(any(cmd.startswith(p) for p in owned_prefixes) for cmd in commands)


def merge_hooks_config(
    existing_hooks: Any,
    generated_hooks: Any,
    owned_prefixes: tuple[str, ...],
) -> dict[str, Any]:
    """Splice freshly generated hook entries into an existing ``hooks`` map.

    CataForge owns the entries whose command starts with one of
    ``owned_prefixes``; those are dropped and replaced by ``generated_hooks``.
    Foreign entries (user- or other-tool-authored, e.g. a hand-written
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
            if not _is_owned_hook_entry(entry, owned_prefixes)
        ]
        combined = preserved + list(generated.get(event, []))
        if combined:
            merged[event] = combined
    return merged
