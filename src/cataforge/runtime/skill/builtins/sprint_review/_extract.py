"""Sprint dev-plan parsing + task extraction (Layer 1 helpers)."""

from __future__ import annotations

import os
import re
from typing import Any

from cataforge.utils.frontmatter import split_yaml_frontmatter

# A dev-plan task-status table row: ``| T-12 | … | done |``. Shared by the
# in-task, standalone-row, and status-backfill scans below.
_TASK_TABLE_RE = re.compile(
    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
    re.IGNORECASE,
)

# A ``### Sprint N`` overview row whose first cell is a task id, regardless of
# whether the table carries a status column: ``| T-12 | … |``. The first cell
# is the sprint-membership signal; status backfills from a status table or is
# treated as externally tracked.
_TASK_ROW_RE = re.compile(r"^\|\s*(T-\d+[a-z]?)\s*\|", re.IGNORECASE)

# A ``### Sprint N`` section heading.
_SPRINT_HEADING_RE = re.compile(r"^###?\s+Sprint\s+(\d+)\b", re.IGNORECASE)


def find_dev_plan_files(dev_plan_dir: str) -> list[str]:
    files: list[str] = []
    if not os.path.isdir(dev_plan_dir):
        return files
    for f in sorted(os.listdir(dev_plan_dir)):
        if f.endswith(".md"):
            files.append(os.path.join(dev_plan_dir, f))
    return files


def load_project_features(dev_plan_files: list[str]) -> dict[str, Any]:
    """Load ``project_features`` block from the dev-plan main volume frontmatter.

    Sprint volumes (``-s{N}.md``) inherit from the main volume; the first
    file containing a ``project_features:`` key wins. Returns ``{}`` when no
    file declares the block — preserving existing checker behavior.

    Recognised keys (all optional):

    * ``merged_review`` (bool, default off) — short-circuit
      ``code_review_present`` (the sprint-review report itself carries
      per-task L2 instead of separate CODE-REVIEW files).
    * ``deliverables_accept_alternation`` (bool, default **on**) — let
      ``deliverables`` lines use ``A | B`` syntax (passes if **either**
      path exists). Set false to treat the literal string as one path.
    * ``task_status_external`` (bool, default off) — skip the
      ``task_status_done`` check for projects whose task status truth lives
      outside dev-plan (EVENT-LOG / project instructions). Auto-detected when
      every sprint task lacks an in-document status even if unset.
    * ``deliverables_representative`` (bool, default off) — skip the
      unplanned-files (gold-plating) check for projects whose deliverables
      lists are representative rather than exhaustive.
    * ``unplanned_glob_patterns`` (list[str]) — fnmatch patterns appended to
      ``DEFAULT_UNPLANNED_GLOB_PATTERNS``; matching files are filtered out
      of the unplanned-files WARN set.
    """
    for f in dev_plan_files:
        if re.search(r"-s\d+\.md$", f):
            continue
        try:
            with open(f, errors="replace") as fh:
                raw = fh.read()
        except OSError:
            continue
        meta, _ = split_yaml_frontmatter(raw)
        pf = meta.get("project_features") if meta else None
        if isinstance(pf, dict):
            return pf
    return {}


def _find_sprint_volume(dev_plan_files: list[str], sprint_number: int) -> str | None:
    """Return the ``-s{N}.md`` volume for this sprint, or None when absent."""
    for f in dev_plan_files:
        if re.search(rf"-s{sprint_number}\.md$", f):
            return f
    return None


def _consume_deliverables(lines: list[str], i: int, current_task: dict[str, Any]) -> int:
    """Absorb the indented bullet block after a ``deliverables:`` line.

    ``i`` points at the ``deliverables:`` line; returns the index of the first
    line past the block.
    """
    i += 1
    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
        path = re.sub(r"^\s+[-*]\s+", "", lines[i]).strip()
        path = re.sub(r"^\[[ x]\]\s*", "", path).strip()
        path = re.sub(r"[`*]", "", path).strip()
        path = re.sub(r"\s+[—\-]{1,2}\s+.*$", "", path).strip()
        if path and "|" in path:
            # `A | B` alternation entry — spaces around the pipe are syntax,
            # not annotation text; keep it whole for check_deliverables.
            if not re.search(r"[一-鿿{]", path):
                current_task["deliverables"].append(path)
        elif path and not re.search(r"[一-鿿\s{]", path):
            current_task["deliverables"].append(path)
        i += 1
    return i


def _consume_acceptance(line: str, lines: list[str], i: int, current_task: dict[str, Any]) -> int:
    """Absorb the ``tdd_acceptance:`` line plus its indented continuation."""
    rest = line + " "
    i += 1
    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
        rest += lines[i] + " "
        i += 1
    current_task["tdd_acceptance"] = list(set(re.findall(r"AC-\d+", rest)))
    return i


