"""Migrate legacy ``docs/NAV-INDEX.md`` to ``docs/.doc-index.json``.

Pre-v0.1.13 projects shipped a hand-maintained markdown table at
``docs/NAV-INDEX.md`` as the canonical document map. From v0.1.13 onwards
the chapter index is machine-only at ``docs/.doc-index.json`` and rebuilt by
``cataforge docs index``.

This migration:

1. Parses the legacy NAV-INDEX.md (extracts doc_id → file_path pairs from the
   "## 文档总览" markdown table — the only signal still meaningful, since
   line numbers are stale and the per-file [NAV] blocks are mirrored by the
   YAML/heading structure that ``cataforge docs index`` already parses).
2. Archives the original to ``.cataforge/.archive/NAV-INDEX-<utc-ts>.md`` so
   the file is recoverable if a downstream tool still depends on it.
3. Deletes the original ``docs/NAV-INDEX.md``.
4. Runs the indexer to produce a fresh ``docs/.doc-index.json``.
5. Reports any doc_id present in the legacy NAV but missing from the rebuilt
   index — usually a sign that the markdown file was renamed or deleted
   without updating NAV-INDEX.md (i.e. existing rot the migration surfaces).

Exit codes:
    0  migration succeeded (or no NAV-INDEX.md found — already migrated)
    1  index rebuild failed
    2  parse error in NAV-INDEX.md
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from cataforge.core.paths import find_project_root
from cataforge.utils.common import ensure_utf8_stdio

_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<doc_id>[A-Za-z0-9_-]+)\s*\|\s*(?P<path>[^|]+?)\s*\|"
)


def _parse_nav_table(nav_text: str) -> list[tuple[str, str]]:
    """Extract ``(doc_id, file_path)`` pairs from the legacy NAV-INDEX table.

    The legacy format is documented in pre-v0.1.13 doc-nav SKILL.md:

        | Doc ID | 文件路径 | 状态 | 分卷 | 章节数 |
        | prd | docs/prd/prd-foo-v1.md | draft | 1 | 5 |

    Anything before the first table is ignored. Header / divider rows are
    skipped by checking for the first column being a known doc_id pattern
    (lowercase letters, digits, dashes, underscores) and the second column
    looking like a markdown path. ``-`` divider rows naturally fail both.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in nav_text.splitlines():
        m = _TABLE_ROW_RE.match(line.strip())
        if not m:
            continue
        doc_id = m.group("doc_id")
        path = m.group("path").strip()
        if doc_id.lower() in {"doc id", "doc_id", "id"}:
            continue
        if not path or not path.endswith(".md"):
            continue
        if path.startswith("--"):
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        pairs.append((doc_id, path))
    return pairs


def _archive_legacy_nav(nav_path: Path, project_root: Path) -> Path:
    archive_dir = project_root / ".cataforge" / ".archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archived = archive_dir / f"NAV-INDEX-{ts}.md"
    shutil.copy2(nav_path, archived)
    return archived


def _rebuild_index(project_root: Path) -> int:
    from cataforge.docs.indexer import main as indexer_main

    return indexer_main(["--project-root", str(project_root)])


def _list_index_doc_ids(project_root: Path) -> set[str]:
    import json

    idx_path = project_root / "docs" / ".doc-index.json"
    if not idx_path.is_file():
        return set()
    try:
        with open(idx_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    return set((data.get("documents") or {}).keys())


def migrate(project_root: Path, *, dry_run: bool = False) -> int:
    nav_path = project_root / "docs" / "NAV-INDEX.md"
    if not nav_path.is_file():
        print(
            f"[OK] {nav_path.relative_to(project_root)} 不存在，无需迁移 — "
            "建议运行 `cataforge docs index` 确保 .doc-index.json 是最新的。"
        )
        return 0

    try:
        nav_text = nav_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[ERROR] 读取 {nav_path} 失败: {e}", file=sys.stderr)
        return 2

    legacy_pairs = _parse_nav_table(nav_text)
    print(f"[SCAN] NAV-INDEX.md 发现 {len(legacy_pairs)} 个文档条目")

    if dry_run:
        print("[DRY-RUN] 跳过归档、删除、重建步骤")
        for doc_id, path in legacy_pairs:
            exists = (project_root / path).is_file()
            marker = "OK" if exists else "MISSING"
            print(f"  [{marker}] {doc_id} → {path}")
        return 0

    archived = _archive_legacy_nav(nav_path, project_root)
    print(f"[ARCHIVE] 已归档到 {archived.relative_to(project_root)}")

    nav_path.unlink()
    print(f"[REMOVE] 已删除 {nav_path.relative_to(project_root)}")

    rc = _rebuild_index(project_root)
    if rc != 0:
        print(
            f"[ERROR] `cataforge docs index` 失败 (exit {rc}) — "
            f"NAV-INDEX.md 的副本仍在 {archived.relative_to(project_root)}",
            file=sys.stderr,
        )
        return 1

    rebuilt = _list_index_doc_ids(project_root)
    legacy_ids = {doc_id for doc_id, _ in legacy_pairs}
    missing = sorted(legacy_ids - rebuilt)
    extras = sorted(rebuilt - legacy_ids)
    print(f"[REBUILD] .doc-index.json 含 {len(rebuilt)} 个文档")
    if missing:
        print(
            f"[WARN] {len(missing)} 个 doc_id 在 NAV-INDEX 中存在但未被 indexer 发现 "
            f"(可能已删除/重命名): {', '.join(missing)}",
            file=sys.stderr,
        )
    if extras:
        print(
            f"[INFO] {len(extras)} 个新发现的 doc_id (NAV-INDEX 未登记): "
            f"{', '.join(extras)}"
        )
    print("[DONE] 迁移完成")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Migrate legacy docs/NAV-INDEX.md to docs/.doc-index.json",
    )
    parser.add_argument("--project-root", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report only — do not archive, delete, or rebuild.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root) if args.project_root else find_project_root()
    return migrate(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
