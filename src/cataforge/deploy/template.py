"""Template override rendering engine.

Implements the base + platform override strategy:
1. Read base template (with OVERRIDE markers)
2. Read platform override file (if exists)
3. Replace marked sections with override content
"""

from __future__ import annotations

import re
from pathlib import Path

_OVERRIDE_PATTERN = re.compile(
    r"<!-- OVERRIDE:(\w+) -->\n(.*?)<!-- /OVERRIDE:\1 -->",
    re.DOTALL,
)


def render_template(
    template_rel_path: str,
    platform_id: str,
    cataforge_dir: Path,
) -> str:
    """Render a template with platform overrides applied.

    Args:
        template_rel_path: Path relative to .cataforge/
            (e.g. "skills/agent-dispatch/templates/dispatch-prompt.md")
        platform_id: Target platform ID.
        cataforge_dir: Absolute path to .cataforge/.

    Returns:
        Merged template text.
    """
    base_path = cataforge_dir / template_rel_path
    base_content = base_path.read_text(encoding="utf-8")

    override_path = (
        cataforge_dir / "platforms" / platform_id / "overrides" / Path(template_rel_path).name
    )

    if not override_path.is_file():
        return _strip_override_markers(base_content)

    override_content = override_path.read_text(encoding="utf-8")
    overrides = _parse_overrides(override_content)

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in overrides:
            return overrides[name]
        return match.group(2)

    return _OVERRIDE_PATTERN.sub(replacer, base_content)


def list_override_points(template_rel_path: str, cataforge_dir: Path) -> list[str]:
    """List all OVERRIDE marker names in a template."""
    base_path = cataforge_dir / template_rel_path
    content = base_path.read_text(encoding="utf-8")
    return [m.group(1) for m in _OVERRIDE_PATTERN.finditer(content)]


def _parse_overrides(content: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _OVERRIDE_PATTERN.finditer(content)}


def _strip_override_markers(content: str) -> str:
    return _OVERRIDE_PATTERN.sub(r"\2", content)
