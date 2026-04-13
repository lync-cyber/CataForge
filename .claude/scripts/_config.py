#!/usr/bin/env python3
"""CataForge Framework Configuration Module.

Extracted from _common.py for single-responsibility:
- framework.json reading and constants
- Template registry (_registry.yaml) loading and mapping
- JSON utilities
"""

import json
import os
import re
from typing import Any, Dict, Optional

from _yaml_parser import parse_template_registry


def _find_project_root_for_config() -> str:
    """Locate project root from this file's position (scripts/ -> .claude/ -> root)."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(2):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


# ============================================================================
# JSON Utilities
# ============================================================================


def load_json_lenient(file_path: str) -> dict:
    """Load a JSON file, tolerating trailing commas and minor format issues."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)


# ============================================================================
# Framework Configuration (framework.json)
# ============================================================================


def load_framework_config(project_root: Optional[str] = None) -> dict:
    """Read .claude/framework.json unified framework configuration.

    Args:
        project_root: Project root directory. Defaults to CWD (matching
                      the original behavior where callers chdir to project root).
    """
    if project_root is None:
        project_root = "."
    config_path = os.path.join(project_root, ".claude", "framework.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_framework_constants(project_root: Optional[str] = None) -> dict:
    """Load the constants section from framework.json.

    Returns:
        {constant_name: value} dict. Empty dict if not found.
    """
    config = load_framework_config(project_root)
    return config.get("constants", {})


def get_constant(name: str, default=None, project_root: Optional[str] = None):
    """Get a single framework constant by name, with fallback default."""
    return load_framework_constants(project_root).get(name, default)


# ============================================================================
# Template Registry (_registry.yaml)
# ============================================================================

_REGISTRY_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_REGISTRY_MTIME: float = 0.0

REGISTRY_FILE = os.path.join(
    ".claude", "skills", "doc-gen", "templates", "_registry.yaml"
)


def load_template_registry(
    project_root: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load .claude/skills/doc-gen/templates/_registry.yaml template registry.

    Returns {template_id: {path, doc_type, mode, role, ...}} dict.
    Result is cached per-process with mtime-based invalidation.
    """
    global _REGISTRY_CACHE, _REGISTRY_MTIME
    if project_root is None:
        project_root = _find_project_root_for_config()

    reg_path = os.path.join(project_root, REGISTRY_FILE)
    if not os.path.isfile(reg_path):
        return {}

    # Invalidate cache if file changed
    try:
        current_mtime = os.path.getmtime(reg_path)
    except OSError:
        current_mtime = 0.0

    if _REGISTRY_CACHE is not None and current_mtime == _REGISTRY_MTIME:
        return _REGISTRY_CACHE

    with open(reg_path, "r", encoding="utf-8") as f:
        content = f.read()

    _REGISTRY_CACHE = parse_template_registry(content)
    _REGISTRY_MTIME = current_mtime
    return _REGISTRY_CACHE


def build_doc_type_map(project_root: Optional[str] = None) -> Dict[str, str]:
    """Build doc_id -> doc_type mapping from the template registry."""
    registry = load_template_registry(project_root)
    result: Dict[str, str] = {}
    for template_id, meta in registry.items():
        doc_type = meta.get("doc_type", "")
        if doc_type:
            result[template_id] = doc_type
    return result


def build_template_path_map(
    project_root: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """Build doc_type -> {volume_type -> relative_path} mapping from registry.

    Returned paths are relative to the templates/ directory.
    """
    registry = load_template_registry(project_root)
    result: Dict[str, Dict[str, str]] = {}
    for template_id, meta in registry.items():
        doc_type = meta.get("doc_type", "")
        role = meta.get("role", "main")
        path = meta.get("path", "")
        if not doc_type or not path:
            continue
        if doc_type not in result:
            result[doc_type] = {}
        if role == "volume":
            vol_type = meta.get("volume_type", "")
            if vol_type:
                result[doc_type][vol_type] = path
        else:
            result[doc_type]["main"] = path
    return result
