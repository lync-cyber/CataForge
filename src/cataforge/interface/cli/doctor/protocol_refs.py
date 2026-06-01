"""Protocol-script reachability + deprecated-reference scans.

Two scans over ``.cataforge/`` markdown/YAML prose:

* :func:`check_protocol_script_references` — every ``python .cataforge/...``
  invocation must point at a file that exists. Silent runtime failures
  surface here instead of waiting for the hook error log.
* :func:`check_deprecated_references` — pattern-match against
  :data:`_DEPRECATED_REFS` (the registry of retired scripts / CLI subcommands
  / artifacts) so new prose can't introduce them.
"""

from __future__ import annotations

import re

import click

from ._helpers import is_relative_to

_DEPRECATED_REFS: tuple[dict[str, str], ...] = (
    {
        "name": "load_section.py",
        # Word-boundary catches ``load_section.py``, ``load_section.py:``, etc.,
        # but not ``cataforge_load_section_py`` (unlikely but cheap).
        "pattern": r"\bload_section\.py\b",
        "replacement": "`cataforge docs load`",
        "since": "v0.1.10",
    },
    {
        "name": "build_doc_index.py",
        "pattern": r"\bbuild_doc_index\.py\b",
        "replacement": "`cataforge docs index`",
        "since": "v0.1.10",
    },
    {
        "name": "docs/NAV-INDEX.md",
        # Tolerate archive paths (``.cataforge/.archive/...``).
        "pattern": r"(?<![\w./-])docs/NAV-INDEX\.md\b",
        "replacement": "`docs/.doc-index.json` (run `cataforge docs migrate-nav`)",
        "since": "v0.1.13",
    },
    {
        "name": "docs/.nav/",
        "pattern": r"\bdocs/\.nav/",
        "replacement": "`docs/.doc-index.json`",
        "since": "v0.1.13",
    },
    {
        "name": "python .cataforge/scripts/framework/event_logger.py",
        # The relative-path invocation breaks when an agent runs from a
        # monorepo subdirectory (cwd != project root).
        "pattern": r"python\s+\.cataforge/scripts/framework/event_logger\.py",
        "replacement": "`cataforge event log` (CLI walks up to find .cataforge/)",
        "since": "v0.1.14",
    },
)


def check_protocol_script_references(cfg) -> int:
    """Scan ``.cataforge/`` protocol docs + hooks spec for ``python .cataforge/...``
    invocations and report any that point at a file that does not exist.

    Returns the number of distinct missing scripts (counts toward the
    ``cataforge doctor`` exit code gate).
    """
    pattern = re.compile(
        r"python\s+(\.cataforge/[^\s`\"'<>|&;]+\.py)"
    )

    root = cfg.paths.root
    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cfg.paths.hooks_dir,
        cfg.paths.commands_dir,
    )

    # Subtrees that legitimately reference example/placeholder paths in
    # tutorial prose (``.cataforge/hooks/custom/`` is user-extension
    # territory; its README walks readers through naming a hook script
    # that doesn't exist yet).
    skip_subtrees = (
        cfg.paths.hooks_dir / "custom",
    )

    suffixes = {".md", ".yaml", ".yml"}
    refs: dict[str, list[str]] = {}
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(is_relative_to(path, sub) for sub in skip_subtrees):
                continue
            try:
                text = path.read_text()
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in pattern.finditer(line):
                    rel = match.group(1)
                    # Documentation placeholders, not real invocations:
                    # ``*`` is a glob wildcard, ``...`` is an ellipsis.
                    if "*" in rel or "..." in rel:
                        continue
                    try:
                        display = path.relative_to(root).as_posix()
                    except ValueError:
                        display = str(path)
                    refs.setdefault(rel, []).append(f"{display}:{lineno}")

    if not refs:
        click.echo("  (no protocol script references found)")
        return 0

    missing: list[tuple[str, list[str]]] = []
    for rel in sorted(refs):
        if not (root / rel).is_file():
            missing.append((rel, sorted(set(refs[rel]))))

    present_count = len(refs) - len(missing)
    parts = [f"{present_count}/{len(refs)} scripts present"]
    if missing:
        parts.append(f"{len(missing)} missing")
    click.echo("  " + ", ".join(parts))

    for rel, callers in missing:
        click.echo(f"  FAIL {rel} (referenced by):")
        shown = callers[:5]
        for caller in shown:
            click.echo(f"    - {caller}")
        extra = len(callers) - len(shown)
        if extra > 0:
            click.echo(f"    - ... and {extra} more call site(s)")

    return len(missing)


def check_deprecated_references(cfg) -> int:
    """Scan agent/skill/rules/hook prose for deprecated script names + artifacts.

    Returns the number of distinct deprecated references found.
    """
    root = cfg.paths.root
    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cfg.paths.hooks_dir,
        cfg.paths.commands_dir,
    )

    skip_subtrees = (
        cfg.paths.hooks_dir / "custom",
        root / ".cataforge" / ".archive",
    )

    patterns = [
        (entry, re.compile(entry["pattern"]))
        for entry in _DEPRECATED_REFS
    ]

    suffixes = {".md", ".yaml", ".yml"}
    findings: dict[str, list[str]] = {}

    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(is_relative_to(path, sub) for sub in skip_subtrees):
                continue
            try:
                text = path.read_text()
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for entry, pat in patterns:
                    if pat.search(line):
                        try:
                            display = path.relative_to(root).as_posix()
                        except ValueError:
                            display = str(path)
                        findings.setdefault(entry["name"], []).append(
                            f"{display}:{lineno}"
                        )

    if not findings:
        click.echo(f"  0 deprecated references found ({len(_DEPRECATED_REFS)} patterns scanned)")
        return 0

    click.echo(
        f"  {len(findings)} deprecated reference(s) found "
        f"({len(_DEPRECATED_REFS)} patterns scanned)"
    )
    by_name = {entry["name"]: entry for entry in _DEPRECATED_REFS}
    for name in sorted(findings):
        entry = by_name[name]
        callers = sorted(set(findings[name]))
        click.echo(
            f"  FAIL {name} → use {entry['replacement']} (deprecated {entry['since']})"
        )
        shown = callers[:5]
        for caller in shown:
            click.echo(f"    - {caller}")
        extra = len(callers) - len(shown)
        if extra > 0:
            click.echo(f"    - ... and {extra} more call site(s)")

    return len(findings)
