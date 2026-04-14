"""YAML file I/O and Markdown front matter (PyYAML only; see ``frontmatter``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cataforge.utils.frontmatter import split_yaml_frontmatter


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file."""
    with open(path, encoding="utf-8") as f:
        result = yaml.safe_load(f)
        return dict(result) if result else {}


def dump_yaml(data: dict[str, Any], path: Path) -> None:
    """Write data to a YAML file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def parse_yaml_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML front matter from Markdown; empty dict if none or invalid."""
    meta, _body = split_yaml_frontmatter(content)
    if meta is None:
        return {}
    return meta
