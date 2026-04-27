"""Guard: every standalone ``scripts/*.py`` reconfigures stdio to UTF-8.

Standalone build/check scripts run outside the ``cataforge`` CLI machinery
(which already calls ``ensure_utf8_stdio()`` in ``cli/main.py``). On
Windows cp1252 terminals these scripts crash with ``UnicodeEncodeError``
when they print arrows / ✓ / Chinese — the v0.1.15 audit caught this in
``sync_scaffold.py`` (since removed by PR #84 along with the scaffold
mirror). This test forces every remaining script to either:

1. Import ``cataforge.utils.common.ensure_utf8_stdio`` and call it, or
2. Inline ``sys.stdout.reconfigure(encoding="utf-8")`` and the same for
   stderr (chicken-and-egg case where cataforge isn't importable yet).

Both forms count as compliance. Any other script must opt in to a
short whitelist below if it provably emits ASCII only.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Scripts permitted to skip the stdio reconfigure because they
# provably emit ASCII only and are never invoked outside CI.
ASCII_ONLY_WHITELIST: frozenset[str] = frozenset({
    "checks/check_no_dev_branch_refs.py",
    "checks/check_doc_versions.py",
    "checks/check_changelog_link_table.py",
    "checks/check_profile_yaml_keys.py",
    "checks/check_hooks_yaml_schema.py",
    "checks/check_schema_python_parity.py",
    "checks/check_skill_count.py",
    "hatch_build.py",
})

CALL_PATTERNS = (
    re.compile(r"\bensure_utf8_stdio\s*\("),
    re.compile(r"sys\.stdout\.reconfigure\s*\(\s*[^)]*encoding\s*=\s*['\"]utf-?8['\"]"),
    re.compile(r"\.reconfigure\s*\(\s*[^)]*encoding\s*=\s*['\"]utf-?8['\"]", re.DOTALL),
)


def test_scripts_reconfigure_stdio_to_utf8() -> None:
    """Every script under scripts/ must reconfigure stdio or be whitelisted."""
    if not SCRIPTS_DIR.is_dir():
        return

    offenders: list[str] = []
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        rel = path.relative_to(SCRIPTS_DIR).as_posix()
        if path.name == "__init__.py":
            continue
        if rel in ASCII_ONLY_WHITELIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            offenders.append(f"{rel}: cannot read ({exc})")
            continue
        if not any(p.search(text) for p in CALL_PATTERNS):
            offenders.append(rel)

    assert not offenders, (
        "These scripts emit text without reconfiguring stdio to UTF-8. "
        "On Windows cp1252 terminals they crash with UnicodeEncodeError. "
        "Either call cataforge.utils.common.ensure_utf8_stdio() at module "
        "top, or inline sys.stdout.reconfigure(encoding='utf-8'). If the "
        "script provably emits ASCII only, add it to ASCII_ONLY_WHITELIST. "
        f"Offenders: {offenders}"
    )
