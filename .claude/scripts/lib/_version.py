#!/usr/bin/env python3
"""CataForge Version and Phase Management Module.

Extracted from _common.py for single-responsibility:
- Semantic version parsing
- Version file reading (pyproject.toml)
- Project phase ordering and lookup
- Branch name validation
"""

import os
import re
import warnings

# ============================================================================
# Version Parsing
# ============================================================================

VERSION_FILE = "pyproject.toml"


def parse_semver(ver_str: str) -> tuple:
    """Parse a semver string into (major, minor, patch) tuple.

    Supports optional 'v' prefix (e.g., "v1.2.3" or "1.2.3").
    Returns (0, 0, 0) if parsing fails.
    """
    ver_str = ver_str.strip()
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", ver_str)
    if not match:
        warnings.warn(f"parse_semver: 无法解析版本号 '{ver_str}'，回退到 (0,0,0)")
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_version(base_path: str) -> str:
    """Read [project].version from pyproject.toml in the given directory."""
    ver_file = os.path.join(base_path, VERSION_FILE)
    if not os.path.exists(ver_file):
        return "0.0.0"
    with open(ver_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


# ============================================================================
# Phase Management
# ============================================================================

PHASE_ORDER = [
    "requirements",
    "architecture",
    "ui_design",
    "dev_planning",
    "development",
    "testing",
    "deployment",
    "completed",
]


def phase_index(phase: str) -> int:
    """Return the index of a phase in the lifecycle. -1 for unknown phases."""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


# ============================================================================
# Input Validation
# ============================================================================


def validate_branch_name(branch: str) -> bool:
    """Validate a git branch name to prevent injection of special characters."""
    return bool(re.match(r"^[a-zA-Z0-9._/-]+$", branch))
