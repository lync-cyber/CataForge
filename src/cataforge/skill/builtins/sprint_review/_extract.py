"""Sprint dev-plan parsing + task extraction (Layer 1 helpers)."""

from __future__ import annotations

import os
import re

from cataforge.utils.frontmatter import split_yaml_frontmatter


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
            with open(f, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            continue
        meta, _ = split_yaml_frontmatter(raw)
        if meta and isinstance(meta.get("project_features"), dict):
            return meta["project_features"]
    return {}


def extract_sprint_tasks(dev_plan_files: list[str], sprint_number: int) -> list[dict]:
    tasks: list[dict] = []
    in_sprint = False
    current_task: dict | None = None

    sprint_volume = None
    for f in dev_plan_files:
        if re.search(rf"-s{sprint_number}\.md$", f):
            sprint_volume = f
            break

    files_to_search = [sprint_volume] if sprint_volume else dev_plan_files

    for filepath in files_to_search:
        with open(filepath, encoding="utf-8") as f:
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
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        path = re.sub(r"^\s+[-*]\s+", "", lines[i]).strip()
                        path = re.sub(r"^\[[ x]\]\s*", "", path).strip()
                        path = re.sub(r"[`*]", "", path).strip()
                        path = re.sub(r"\s+[—\-]{1,2}\s+.*$", "", path).strip()
                        if path and not re.search(r"[一-鿿\s{]", path):
                            current_task["deliverables"].append(path)
                        i += 1
                    continue

                ac_match = re.match(
                    r"^[-*]\s+\*?\*?(?:tdd_acceptance|验收标准)\*?\*?\s*[:：]",
                    line,
                    re.IGNORECASE,
                )
                if ac_match:
                    rest = line + " "
                    i += 1
                    while i < len(lines) and re.match(r"^\s+[-*]", lines[i]):
                        rest += lines[i] + " "
                        i += 1
                    ac_ids = re.findall(r"AC-\d+", rest)
                    current_task["tdd_acceptance"] = list(set(ac_ids))
                    continue

                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line,
                    re.IGNORECASE,
                )
                if (
                    table_match
                    and not current_task["status"]
                    and table_match.group(1) == current_task["id"]
                ):
                    current_task["status"] = table_match.group(2).strip().lower()

            if not current_task:
                table_match = re.match(
                    r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                    line,
                    re.IGNORECASE,
                )
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

    tasks_missing_status = {t["id"] for t in tasks if not t["status"]}
    if tasks_missing_status:
        for filepath in dev_plan_files:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    table_match = re.match(
                        r"^\|\s*(T-\d+[a-z]?)\s*\|.*?\|\s*(done|todo|in[_-]?progress|blocked)\s*\|",
                        line,
                        re.IGNORECASE,
                    )
                    if table_match and table_match.group(1) in tasks_missing_status:
                        tid = table_match.group(1)
                        for t in tasks:
                            if t["id"] == tid and not t["status"]:
                                t["status"] = table_match.group(2).strip().lower()
                        tasks_missing_status.discard(tid)
            if not tasks_missing_status:
                break

    return tasks
