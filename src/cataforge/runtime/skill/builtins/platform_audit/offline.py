"""Offline platform-audit — the no-network subset that gates a PR.

Runs the static checks the full platform-audit skill performs without an LLM or
network: core conformance, cross-field/cross-platform consistency, and profile
schema required-keys. FAIL-level findings (unloadable profile, missing required
capability, schema violation) exit non-zero to block a PR; consistency findings
print as WARN but never block — they track accepted degradations, not breakage.
``version_tested`` staleness is a separate weekly guard
(``scripts/checks/check_profile_version_tested.py``), git-history-based and so
out of scope for a possibly-shallow PR checkout.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from cataforge.adapter.platform.conformance import (
    check_all_conformance,
    check_all_consistency,
)
from cataforge.core.paths import find_project_root

_USAGE = "usage: cataforge skill run platform-audit -- --offline"


def _required_schema_keys(platforms_dir: Path) -> set[str]:
    schema = platforms_dir / "_schema.yaml"
    if not schema.is_file():
        return set()
    keys: set[str] = set()
    in_required = False
    for line in schema.read_text(encoding="utf-8").splitlines():
        if line.startswith("required_fields:"):
            in_required = True
            continue
        if line.startswith("optional_fields:"):
            in_required = False
            continue
        m = re.match(r"^  ([a-z_]+):", line)
        if in_required and m:
            keys.add(m.group(1))
    return keys


def check_profile_schema(platforms_dir: Path) -> list[str]:
    """FAIL lines for real profiles missing a schema-required top-level key."""
    required = _required_schema_keys(platforms_dir)
    if not required:
        return []
    issues: list[str] = []
    for profile in sorted(platforms_dir.glob("*/profile.yaml")):
        pid = profile.parent.name
        try:
            data = yaml.safe_load(profile.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as e:
            issues.append(f"FAIL: {pid} profile.yaml is unreadable: {e}")
            continue
        missing = required - set(data.keys())
        if missing:
            issues.append(
                f"FAIL: {pid} profile.yaml missing required keys: {', '.join(sorted(missing))}"
            )
    return issues


def run_offline_audit(platforms_dir: Path) -> int:
    """Run the offline checks and return a process exit code (0 ok / 1 block)."""
    core = check_all_conformance(platforms_dir)
    consistency = check_all_consistency(platforms_dir)
    schema = check_profile_schema(platforms_dir)

    print("== platform-audit (offline) ==")
    if core:
        print("\n[core conformance]")
        print("\n".join(core))
    if consistency:
        print("\n[consistency]")
        print("\n".join(consistency))
    if schema:
        print("\n[schema]")
        print("\n".join(schema))

    # Core FAIL (unloadable / no dispatch) and required-capability WARN both
    # block; INFO (missing optional capability) does not. Consistency WARNs are
    # advisory; only an unloadable-profile FAIL there blocks. Schema misses block.
    blocking = (
        [ln for ln in core if "FAIL:" in ln or "WARN:" in ln]
        + [ln for ln in consistency if "FAIL:" in ln]
        + schema
    )
    if blocking:
        print(f"\nFAIL: {len(blocking)} blocking finding(s):", file=sys.stderr)
        for ln in blocking:
            print(f"  {ln.strip()}", file=sys.stderr)
        return 1

    advisory = [ln for ln in consistency if "WARN:" in ln]
    print(
        f"\nOK: no blocking findings ({len(advisory)} advisory consistency WARN — "
        "accepted degradations)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # The offline subset is the only executable mode of this builtin; accept the
    # documented ``--offline`` invocation or a bare call. Anything else is the
    # LLM playbook surface, which has no executable form — reject as bad args.
    if args and args != ["--offline"]:
        print(_USAGE, file=sys.stderr)
        return 2
    return run_offline_audit(find_project_root() / ".cataforge" / "platforms")


if __name__ == "__main__":
    sys.exit(main())
