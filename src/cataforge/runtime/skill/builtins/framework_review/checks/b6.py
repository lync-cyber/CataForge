"""B6 — hooks.yaml consistency: script reachability, syntax, capability, manifest, degradation."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from .._hook_resolution import (
    load_capability_ids,
    load_hooks_manifest_names,
    resolve_builtin_hook_dir,
    resolve_hook_script,
)
from .._types import Report


def check_b6_hook_consistency(root: Path, report: Report) -> None:
    """B6: hook 元资产审查.

    Five sub-checks operating on ``.cataforge/hooks/hooks.yaml`` and the
    per-platform ``profile.yaml`` files:

    * α — script reachability: every ``script`` referenced in hooks.yaml
      resolves to a real .py file.  Builtins live in
      ``cataforge.runtime.hook.scripts.<name>`` (resolved via ``importlib.resources``
      so editable / wheel installs both work); customs are referenced as
      ``custom:<name>`` and live at ``.cataforge/hooks/custom/<name>.py``.
    * β — script syntax: each resolved script is ``ast.parse``-able.
      Catches half-edited scripts before deploy generates broken hook
      configs.
    * γ — matcher_capability validity: each ``matcher_capability`` value
      is a member of ``CAPABILITY_IDS`` ∪ ``EXTENDED_CAPABILITY_IDS``.
      A typo here silently produces a hook that never fires.
    * δ — degradation parity: for every platform ``profile.yaml`` under
      ``.cataforge/platforms/``, the keys of ``hooks.degradation`` must
      exactly match the set of script names referenced in hooks.yaml.
      Missing flag → WARN; orphan flag → WARN (dead config).
    * ε — manifest drift: every non-``custom:`` script in hooks.yaml
      must appear in ``cataforge.runtime.hook.manifest.HOOKS_MANIFEST``. Catches
      "wired a helper module as a hook" bugs.
    """
    hooks_yaml = root / ".cataforge" / "hooks" / "hooks.yaml"
    if not hooks_yaml.is_file():
        return
    try:
        hooks_data = yaml.safe_load(hooks_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        report.add(
            "B6_hook_consistency",
            "FAIL",
            "hooks/hooks.yaml",
            f"failed to parse hooks.yaml: {e}",
        )
        return
    if not isinstance(hooks_data, dict):
        return

    referenced_scripts, referenced_caps = _collect_references(hooks_data)

    _check_reachability_and_syntax(referenced_scripts, root, report)
    _check_capabilities(referenced_caps, report)
    _check_manifest_drift(referenced_scripts, report)
    _check_degradation_parity(referenced_scripts, root, report)


def _collect_references(hooks_data: dict) -> tuple[set[str], set[str]]:
    """Gather the ``script`` and ``matcher_capability`` values wired in hooks.yaml."""
    referenced_scripts: set[str] = set()
    referenced_caps: set[str] = set()
    for _event, entries in (hooks_data.get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            script = entry.get("script")
            cap = entry.get("matcher_capability")
            if script:
                referenced_scripts.add(script)
            if cap:
                referenced_caps.add(cap)
    return referenced_scripts, referenced_caps


def _check_reachability_and_syntax(
    referenced_scripts: set[str], root: Path, report: Report
) -> None:
    """α + β: every referenced script resolves to a real, ast-parseable .py."""
    builtin_dir = resolve_builtin_hook_dir()
    custom_dir = root / ".cataforge" / "hooks" / "custom"
    for script in sorted(referenced_scripts):
        py_path = resolve_hook_script(script, builtin_dir, custom_dir)
        if py_path is None:
            report.add(
                "B6_hook_script_reachability",
                "FAIL",
                f"hooks/{script}",
                "script referenced in hooks.yaml but no .py file found "
                "(checked builtin cataforge.runtime.hook.scripts and "
                ".cataforge/hooks/custom/)",
            )
            continue
        try:
            ast.parse(py_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as e:
            report.add(
                "B6_hook_script_syntax",
                "FAIL",
                f"hooks/{script}",
                f"script {py_path.name} not ast-parseable: {e}",
            )


def _check_capabilities(referenced_caps: set[str], report: Report) -> None:
    """γ: every matcher_capability is a known CAPABILITY id."""
    valid_caps = load_capability_ids()
    if valid_caps:
        for cap in sorted(referenced_caps):
            if cap not in valid_caps:
                report.add(
                    "B6_hook_matcher_capability",
                    "FAIL",
                    f"hooks/{cap}",
                    f"matcher_capability {cap!r} not in CAPABILITY_IDS / "
                    "EXTENDED_CAPABILITY_IDS — hook will silently never "
                    "fire (bridge can't map unknown capability to a "
                    "platform tool)",
                )


def _check_manifest_drift(referenced_scripts: set[str], report: Report) -> None:
    """ε: hooks.yaml builtin scripts must appear in HOOKS_MANIFEST (and vice versa)."""
    manifest_names_set = load_hooks_manifest_names()
    if manifest_names_set:
        for script in sorted(referenced_scripts):
            if script.startswith("custom:"):
                continue
            if script not in manifest_names_set:
                report.add(
                    "B6_hook_manifest_drift",
                    "FAIL",
                    f"hooks/{script}",
                    f"hooks.yaml references {script!r} but it is not in "
                    f"cataforge.runtime.hook.manifest.HOOKS_MANIFEST; either "
                    f"register it there (preferred — declares it as a "
                    f"hook target) or use 'custom:' prefix to opt out",
                )
        # Reverse: every manifest entry that's never wired in hooks.yaml
        # is dead inventory (WARN).
        wired_builtins = {
            s for s in referenced_scripts if not s.startswith("custom:")
        }
        for unwired in sorted(manifest_names_set - wired_builtins):
            report.add(
                "B6_hook_manifest_drift",
                "WARN",
                f"hooks/{unwired}",
                f"HOOKS_MANIFEST entry {unwired!r} not referenced by "
                f"hooks.yaml; either wire it in or remove the manifest "
                f"entry to avoid shipping dead inventory",
            )


def _check_degradation_parity(
    referenced_scripts: set[str], root: Path, report: Report
) -> None:
    """δ: each platform profile's degradation keys match hooks.yaml scripts."""
    platforms_dir = root / ".cataforge" / "platforms"
    if not platforms_dir.is_dir():
        return
    for plat_dir in sorted(platforms_dir.iterdir()):
        if not plat_dir.is_dir():
            continue
        profile_path = plat_dir / "profile.yaml"
        if not profile_path.is_file():
            continue
        try:
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(profile, dict):
            continue
        degradation = ((profile.get("hooks") or {}).get("degradation")) or {}
        if not isinstance(degradation, dict):
            continue
        declared = set(degradation.keys())
        # custom: scripts ship per-project; degradation key drops the prefix.
        normalized_refs = {
            s.removeprefix("custom:") for s in referenced_scripts
        }
        missing = sorted(normalized_refs - declared)
        orphan = sorted(declared - normalized_refs)
        for script in missing:
            report.add(
                "B6_hook_degradation_coverage",
                "WARN",
                f"platforms/{plat_dir.name}",
                f"script {script!r} referenced in hooks.yaml but has no "
                "degradation flag in this profile.yaml — deploy will "
                "default to implicit 'native' which may silently mask a "
                "real degradation requirement",
            )
        for script in orphan:
            report.add(
                "B6_hook_degradation_coverage",
                "WARN",
                f"platforms/{plat_dir.name}",
                f"degradation entry {script!r} has no matching hooks.yaml "
                "script — dead config (silently outdated since the script "
                "was removed)",
            )
