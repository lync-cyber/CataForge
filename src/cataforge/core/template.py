"""Rendering layer for in-tree templates and platform-bound content.

Two responsibilities, kept in one module so callers have a single import for
"substitute the platform-specific bits before this string reaches the LLM":

* :func:`render_project_state` — substitutes ``运行时: {platform}`` in
  PROJECT-STATE.md. Predates :func:`render_runtime_content` and is kept as a
  thin alias so PROJECT-STATE.md callers don't need to thread an adapter.
* :func:`render_runtime_content` — substitutes ``{INSTRUCTION_FILE}``,
  ``{AGENTS_DIR}``, ``{RULES_DIR}``, ``{SKILLS_DIR}``, ``{COMMANDS_DIR}``
  into any markdown body before it lands at a platform-native path.

Why a registry, not free-form ``str.format``:

Source files contain literal braces in unrelated contexts (frontmatter
examples, JSON snippets, Python code). ``str.format`` would crash on any
``{unknown}`` token, and a permissive ``str.format_map`` over an unbounded
dict would silently swallow typos. The registry approach loops over a
fixed set of names and uses ``str.replace`` per token — unrelated braces
pass through untouched, typos surface as un-substituted placeholders that
guards can grep for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.platform.base import PlatformAdapter

_PROJECT_STATE_PLATFORM_PLACEHOLDER = "运行时: {platform}"


def render_project_state(content: str, platform_id: str) -> str:
    """Substitute the runtime-platform placeholder in PROJECT-STATE.md."""
    return content.replace(
        _PROJECT_STATE_PLATFORM_PLACEHOLDER,
        f"运行时: {platform_id}",
    )


# Source-of-truth for placeholder names. The token is the literal text in
# source markdown; the resolver receives the adapter and returns the
# platform-native string (or ``None`` to leave the token in place — used
# only when the platform genuinely has no analog and we'd rather fail loud
# at guard time than render a wrong path).
_PLACEHOLDER_RESOLVERS: dict[str, str] = {
    "{INSTRUCTION_FILE}": "_resolve_instruction_file",
    "{AGENTS_DIR}": "_resolve_agents_dir",
    "{RULES_DIR}": "_resolve_rules_dir",
    "{SKILLS_DIR}": "_resolve_skills_dir",
    "{COMMANDS_DIR}": "_resolve_commands_dir",
}


def _resolve_instruction_file(adapter: PlatformAdapter) -> str | None:
    """Platform-native instruction file name (``CLAUDE.md`` / ``AGENTS.md``)."""
    for target in adapter.instruction_targets:
        path = target.get("path")
        if path:
            return str(path)
    return None


def _resolve_agents_dir(adapter: PlatformAdapter) -> str | None:
    """Platform-native deployed-agents directory.

    Resolves to whatever ``agent_definition.scan_dirs[0]`` declares — so for
    Claude/OpenCode this is the per-agent-subdir tree, and for Codex/Cursor
    it's the flat ``.codex/agents`` / ``.cursor/agents`` tree. Cross-references
    that include sibling filenames (``{AGENTS_DIR}/<name>/PROTOCOLS.md``)
    only resolve to a real path on subdir-layout platforms; flat-layout
    platforms deploy only the agent body, so the sibling path is a
    documentation hint pointing at the source overlay.
    """
    scan_dirs = adapter.get_agent_scan_dirs()
    if scan_dirs:
        return scan_dirs[0]
    return None


# Source-location fallbacks used when a platform doesn't materialise content
# under its native tree. Examples:
#   * OpenCode registers rules via ``opencode.json#instructions`` glob — no
#     per-file dir to substitute, so ``{RULES_DIR}`` falls back to the
#     ``.cataforge/rules`` source overlay (which OpenCode's glob includes).
#   * Codex / Cursor / OpenCode don't deploy a project-level skills dir, so
#     ``{SKILLS_DIR}`` falls back to ``.cataforge/skills`` source.
#
# Why fall back to source instead of leaving the token: the source paths
# are real, readable, and identical across every platform — exactly the
# guarantee we need for ``{SKILLS_DIR}/research/SKILL.md`` to resolve to a
# file the LLM can open regardless of which platform's deploy ran.
_SOURCE_FALLBACKS = {
    "{RULES_DIR}": ".cataforge/rules",
    "{SKILLS_DIR}": ".cataforge/skills",
    "{COMMANDS_DIR}": ".cataforge/commands",
}


def _looks_like_directory(target: str | None) -> bool:
    """Return True only if *target* names a directory path.

    OpenCode declares ``rules_distribution.target: opencode.json`` — a JSON
    config file, not a directory. Rendering ``{RULES_DIR}/COMMON-RULES.md``
    to ``opencode.json/COMMON-RULES.md`` would produce a nonsense path that
    silently breaks every cross-reference on OpenCode. The cheap proxy:
    paths that have a file extension are treated as files; bare names and
    paths with no extension are treated as directories.
    """
    if not target:
        return False
    last = target.rsplit("/", 1)[-1]
    return "." not in last


def _resolve_rules_dir(adapter: PlatformAdapter) -> str | None:
    declared = adapter._default_rules_target_dir()
    if _looks_like_directory(declared):
        return declared
    return _SOURCE_FALLBACKS["{RULES_DIR}"]


def _resolve_skills_dir(adapter: PlatformAdapter) -> str | None:
    declared = adapter.get_skill_target_dir()
    if _looks_like_directory(declared):
        return declared
    return _SOURCE_FALLBACKS["{SKILLS_DIR}"]


def _resolve_commands_dir(adapter: PlatformAdapter) -> str | None:
    declared = adapter.get_command_target_dir()
    if _looks_like_directory(declared):
        return declared
    return _SOURCE_FALLBACKS["{COMMANDS_DIR}"]


# Index resolver functions by name so the registry above stays a plain
# ``dict[str, str]`` (importable without forward refs and easy to enumerate
# in tests). The indirection costs nothing at runtime — one extra dict
# lookup per placeholder per render call.
_RESOLVER_FUNCS = {
    "_resolve_instruction_file": _resolve_instruction_file,
    "_resolve_agents_dir": _resolve_agents_dir,
    "_resolve_rules_dir": _resolve_rules_dir,
    "_resolve_skills_dir": _resolve_skills_dir,
    "_resolve_commands_dir": _resolve_commands_dir,
}


def known_placeholders() -> tuple[str, ...]:
    """Return the literal placeholder tokens this renderer recognises.

    Used by tests and the per-PR doc-structure guard to enumerate the
    placeholder surface without importing the resolver internals.
    """
    return tuple(_PLACEHOLDER_RESOLVERS.keys())


def resolve_placeholder(token: str, adapter: PlatformAdapter) -> str | None:
    """Resolve a single placeholder token against an adapter.

    Returns ``None`` when the token is unknown or the platform has no
    binding for it. Callers decide whether to leave the literal token in
    place (the renderer's choice) or fail loud.
    """
    resolver_name = _PLACEHOLDER_RESOLVERS.get(token)
    if resolver_name is None:
        return None
    return _RESOLVER_FUNCS[resolver_name](adapter)


def render_runtime_content(content: str, adapter: PlatformAdapter) -> str:
    """Substitute every known placeholder in *content* for *adapter*.

    Behaviour rules:

    * Tokens not in the registry are left untouched (so foreign ``{x}``
      patterns in JSON / code blocks survive).
    * Tokens whose resolver returns ``None`` (platform has no binding) are
      left as the literal placeholder. The pre-commit
      ``check_no_unrendered_placeholder`` guard will fail loud if any of
      these reach a deployed artefact.
    * Substitution uses ``str.replace`` so the same token can appear
      multiple times in one body.

    Idempotency: re-running on already-rendered content is a no-op because
    the rendered values don't contain any of the literal placeholder tokens.
    """
    for token in _PLACEHOLDER_RESOLVERS:
        if token not in content:
            continue
        value = resolve_placeholder(token, adapter)
        if value is None:
            continue
        content = content.replace(token, value)
    return content