def _process_task_line(
    line: str,
    lines: list[str],
    i: int,
    current_task: dict[str, Any] | None,
    tasks: list[dict[str, Any]],
    in_sprint: bool,
    sprint_volume: str | None,
) -> tuple[int, dict[str, Any] | None]:
    """Process one line inside the sprint task scan loop.

    Returns the updated ``(i, current_task)`` pair; may append to *tasks*.
    """
    task_match = re.match(r"^#{2,4}\s+(T-\d+[a-z]?)", line)
    if task_match:
        if current_task:
            tasks.append(current_task)
        current_task = {
            "id": task_match.group(1),
            "status": "",
            "deliverables": [],
            "tdd_acceptance": [],
        }
        return i + 1, current_task

    if current_task:
        status_match = re.match(
            r"^[-*]\s+\*?\*?(?:status|状态)\*?\*?\s*[:：]\s*(.+)", line, re.IGNORECASE
        )
        if status_match:
            current_task["status"] = status_match.group(1).strip().lower()

        deliv_match = re.match(
            r"^[-*]\s+\*?\*?(?:deliverables|交付物)\*?\*?\s*(?:\([^)]*\)\s*)?[:：]",
            line,
            re.IGNORECASE,
        )
        if deliv_match:
            return _consume_deliverables(lines, i, current_task), current_task

        ac_match = re.match(
            r"^[-*]\s+\*?\*?(?:tdd_acceptance|验收标准)\*?\*?\s*[:：]",
            line,
            re.IGNORECASE,
        )
        if ac_match:
            return _consume_acceptance(line, lines, i, current_task), current_task

        table_match = _TASK_TABLE_RE.match(line)
        if (
            table_match
            and not current_task["status"]
            and table_match.group(1) == current_task["id"]
        ):
            current_task["status"] = table_match.group(2).strip().lower()
    else:
        table_match = _TASK_TABLE_RE.match(line)
        if table_match and (in_sprint or sprint_volume):
            tasks.append(
                {
                    "id": table_match.group(1),
                    "status": table_match.group(2).strip().lower(),
                    "deliverables": [],
                    "tdd_acceptance": [],
                }
            )
        elif in_sprint:
            row_match = _TASK_ROW_RE.match(line)
            if row_match:
                tasks.append(
                    {
                        "id": row_match.group(1),
                        "status": "",
                        "deliverables": [],
                        "tdd_acceptance": [],
                    }
                )

    return i + 1, current_task


def extract_sprint_tasks(dev_plan_files: list[str], sprint_number: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    current_task: dict[str, Any] | None = None

    sprint_volume = _find_sprint_volume(dev_plan_files, sprint_number)
    files_to_search = [sprint_volume] if sprint_volume else dev_plan_files

    for filepath in files_to_search:
        with open(filepath, errors="replace") as f:
            content = f.read()

        # in_sprint is reset per file so a heading in one file never attributes
        # a card living in another file with no heading of its own.
        in_sprint = False
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(rf"^###?\s+Sprint\s+{sprint_number}\b", line, re.IGNORECASE):
                in_sprint = True
                i += 1
                continue
            if in_sprint and re.match(r"^###?\s+Sprint\s+\d+", line, re.IGNORECASE):
                in_sprint = False
                i += 1
                continue
            if not in_sprint and not sprint_volume:
                i += 1
                continue

            i, current_task = _process_task_line(
                line, lines, i, current_task, tasks, in_sprint, sprint_volume
            )

        if current_task:
            tasks.append(current_task)
            current_task = None

    tasks = _dedup_tasks(tasks)
    _backfill_missing_status(tasks, dev_plan_files)
    return tasks


def _dedup_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse entries sharing a task id (an overview row plus its detail
    card) into one, preferring a concrete status and unioning the lists."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for t in tasks:
        tid = t["id"]
        existing = merged.get(tid)
        if existing is None:
            merged[tid] = {
                "id": tid,
                "status": t["status"],
                "deliverables": list(t["deliverables"]),
                "tdd_acceptance": list(t["tdd_acceptance"]),
            }
            order.append(tid)
            continue
        if not existing["status"] and t["status"]:
            existing["status"] = t["status"]
        for d in t["deliverables"]:
            if d not in existing["deliverables"]:
                existing["deliverables"].append(d)
        for ac in t["tdd_acceptance"]:
            if ac not in existing["tdd_acceptance"]:
                existing["tdd_acceptance"].append(ac)
    return [merged[tid] for tid in order]


def classify_empty_extraction(dev_plan_files: list[str], sprint_number: int) -> str:
    """Diagnose why a sprint extracted no tasks, separating a layout/anchor
    miss from a genuinely empty sprint.

    * ``no_tasks`` — the dev-plan declares no ``T-NNN`` task ids anywhere.
    * ``no_anchor`` — tasks exist, but this sprint has no ``### Sprint N``
      heading and no ``-s{N}.md`` volume to scope them (likely an out-of-range
      number or a detail-volume naming mismatch).
    * ``anchored_empty`` — the sprint is anchored yet yields nothing (genuinely
      empty, or an overview table the parser can't read).
    """
    has_any_task = False
    anchored = _find_sprint_volume(dev_plan_files, sprint_number) is not None

    for filepath in dev_plan_files:
        with open(filepath) as f:
            lines = f.read().split("\n")
        for line in lines:
            if re.search(r"\bT-\d+", line):
                has_any_task = True
            heading = _SPRINT_HEADING_RE.match(line)
            if heading and int(heading.group(1)) == sprint_number:
                anchored = True

    if not has_any_task:
        return "no_tasks"
    if not anchored:
        return "no_anchor"
    return "anchored_empty"


def _backfill_missing_status(tasks: list[dict[str, Any]], dev_plan_files: list[str]) -> None:
    """Fill in status for tasks parsed without one from any status table row."""
    tasks_missing_status = {t["id"] for t in tasks if not t["status"]}
    if not tasks_missing_status:
        return
    for filepath in dev_plan_files:
        with open(filepath) as f:
            for line in f:
                table_match = _TASK_TABLE_RE.match(line)
                if table_match and table_match.group(1) in tasks_missing_status:
                    tid = table_match.group(1)
                    for t in tasks:
                        if t["id"] == tid and not t["status"]:
                            t["status"] = table_match.group(2).strip().lower()
                    tasks_missing_status.discard(tid)
        if not tasks_missing_status:
            break
