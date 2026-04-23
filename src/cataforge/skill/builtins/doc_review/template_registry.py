"""Doc-gen template registry and required-section loading."""

from __future__ import annotations

import contextlib
import importlib.resources
import json
import re
from pathlib import Path

from cataforge.utils.yaml_parser import load_yaml

__all__ = [
    "load_template_required_sections",
    "build_template_path_map",
]


def build_template_path_map() -> dict[str, dict[str, dict[str, str]]]:
    """Build doc_type → mode → {volume_type → template_filename} from _registry.yaml.

    Volumes (role=volume) always attach to their parent mode (from split_from's
    template entry). Utility entries declaring mode=any register under
    ``"standard"`` and also get fallback lookups from any other mode.
    """
    try:
        registry_dir = Path(
            importlib.resources.files("cataforge").joinpath(
                "..", "..", "..", ".cataforge", "skills", "doc-gen", "templates"
            )
        ).resolve()
    except Exception:
        registry_dir = None

    if registry_dir is None or not (registry_dir / "_registry.yaml").is_file():
        from cataforge.core.paths import find_project_root

        registry_dir = find_project_root() / ".cataforge" / "skills" / "doc-gen" / "templates"

    registry_path = registry_dir / "_registry.yaml"
    if not registry_path.is_file():
        return {}

    registry = load_yaml(registry_path)
    templates = registry.get("templates", {})
    result: dict[str, dict[str, dict[str, str]]] = {}

    def _normalize_mode(mode: str) -> str:
        return "standard" if mode in ("", "any") else mode

    # Map template id → mode for resolving volumes' parent mode
    tpl_mode: dict[str, str] = {}
    for tpl_id, tpl in templates.items():
        if isinstance(tpl, dict):
            tpl_mode[tpl_id] = _normalize_mode(tpl.get("mode", "standard"))

    for _tpl_id, tpl in templates.items():
        if not isinstance(tpl, dict):
            continue
        doc_type = tpl.get("doc_type", "")
        path = tpl.get("path", "")
        role = tpl.get("role", "main")
        if not doc_type or not path:
            continue
        if role == "main":
            mode = _normalize_mode(tpl.get("mode", "standard"))
            result.setdefault(doc_type, {}).setdefault(mode, {})["main"] = path
        elif role == "volume":
            vt = tpl.get("volume_type", "")
            if not vt:
                continue
            parent_id = tpl.get("split_from", "")
            mode = tpl_mode.get(parent_id) or _normalize_mode(tpl.get("mode", "standard"))
            result.setdefault(doc_type, {}).setdefault(mode, {})[vt] = path
    return result


_templates_dir: Path | None = None
_template_map: dict[str, dict[str, dict[str, str]]] | None = None


def _get_templates_dir() -> Path:
    global _templates_dir
    if _templates_dir is not None:
        return _templates_dir
    from cataforge.core.paths import find_project_root

    _templates_dir = find_project_root() / ".cataforge" / "skills" / "doc-gen" / "templates"
    return _templates_dir


def _get_template_map() -> dict[str, dict[str, dict[str, str]]]:
    global _template_map
    if _template_map is None:
        _template_map = build_template_path_map()
    return _template_map


def _parse_required_sections(headings: list[str]) -> list[tuple[str, str]]:
    result = []
    for h in headings:
        m = re.match(r"##\s+(?:\d+\.\s*)?(.+)", h)
        name = m.group(1).strip() if m else h.replace("## ", "").strip()
        result.append((h, name))
    return result


def load_template_required_sections(
    doc_type: str, volume_type: str, mode: str = "standard"
) -> list[tuple[str, str]] | None:
    mode_map = _get_template_map().get(doc_type)
    if not mode_map:
        return None
    mode_key = mode if mode in mode_map else (
        "standard" if "standard" in mode_map else next(iter(mode_map), "")
    )
    type_map = mode_map.get(mode_key) or {}
    filename = type_map.get(volume_type)
    if not filename and mode_key != "standard" and "standard" in mode_map:
        filename = mode_map["standard"].get(volume_type)
    if not filename:
        return None
    template_path = _get_templates_dir() / filename
    try:
        content = template_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    fm_text = fm_match.group(1)
    headings: list[str] = []
    in_required_sections = False
    for line in fm_text.splitlines():
        if re.match(r"^required_sections\s*:", line):
            in_required_sections = True
            inline = re.search(r":\s*(\[.*\])", line)
            if inline:
                with contextlib.suppress(json.JSONDecodeError):
                    headings = json.loads(inline.group(1))
                break
            continue
        if in_required_sections:
            list_item = re.match(r'^\s+-\s+"(.*)"', line) or re.match(
                r"^\s+-\s+'(.*)'", line
            )
            if list_item:
                headings.append(list_item.group(1))
            elif re.match(r"^\s+-\s+", line):
                val = re.match(r"^\s+-\s+(.*)", line)
                if val:
                    headings.append(val.group(1).strip())
            else:
                break
    if not headings:
        return None
    return _parse_required_sections(headings)
