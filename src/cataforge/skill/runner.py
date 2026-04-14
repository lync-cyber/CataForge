"""Skill script executor — run executable skills in a controlled environment.

Built-in skills are invoked via ``python -m cataforge.skill.builtins.<pkg>.<script>``.
Project-level skills are invoked via ``python <script_path>``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.skill.loader import SkillLoader, SkillMeta


class SkillRunner:
    """Execute skill scripts with proper environment setup."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._loader = SkillLoader(self._paths.root)

    def run(
        self,
        skill_id: str,
        args: list[str] | None = None,
        script_name: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a skill's script.

        Args:
            skill_id: Skill identifier (e.g. "code-review").
            args: Arguments to pass to the script.
            script_name: Specific script name (if skill has multiple). Defaults to first.

        Returns:
            CompletedProcess result.
        """
        meta = self._loader.get_skill(skill_id)
        if meta is None:
            raise ValueError(f"Skill not found: {skill_id}")

        if not meta.scripts:
            raise ValueError(f"Skill {skill_id} has no executable scripts")

        script_entry = self._find_script(meta, script_name)
        if script_entry is None:
            raise ValueError(
                f"Script {script_name!r} not found in skill {skill_id}. "
                f"Available: {[s['name'] for s in meta.scripts]}"
            )

        env = self._build_env()

        if meta.builtin:
            module_path = f"cataforge.skill.builtins.{script_entry['module']}"
            cmd = [sys.executable, "-m", module_path] + (args or [])
        else:
            script_path = self._paths.skill_dir(skill_id) / script_entry["entry"]
            if not script_path.is_file():
                raise FileNotFoundError(f"Script file not found: {script_path}")
            cmd = [sys.executable, str(script_path)] + (args or [])

        return subprocess.run(
            cmd,
            cwd=str(self._paths.root),
            env=env,
            capture_output=True,
            text=True,
        )

    def _find_script(self, meta: SkillMeta, script_name: str | None) -> dict[str, str] | None:
        if script_name is None:
            return meta.scripts[0] if meta.scripts else None
        for s in meta.scripts:
            if s["name"] == script_name:
                return s
        return None

    def _build_env(self) -> dict[str, str]:
        """Build environment for skill script execution."""
        env = os.environ.copy()
        env["CATAFORGE_PROJECT_ROOT"] = str(self._paths.root)
        return env
