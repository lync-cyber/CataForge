"""Migration check runner + runtime API version contract enforcement."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from cataforge.core.version import parse_semver

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


SUPPORTED_RUNTIME_API_VERSION = "1.0"
"""scaffold ↔ runtime contract version.

Bumped on backwards-incompatible scaffold/runtime interface changes
(field rename, removed key, type change). Fresh installs and
``cataforge upgrade apply`` always restamp framework.json with this
value via ``_merge_framework_json``; mismatch on a Config.load() means
either the user hand-edited framework.json to an unsupported version,
or they're running a wheel from before the contract bump against a
framework.json from after.
"""


def check_runtime_api_version(cfg: ConfigManager) -> int:
    declared = cfg.load().get("runtime_api_version")
    if declared is None:
        # Field ships in the scaffold framework.json and is refreshed as a
        # framework-owned key on every install/upgrade write, so a real
        # on-disk framework.json that went through the normal install path
        # can't be missing it. Hard-fail so the contract is meaningful —
        # hand-edits that drop it get told to restamp.
        click.echo(
            f"  FAIL: runtime_api_version field missing from framework.json "
            f"(expected {SUPPORTED_RUNTIME_API_VERSION!r}); "
            "run `cataforge upgrade apply` to restamp."
        )
        return 1
    if str(declared) != SUPPORTED_RUNTIME_API_VERSION:
        click.echo(
            f"  FAIL: runtime_api_version = {declared!r}, "
            f"package supports {SUPPORTED_RUNTIME_API_VERSION!r}. "
            "Either upgrade the cataforge package (when on-disk is newer) "
            "or run `cataforge upgrade apply` (when on-disk is older) to "
            "restamp framework.json."
        )
        return 1
    click.echo(f"  OK: runtime_api_version = {declared}")
    return 0


def run_migration_checks(cfg: ConfigManager, platforms: list[str] | None = None) -> int:
    """Run migration checks; return the number of failures.

    Checks marked ``requires_deploy: true`` are SKIPPED (not failed) when the
    project has not yet been deployed — they target deploy-produced artifacts
    like ``.claude/settings.json`` that cannot exist until the first
    ``cataforge deploy`` run.

    Checks with a ``platforms`` list only apply when at least one of those
    platforms has a deploy record — a check against ``.claude/settings.json``
    must not fail a codex-only project.

    Checks with ``deprecate_after: <semver>`` are SKIPPED once the running
    package version has caught up to that semver.
    """
    from cataforge import __version__ as pkg_version
    from cataforge.runtime.deploy.manifest import deployed_platforms

    checks = cfg.load().get("migration_checks") or []
    if not checks:
        click.echo("  (none defined)")
        return 0

    deployed_set = set(deployed_platforms(cfg.paths.root))
    if platforms is not None:
        deployed_set &= set(platforms)

    passed = 0
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    for check in checks:
        cid = str(check.get("id", "?"))
        deprecate_after = check.get("deprecate_after")
        if isinstance(deprecate_after, str) and _semver_ge(pkg_version, deprecate_after):
            skipped.append((cid, f"deprecated since {deprecate_after} (current {pkg_version})"))
            continue
        if bool(check.get("requires_deploy", False)) and not deployed_set:
            skipped.append((cid, "requires deploy (run `cataforge deploy` first)"))
            continue
        check_platforms = check.get("platforms")
        if (
            isinstance(check_platforms, list)
            and check_platforms
            and not (set(map(str, check_platforms)) & deployed_set)
        ):
            skipped.append((cid, f"not applicable — requires platform(s) {check_platforms}"))
            continue
        ok, reason = _evaluate_check(check, cfg.paths.root)
        if ok:
            passed += 1
        else:
            failed.append((cid, reason))

    parts = [f"{passed}/{len(checks)} passed"]
    if skipped:
        parts.append(f"{len(skipped)} skipped")
    click.echo("  " + ", ".join(parts))
    for cid, reason in skipped:
        click.echo(f"  SKIP {cid}: {reason}")
    for cid, reason in failed:
        click.echo(f"  FAIL {cid}: {reason}")
    return len(failed)


def _semver_ge(a: str, b: str) -> bool:
    """True iff *a* >= *b* on the leading dotted-numeric prefix.

    Both args are best-effort parsed; non-numeric suffixes (e.g.
    ``0.0.0-template``, ``0.2.0rc1``) are ignored. Falls through to
    False when either side can't be parsed — avoids silently skipping a
    check that should still run.
    """
    ta = parse_semver(a)
    tb = parse_semver(b)
    if ta is None or tb is None:
        return False
    return ta >= tb


def _check_file_must_exist(
    target: Path, rel: str, patterns: list[str], check: dict[str, Any]
) -> tuple[bool, str]:
    return (target.is_file(), "" if target.is_file() else f"{rel} does not exist")


def _check_file_must_contain(
    target: Path, rel: str, patterns: list[str], check: dict[str, Any]
) -> tuple[bool, str]:
    if not target.is_file():
        return False, f"{rel} does not exist"
    try:
        text = target.read_text()
    except OSError as e:
        return False, f"cannot read {rel}: {e}"
    missing = [p for p in patterns if p not in text]
    if missing:
        return False, f"{rel} missing patterns: {missing}"
    return True, ""


def _check_file_must_not_contain(
    target: Path, rel: str, patterns: list[str], check: dict[str, Any]
) -> tuple[bool, str]:
    if not target.is_file():
        # A non-existent file trivially satisfies "must not contain". An
        # ``allow_missing`` opt-out is required so guards against
        # framework-source-only paths (e.g. dogfood-only checks against
        # ``src/cataforge/...``) don't quietly turn into vacuous PASS for
        # end users where the path doesn't exist.
        if check.get("allow_missing", False):
            return True, ""
        return False, (
            f"{rel} does not exist — `file_must_not_contain` cannot be "
            "vacuously asserted; either fix the path, mark the check "
            "`allow_missing: true`, or set `deprecate_after` for it"
        )
    try:
        text = target.read_text()
    except OSError as e:
        return False, f"cannot read {rel}: {e}"
    present = [p for p in patterns if p in text]
    if present:
        return False, f"{rel} contains forbidden patterns: {present}"
    return True, ""


def _check_dir_must_contain_files(
    target: Path, rel: str, patterns: list[str], check: dict[str, Any]
) -> tuple[bool, str]:
    if not target.is_dir():
        return False, f"{rel} is not a directory"
    missing = [p for p in patterns if not (target / p).is_file()]
    if missing:
        return False, f"{rel} missing files: {missing}"
    return True, ""


_CHECK_HANDLERS: dict[str, Callable[[Path, str, list[str], dict[str, Any]], tuple[bool, str]]] = {
    "file_must_exist": _check_file_must_exist,
    "file_must_contain": _check_file_must_contain,
    "file_must_not_contain": _check_file_must_not_contain,
    "dir_must_contain_files": _check_dir_must_contain_files,
}


def _evaluate_check(check: dict[str, Any], root: Path) -> tuple[bool, str]:
    """Evaluate a single migration_check entry.  Returns (ok, reason)."""
    ctype = str(check.get("type", ""))
    handler = _CHECK_HANDLERS.get(ctype)
    if handler is None:
        return False, f"unknown check type: {ctype}"
    rel = str(check.get("path", ""))
    target = root / rel
    patterns = list(check.get("patterns") or [])
    return handler(target, rel, patterns, check)
