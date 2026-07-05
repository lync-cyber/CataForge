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
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager

import click

from cataforge.core.retired_assets import retired_skill_dirs

from ._helpers import is_relative_to

_DEPRECATED_REFS: tuple[dict[str, str], ...] = (
    {
        "name": "load_section.py",
        # Word-boundary catches ``load_section.py``, ``load_section.py:``, etc.,
        # but not ``cataforge_load_section_py`` (unlikely but cheap).
        "pattern": r"\bload_section\.py\b",
        "replacement": "`cataforge context read`",
        "since": "v0.1.10",
    },
    {
        "name": "build_doc_index.py",
        "pattern": r"\bbuild_doc_index\.py\b",
        "replacement": "`cataforge context index`",
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
    {
        "name": "cataforge docs load",
        # Anchored on the ``cataforge docs`` prefix so the ``docs/`` path
        # spelling and other ``docs`` subcommands are untouched.
        "pattern": r"\bcataforge\s+docs\s+load\b",
        "replacement": "`cataforge context read`",
        "since": "v0.11.0",
    },
    {
        "name": "cataforge docs index",
        "pattern": r"\bcataforge\s+docs\s+index\b",
        "replacement": "`cataforge context index`",
        "since": "v0.11.0",
    },
    {
        "name": "cataforge docs validate",
        "pattern": r"\bcataforge\s+docs\s+validate\b",
        "replacement": "`cataforge context validate`",
        "since": "v0.11.0",
    },
    {
        "name": "kg trace --output mermaid",
        # `kg trace` keeps table/json analysis output; the mermaid surface
        # moved to `cataforge viz trace`. Matches either argument order on a
        # single line (`kg trace F-001 --output mermaid` / `--output=mermaid`).
        "pattern": r"\bkg\s+trace\b[^\n]*--output[=\s]+mermaid\b",
        "replacement": "`cataforge viz trace`",
        "since": "v0.13.0",
    },
    {
        "name": "task-dep-analysis --format mermaid",
        # task-dep-analysis keeps --format json analysis; the mermaid surface
        # moved to `cataforge viz tasks`. The tempered `(?!viz)` gap binds the
        # `--format mermaid` to task-dep-analysis itself, so prose that names
        # both commands on one line (`task-dep-analysis ... cataforge viz tasks
        # --format mermaid`) is not a false positive.
        "pattern": r"\btask-dep-analysis\b(?:(?!viz).)*--format[=\s]+(?:json\|)?mermaid\b",
        "replacement": "`cataforge viz tasks --format mermaid`",
        "since": "v0.13.0",
    },
)


def _iter_prose_files(
    scan_roots: Iterable[Path], skip_subtrees: Iterable[Path], root: Path
) -> Iterator[tuple[str, str]]:
    """Yield ``(display_path, text)`` for each ``.md``/``.yaml``/``.yml`` prose
    file under ``scan_roots``, skipping ``skip_subtrees`` and unreadable files."""
    suffixes = {".md", ".yaml", ".yml"}
    skip = tuple(skip_subtrees)
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(is_relative_to(path, sub) for sub in skip):
                continue
            try:
                text = path.read_text()
            except OSError:
                continue
            try:
                display = path.relative_to(root).as_posix()
            except ValueError:
                display = str(path)
            yield display, text


def _scan_for_script_refs(
    scan_roots: Iterable[Path],
    skip_subtrees: Iterable[Path],
    root: Path,
    pattern: re.Pattern[str],
) -> dict[str, list[str]]:
    """Collect ``{script_rel: [caller:lineno, ...]}`` from prose files."""
    refs: dict[str, list[str]] = {}
    for display, text in _iter_prose_files(scan_roots, skip_subtrees, root):
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                rel = match.group(1)
                if "*" in rel or "..." in rel:
                    continue
                refs.setdefault(rel, []).append(f"{display}:{lineno}")
    return refs


def _echo_callers(callers: list[str], limit: int = 5) -> None:
    """Echo up to ``limit`` caller sites, folding the rest into a count."""
    shown = callers[:limit]
    for caller in shown:
        click.echo(f"    - {caller}")
    extra = len(callers) - len(shown)
    if extra > 0:
        click.echo(f"    - ... and {extra} more call site(s)")


def check_protocol_script_references(cfg: ConfigManager) -> int:
    """Scan ``.cataforge/`` protocol docs + hooks spec for ``python .cataforge/...``
    invocations and report any that point at a file that does not exist.

    Returns the number of distinct missing scripts (counts toward the
    ``cataforge doctor`` exit code gate).
    """
    pattern = re.compile(r"python\s+(\.cataforge/[^\s`\"'<>|&;]+\.py)")

    root = cfg.paths.root
    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cfg.paths.hooks_dir,
        cfg.paths.commands_dir,
    )
    skip_subtrees = (cfg.paths.hooks_dir / "custom",)

    refs = _scan_for_script_refs(scan_roots, skip_subtrees, root, pattern)

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
        _echo_callers(callers)

    return len(missing)


def _collect_deprecated_findings(
    scan_roots: Iterable[Path],
    skip_subtrees: Iterable[Path],
    root: Path,
    patterns: list[tuple[dict[str, str], re.Pattern[str]]],
) -> dict[str, list[str]]:
    """Collect ``{deprecated_name: [caller:lineno, ...]}`` from prose files."""
    findings: dict[str, list[str]] = {}
    for display, text in _iter_prose_files(scan_roots, skip_subtrees, root):
        for lineno, line in enumerate(text.splitlines(), start=1):
            for entry, pat in patterns:
                if pat.search(line):
                    findings.setdefault(entry["name"], []).append(f"{display}:{lineno}")
    return findings


