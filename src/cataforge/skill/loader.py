"""Skill discovery and loading."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass, field
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.types import SkillType
from cataforge.utils.frontmatter import split_yaml_frontmatter

# Mapping from builtin directory name → skill ID (directory names use underscores)
_BUILTIN_ID_MAP = {
    "code_review": "code-review",
    "dep_analysis": "dep-analysis",
    "doc_review": "doc-review",
    "sprint_review": "sprint-review",
}


@dataclass
class SkillMeta:
    """Metadata parsed from a SKILL.md frontmatter."""

    id: str
    name: str
    description: str
    skill_type: SkillType
    scripts: list[dict[str, str]] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
    pip_depends: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    user_invocable: bool = True
    path: Path | None = None
    builtin: bool = False


class SkillLoader:
    """Discover and load skill definitions from .cataforge/skills/ and package builtins."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())

    def discover(self) -> list[SkillMeta]:
        """Scan skills directory and builtins, return metadata for all found skills."""
        seen_ids: set[str] = set()
        result: list[SkillMeta] = []
        builtins_by_id = {m.id: m for m in self._scan_builtins()}

        # Project-level skills take precedence
        skills_dir = self._paths.skills_dir
        if skills_dir.is_dir():
            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                meta = self._parse_skill(skill_dir.name, skill_md)
                if meta:
                    meta = self._merge_builtin_fallback(meta, builtins_by_id)
                    seen_ids.add(meta.id)
                    result.append(meta)

        # Built-in skills (only if not overridden at project level)
        for meta in builtins_by_id.values():
            if meta.id not in seen_ids:
                seen_ids.add(meta.id)
                result.append(meta)

        return result

    def get_skill(self, skill_id: str) -> SkillMeta | None:
        """Load a single skill by ID (project-level first, then builtins).

        When a project-level SKILL.md exists but declares no executable
        scripts (i.e. it is a pure playbook overriding a builtin's prose),
        the matching builtin's scripts are merged in so that
        ``cataforge skill run`` remains functional. Without this merge,
        a project-level SKILL.md silently shadows the builtin and the
        runner reports ``no executable scripts``.
        """
        skill_md = self._paths.skill_dir(skill_id) / "SKILL.md"
        if skill_md.is_file():
            meta = self._parse_skill(skill_id, skill_md)
            if meta is not None:
                builtins_by_id = {m.id: m for m in self._scan_builtins()}
                meta = self._merge_builtin_fallback(meta, builtins_by_id)
            return meta
        # Try builtin
        for meta in self._scan_builtins():
            if meta.id == skill_id:
                return meta
        return None

    @staticmethod
    def _merge_builtin_fallback(
        meta: SkillMeta,
        builtins_by_id: dict[str, SkillMeta],
    ) -> SkillMeta:
        """If *meta* has no scripts but a matching builtin does, borrow them.

        The project-level SKILL.md still provides frontmatter (description,
        depends, suggested-tools, user-invocable). Only ``scripts`` and
        ``builtin`` are taken from the builtin — the runner keys off
        ``builtin`` to pick ``python -m`` over a file-path invocation.
        """
        if meta.scripts:
            return meta
        fallback = builtins_by_id.get(meta.id)
        if fallback is None or not fallback.scripts:
            return meta
        meta.scripts = list(fallback.scripts)
        meta.builtin = True
        # Promote skill_type so list output distinguishes it from
        # pure-playbook skills.
        if meta.skill_type == SkillType.INSTRUCTIONAL:
            meta.skill_type = SkillType.HYBRID
        return meta

    def _scan_builtins(self) -> list[SkillMeta]:
        """Discover built-in skills shipped with the cataforge package."""
        result: list[SkillMeta] = []
        try:
            builtins_pkg = importlib.resources.files("cataforge.skill.builtins")
        except (ModuleNotFoundError, TypeError):
            return result

        builtins_dir = Path(str(builtins_pkg))
        if not builtins_dir.is_dir():
            return result

        for child in sorted(builtins_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            skill_id = _BUILTIN_ID_MAP.get(child.name, child.name)
            py_files = sorted(child.glob("*.py"))
            # Only files with an ``if __name__ == "__main__":`` guard are
            # CLI entry points — the rest are helper modules (``checker.py``,
            # ``constants.py``, ``typed_checks.py``, ...). Enumerating every
            # ``.py`` file would make ``cataforge skill run doc-review``
            # default to the alphabetically-first file (a helper), which
            # does nothing when spawned as ``python -m``.
            scripts = [
                {"name": f.stem, "entry": f.name, "module": f"{child.name}.{f.stem}"}
                for f in py_files
                if f.name != "__init__.py" and _has_main_guard(f)
            ]
            if not scripts:
                continue
            result.append(SkillMeta(
                id=skill_id,
                name=skill_id,
                description=f"Built-in {skill_id} skill",
                skill_type=SkillType.HYBRID,
                scripts=scripts,
                builtin=True,
                path=child,
            ))
        return result

    def _parse_skill(self, skill_id: str, skill_md: Path) -> SkillMeta | None:
        """Parse SKILL.md frontmatter to extract metadata."""
        content = skill_md.read_text(encoding="utf-8")
        fm, _body = split_yaml_frontmatter(content)
        if fm is None:
            return SkillMeta(
                id=skill_id,
                name=skill_id,
                description="",
                skill_type=SkillType.INSTRUCTIONAL,
                path=skill_md,
            )

        skill_type_str = fm.get("type", "")
        if skill_type_str:
            try:
                skill_type = SkillType(skill_type_str)
            except ValueError:
                skill_type = SkillType.INSTRUCTIONAL
        else:
            skill_type = self._infer_type(skill_md.parent)

        scripts: list[dict[str, str]] = []
        scripts_dir = skill_md.parent / "scripts"
        if scripts_dir.is_dir():
            for py_file in sorted(scripts_dir.glob("*.py")):
                scripts.append({"name": py_file.stem, "entry": f"scripts/{py_file.name}"})

        return SkillMeta(
            id=skill_id,
            name=fm.get("name", skill_id),
            description=fm.get("description", ""),
            skill_type=skill_type,
            scripts=scripts,
            depends=_to_list(fm.get("depends", [])),
            pip_depends=_to_list(fm.get("pip-depends", [])),
            suggested_tools=_to_list(fm.get("suggested-tools", [])),
            user_invocable=fm.get("user-invocable", True),
            path=skill_md,
        )

    def _infer_type(self, skill_dir: Path) -> SkillType:
        """Infer skill type from directory structure."""
        has_scripts = (skill_dir / "scripts").is_dir()
        if has_scripts:
            return SkillType.HYBRID
        return SkillType.INSTRUCTIONAL


def _has_main_guard(py_file: Path) -> bool:
    """True iff *py_file* contains an ``if __name__ == "__main__":`` guard.

    Read-only textual check so the loader stays import-free — we never
    execute builtin scripts as a side effect of discovery.
    """
    try:
        text = py_file.read_text(encoding="utf-8")
    except OSError:
        return False
    return "__main__" in text and "__name__" in text


def _to_list(val: str | list[str]) -> list[str]:
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val:
        return [v.strip() for v in val.split(",") if v.strip()]
    return []
