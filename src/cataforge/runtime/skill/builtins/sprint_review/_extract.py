"""Sprint dev-plan parsing + task extraction (Layer 1 helpers)."""

from __future__ import annotations

import os
import re

from cataforge.utils.frontmatter import split_yaml_frontmatter

# A dev-plan task-status table row: ``| T-12 | … | done |``. Shared by the
# in-task, standalone-row, and status-backfill scans below.
_TASK_TABLE_RE = re.compile(
    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
    re.IGNORECASE,
)


def find_dev_plan_files(dev_plan_dir: str) -> list[str]:
    files = []
    if not os.path.isdir(dev_plan_dir):
        return files
    for f in sorted(os.listdir(dev_plan_dir)):
        if f.endswith(".md"):
            files.append(os.path.join(dev_plan_dir, f))
    return files


def load_project_features(dev_plan_files: list[str]) -> dict:
    """Load ``project_features`` block from the dev-plan main volume frontmatter.

    Sprint volumes (``-s{N}.md``) inherit from the main volume; the first
    file containing a ``project_features:`` key wins. Returns ``{}`` when no
    file declares the block — preserving existing checker behavior.

    Recognised keys (all optional, all default off):

    * ``merged_review`` (bool) — short-circuit ``code_review_present`` (the
      sprint-review report itself carries per-task L2 instead of separate
      CODE-REVIEW files).
    * ``deliverables_accept_alternation`` (bool) — let ``deliverables`` lines
      use ``A | B`` syntax (passes if **either** path exists).
    * ``unplanned_glob_patterns`` (list[str]) — fnmatch patterns; matching
      files are filtered out of the unplanned-files WARN set.
    """
    for f in dev_plan_files:
        if re.search(r"-s\d+\.md$", f):
            continue
        try:
            with open(f) as fh:
                raw = fh.read()
        except OSError:
            continue
        meta, _ = split_yaml_frontmatter(raw)
        if meta and isinstance(meta.get("project_features"), dict):
            return meta["project_features"]
    return {}


def _find_sprint_volume(dev_plan_files: list[str], sprint_number: int) -> str | None:
    """Return the ``-s{N}.md`` volume for this sprint, or None when absent."""
    for f in dev_plan_files:
        if re.search(rf"-s{sprint_number}\.md$", f):
            return f
    return None


def _consume_deliverables(lines: list[str], i: int, current_task: dict) -> int:
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
        if path and not re.search(r"[一-鿿\s{]", path):
            current_task["deliverables"].append(path)
        i += 1
    return i


def _consume_acceptance(line: str, lines: list[str], i: int, current_task: dict) -> int:
    """Absorb the ``tdd_acceptance:`` line plus its indented continuation."""
    rest = line + " "
    i += 1
    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
        rest += lines[i] + " "
        i += 1
    current_task["tdd_acceptance"] = list(set(re.findall(r"AC-\d+", rest)))
    return i


def extract_sprint_tasks(dev_plan_files: list[str], sprint_number: int) -> list[dict]:
    tasks: list[dict] = []
    in_sprint = False
    current_task: dict | None = None

    sprint_volume = _find_sprint_volume(dev_plan_files, sprint_number)
    files_to_search = [sprint_volume] if sprint_volume else dev_plan_files

    for filepath in files_to_search:
        with open(filepath) as f:
            content = f.read()

        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(rf"^###?\s+Sprint\s+{sprint_number}\b", line, re.IGNORECASE):
                in_sprint = True
                i += 1
                continue
            elif in_sprint and re.match(r"^###?\s+Sprint\s+\d+", line, re.IGNORECASE):
                in_sprint = False
                i += 1
                continue

            if not in_sprint and not sprint_volume:
                i += 1
                continue

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
                i += 1
                continue

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
                    i = _consume_deliverables(lines, i, current_task)
                    continue

                ac_match = re.match(
                    r"^[-*]\s+\*?\*?(?:tdd_acceptance|验收标准)\*?\*?\s*[:：]",
                    line,
                    re.IGNORECASE,
                )
                if ac_match:
                    i = _consume_acceptance(line, lines, i, current_task)
                    continue

                table_match = _TASK_TABLE_RE.match(line)
                if (
                    table_match
                    and not current_task["status"]
                    and table_match.group(1) == current_task["id"]
                ):
                    current_task["status"] = table_match.group(2).strip().lower()

            if not current_task:
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

            i += 1

        if current_task:
            tasks.append(current_task)
            current_task = None

    _backfill_missing_status(tasks, dev_plan_files)
    return tasks


def _backfill_missing_status(tasks: list[dict], dev_plan_files: list[str]) -> None:
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