def _report_deprecated_findings(findings: dict[str, list[str]]) -> None:
    click.echo(
        f"  {len(findings)} deprecated reference(s) found "
        f"({len(_DEPRECATED_REFS)} patterns scanned)"
    )
    by_name = {entry["name"]: entry for entry in _DEPRECATED_REFS}
    for name in sorted(findings):
        entry = by_name[name]
        click.echo(f"  FAIL {name} → use {entry['replacement']} (deprecated {entry['since']})")
        _echo_callers(sorted(set(findings[name])))


def check_deprecated_references(cfg: ConfigManager) -> int:
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

    # Retired skill source dirs are stale upgrade leftovers (see
    # ``check_retired_skill_assets``); their old CLI calls are real but the fix
    # is "remove the dir", not "edit the prose". Skip them here so a leftover
    # surfaces only as the actionable retired-asset WARN, not a misleading FAIL.
    skip_subtrees = (
        cfg.paths.hooks_dir / "custom",
        root / ".cataforge" / ".archive",
        *retired_skill_dirs(cfg.paths.skills_dir),
    )

    patterns = [(entry, re.compile(entry["pattern"])) for entry in _DEPRECATED_REFS]
    findings = _collect_deprecated_findings(scan_roots, skip_subtrees, root, patterns)

    if not findings:
        click.echo(f"  0 deprecated references found ({len(_DEPRECATED_REFS)} patterns scanned)")
        return 0
    _report_deprecated_findings(findings)
    return len(findings)


# Markdown inline link: ``[text](target)``. Reference-style and image links
# are out of scope — prompt assets use inline links for cross-references.
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _deployable_md_files(
    scan_roots: Iterable[Path],
    skip_subtrees: Iterable[Path],
) -> Iterator[Path]:
    """Yield deployable ``.md`` files under *scan_roots*.

    ``templates/`` is excluded: a template's links resolve against the
    generated ``docs/`` tree it produces, not against ``.cataforge/``.
    """
    skips = tuple(skip_subtrees)
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if not path.is_file():
                continue
            if "templates" in path.parts:
                continue
            if any(is_relative_to(path, sub) for sub in skips):
                continue
            yield path


def _unresolved_link_key(target: str, base_dir: Path, cataforge_root: Path) -> str | None:
    """Classify one markdown link target.

    Returns a violation label when the target escapes ``cataforge_root`` (not
    deployed downstream) or is missing; ``None`` when it resolves cleanly or is
    not a deploy-relevant file link (external URL, anchor, glob/placeholder).
    """
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return None
    target_path = target.split("#", 1)[0].split(" ", 1)[0].strip()
    if not target_path or any(c in target_path for c in "*<>{"):
        return None
    if not Path(target_path).suffix:
        return None
    resolved = (base_dir / target_path).resolve()
    if not is_relative_to(resolved, cataforge_root):
        return f"{target_path} (escapes .cataforge/ — not deployed downstream)"
    if not resolved.exists():
        return f"{target_path} (target missing)"
    return None


def check_markdown_link_resolution(cfg: ConfigManager) -> int:
    """Scan deployable ``.cataforge/`` prompt assets for markdown links whose
    relative target resolves *outside* the ``.cataforge/`` tree or to a missing
    file.

    ``cataforge deploy`` materializes only ``.cataforge/**`` into a downstream
    project; ``docs/`` is never copied. A SKILL/AGENT link to repo-root
    ``docs/reference/...`` therefore resolves to a path that does not exist
    downstream — the agent follows a dead link. This gate keeps the
    deployable-asset boundary closed: every link an agent can follow must land
    on a file that ships with it.

    Returns the number of distinct unresolvable targets (gates the exit code).
    """
    root = cfg.paths.root
    # Unresolved for scan/skip (shares the rglob path prefix); resolved only for
    # the link-boundary check, where the target's ``../`` must be normalized.
    cataforge_root = root / ".cataforge"
    cataforge_root_resolved = cataforge_root.resolve()
    # Prompt-asset surfaces whose links an agent follows from the asset's own
    # deployed location.
    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cataforge_root / "references",
        cataforge_root / "platforms",
    )
    # Top-level ``overrides/`` and ``.archive/`` never deploy; retired skill
    # dirs are stale upgrade leftovers (surfaced by the retired-asset scan).
    skip_subtrees = (
        cataforge_root / "overrides",
        cataforge_root / ".archive",
        *retired_skill_dirs(cfg.paths.skills_dir),
    )

    violations: dict[str, list[str]] = {}
    for path in _deployable_md_files(scan_roots, skip_subtrees):
        try:
            text = path.read_text()
        except OSError:
            continue
        try:
            display = path.relative_to(root).as_posix()
        except ValueError:
            display = str(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _MD_LINK.finditer(line):
                key = _unresolved_link_key(
                    match.group(1).strip(), path.parent, cataforge_root_resolved
                )
                if key is not None:
                    violations.setdefault(key, []).append(f"{display}:{lineno}")

    if not violations:
        click.echo("  (all .cataforge/ markdown links resolve within the deployed tree)")
        return 0

    click.echo(f"  {len(violations)} unresolvable markdown link target(s):")
    for key in sorted(violations):
        callers = sorted(set(violations[key]))
        click.echo(f"  FAIL {key}")
        for caller in callers[:5]:
            click.echo(f"    - {caller}")
        extra = len(callers) - 5
        if extra > 0:
            click.echo(f"    - ... and {extra} more call site(s)")

    return len(violations)
