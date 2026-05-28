"""End-to-end regression for portable skill links + doctor as a real gate.

Two coupled bugs are pinned here:

1. ``cataforge bootstrap`` on Windows materialised ``.claude/skills/*`` as
   NTFS junctions that store *absolute* paths in their reparse data.
   Moving / renaming the project directory broke every link silently —
   bad for multi-developer projects and devcontainer setups.

2. ``cataforge doctor`` exited 0 even when the directories it listed as
   ``[absent]`` truly were absent — so the broken-link state above was
   undetectable from the verification gate.

These tests exercise the *real* wheel-install path via the
session-scoped ``cataforge_venv`` fixture in ``tests/e2e/conftest.py``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.e2e.conftest import run_cataforge

pytestmark = pytest.mark.slow


@pytest.fixture
def bootstrapped_project(tmp_path: Path, cataforge_venv: Path) -> Path:
    """Fresh project bootstrapped to claude-code, doctor skipped (we want
    a clean fixture; tests opt in to doctor themselves)."""
    project = tmp_path / "proj"
    project.mkdir()
    run_cataforge(
        cataforge_venv,
        "bootstrap",
        "--platform",
        "claude-code",
        "--yes",
        "--skip-doctor",
        cwd=project,
    )
    return project


class TestPortableSkillLinks:
    def test_deployed_skill_links_avoid_absolute_paths_when_possible(
        self, bootstrapped_project: Path
    ) -> None:
        """Every deployed skill must be either (a) a relative symlink,
        (b) a junction (only on Windows without Developer Mode), or
        (c) a copy. Copy is the default now (deploy renders runtime
        placeholders into SKILL.md, which requires an independent copy);
        the assertion below only fires when the deploy *did* produce a
        symlink — in which case the stored target must still be relative."""
        skills_dir = bootstrapped_project / ".claude" / "skills"
        assert skills_dir.is_dir(), (
            "bootstrap did not materialise .claude/skills/ — deploy regression."
        )
        children = list(skills_dir.iterdir())
        assert children, "no skills deployed — scaffold mismatch?"

        for child in children:
            if not child.is_symlink():
                # Copy or junction — both legitimate post-J deploy outcomes.
                continue
            stored = os.readlink(str(child))
            assert not os.path.isabs(stored), (
                f"{child} stores absolute target {stored!r}; "
                "any symlink path must be relative for project-rename portability."
            )

    def test_deployed_skills_survive_project_rename(
        self, bootstrapped_project: Path, tmp_path: Path
    ) -> None:
        """Move the project to a sibling directory; deployed skill content
        must still be reachable through the link.

        The pre-fix Windows-junction layout fails this because junctions
        store absolute paths in the NTFS reparse point. Relative symlinks
        (Unix and Windows-with-DevMode) and copy-fallback both survive.

        Windows-without-DevMode legitimately falls back to a junction —
        Windows refuses to issue symlinks to unprivileged processes — so
        we skip there. The skip is itself a documented contract: users on
        such a host get a WARN at deploy time pointing them at Developer
        Mode, and ``doctor`` will FAIL post-rename via the deploy-integrity
        check covered by :class:`TestDoctorIsIntegrityGate`.
        """
        skills_dir = bootstrapped_project / ".claude" / "skills"
        sample = next(skills_dir.iterdir(), None)
        if sample is not None and os.name == "nt" and not sample.is_symlink():
            # Junction or copy. Junction is the only one that fails this
            # invariant; copy survives but we can't easily distinguish here.
            # When we can't tell, skip rather than encode platform-specific
            # detection logic that masks real regressions on other hosts.
            pytest.skip(
                "Windows without Developer Mode falls back to junctions — "
                "rename portability is not achievable without symlink privilege."
            )

        moved = tmp_path / "proj-renamed"
        bootstrapped_project.rename(moved)

        skills_dir = moved / ".claude" / "skills"
        assert skills_dir.is_dir(), skills_dir

        # Pick any deployed skill and verify SKILL.md is reachable through it.
        reachable: list[Path] = []
        for child in skills_dir.iterdir():
            skill_md = child / "SKILL.md"
            if skill_md.is_file():
                reachable.append(skill_md)

        assert reachable, (
            f"no SKILL.md reachable under {skills_dir} after rename — "
            "links stored absolute paths and now dangle. This is the "
            "multi-developer / devcontainer portability bug."
        )


class TestDoctorIsIntegrityGate:
    def test_doctor_fails_when_claude_skills_missing(
        self, bootstrapped_project: Path, cataforge_venv: Path
    ) -> None:
        """Delete the deployed skills dir; doctor must exit non-zero."""
        shutil.rmtree(bootstrapped_project / ".claude" / "skills")

        result = run_cataforge(cataforge_venv, "doctor", cwd=bootstrapped_project, check=False)
        assert result.returncode != 0, result.stdout + result.stderr
        out = result.stdout
        assert ".claude/skills" in out, out
        # Remediation hint: tell the user how to fix it.
        assert "cataforge deploy" in out, out

    def test_doctor_passes_on_freshly_bootstrapped_project(
        self, bootstrapped_project: Path, cataforge_venv: Path
    ) -> None:
        """Sanity check: a green project must remain green after we tighten
        the gate — otherwise we have just broken every existing user."""
        result = run_cataforge(cataforge_venv, "doctor", cwd=bootstrapped_project, check=False)
        assert result.returncode == 0, (
            f"doctor failed on a freshly bootstrapped project:\n{result.stdout}\n{result.stderr}"
        )
        # The Summary line is part of the contract — tests in
        # tests/cli/test_doctor_deploy_integrity.py guard its shape; here
        # we only assert it is present so the UX regression is caught even
        # on the real wheel path.
        assert "Summary:" in result.stdout, result.stdout
