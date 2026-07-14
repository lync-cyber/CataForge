"""Runtime placeholder rendering for platform-bound deploy content.

Substitutes ``{INSTRUCTION_FILE}``, ``{AGENTS_DIR}``, ``{AGENTS_SRC_DIR}``,
``{RULES_DIR}``, ``{SKILLS_DIR}``, ``{COMMANDS_DIR}``, ``{FRAMEWORK_VERSION}``
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
    from cataforge.adapter.platform.adapter import PlatformAdapter


# Source-of-truth for placeholder names. The token is the literal text in
# source markdown; the resolver receives the adapter and returns the
# platform-native string (or ``None`` to leave the token in place — used
# only when the platform genuinely has no analog and we'd rather fail loud
# at guard time than render a wrong path).
_PLACEHOLDER_RESOLVERS: dict[str, str] = {
    "{INSTRUCTION_FILE}": "_resolve_instruction_file",
    "{AGENTS_DIR}": "_resolve_agents_dir",
    "{AGENTS_SRC_DIR}": "_resolve_agents_src_dir",
    "{RULES_DIR}": "_resolve_rules_dir",
    "{SKILLS_DIR}": "_resolve_skills_dir",
    "{COMMANDS_DIR}": "_resolve_commands_dir",
    "{FRAMEWORK_VERSION}": "_resolve_framework_version",
}


def _resolve_instruction_file(adapter: PlatformAdapter) -> str | None:
    """Platform-native instruction file name (``CLAUDE.md`` / ``AGENTS.md``)."""
    for target in adapter.instruction_targets:
        path = target.get("path")
        if path:
            return str(path)
    return None


def _resolve_agents_dir(adapter: PlatformAdapter) -> str | None:
    """Platform-native deployed-agents directory (``scan_dirs[0]``).

    Flat-layout platforms (Claude Code, OpenCode, Codex) deploy one file per
    agent — ``<name>.md`` / ``<name>.toml`` directly under this dir — so the
    source ``<name>/AGENT.md`` subdir and its sibling ``*PROTOCOLS*.md`` files
    are NOT reproduced here. Subdir-layout platforms (Cursor) keep the
    ``<name>/AGENT.md`` tree intact.

    A cross-reference that reaches a file *inside* an agent dir (a sibling
    protocol file, or another agent's ``AGENT.md``) must therefore use
    :func:`_resolve_agents_src_dir`'s ``{AGENTS_SRC_DIR}`` token — which points
    at the persistent ``.cataforge/agents`` source on every platform — not
    this token, whose ``<name>/<file>`` subpath only exists on subdir
    platforms and dangles everywhere else.
    """
    scan_dirs = adapter.get_agent_scan_dirs()
    if scan_dirs:
        return scan_dirs[0]
    return None


def _resolve_agents_src_dir(adapter: PlatformAdapter) -> str | None:
    """Source-overlay agents directory — ``.cataforge/agents`` on every platform.

    Deploy never removes the source overlay (self-heal even refills it), so
    ``.cataforge/agents/<name>/AGENT.md`` and its sibling ``*PROTOCOLS*.md``
    are readable from any platform's deployed tree. This is the only stable
    target for agent-internal cross-references on flat-layout platforms, where
    :func:`_resolve_agents_dir` deploys the agent body alone. Mirrors the
    lang-fragment links, which point at the same source overlay for the same
    reason.
    """
    del adapter  # source overlay is platform-independent
    return ".cataforge/agents"


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


def _resolve_framework_version(_adapter: PlatformAdapter) -> str | None:
    """Installed cataforge package version — the single source of truth,
    stamped into the 框架版本 field at every deploy (adapter-independent)."""
    from cataforge import __version__

    return __version__


# Index resolver functions by name so the registry above stays a plain
# ``dict[str, str]`` (importable without forward refs and easy to enumerate
# in tests). The indirection costs nothing at runtime — one extra dict
# lookup per placeholder per render call.
_RESOLVER_FUNCS = {
    "_resolve_instruction_file": _resolve_instruction_file,
    "_resolve_agents_dir": _resolve_agents_dir,
    "_resolve_agents_src_dir": _resolve_agents_src_dir,
    "_resolve_rules_dir": _resolve_rules_dir,
    "_resolve_skills_dir": _resolve_skills_dir,
    "_resolve_commands_dir": _resolve_commands_dir,
    "_resolve_framework_version": _resolve_framework_version,
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


def render_runtime_content(content: str, adapter: PlatformAdapter, *, neutral: bool = False) -> str:
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
    * ``neutral=True`` renders directory placeholders to the platform-
      independent ``.cataforge/`` source paths. Used for instruction files
      shared by several platforms (AGENTS.md) — a platform-specific path
      there would flip with whichever platform deployed last.

    Idempotency: re-running on already-rendered content is a no-op because
    the rendered values don't contain any of the literal placeholder tokens.
    """
    neutral_values = {
        **_SOURCE_FALLBACKS,
        "{AGENTS_DIR}": ".cataforge/agents",
        "{AGENTS_SRC_DIR}": ".cataforge/agents",
    }
    for token in _PLACEHOLDER_RESOLVERS:
        if token not in content:
            continue
        if neutral and token in neutral_values:
            content = content.replace(token, neutral_values[token])
            continue
        value = resolve_placeholder(token, adapter)
        if value is None:
            continue
        content = content.replace(token, value)
    return content
