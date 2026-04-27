"""Sync .cataforge/ → src/cataforge/_assets/cataforge_scaffold/.

The repo's ``.cataforge/`` directory is the single source of truth for the
bundled scaffold that ``cataforge setup`` / ``cataforge upgrade`` install
into user projects.  ``src/cataforge/_assets/cataforge_scaffold/`` is a
generated mirror shipped inside the wheel — editing it directly is
forbidden; CI will reject drift.

Usage:
    python scripts/sync_scaffold.py             # mirror, prune orphans
    python scripts/sync_scaffold.py --check     # exit 1 on drift, no writes

Excluded from mirror (dogfood / repo-only):
    scripts/dogfood/**

Cross-platform (no rsync dependency); uses pure stdlib walks.
"""

from __future__ import annotations

import argparse
import contextlib
import filecmp
import shutil
import sys
from pathlib import Path

# Reconfigure stdio to UTF-8 before any print() runs so the unicode
# arrow ('→') in the sync summary doesn't crash the script on Windows
# cp1252 terminals. The cataforge package isn't necessarily importable
# from this build script (chicken-and-egg in fresh checkouts), so we
# inline the same logic as cataforge.utils.common.ensure_utf8_stdio.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / ".cataforge"
TARGET = REPO_ROOT / "src" / "cataforge" / "_assets" / "cataforge_scaffold"

# Directory prefixes (relative to SOURCE / TARGET) excluded from the mirror.
# Paths are posix-style, checked against the relative path of each entry.
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "scripts/dogfood",
)

# Files that exist only in the TARGET mirror (never in SOURCE) and must
# survive the sync — they're markers for the mirror itself, not part of
# the scaffold delivered to user projects.
TARGET_ONLY_FILES: frozenset[str] = frozenset({
    "GENERATED.md",
})


def _is_excluded(rel_posix: str) -> bool:
    return any(
        rel_posix == p or rel_posix.startswith(p + "/") for p in EXCLUDE_PREFIXES
    )


def _walk_files(root: Path, *, is_target: bool = False) -> list[str]:
    """Return sorted list of relative posix paths for every file under *root*.

    When walking the TARGET mirror, files in :data:`TARGET_ONLY_FILES`
    are filtered out so they neither show up as "extra" in `_classify`
    nor get pruned by `sync()`.
    """
    if not root.is_dir():
        return []
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_excluded(rel):
            continue
        if is_target and rel in TARGET_ONLY_FILES:
            continue
        out.append(rel)
    out.sort()
    return out


def _classify(source: Path, target: Path) -> tuple[list[str], list[str], list[str]]:
    """Return ``(missing, differs, extra)`` relative to *source* → *target*."""
    src_files = set(_walk_files(source))
    dst_files = set(_walk_files(target, is_target=True))

    missing = sorted(src_files - dst_files)
    extra = sorted(dst_files - src_files)
    differs = sorted(
        rel
        for rel in (src_files & dst_files)
        if not filecmp.cmp(source / rel, target / rel, shallow=False)
    )
    return missing, differs, extra


def check() -> int:
    missing, differs, extra = _classify(SOURCE, TARGET)
    total = len(missing) + len(differs) + len(extra)
    if total == 0:
        print("scaffold in sync.")
        return 0
    print(
        f"scaffold drift detected ({total} path(s)); "
        "run `python scripts/sync_scaffold.py` to resync.",
        file=sys.stderr,
    )
    for rel in missing:
        print(f"  + {rel}  (missing in mirror)", file=sys.stderr)
    for rel in differs:
        print(f"  ~ {rel}  (content differs)", file=sys.stderr)
    for rel in extra:
        print(f"  - {rel}  (extra in mirror — should be removed or excluded)",
              file=sys.stderr)
    return 1


def sync() -> int:
    missing, differs, extra = _classify(SOURCE, TARGET)

    for rel in missing + differs:
        src = SOURCE / rel
        dst = TARGET / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in extra:
        dst = TARGET / rel
        dst.unlink()

    # Drop empty directories left behind by removals.
    if TARGET.is_dir():
        for path in sorted(
            (p for p in TARGET.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            with contextlib.suppress(OSError):
                path.rmdir()

    if missing or differs or extra:
        print(
            f"synced: +{len(missing)} ~{len(differs)} -{len(extra)} "
            f"({SOURCE} → {TARGET})"
        )
    else:
        print("scaffold already in sync.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if drift detected; do not write",
    )
    args = parser.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    raise SystemExit(main())
