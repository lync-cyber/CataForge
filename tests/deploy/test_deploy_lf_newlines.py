"""Deployed/scaffolded artefacts must be written with LF, not CRLF.

On Windows ``Path.write_text(data)`` opens in text mode and translates
``\\n`` → ``os.linesep`` (``\\r\\n``), so every deployed file lands with
CRLF — fighting the cataforge-default ``.gitattributes`` (``eol=lf``) and
emitting a wall of ``safecrlf`` warnings on the next ``git add``. The deploy
and scaffold write paths therefore route through
:func:`cataforge.utils.atomic_write.atomic_write_text`, which pins
``newline="\\n"`` (and writes atomically via temp-file + ``os.replace``).

Two guards:

* a behavioural test that deploys into a tmp project and asserts no
  deployed artefact contains a ``\\r\\n`` byte — the real check on Windows;
* a static guard that asserts the deploy/scaffold modules carry no bare
  ``Path.write_text(`` — catches a reintroduced raw write on every platform,
  including LF-only CI where the behavioural test cannot observe the defect.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import cataforge
import cataforge.core.scaffold as scaffold_mod
from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer

_CLAUDE_PROFILE: dict = {
    "platform_id": "claude-code",
    "display_name": "Claude Code",
    "tool_map": {"file_read": "Read", "file_edit": "Write"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".claude/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": True,
        "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
    },
    "dispatch": {"tool_name": "Agent", "is_async": False},
    "hooks": {
        "config_format": None,
        "config_path": None,
        "event_map": {},
        "degradation": {},
    },
    "skill_definition": {"needs_deploy": True, "target_dir": ".claude/skills"},
    "command_definition": {"needs_deploy": True, "target_dir": ".claude/commands"},
}

# Source scaffold content, all multi-line so a CRLF translation is observable.
# Written with LF so any CRLF in the *deploy output* is the write path's doing
# — never inherited from a CRLF source through ``shutil.copytree`` (verbatim).
_SCAFFOLD_CONTENT: dict[str, str] = {
    "framework.json": '{"version": "0.1.0", "runtime": {"platform": "claude-code"}}\n',
    "PROJECT-STATE.md": "platform: {platform}\nline two\n",
    "rules/COMMON-RULES.md": "# common\nrule line\n",
    "agents/orchestrator/AGENT.md": (
        "---\nname: orchestrator\ntools: file_read\n---\nbody\nsecond line\n"
    ),
    "hooks/hooks.yaml": "hooks: {}\ndegradation_templates: {}\n",
    "skills/demo-skill/SKILL.md": "---\nname: demo-skill\ndescription: demo\n---\nbody\nmore\n",
    "skills/demo-skill/helper.md": "helper content\nrow two\n",
    "commands/bootstrap.md": "---\ndescription: bootstrap\n---\nbody\nrow\n",
    "platforms/claude-code/profile.yaml": yaml.safe_dump(_CLAUDE_PROFILE),
}


def _write_tree_lf(root: Path, content: dict[str, str]) -> None:
    """Materialise *content* under *root* with LF endings (no text-mode xlat)."""
    for rel, text in content.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(text.encode("utf-8"))


def _deploy_output_files(root: Path) -> list[Path]:
    """Every regular file a claude-code deploy materialises in *root*."""
    files: list[Path] = []
    if (root / "CLAUDE.md").is_file():
        files.append(root / "CLAUDE.md")
    if (root / ".claude").is_dir():
        files.extend(p for p in (root / ".claude").rglob("*") if p.is_file())
    for rel in (".deploy-state", ".deploy-manifest.json", ".instruction-hashes.json"):
        cand = root / ".cataforge" / rel
        if cand.is_file():
            files.append(cand)
    return files


def test_deployed_artefacts_use_lf_newlines(tmp_path: Path, monkeypatch) -> None:
    """No file the deploy writes may contain a CRLF byte sequence.

    The project ``.cataforge/`` and the scaffold self-heal source are both
    pinned to a controlled LF tree, so the deploy never pulls the repo's own
    (possibly CRLF-in-worktree) bundled scaffold — isolating the write path
    as the only thing under test.
    """
    root = tmp_path / "proj"
    _write_tree_lf(root / ".cataforge", _SCAFFOLD_CONTENT)

    fake_scaffold = tmp_path / "_fake_scaffold"
    _write_tree_lf(fake_scaffold, _SCAFFOLD_CONTENT)
    monkeypatch.setattr(scaffold_mod, "_scaffold_root", lambda: fake_scaffold)

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code", force_copy=True)

    produced = _deploy_output_files(root)
    assert produced, "precondition: deploy must materialise at least one artefact"

    crlf = [
        str(p.relative_to(root)).replace("\\", "/") for p in produced if b"\r\n" in p.read_bytes()
    ]
    assert not crlf, (
        "deploy wrote artefacts with CRLF line endings (expected LF):\n  " + "\n  ".join(crlf)
    )


# Deploy/scaffold modules whose artefact writes must route through
# ``atomic_write_text``. A bare ``.write_text(`` here reintroduces the
# Windows CRLF defect even when CI runs on an LF-only platform.
_GUARDED_RELPATHS = (
    "runtime/deploy/steps/agents.py",
    "runtime/deploy/steps/commands_rules.py",
    "runtime/deploy/steps/instructions.py",
    "runtime/deploy/steps/skills.py",
    "adapter/platform/fileops.py",
    "adapter/platform/hooks_config.py",
    "adapter/platform/mcp_config.py",
    "adapter/platform/cursor.py",
    "adapter/platform/opencode.py",
    "adapter/platform/instruction_cache.py",
    "interface/cli/setup_cmd.py",
    "core/scaffold.py",
    "core/scaffold_backup.py",
    "runtime/deploy/deployer.py",
    "runtime/hook/bridge.py",
)

_BARE_WRITE_TEXT = re.compile(r"\.write_text\(")


def test_deploy_scaffold_modules_have_no_bare_write_text() -> None:
    """Static guard: deploy/scaffold artefact writes go through the helper."""
    pkg_root = Path(cataforge.__file__).parent
    offenders: list[str] = []
    for rel in _GUARDED_RELPATHS:
        src = (pkg_root / rel).read_text(encoding="utf-8")
        if _BARE_WRITE_TEXT.search(src):
            offenders.append(rel)
    assert not offenders, (
        "bare `.write_text(` found in deploy/scaffold modules — route the "
        "write through `atomic_write_text` (LF + atomic):\n  " + "\n  ".join(offenders)
    )
