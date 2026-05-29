"""Tests for the runtime placeholder renderer.

Pins the per-platform substitution table for ``{INSTRUCTION_FILE}`` and
friends. Documents what each token resolves to so future placeholder
additions don't accidentally break the cross-platform contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.registry import get_adapter
from cataforge.core.template import (
    known_placeholders,
    render_runtime_content,
    resolve_placeholder,
)


def _platforms_dir() -> Path:
    return Path.cwd() / ".cataforge" / "platforms"


# Resolver outputs per platform — pinned so any profile.yaml drift trips
# a test instead of silently shifting deployed content.
_EXPECTED = {
    "claude-code": {
        "{INSTRUCTION_FILE}": "CLAUDE.md",
        "{AGENTS_DIR}": ".claude/agents",
        "{RULES_DIR}": ".claude/rules",
        "{SKILLS_DIR}": ".claude/skills",
        "{COMMANDS_DIR}": ".claude/commands",
    },
    "cursor": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".cursor/agents",
        "{RULES_DIR}": ".cursor/rules",
        "{SKILLS_DIR}": ".claude/skills",  # Cursor shares Claude's skills dir
        "{COMMANDS_DIR}": ".cursor/commands",
    },
    "codex": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".codex/agents",
        "{RULES_DIR}": ".codex/rules",
        # Codex doesn't deploy skills/commands — fallback to source overlay
        # so cross-refs resolve to a readable path on every platform.
        "{SKILLS_DIR}": ".cataforge/skills",
        "{COMMANDS_DIR}": ".cataforge/commands",
    },
    "opencode": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".opencode/agents",
        # OpenCode registers rules through opencode.json#instructions (file,
        # not dir). Render path falls back to the source overlay; the
        # in-place glob still picks the same content up.
        "{RULES_DIR}": ".cataforge/rules",
        "{SKILLS_DIR}": ".cataforge/skills",
        "{COMMANDS_DIR}": ".cataforge/commands",
    },
}


@pytest.mark.parametrize("platform_id", sorted(_EXPECTED))
def test_resolve_placeholder_matches_profile(platform_id: str) -> None:
    """Every pinned token resolves to the expected platform-native value."""
    adapter = get_adapter(platform_id, _platforms_dir())
    for token, expected in _EXPECTED[platform_id].items():
        assert resolve_placeholder(token, adapter) == expected, (
            f"{platform_id}: {token} did not resolve to {expected!r}"
        )


def test_known_placeholders_lists_full_surface() -> None:
    """Guards that build a regex from this list rely on it being exhaustive."""
    assert set(known_placeholders()) == {
        "{INSTRUCTION_FILE}",
        "{AGENTS_DIR}",
        "{RULES_DIR}",
        "{SKILLS_DIR}",
        "{COMMANDS_DIR}",
    }


def test_render_substitutes_all_known_tokens_in_one_pass() -> None:
    adapter = get_adapter("claude-code", _platforms_dir())
    source = (
        "见 {INSTRUCTION_FILE} §项目状态；细则见 {RULES_DIR}/COMMON-RULES.md；"
        "skill 引用 {SKILLS_DIR}/research/SKILL.md；agent 协议见 "
        "{AGENTS_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md。"
    )
    rendered = render_runtime_content(source, adapter)
    assert "{INSTRUCTION_FILE}" not in rendered
    assert "{RULES_DIR}" not in rendered
    assert "{SKILLS_DIR}" not in rendered
    assert "{AGENTS_DIR}" not in rendered
    assert "CLAUDE.md" in rendered
    assert ".claude/rules/COMMON-RULES.md" in rendered
    assert ".claude/skills/research/SKILL.md" in rendered
    assert ".claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md" in rendered


def test_render_leaves_unknown_braces_untouched() -> None:
    """The renderer must not crash on stray ``{...}`` in JSON / code blocks."""
    adapter = get_adapter("claude-code", _platforms_dir())
    source = (
        'frontmatter: { "key": "value" }\n'
        "format string example: {self.module}\n"
        "real placeholder: {INSTRUCTION_FILE}\n"
    )
    rendered = render_runtime_content(source, adapter)
    assert '{ "key": "value" }' in rendered  # JSON survived
    assert "{self.module}" in rendered  # Python-style format string survived
    assert "{INSTRUCTION_FILE}" not in rendered
    assert "CLAUDE.md" in rendered


def test_render_is_idempotent() -> None:
    """Re-rendering already-rendered content is a no-op."""
    adapter = get_adapter("claude-code", _platforms_dir())
    source = "见 {INSTRUCTION_FILE} §项目状态"
    once = render_runtime_content(source, adapter)
    twice = render_runtime_content(once, adapter)
    assert once == twice


def test_opencode_rules_dir_falls_back_to_source_overlay() -> None:
    """OpenCode declares ``rules_distribution.target: opencode.json`` — a
    file, not a directory. Rendering ``{RULES_DIR}/COMMON-RULES.md`` as
    ``opencode.json/COMMON-RULES.md`` would silently break every
    cross-ref. We fall back to the ``.cataforge/rules`` source overlay,
    which OpenCode's ``opencode.json#instructions`` glob already includes.
    """
    adapter = get_adapter("opencode", _platforms_dir())
    source = "rules 在 {RULES_DIR}/COMMON-RULES.md"
    rendered = render_runtime_content(source, adapter)
    assert rendered == "rules 在 .cataforge/rules/COMMON-RULES.md"
    assert "opencode.json/COMMON-RULES.md" not in rendered
