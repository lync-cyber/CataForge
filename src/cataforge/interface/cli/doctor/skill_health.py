"""Built-in skill reachability + docs validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_builtin_skill_reachability(cfg: ConfigManager) -> int:
    """Verify every built-in skill is reachable via ``cataforge skill run``.

    Built-in skills ship Python entry points under
    ``cataforge.runtime.skill.builtins.<pkg>``. Projects may override a skill by
    placing their own SKILL.md under ``.cataforge/skills/<id>/``; when the
    override carries no ``scripts/`` directory the loader borrows the
    builtin scripts (see ``SkillLoader._merge_builtin_fallback``). This
    check enumerates **all** discovered builtins (not a hardcoded subset).
    """
    from cataforge.runtime.skill.loader import SkillLoader

    loader = SkillLoader(project_root=cfg.paths.root)
    targets = sorted(m.id for m in loader._scan_builtins())

    if not targets:
        click.echo("  (no built-in skills discovered)")
        return 0

    missing: list[tuple[str, str]] = []
    for skill_id in targets:
        meta = loader.get_skill(skill_id)
        if meta is None:
            missing.append((skill_id, "skill not discovered (no SKILL.md and no builtin)"))
            continue
        if not meta.scripts:
            missing.append(
                (
                    skill_id,
                    "SKILL.md found but no executable scripts — project override "
                    "shadowing the builtin. Delete .cataforge/skills/"
                    f"{skill_id}/SKILL.md or add scripts/ alongside it.",
                )
            )

    present = len(targets) - len(missing)
    click.echo(f"  {present}/{len(targets)} built-in skills have an executable entry point")
    for skill_id, reason in missing:
        click.echo(f"  FAIL {skill_id}: {reason}")
    if missing:
        click.echo(
            "  Built-in skills are invoked via `cataforge skill run <id> -- <args>`; "
            "see docs/architecture/quality-and-learning.md §2.1."
        )
    return len(missing)


def _emit_doctor_stale_deps(stale_deps: list[dict[str, str]]) -> None:
    """Print stale-dep warnings under doctor's indentation.

    Stale deps are a WARN, not a gating failure — surfaced here so they show
    in ``doctor`` as well as ``docs validate``, but never added to the
    returned fail count.
    """
    from cataforge.domain.docs.indexer import format_stale_deps_warning

    for line in format_stale_deps_warning(stale_deps):
        click.echo(f"  {line}")


def _emit_docignored(ignored: list[str]) -> None:
    """Print the docs/.docignore exclusion count under doctor's indentation."""
    if ignored:
        click.echo(f"  {len(ignored)} doc(s) excluded by docs/.docignore")


def _emit_index_failures(
    orphans: list[str],
    stale: list[tuple[str, str]],
    xref_errors: list[dict[str, str]],
) -> None:
    """Echo orphan, stale, and xref FAIL lines under doctor's indentation."""
    if orphans:
        click.echo(f"  {len(orphans)} orphan document(s) — missing YAML front matter (id field):")
        for rel in orphans[:5]:
            click.echo(f"    FAIL {rel}")
        if len(orphans) > 5:
            click.echo(f"    - ... and {len(orphans) - 5} more")
        click.echo("  → add `id`/`doc_type` front matter and rerun `cataforge docs index`.")

    if stale:
        click.echo(f"  {len(stale)} stale index entry(ies) — file_path missing on disk:")
        for doc_id, rel in stale[:5]:
            click.echo(f"    FAIL {doc_id} → {rel}")
        if len(stale) > 5:
            click.echo(f"    - ... and {len(stale) - 5} more")
        click.echo("  → run `cataforge docs index` (full rebuild) to drop stale entries.")

    if xref_errors:
        click.echo(
            f"  {len(xref_errors)} cross-reference error(s) — frontmatter deps that don't resolve:"
        )
        for e in xref_errors[:5]:
            click.echo(f"    FAIL {e['doc_id']} ({e['file_path']}) → {e['ref']}: {e['reason']}")
        if len(xref_errors) > 5:
            click.echo(f"    - ... and {len(xref_errors) - 5} more")
        click.echo(
            "  → use the registered full doc_id, or declare an `aliases:` "
            "list in the source doc's frontmatter."
        )


