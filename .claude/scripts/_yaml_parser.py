#!/usr/bin/env python3
"""CataForge Unified Simple YAML Parser.

Lightweight YAML subset parser for framework internal use, avoiding
the PyYAML dependency. Supports:
- Key-value pairs (key: value)
- Inline lists [a, b, c]
- Block lists (- item)
- Quoted strings (single/double)
- Comments (#)

Used by:
- _common.py / _config.py: template registry parsing (_registry.yaml)
- build_doc_index.py: YAML Front Matter parsing
- doc_check.py: YAML Front Matter parsing

NOT a full YAML parser. For complex YAML, consider PyYAML.
"""

import re
from typing import Any, Dict, List, Optional

YAML_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_yaml_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML Front Matter from Markdown content.

    Extracts the block between the first ``---`` fences and parses it
    as simple YAML key-value pairs.

    Args:
        content: Full Markdown file content.

    Returns:
        Dict of parsed key-value pairs. Empty dict if no front matter found.
    """
    m = YAML_FM_RE.match(content)
    if not m:
        return {}
    return parse_simple_yaml(m.group(1))


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse a simple YAML text block into a dict.

    Supports:
    - ``key: value`` scalar pairs
    - ``key: [a, b, c]`` inline lists
    - Block lists::

        key:
          - item1
          - item2

    - Quoted values (single/double quotes stripped)
    - Comment lines (starting with #)
    - Nested keys are NOT supported (flattened)

    Args:
        text: YAML text (without ``---`` fences).

    Returns:
        Parsed dict.
    """
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[str]] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List continuation: "  - item"
        if stripped.startswith("- ") and current_key and current_list is not None:
            val = _unquote(stripped[2:].strip())
            current_list.append(val)
            result[current_key] = current_list
            continue

        # Key-value line: "key: value"
        colon_idx = stripped.find(":")
        if colon_idx > 0:
            key = stripped[:colon_idx].strip()
            val_part = stripped[colon_idx + 1 :].strip()

            if not val_part:
                # Empty value -- possibly start of a block list
                current_key = key
                current_list = []
                result[key] = current_list
                continue

            current_key = key
            current_list = None

            # Inline list: [a, b, c]
            if val_part.startswith("[") and val_part.endswith("]"):
                items = val_part[1:-1].split(",")
                result[key] = [_unquote(i.strip()) for i in items if i.strip()]
            else:
                result[key] = _unquote(val_part)

    return result


def parse_template_registry(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse the _registry.yaml template registry format.

    This handles the specific two-level indentation structure::

        templates:
          prd:
            path: standard/prd.md
            doc_type: prd
            volumes: [features]

    Args:
        text: Full _registry.yaml content.

    Returns:
        Dict of {template_id: {attribute: value}} entries.
    """
    templates: Dict[str, Dict[str, Any]] = {}
    current_id: Optional[str] = None
    current_dict: Optional[Dict[str, Any]] = None
    current_list_key: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Skip top-level keys
        if stripped in ("templates:", 'version: "1"', "version: '1'"):
            continue

        indent = len(line) - len(line.lstrip())

        # Template ID (indent=2): "  prd:"
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            if current_id and current_dict:
                templates[current_id] = current_dict
            current_id = stripped[:-1].strip()
            current_dict = {}
            current_list_key = None
            continue

        # Attribute (indent=4): "    path: standard/prd.md"
        if indent == 4 and ":" in stripped and current_dict is not None:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = val[1:-1].split(",")
                current_dict[key] = [_unquote(i.strip()) for i in items if i.strip()]
                current_list_key = None
            elif not val:
                current_dict[key] = []
                current_list_key = key
            else:
                current_dict[key] = _unquote(val)
                current_list_key = None
            continue

        # List continuation (indent=4+): "    - item"
        if stripped.startswith("- ") and current_list_key and current_dict is not None:
            current_dict.setdefault(current_list_key, []).append(
                _unquote(stripped[2:].strip())
            )

    if current_id and current_dict:
        templates[current_id] = current_dict

    return templates


def _unquote(s: str) -> str:
    """Strip surrounding single or double quotes from a string."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s
