"""Tests for the runtime placeholder renderer.

Pins the per-platform substitution table for ``{INSTRUCTION_FILE}`` and
friends. Documents what each token resolves to so future placeholder
additions don't accidentally break the cross-platform contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy.template_render import (
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
        "{AGENTS_SRC_DIR}": ".cataforge/agents",
        "{RULES_DIR}": ".claude/rules",
        "{SKILLS_DIR}": ".claude/skills",
        "{COMMANDS_DIR}": ".claude/commands",
    },
    "cursor": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".cursor/agents",
        "{AGENTS_SRC_DIR}": ".cataforge/agents",
        "{RULES_DIR}": ".cursor/rules",
        "{SKILLS_DIR}": ".claude/skills",  # Cursor shares Claude's skills dir
        "{COMMANDS_DIR}": ".cursor/commands",
    },
    "codex": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".codex/agents",
        "{AGENTS_SRC_DIR}": ".cataforge/agents",
        "{RULES_DIR}": ".codex/rules",
        # Codex doesn't deploy skills/commands — fallback to source overlay
        # so cross-refs resolve to a readable path on every platform.
        "{SKILLS_DIR}": ".cataforge/skills",
        "{COMMANDS_DIR}": ".cataforge/commands",
    },
    "opencode": {
        "{INSTRUCTION_FILE}": "AGENTS.md",
        "{AGENTS_DIR}": ".opencode/agents",
        "{AGENTS_SRC_DIR}": ".cataforge/agents",
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
        "{AGENTS_SRC_DIR}",
        "{RULES_DIR}",
        "{SKILLS_DIR}",
        "{COMMANDS_DIR}",
        "{FRAMEWORK_VERSION}",
    }


def test_framework_version_resolves_to_package_version() -> None:
    """``{FRAMEWORK_VERSION}`` is adapter-independent and resolves to the
    installed package version on every platform, so the instruction file's
    框架版本 field is stamped deterministically at deploy."""
    import cataforge

    for platform_id in sorted(_EXPECTED):
        adapter = get_adapter(platform_id, _platforms_dir())
        assert resolve_placeholder("{FRAMEWORK_VERSION}", adapter) == cataforge.__version__
        rendered = render_runtime_content("- 框架版本: {FRAMEWORK_VERSION}", adapter)
        assert rendered == f"- 框架版本: {cataforge.__version__}"


@pytest.mark.parametrize("platform_id", sorted(_EXPECTED))
def test_agents_src_dir_resolves_to_source_overlay(platform_id: str) -> None:
    """``{AGENTS_SRC_DIR}`` resolves to the persistent ``.cataforge/agents``
    source on every platform, so cross-references reaching a file *inside* an
    agent dir (sibling ``*PROTOCOLS*.md`` or another agent's ``AGENT.md``)
    point at a path that survives flat-layout deploy.

    Flat platforms (Claude/OpenCode/Codex) deploy ``<name>.md`` only, so the
    same reference rendered through ``{AGENTS_DIR}`` would dangle at a
    ``<name>/<file>`` subpath that flat deploy never produces.
    """
    adapter = get_adapter(platform_id, _platforms_dir())
    source = "协议见 {AGENTS_SRC_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md"
    rendered = render_runtime_content(source, adapter)
    assert rendered == "协议见 .cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md"


def test_agents_dir_and_src_dir_coexist_without_clobber() -> None:
    """Both tokens render independently; substituting ``{AGENTS_DIR}`` must not
    corrupt the longer ``{AGENTS_SRC_DIR}`` token sharing the ``AGENTS_`` stem."""
    adapter = get_adapter("claude-code", _platforms_dir())
    source = "body 在 {AGENTS_DIR}/x.md；源协议在 {AGENTS_SRC_DIR}/x/P.md"
    rendered = render_runtime_content(source, adapter)
    assert rendered == "body 在 .claude/agents/x.md；源协议在 .cataforge/agents/x/P.md"
    assert "{AGENTS_DIR}" not in rendered
    assert "{AGENTS_SRC_DIR}" not in rendered


def test_render_substitutes_all_known_tokens_in_one_pass() -> None:
    adapter = get_adapter("claude-code", _platforms_dir())
    source = (
        "见 {INSTRUCTION_FILE} §项目状态；细则见 {RULES_DIR}/COMMON-RULES.md；"
        "skill 引用 {SKILLS_DIR}/research/SKILL.md；部署后 agent 目录 {AGENTS_DIR}；"
        "源协议见 {AGENTS_SRC_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md。"
    )
    rendered = render_runtime_content(source, adapter)
    assert "{INSTRUCTION_FILE}" not in rendered
    assert "{RULES_DIR}" not in rendered
    assert "{SKILLS_DIR}" not in rendered
    assert "{AGENTS_DIR}" not in rendered
    assert "{AGENTS_SRC_DIR}" not in rendered
    assert "CLAUDE.md" in rendered
    assert ".claude/rules/COMMON-RULES.md" in rendered
    assert ".claude/skills/research/SKILL.md" in rendered
    assert "部署后 agent 目录 .claude/agents；" in rendered
    assert ".cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md" in rendered


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