def _emit_id_failures(
    alias_conflicts: list[dict[str, str]],
    invalid_ids: list[dict[str, str]],
) -> None:
    """Echo alias-conflict and invalid-id FAIL lines under doctor's indentation."""
    if alias_conflicts:
        click.echo(f"  {len(alias_conflicts)} alias conflict(s) — second claim silently ignored:")
        for c in alias_conflicts[:5]:
            click.echo(f"    FAIL {c['alias']} (claimed by {c['claimed_by']}): {c['reason']}")
        if len(alias_conflicts) > 5:
            click.echo(f"    - ... and {len(alias_conflicts) - 5} more")

    if invalid_ids:
        click.echo(
            f"  {len(invalid_ids)} invalid id(s) — slug must match "
            f"[A-Za-z0-9_-]+ (no dots / version strings):"
        )
        for e in invalid_ids[:5]:
            click.echo(f"    FAIL [{e['kind']}] {e['value']!r} ({e['file_path']}): {e['reason']}")
        if len(invalid_ids) > 5:
            click.echo(f"    - ... and {len(invalid_ids) - 5} more")
        click.echo(
            "  → 别在 doc id/alias 里塞版本号或带 '.' 的串；版本归 frontmatter "
            "`version:` 字段。doc-gen 已遵循该规则。"
        )


def _emit_doctor_validate_failures(
    orphans: list[str],
    stale: list[tuple[str, str]],
    xref_errors: list[dict[str, str]],
    alias_conflicts: list[dict[str, str]],
    invalid_ids: list[dict[str, str]],
) -> None:
    """Echo per-category FAIL lines under doctor's indentation."""
    _emit_index_failures(orphans, stale, xref_errors)
    _emit_id_failures(alias_conflicts, invalid_ids)


def check_docs_validate(cfg) -> int:
    """Run the same validation suite as ``cataforge docs validate``.

    Shares :func:`cataforge.domain.docs.indexer.validate_docs` with the CLI so any
    new validator (orphans, stale entries, broken cross-refs, ...) flows
    into both gates without duplication.

    When ``docs/.doc-index.json`` is missing but ``docs/`` contains markdown
    files, emits a non-blocking WARN pointing at ``cataforge docs index``;
    empty / absent ``docs/`` directories are skipped silently.
    """
    import glob
    import os

    from cataforge.domain.docs.indexer import INDEX_FILENAME, validate_docs

    root = cfg.paths.root
    if not (root / "docs").is_dir():
        click.echo("  (no docs/ directory — skipping)")
        return 0

    if not (root / "docs" / INDEX_FILENAME).is_file():
        md_files = glob.glob(os.path.join(str(root), "docs", "**", "*.md"), recursive=True)
        if not md_files:
            click.echo(f"  (no docs/{INDEX_FILENAME} and docs/ has no markdown — skipping)")
            return 0
        click.secho(
            f"  WARN no docs/{INDEX_FILENAME} but docs/ contains {len(md_files)} markdown file(s)",
            fg="yellow",
        )
        click.echo(
            "  → run `cataforge docs index` to enable section-level loading "
            "via `cataforge docs load <doc_id>#§N`."
        )
        return 0

    result = validate_docs(str(root))
    orphans = result["orphans"]
    ignored = result.get("ignored", [])
    stale = result["stale"]
    xref_errors = result["xref_errors"]
    alias_conflicts = result["alias_conflicts"]
    invalid_ids = result.get("invalid_ids", [])
    stale_deps = result.get("stale_deps", [])

    _emit_docignored(ignored)

    if not orphans and not stale and not xref_errors and not alias_conflicts and not invalid_ids:
        click.echo(
            "  0 orphan documents · 0 stale entries · 0 xref errors · "
            "0 alias conflicts · 0 invalid ids (everything in sync)"
        )
        _emit_doctor_stale_deps(stale_deps)
        return 0

    _emit_doctor_validate_failures(orphans, stale, xref_errors, alias_conflicts, invalid_ids)
    _emit_doctor_stale_deps(stale_deps)

    return len(orphans) + len(stale) + len(xref_errors) + len(alias_conflicts) + len(invalid_ids)
