"""Guard: prompt assets reference the instruction-file section by its real name.

The deployed instruction file (and ``section_merge`` schema policy) name the
metadata section ``项目信息``. Protocols that read ``§项目信息.执行模式`` must use
that exact name — a stray ``框架元信息`` reference points at a section that does
not exist, so the orchestrator's Mode Routing read silently falls back to
``standard``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIRS = (
    REPO_ROOT / ".cataforge" / "agents",
    REPO_ROOT / ".cataforge" / "skills",
    REPO_ROOT / ".cataforge" / "rules",
)
PHANTOM_SECTION = "框架元信息"


def test_claude_md_section_name_matches_protocol_refs() -> None:
    offenders: list[str] = []
    for base in PROMPT_DIRS:
        for md in base.rglob("*.md"):
            if PHANTOM_SECTION in md.read_text(encoding="utf-8"):
                offenders.append(str(md.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"prompt assets reference phantom section §{PHANTOM_SECTION}; "
        f"the instruction-file metadata section is §项目信息: {offenders}"
    )
