"""Agent cross-references must resolve to a real file on flat-layout deploy.

Flat platforms (Claude Code, OpenCode, Codex) deploy one ``<name>.md`` /
``<name>.toml`` per agent — the source ``<name>/AGENT.md`` subdir and its
sibling ``*PROTOCOLS*.md`` files are not reproduced under the platform tree.
A reference written as ``{AGENTS_DIR}/<name>/<file>`` therefore renders to a
subpath flat deploy never produces (e.g. ``.claude/agents/orchestrator/
ORCHESTRATOR-PROTOCOLS.md``) and dangles at runtime.

``{AGENTS_SRC_DIR}`` resolves to the persistent ``.cataforge/agents`` source
on every platform, so any cross-reference that reaches a file *inside* an
agent dir must use it. These tests pin the mechanism and guard the source
tree against re-introducing the dangling form.
"""

from __future__ import annotations

import re
from pathlib import Path

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy import steps


def _platforms_dir() -> Path:
    return Path.cwd() / ".cataforge" / "platforms"


def _cataforge_dir() -> Path:
    return Path.cwd() / ".cataforge"


def _write_agent(agents_dir: Path, name: str, body: str) -> None:
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "AGENT.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n\n{body}",
        encoding="utf-8",
    )


def test_flat_deploy_keeps_src_xref_resolvable(tmp_path: Path) -> None:
    """A Claude Code (flat) deploy renders ``{AGENTS_SRC_DIR}`` cross-refs to
    the source overlay, never to the ``.claude/agents/<name>/<file>`` subpath
    a flat deploy cannot produce."""
    adapter = get_adapter("claude-code", _platforms_dir())
    src = tmp_path / ".cataforge" / "agents"
    _write_agent(
        src,
        "orchestrator",
        "协议见 {AGENTS_SRC_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md",
    )

    steps.deploy_agents(adapter, src, tmp_path)

    body = (tmp_path / ".claude" / "agents" / "orchestrator.md").read_text(encoding="utf-8")
    assert "{AGENTS_SRC_DIR}" not in body
    assert ".cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md" in body
    # The dangling form a flat deploy never materialises must be absent.
    assert ".claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md" not in body


# Matches ``{AGENTS_DIR}/<seg>/`` — a reference reaching *into* an agent dir,
# which dangles on every flat-layout platform. ``[^/\s]+`` spans nested
# runtime placeholders like ``{agent_id}`` without crossing a path separator.
_DANGLING_XREF = re.compile(r"\{AGENTS_DIR\}/[^/\s]+/")

# Captures the relative path inside a ``{AGENTS_SRC_DIR}/...`` reference up to
# a ``.md`` suffix. The character class excludes ``{`` so references carrying a
# nested runtime placeholder (``{AGENTS_SRC_DIR}/{agent_id}/AGENT.md``) are
# skipped — those resolve per-dispatch, not to a fixed file.
_SRC_XREF = re.compile(r"\{AGENTS_SRC_DIR\}/([A-Za-z0-9_./-]+\.md)")


def _iter_source_md() -> list[Path]:
    return sorted(p for p in _cataforge_dir().rglob("*.md") if p.is_file())


def test_no_dangling_agents_dir_xref_in_source() -> None:
    """No source prompt may reach into an agent dir via ``{AGENTS_DIR}`` —
    that subpath only exists on subdir-layout platforms (Cursor) and dangles
    on Claude/OpenCode/Codex. Use ``{AGENTS_SRC_DIR}`` instead."""
    offenders: list[str] = []
    for path in _iter_source_md():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _DANGLING_XREF.search(line):
                rel = path.relative_to(Path.cwd()).as_posix()
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Found `{AGENTS_DIR}/<name>/<file>` cross-references that dangle on "
        "flat-layout platforms — switch them to `{AGENTS_SRC_DIR}`:\n" + "\n".join(offenders)
    )


def test_src_xrefs_point_at_real_files() -> None:
    """Every fixed-path ``{AGENTS_SRC_DIR}/...`` reference in the source tree
    resolves to a file that actually exists under ``.cataforge/agents``."""
    agents_root = _cataforge_dir() / "agents"
    seen: list[str] = []
    missing: list[str] = []
    for path in _iter_source_md():
        text = path.read_text(encoding="utf-8")
        for rel in _SRC_XREF.findall(text):
            seen.append(rel)
            if not (agents_root / rel).is_file():
                missing.append(f"{path.relative_to(Path.cwd()).as_posix()} → {rel}")
    assert seen, (
        "Expected at least one `{AGENTS_SRC_DIR}/...` cross-reference in the "
        "source tree — none found, so the migration off `{AGENTS_DIR}` has "
        "not landed."
    )
    assert not missing, "Dangling `{AGENTS_SRC_DIR}` references:\n" + "\n".join(missing)
