"""B9 — migration_checks structural audit (forward-looking guard)."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.version import parse_semver

from .._framework_data import is_editable_tree, read_framework_data
from .._types import Report


def _semver_ge(a: str, b: str) -> bool:
    ta, tb = parse_semver(a), parse_semver(b)
    return ta is not None and tb is not None and ta >= tb


def _semver_le(a: str, b: str) -> bool:
    ta, tb = parse_semver(a), parse_semver(b)
    return ta is not None and tb is not None and ta <= tb


def _runtime_version() -> str | None:
    try:
        from cataforge import __version__ as version
    except ImportError:
        return None
    return version


def check_b9_migration_checks(root: Path, report: Report) -> None:
    """B9: structural sanity of ``framework.json#/migration_checks``.

    Three forward-looking sub-checks (each its own check_id). The audit
    never rewrites migration_checks — it surfaces dead / misconfigured
    entries so a maintainer prunes them by hand.

    * ``B9_migration_path_validity`` — a live (non-deprecated) check whose
      ``path`` sits under ``src/`` but is absent in an editable tree passes
      against nothing → WARN; ``allow_missing`` on any type other than
      ``file_must_not_contain`` (the only type that consults it) → WARN.
    * ``B9_migration_deprecate_order`` — ``deprecate_after <= release_version``
      means the check is deprecated at or before it ships and never runs in
      any released version → WARN.
    * ``B9_migration_dead_entry`` — an already-deprecated check whose path is
      absent is dead weight → INFO suggesting removal.
    """
    checks = read_framework_data(root).get("migration_checks")
    if not isinstance(checks, list):
        return
    editable = is_editable_tree(root)
    pkg_version = _runtime_version()

    for check in checks:
        if not isinstance(check, dict):
            continue
        cid = str(check.get("id", "?"))
        loc = f"migration_checks/{cid}"
        deprecate = check.get("deprecate_after")
        release = check.get("release_version")
        path = str(check.get("path", ""))
        ctype = str(check.get("type", ""))

        if (
            isinstance(deprecate, str)
            and isinstance(release, str)
            and _semver_le(deprecate, release)
        ):
            report.add(
                "B9_migration_deprecate_order",
                "WARN",
                loc,
                f"deprecate_after={deprecate!r} <= release_version={release!r}; "
                "the check is deprecated at or before it ships and never runs",
            )

        deprecated = (
            isinstance(deprecate, str)
            and pkg_version is not None
            and _semver_ge(pkg_version, deprecate)
        )
        if deprecated:
            if path and not (root / path).exists():
                report.add(
                    "B9_migration_dead_entry",
                    "INFO",
                    loc,
                    f"deprecated (deprecate_after={deprecate}, current "
                    f"{pkg_version}) and path {path!r} is absent — dead entry, "
                    "safe to drop from framework.json#/migration_checks",
                )
            continue

        if check.get("allow_missing") and ctype != "file_must_not_contain":
            report.add(
                "B9_migration_path_validity",
                "WARN",
                loc,
                f"allow_missing set on type={ctype!r}; the flag is only "
                "consulted for file_must_not_contain — drop it or fix the type",
            )
        if editable and path.startswith("src/") and not (root / path).exists():
            report.add(
                "B9_migration_path_validity",
                "WARN",
                loc,
                f"path {path!r} under src/ is absent in this editable tree; "
                "the check passes against nothing (source moved or renamed?)",
            )
