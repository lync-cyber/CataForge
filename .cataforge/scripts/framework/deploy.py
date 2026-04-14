#!/usr/bin/env python3
"""CLI: python .cataforge/scripts/framework/deploy.py

Usage:
  python .cataforge/scripts/framework/deploy.py [--platform claude-code|cursor|codex|opencode|all]
  python .cataforge/scripts/framework/deploy.py --check
  python .cataforge/scripts/framework/deploy.py --conformance --platform <id>
"""
import argparse
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("cp"):
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_CATAFORGE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_CATAFORGE_DIR))

from runtime.deploy import deploy, get_project_root
from runtime.profile_loader import detect_platform


ALL_PLATFORMS = ["claude-code", "cursor", "codex", "opencode"]


def main() -> None:
    parser = argparse.ArgumentParser(description="CataForge platform deploy")
    parser.add_argument(
        "--platform",
        choices=ALL_PLATFORMS + ["all"],
        default=None,
        help="Target platform (default: from framework.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check deploy status",
    )
    parser.add_argument(
        "--conformance",
        action="store_true",
        help="Run platform conformance check",
    )
    args = parser.parse_args()

    if args.conformance:
        from runtime.conformance import check_conformance
        platform_id = args.platform or detect_platform()
        if platform_id == "all":
            platforms = ALL_PLATFORMS
        else:
            platforms = [platform_id]

        exit_code = 0
        for pid in platforms:
            issues = check_conformance(pid)
            if issues:
                print(f"\n[{pid}] ISSUES:")
                for issue in issues:
                    print(f"  {issue}")
                exit_code = 1
            else:
                print(f"[{pid}] OK")
        sys.exit(exit_code)

    if args.check:
        root = get_project_root()
        state_file = root / ".cataforge" / ".deploy-state"
        if state_file.is_file():
            import json
            state = json.loads(state_file.read_text(encoding="utf-8"))
            print(f"Deployed platform: {state.get('platform', 'unknown')}")
            sys.exit(0)
        else:
            print("No deploy state found (.cataforge/.deploy-state)")
            sys.exit(1)

    platform_id = args.platform or detect_platform()
    if platform_id == "all":
        platforms = ALL_PLATFORMS
    else:
        platforms = [platform_id]

    for pid in platforms:
        print(f"\n=== 部署到 {pid} ===")
        try:
            actions = deploy(pid)
            for action in actions:
                print(f"  {action}")
            print(f"  DONE")
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
