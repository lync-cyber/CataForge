#!/usr/bin/env python3
"""upgrade.py — CataForge Unified Upgrade Tool (CLI Entry Point)

Subcommands:
  local   <source_path>   Upgrade framework files from a local path
  check                   Check if a remote update is available
  upgrade                 Check + execute remote upgrade
  verify                  Post-upgrade verification (integrity + compatibility)

Usage:
  python .claude/scripts/framework/upgrade.py local /path/to/new [--dry-run] [--backup-dir <dir>]
  python .claude/scripts/framework/upgrade.py check [--repo owner/repo] [--url URL] [--branch main]
  python .claude/scripts/framework/upgrade.py upgrade [--repo owner/repo] [--url URL] [--dry-run]
  python .claude/scripts/framework/upgrade.py verify

Returns: exit 0=success, exit 1=failure, exit 2=already up-to-date

Implementation is split across sub-modules:
  _upgrade_local.py   — backup / copy / merge logic
  _upgrade_remote.py  — remote detection / clone / self-upgrade
  _upgrade_verify.py  — post-upgrade verification / migration checks
"""

import argparse
import os
import shutil
import sys

# ============================================================================
# Shared utilities
# ============================================================================

_FRAMEWORK_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_ROOT = os.path.dirname(_FRAMEWORK_DIR)
_LIB = os.path.join(_SCRIPTS_ROOT, "lib")
for _p in (_LIB, _FRAMEWORK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _common import ensure_utf8_stdio, load_dotenv
from _upgrade_local import run_local_upgrade
from _upgrade_remote import (
    SELF_UPGRADE_SRC_ENV,
    clone_and_upgrade,
    detect_remote_state,
    resolve_remote_source,
    save_upgrade_state,
)
from _upgrade_verify import run_verify
from _version import parse_semver, read_version, validate_branch_name


# ============================================================================
# Subcommand handlers
# ============================================================================


def cmd_local(args):
    """Subcommand: local — upgrade from a local path.

    Self-upgrade stage 2 fallback: if CATAFORGE_SELF_UPGRADE_SRC points to
    the current source_path, clean up the temp dir after upgrade.
    """
    exit_code = run_local_upgrade(args.source_path, args.dry_run, args.backup_dir)

    self_upgrade_src = os.environ.get(SELF_UPGRADE_SRC_ENV, "")
    if (
        self_upgrade_src
        and os.path.abspath(self_upgrade_src) == os.path.abspath(args.source_path)
        and os.path.isdir(self_upgrade_src)
    ):
        try:
            shutil.rmtree(self_upgrade_src, ignore_errors=True)
            print(f"\n[自升级] 清理临时目录: {self_upgrade_src}")
        except OSError:
            pass

    sys.exit(exit_code)


def cmd_check(args):
    """Subcommand: check — detect whether a newer remote version exists."""
    source_type, repo, url, branch, token_env = resolve_remote_source(args)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    from _upgrade_remote import load_upgrade_source

    config = load_upgrade_source()
    last_commit = config.get("last_commit", "")

    print(f"当前版本: {local_ver}")
    if last_commit:
        print(f"上次升级 commit: {last_commit[:12]}")

    remote_ver, remote_commit, _, _ = detect_remote_state(
        source_type, repo, url, branch, token_env
    )

    if not remote_ver and not remote_commit:
        print("错误: 无法获取远程版本和 commit 信息", file=sys.stderr)
        sys.exit(1)

    if remote_ver:
        print(f"远程版本: {remote_ver}")
    if remote_commit:
        print(f"远程 commit: {remote_commit[:12]}")

    # Prefer commit SHA comparison
    if remote_commit and last_commit:
        if remote_commit == last_commit:
            print(f"\n当前已是最新 (commit: {last_commit[:12]})，无需升级。")
            sys.exit(2)
        else:
            print(f"\n发现更新: commit {last_commit[:12]} → {remote_commit[:12]}")
            if remote_ver:
                print(f"版本: {local_ver} → {remote_ver}")
    elif not last_commit:
        print("\n首次检测，无历史升级记录。")
        if remote_commit:
            print(f"远程 commit: {remote_commit[:12]}")
    elif remote_ver:
        if parse_semver(remote_ver) <= parse_semver(local_ver):
            print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
            sys.exit(2)
        print(f"\n发现新版本: {local_ver} → {remote_ver}")
    else:
        print(f"\n检测到远程 commit 变更: {remote_commit[:12]}")

    print("\n可运行以下命令升级:")
    print("  python .claude/scripts/framework/upgrade.py upgrade --dry-run  # 预览变更")
    print("  python .claude/scripts/framework/upgrade.py upgrade             # 执行升级")
    sys.exit(0)


def cmd_upgrade(args):
    """Subcommand: upgrade — check + execute remote upgrade."""
    source_type, repo, url, branch, token_env = resolve_remote_source(args)
    force = getattr(args, "force", False)

    if not validate_branch_name(branch):
        print(f"错误: 无效的分支名 '{branch}'", file=sys.stderr)
        sys.exit(1)

    local_ver = read_version(".")
    from _upgrade_remote import load_upgrade_source

    config = load_upgrade_source()
    last_commit = config.get("last_commit", "")

    print(f"当前版本: {local_ver}")
    if last_commit:
        print(f"上次升级 commit: {last_commit[:12]}")

    remote_ver, remote_commit, clone_url, token = detect_remote_state(
        source_type, repo, url, branch, token_env
    )

    if not remote_ver and not remote_commit:
        print("错误: 无法获取远程版本和 commit 信息", file=sys.stderr)
        sys.exit(1)

    if remote_ver:
        print(f"远程版本: {remote_ver}")
    if remote_commit:
        print(f"远程 commit: {remote_commit[:12]}")

    # Determine if upgrade is needed
    needs_upgrade = True
    if remote_commit and last_commit:
        if remote_commit == last_commit:
            if force:
                print("\ncommit 相同，但 --force 强制升级。")
            else:
                print(f"\n当前已是最新 (commit: {last_commit[:12]})，无需升级。")
                sys.exit(2)
            needs_upgrade = force
    elif not last_commit:
        print("\n首次升级，无历史升级记录。")
    elif remote_ver:
        if parse_semver(remote_ver) <= parse_semver(local_ver):
            if force:
                print("\n版本相同或更低，但 --force 强制升级。")
            else:
                print(f"\n当前已是最新版本 ({local_ver})，无需升级。")
                sys.exit(2)
            needs_upgrade = force

    if needs_upgrade:
        ver_info = f"{local_ver} → {remote_ver}" if remote_ver else ""
        commit_info = ""
        if remote_commit:
            commit_info = (
                f"commit {last_commit[:12] if last_commit else '(首次)'}"
                f" → {remote_commit[:12]}"
            )
        summary = " | ".join(filter(None, [ver_info, commit_info]))
        if summary:
            print(f"\n升级: {summary}")

    exit_code = clone_and_upgrade(clone_url, branch, token=token, dry_run=args.dry_run)

    # Record state after successful upgrade
    if exit_code == 0 and not args.dry_run:
        new_ver = read_version(".")
        save_upgrade_state(remote_commit or "", new_ver)
        print("\n已记录升级状态到 .claude/framework.json")

    sys.exit(exit_code)


def cmd_verify(args):
    """Subcommand: verify — post-upgrade verification."""
    sys.exit(run_verify())


# ============================================================================
# CLI entry point
# ============================================================================


def main():
    ensure_utf8_stdio()
    load_dotenv(set_env=True)

    parser = argparse.ArgumentParser(
        description="CataForge 统一升级工具",
        epilog=(
            "示例:\n"
            "  python .claude/scripts/framework/upgrade.py local /path/to/new --dry-run\n"
            "  python .claude/scripts/framework/upgrade.py check --repo owner/CataForge\n"
            "  python .claude/scripts/framework/upgrade.py upgrade --repo owner/CataForge\n"
            "  python .claude/scripts/framework/upgrade.py verify\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # local
    p_local = subparsers.add_parser("local", help="从本地路径升级框架文件")
    p_local.add_argument("source_path", help="CataForge 新版本的根目录路径")
    p_local.add_argument(
        "--dry-run", action="store_true", help="仅显示变更，不实际修改"
    )
    p_local.add_argument("--backup-dir", default=None, help="自定义备份目录路径")
    p_local.set_defaults(func=cmd_local)

    # Shared remote source arguments
    def add_remote_args(p):
        source_group = p.add_mutually_exclusive_group()
        source_group.add_argument(
            "--repo", type=str, default=None, help="GitHub 仓库 (owner/repo)"
        )
        source_group.add_argument("--url", type=str, default=None, help="Git 仓库 URL")
        p.add_argument("--branch", type=str, default=None, help="分支名 (默认: main)")
        p.add_argument(
            "--token-env", type=str, default=None, help="存放 token 的环境变量名"
        )

    # check
    p_check = subparsers.add_parser("check", help="检测远程是否有新版本")
    add_remote_args(p_check)
    p_check.set_defaults(func=cmd_check)

    # upgrade
    p_upgrade = subparsers.add_parser("upgrade", help="检测 + 执行远程升级")
    add_remote_args(p_upgrade)
    p_upgrade.add_argument(
        "--dry-run", action="store_true", help="仅预览变更，不实际修改"
    )
    p_upgrade.add_argument(
        "--force", action="store_true", help="忽略 commit SHA 比较，强制执行升级"
    )
    p_upgrade.set_defaults(func=cmd_upgrade)

    # verify
    p_verify = subparsers.add_parser(
        "verify", help="升级后验证（文件完整性 + 功能适用性）"
    )
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
