"""SessionStart Hook: nudge when deployed IDE artefacts are stale.

Best-effort only: opening an IDE session must never mutate tracked files or
shell out. When the ``.cataforge/`` source or the installed ``cataforge``
version has moved since the last ``cataforge deploy``, print a one-line
hint to stderr so the user redeploys. Any failure degrades to silence.
"""

import sys

from cataforge.runtime.hook.base import hook_main, read_hook_input


def _warn_on_drift() -> None:
    """Print a redeploy hint when drift is detected; never raise."""
    try:
        from cataforge.core.paths import ProjectPaths
        from cataforge.runtime.deploy.drift import detect_drift, drift_hint_lines

        report = detect_drift(ProjectPaths())
        if not report.any_drift:
            return
        for line in drift_hint_lines(report):
            print(f"cataforge: {line}", file=sys.stderr)
    except Exception as e:
        print(f"warn: deploy-drift check skipped: {e}", file=sys.stderr)


@hook_main
def main() -> None:
    read_hook_input()
    _warn_on_drift()
    sys.exit(0)


if __name__ == "__main__":
    main()
