"""Framework meta-asset structural audit (Layer 1) — entrypoint.

CLI entry plus public re-exports.  Individual checks live in
``checks/b1.py`` … ``checks/b8.py``; shared dataclasses, discovery
helpers, framework.json readers, and hook script resolution live in
sibling modules prefixed with ``_``.

Usage:
  python -m cataforge.runtime.skill.builtins.framework_review.framework_check \\
        <scope: agents|skills|hooks|rules|workflow|all> \\
        [--focus B1,B2,B3,B4,B5,B6,B7,B8,B9] \\
        [--root <project_root>] \\
        [--meta-size-threshold N]

Exit codes follow §Layer 1 调用协议: 0=PASS, 1=FAIL, 2=usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import ProjectPaths
from cataforge.utils.common import ensure_utf8

from ._constants import (
    B1_REQUIRED_SECTIONS_EXEMPT_AGENTS,
    B1_REQUIRED_SECTIONS_EXEMPT_SKILLS,
    B5_CROSS_CUTTING,
    B5_SUBAGENTS,
    DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS,
    DEFAULT_META_SIZE,
    ORPHAN_SKILL_WHITELIST,
    REQUIRED_SECTIONS_AGENT,
    REQUIRED_SECTIONS_SKILL,
    VALID_MODEL_TIERS,
)
from ._discover import (
    discover_agent_protocol_docs,
    discover_agents,
    discover_skills,
    parse_depends_field,
    parse_skills_field,
)
from ._types import Finding, Report
from .checks.b1 import check_b1_required_sections, check_b1_size
from .checks.b2 import check_b2_cross_references
from .checks.b3 import check_b3_manifest_drift, check_b3_rules_schema
from .checks.b4 import check_b4_hardcoded_constants
from .checks.b5 import check_b5_workflow_coverage
from .checks.b6 import check_b6_hook_consistency
from .checks.b7 import check_b7_model_tier
from .checks.b8 import check_b8_anti_pattern_floor
from .checks.b9 import check_b9_migration_checks

__all__ = [
    # Dataclasses
    "Finding",
    "Report",
    # Discovery
    "discover_agents",
    "discover_skills",
    "discover_agent_protocol_docs",
    "parse_skills_field",
    "parse_depends_field",
    # Constants
    "VALID_MODEL_TIERS",
    "REQUIRED_SECTIONS_SKILL",
    "REQUIRED_SECTIONS_AGENT",
    "B1_REQUIRED_SECTIONS_EXEMPT_SKILLS",
    "B1_REQUIRED_SECTIONS_EXEMPT_AGENTS",
    "ORPHAN_SKILL_WHITELIST",
    "DEFAULT_META_SIZE",
    "DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS",
    "B5_SUBAGENTS",
    "B5_CROSS_CUTTING",
    # Checks
    "check_b1_required_sections",
    "check_b1_size",
    "check_b2_cross_references",
    "check_b3_manifest_drift",
    "check_b3_rules_schema",
    "check_b4_hardcoded_constants",
    "check_b5_workflow_coverage",
    "check_b6_hook_consistency",
    "check_b7_model_tier",
    "check_b8_anti_pattern_floor",
    "check_b9_migration_checks",
    # Entry
    "run",
    "main",
]


def run(
    scope: str,
    focus: list[str] | None,
    root: Path,
    meta_size_threshold: int,
) -> int:
    report = Report()

    enabled = set(focus) if focus else {"B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"}

    if "B1" in enabled and scope in ("agents", "skills", "rules", "all"):
        check_b1_required_sections(root, scope, report)
        check_b1_size(root, scope, meta_size_threshold, report)
    if "B2" in enabled and scope in ("agents", "skills", "all"):
        check_b2_cross_references(root, report)
    if "B3" in enabled and scope in ("skills", "all"):
        check_b3_manifest_drift(root, report)
        check_b3_rules_schema(root, report)
    if "B4" in enabled and scope in ("agents", "skills", "rules", "all"):
        check_b4_hardcoded_constants(root, report)
    if "B5" in enabled and scope in ("workflow", "all"):
        check_b5_workflow_coverage(root, report)
    if "B6" in enabled and scope in ("hooks", "all"):
        check_b6_hook_consistency(root, report)
    if "B7" in enabled and scope in ("agents", "all"):
        check_b7_model_tier(root, report)
    if "B8" in enabled and scope in ("agents", "skills", "all"):
        check_b8_anti_pattern_floor(root, scope, report)
    if "B9" in enabled and scope in ("workflow", "all"):
        check_b9_migration_checks(root, report)

    print(f"framework-review scope={scope} focus={sorted(enabled)} root={root}")
    print("=" * 60)
    if not report.findings:
        print("No findings.")
        print("RESULT: PASS")
        return 0

    for f in report.findings:
        print(f.render())

    print()
    print("=" * 60)
    print(f"Summary: {report.fail_count} FAIL, {report.warn_count} WARN, {report.info_count} INFO")
    if report.fail_count > 0:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS (warnings/info only)")
    return 0


def main() -> None:
    ensure_utf8()
    parser = argparse.ArgumentParser(
        description="CataForge framework meta-asset audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scope",
        choices=("agents", "skills", "hooks", "rules", "workflow", "all"),
        help="Asset scope to audit",
    )
    parser.add_argument(
        "--focus",
        default=None,
        help="Comma-separated subset of B1,B2,B3,B4,B5,B6,B7,B8,B9",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root (defaults to current directory)",
    )
    parser.add_argument(
        "--meta-size-threshold",
        type=int,
        default=None,
        help="META_DOC_SPLIT_THRESHOLD_LINES override",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path.cwd()
    focus = [s.strip() for s in args.focus.split(",") if s.strip()] if args.focus else None

    threshold = args.meta_size_threshold
    if threshold is None:
        fw_json = ProjectPaths(root).framework_json
        threshold = DEFAULT_META_SIZE
        if fw_json.is_file():
            try:
                data = read_json(fw_json)
                v = (data.get("constants") or {}).get("META_DOC_SPLIT_THRESHOLD_LINES")
                if isinstance(v, int) and v > 0:
                    threshold = v
            except ConfigError:
                pass

    sys.exit(run(scope=args.scope, focus=focus, root=root, meta_size_threshold=threshold))


if __name__ == "__main__":
    main()
