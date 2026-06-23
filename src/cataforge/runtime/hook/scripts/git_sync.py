"""SessionStart Hook: fetch + fast-forward clean main + prune gone branches.

Best-effort only: opening a session must never switch branches, never touch a
dirty tree, and never raise. When the session opens on a clean default branch
the local branch is fast-forwarded from origin; local branches whose upstream
is gone (squash-merged + head deleted) are pruned. A debounce stamp suppresses
repeat fetches across rapid restarts. Any failure degrades to one stderr line.

Pure config→service orchestration: every git decision lives in
:mod:`cataforge.application.services.git_hygiene`.
"""

import sys
import time
from pathlib import Path

from cataforge.runtime.hook.base import hook_main, read_hook_input


def _debounced(stamp: Path, seconds: int) -> bool:
    """True when ``stamp`` was written less than ``seconds`` ago."""
    if seconds <= 0 or not stamp.is_file():
        return False
    return (time.time() - stamp.stat().st_mtime) < seconds


def _touch(stamp: Path) -> None:
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("")


def _run_git_sync() -> None:
    """Run one session sweep; never raise."""
    try:
        from cataforge.application.services.git_hygiene import (
            GitHubRepo,
            GitWorkTree,
            run_session_sync,
        )
        from cataforge.core.config import ConfigManager
        from cataforge.core.paths import ProjectPaths, find_project_root_or_none

        root = find_project_root_or_none()
        if root is None:
            return
        cfg = ConfigManager(project_root=root)
        opts = cfg.git_session_sync
        if not opts.enabled:
            return

        git = GitWorkTree(root)
        if not git.is_inside_work_tree():
            return

        stamp = ProjectPaths(root).git_sync_stamp
        if _debounced(stamp, opts.debounce_seconds):
            return

        gh = GitHubRepo.from_remote(git) if opts.confirm_via_gh else None
        report = run_session_sync(
            git,
            gh,
            fast_forward_clean=opts.fast_forward_clean,
            prune_gone=opts.prune_gone,
            confirm_via_gh=opts.confirm_via_gh,
            fetch_timeout=opts.fetch_timeout_seconds,
        )
        _touch(stamp)

        if report.synced is not None and report.synced.action == "fast-forwarded":
            print(
                f"cataforge: fast-forwarded {report.synced.branch} "
                f"by {report.synced.behind} commit(s)",
                file=sys.stderr,
            )
        if report.pruned:
            print(
                f"cataforge: pruned {len(report.pruned)} merged branch(es): "
                f"{', '.join(report.pruned)}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"warn: git session-sync skipped: {e}", file=sys.stderr)


@hook_main
def main() -> None:
    read_hook_input()
    _run_git_sync()
    sys.exit(0)


if __name__ == "__main__":
    main()
