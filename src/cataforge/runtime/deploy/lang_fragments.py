"""Deploy-time language-fragment injection for language-aware agents.

Agent prompts stay language-agnostic in the repo (the ``check_no_language_coupling``
guard enforces this on ``AGENT.md`` bodies). Language specifics live in
per-agent fragment files ``.cataforge/agents/<id>/rules/lang-<lang>.md`` —
outside the guard's scan globs.

At deploy time, for agents whose frontmatter declares ``lang_aware: true``, a
``## 语言细则`` section is appended to the *staged* copy linking the fragments
for the project's active languages. The repo source stays neutral; only the
deployed artefact carries the language links.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.utils.atomic_write import atomic_write_text
from cataforge.utils.frontmatter import split_yaml_frontmatter

_SECTION_TITLE = "语言细则"


def inject_lang_fragments(
    agent_md: str, agent_id: str, langs: list[str], paths: ProjectPaths
) -> str:
    """Append a ``## 语言细则`` section linking the agent's per-language fragments.

    Links point at the persistent source fragments under
    ``.cataforge/agents/<id>/rules/lang-<lang>.md`` (so the reference survives
    the temp staging dir). Returns *agent_md* unchanged when no fragment exists
    for any active language.
    """
    frags = [
        f
        for lang in langs
        if (f := paths.agents_dir / agent_id / "rules" / f"lang-{lang}.md").is_file()
    ]
    if not frags:
        return agent_md
    links = "\n".join(f"- 见 `{f.relative_to(paths.root).as_posix()}`" for f in frags)
    sep = "" if agent_md.endswith("\n") else "\n"
    return f"{agent_md}{sep}\n## {_SECTION_TITLE}\n{links}\n"


def inject_into_staged_agents(agents_dir: Path, langs: list[str], paths: ProjectPaths) -> list[str]:
    """Inject fragments into every ``lang_aware`` agent under *agents_dir*.

    Mutates the staged AGENT.md files in place. Returns the ids injected.
    No-op when there are no active languages.
    """
    if not langs or not agents_dir.is_dir():
        return []
    injected: list[str] = []
    for agent_dir in sorted(p for p in agents_dir.iterdir() if p.is_dir()):
        agent_md = agent_dir / "AGENT.md"
        if not agent_md.is_file():
            continue
        content = agent_md.read_text()
        fm, _ = split_yaml_frontmatter(content)
        if not (fm and fm.get("lang_aware")):
            continue
        new = inject_lang_fragments(content, agent_dir.name, langs, paths)
        if new != content:
            atomic_write_text(agent_md, new)
            injected.append(agent_dir.name)
    return injected
