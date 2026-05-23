"""Tests for deploy_skills per-skill linking + maintainer-only filtering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cataforge.platform.base import PlatformAdapter


class _MinimalAdapter(PlatformAdapter):
    """Test adapter exercising default deploy_skills."""

    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__(profile)

    @property
    def platform_id(self) -> str:
        return "test"

    @property
    def display_name(self) -> str:
        return "Test"

    def get_tool_map(self) -> dict[str, str | None]:
        return {}

    def get_project_root_env_var(self) -> str | None:
        return None

    def get_agent_scan_dirs(self) -> list[str]:
        return []

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def inject_mcp_config(self, server_id, server_config, project_root, *, dry_run=False):
        return []


@pytest.fixture()
def adapter() -> _MinimalAdapter:
    return _MinimalAdapter(
        {
            "skill_definition": {
                "needs_deploy": True,
                "target_dir": ".test/skills",
            }
        }
    )


def _write_skill(
    skills_dir: Path,
    name: str,
    *,
    maintainer_only: bool = False,
) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        "---",
        f"name: {name}",
        "description: test",
        "disable-model-invocation: false",
        "user-invocable: true",
    ]
    if maintainer_only:
        fm_lines.append("maintainer-only: true")
    fm_lines += ["---", "", f"# {name}", ""]
    (skill_dir / "SKILL.md").write_text("\n".join(fm_lines), encoding="utf-8")


def test_default_skips_maintainer_only_skill(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "normal-skill")
    _write_skill(source, "maintainer-only-skill", maintainer_only=True)

    actions = adapter.deploy_skills(source, tmp_path)

    target = tmp_path / ".test" / "skills"
    assert (target / "normal-skill" / "SKILL.md").is_file()
    assert not (target / "maintainer-only-skill").exists()
    assert any(
        "SKIP" in a and "maintainer-only-skill" in a and "maintainer-only" in a
        for a in actions
    )


def test_include_maintainer_only_links_everything(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "normal-skill")
    _write_skill(source, "maintainer-only-skill", maintainer_only=True)

    adapter.deploy_skills(source, tmp_path, include_maintainer_only=True)

    target = tmp_path / ".test" / "skills"
    assert (target / "normal-skill" / "SKILL.md").is_file()
    assert (target / "maintainer-only-skill" / "SKILL.md").is_file()


def test_dirs_without_skill_md_are_silently_ignored(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "good-skill")
    # Directory without SKILL.md — shouldn't show up downstream.
    (source / "drafts").mkdir(parents=True)
    (source / "drafts" / "notes.md").write_text("wip\n", encoding="utf-8")

    adapter.deploy_skills(source, tmp_path)

    target = tmp_path / ".test" / "skills"
    assert (target / "good-skill" / "SKILL.md").is_file()
    assert not (target / "drafts").exists()


def test_prunes_orphan_per_skill_entries(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "kept-skill")

    # Pre-seed an orphan skill dir that would have been deployed by a
    # previous `cataforge deploy` then deleted upstream.
    target = tmp_path / ".test" / "skills"
    orphan = target / "removed-skill"
    orphan.mkdir(parents=True)
    (orphan / "SKILL.md").write_text(
        "---\nname: removed-skill\n---\nstale\n", encoding="utf-8"
    )

    actions = adapter.deploy_skills(source, tmp_path)
    assert (target / "kept-skill" / "SKILL.md").is_file()
    assert not orphan.exists()
    assert any("pruned orphan" in a and "removed-skill" in a for a in actions)


def test_unwraps_legacy_whole_dir_link(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    """A whole-directory symlink left over from the pre-filter deploy gets
    torn down so per-skill linking can take over on the next run.
    """
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "alpha")

    target_parent = tmp_path / ".test"
    target_parent.mkdir(parents=True)
    target = target_parent / "skills"

    # Create a whole-dir symlink, mimicking the legacy deploy result.
    # Skip on Windows when symlinks are unavailable to the test process.
    try:
        target.symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported in this environment")

    assert target.is_symlink()

    actions = adapter.deploy_skills(source, tmp_path)

    # Symlink must be gone; in its place a real dir with a per-skill symlink.
    assert not target.is_symlink()
    assert target.is_dir()
    assert (target / "alpha" / "SKILL.md").is_file()
    assert any("unwrapped whole-dir link" in a for a in actions)


def test_dry_run_emits_actions_without_writing(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "skills"
    _write_skill(source, "normal")
    _write_skill(source, "internal", maintainer_only=True)

    actions = adapter.deploy_skills(source, tmp_path, dry_run=True)
    target = tmp_path / ".test" / "skills"

    # Nothing should have been written.
    assert not target.exists() or not any(target.iterdir())
    # SKIP for maintainer-only still reported.
    assert any("SKIP" in a and "internal" in a for a in actions)
    # Normal skill scheduled.
    assert any("would link" in a and "normal" in a for a in actions)


def test_maintainer_only_phrase_in_body_does_not_trigger_skip(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    """Only the frontmatter directive counts; mentioning the phrase in the
    body (e.g. ``maintainer-only`` discussed in prose) must not flip the
    skill off.
    """
    source = tmp_path / ".cataforge" / "skills"
    skill_dir = source / "documented"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: documented\n"
        "description: test\n"
        "---\n"
        "\n"
        "This skill talks about `maintainer-only: true` as an example "
        "elsewhere, but is itself a regular shipping skill.\n",
        encoding="utf-8",
    )

    adapter.deploy_skills(source, tmp_path)

    target = tmp_path / ".test" / "skills"
    assert (target / "documented" / "SKILL.md").is_file()
