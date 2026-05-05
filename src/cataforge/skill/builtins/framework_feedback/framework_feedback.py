"""framework_feedback.py — assemble an upstream-bound feedback bundle.

Layer 1 entry point for the ``framework-feedback`` builtin skill.
Thin wrapper over ``cataforge.core.feedback.assemble_*`` so the skill
runner gets a deterministic ``python -m`` target that mirrors the
``cataforge feedback`` CLI surface.

Why a skill *and* a CLI? Two non-overlapping audiences:

* Humans / shell pipelines use ``cataforge feedback bug --gh`` directly.
* Orchestrator / agents call ``cataforge skill run framework-feedback``
  so the run gets recorded in EVENT-LOG via the standard skill runner
  instrumentation (``record_to_event_log=True``), giving a durable
  signal that "we drafted upstream feedback at this point in the
  workflow".

Usage::

    python -m cataforge.skill.builtins.framework_feedback.framework_feedback \
        <kind: bug|suggest|correction-export> \
        --summary "<one-line summary>" \
        [--out PATH] [--include-paths] [--since YYYY-MM-DD] \
        [--threshold N]            # correction-export only
        [--skip-framework-review]  # bug only

Returns:
    exit 0  — bundle assembled (and written to PATH if --out)
    exit 1  — assembler failed (e.g. correction-export below threshold)
    exit 2  — usage error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cataforge.core.feedback import (
    DEFAULT_EVENT_LOG_TAIL,
    RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
    UPSTREAM_GAP,
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    upstream_gap_count,
)
from cataforge.core.paths import find_project_root
from cataforge.utils.common import ensure_utf8_stdio


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="framework-feedback",
        description="Assemble a CataForge framework feedback bundle.",
    )
    p.add_argument(
        "kind",
        choices=["bug", "suggest", "correction-export"],
        help="Bundle flavour.",
    )
    p.add_argument(
        "--summary",
        default="(no summary provided)",
        help="One-paragraph summary written into the body.",
    )
    p.add_argument(
        "--title",
        default=None,
        help="Issue title (default: synthesised from kind + summary).",
    )
    p.add_argument(
        "--notes",
        default="",
        help="Free-form text appended under '## Additional notes'.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the body to PATH (relative resolves under the project root).",
    )
    p.add_argument(
        "--include-paths",
        action="store_true",
        help="Disable the ~/<project> path redaction.",
    )
    p.add_argument(
        "--since",
        default=None,
        help="Only include EVENT-LOG / corrections at or after YYYY-MM-DD.",
    )
    p.add_argument(
        "--event-limit",
        type=int,
        default=DEFAULT_EVENT_LOG_TAIL,
        help=f"Max EVENT-LOG records to include (default {DEFAULT_EVENT_LOG_TAIL}).",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
        help=(
            "correction-export only: minimum upstream-gap count required "
            f"(default {RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT}, 0 = always export)."
        ),
    )
    p.add_argument(
        "--skip-framework-review",
        action="store_true",
        help="bug only: skip the framework-review pre-check.",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (default: walk up from cwd).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    args = _build_parser().parse_args(argv)
    project_root = (args.root or find_project_root()).resolve()

    title_seed = args.summary.splitlines()[0][:60] if args.summary else "(unspecified)"

    if args.kind == "bug":
        title = args.title or f"bug: {title_seed}"
        _payload, body = assemble_bug(
            project_root,
            title=title,
            summary=args.summary,
            user_notes=args.notes,
            event_limit=args.event_limit,
            since=args.since,
            include_paths=args.include_paths,
            skip_framework_review=args.skip_framework_review,
        )
    elif args.kind == "suggest":
        title = args.title or f"feedback: {title_seed}"
        _payload, body = assemble_suggestion(
            project_root,
            title=title,
            summary=args.summary,
            user_notes=args.notes,
            include_paths=args.include_paths,
        )
    else:  # correction-export
        count = upstream_gap_count(project_root)
        if count == 0:
            print(
                f"No `{UPSTREAM_GAP}` corrections found. Record one first via "
                f"`cataforge correction record --deviation {UPSTREAM_GAP} ...`.",
                file=sys.stderr,
            )
            return 1
        if count < args.threshold:
            print(
                f"Only {count} `{UPSTREAM_GAP}` correction(s) "
                f"(threshold={args.threshold}). Lower with --threshold 0 to force.",
                file=sys.stderr,
            )
            return 1
        title = args.title or f"feedback: {count} upstream-gap signals"
        _payload, body = assemble_correction_export(
            project_root,
            title=title,
            summary=args.summary,
            since=args.since,
            user_notes=args.notes,
            include_paths=args.include_paths,
        )

    if args.out is not None:
        target = args.out if args.out.is_absolute() else project_root / args.out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        print(f"Wrote {target}")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
