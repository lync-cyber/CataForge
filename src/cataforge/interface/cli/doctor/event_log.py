"""EVENT-LOG schema sampling + bypass-write guard."""

from __future__ import annotations

import re
from datetime import UTC
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_event_log_schema(cfg: ConfigManager, *, sample_size: int = 200) -> int:
    """Validate the last ``sample_size`` EVENT-LOG.jsonl records via
    :func:`validate_record`. Returns the count of invalid records.

    Honors the ``upgrade.state.event_log_validate_since`` ISO-8601 watermark
    (set by ``cataforge event accept-legacy``): records whose ``ts`` predates
    the watermark are skipped — pre-v0.1.7 bypass-write residue must not
    hold doctor hostage forever.
    """
    import json
    from datetime import datetime

    from cataforge.core.event_log import event_log_path, validate_record

    log_path = event_log_path(cfg.paths.root)
    if not log_path.is_file():
        click.echo("  (no EVENT-LOG.jsonl yet — nothing to validate)")
        return 0

    try:
        with open(log_path) as f:
            lines = f.readlines()
    except OSError as e:
        click.echo(f"  (cannot read {log_path}: {e})")
        return 0

    cutoff_raw = (cfg.load().get("upgrade") or {}).get("state", {}).get("event_log_validate_since")
    cutoff: datetime | None = None
    if isinstance(cutoff_raw, str) and cutoff_raw.strip():
        try:
            cutoff = datetime.fromisoformat(cutoff_raw.replace("Z", "+00:00"))
        except ValueError:
            click.echo(f"  (ignoring malformed event_log_validate_since={cutoff_raw!r})")

    total_lines = len(lines)
    start_idx = max(0, total_lines - sample_size)
    sampled = lines[start_idx:]

    bad: list[tuple[int, str, list[str]]] = []
    skipped_pre_cutoff = 0
    for offset, raw in enumerate(sampled):
        line_no = start_idx + offset + 1
        text = raw.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            if cutoff is not None:
                # Unparseable lines can't be timestamp-compared; treat as
                # pre-cutoff iff the cutoff is set, to match the intent of
                # "ignore historical rot".
                skipped_pre_cutoff += 1
                continue
            bad.append((line_no, text[:80], [f"invalid JSON: {e}"]))
            continue
        if not isinstance(obj, dict):
            bad.append((line_no, text[:80], ["not a JSON object"]))
            continue
        if cutoff is not None and _ts_before(obj.get("ts"), cutoff):
            skipped_pre_cutoff += 1
            continue
        errors = validate_record(obj)
        if errors:
            preview = obj.get("event") or obj.get("timestamp") or "?"
            bad.append((line_no, str(preview)[:80], errors))

    sampled_count = sum(1 for ln in sampled if ln.strip())
    validated = sampled_count - skipped_pre_cutoff
    summary = (
        f"  {validated - len(bad)}/{validated} sampled records valid "
        f"(window: last {sampled_count} of {total_lines} total"
    )
    if skipped_pre_cutoff:
        summary += f"; {skipped_pre_cutoff} pre-cutoff skipped"
    summary += ")"
    click.echo(summary)

    shown = bad[:5]
    for line_no, preview, errors in shown:
        click.echo(f"  FAIL line {line_no} ({preview}): {'; '.join(errors)}")
    if len(bad) > len(shown):
        click.echo(f"    ... and {len(bad) - len(shown)} more invalid record(s)")

    if bad and cutoff is None:
        click.echo(
            "  Hint: if these are legacy bypass writes from before v0.1.7, "
            "run `cataforge event accept-legacy` to set a cutoff and stop "
            "failing doctor on historical records."
        )
    return len(bad)


def _ts_before(ts_value, cutoff) -> bool:  # cutoff: datetime
    """True iff ``ts_value`` parses and is strictly before *cutoff*.

    Unparseable or missing ``ts`` returns False — only records that *prove*
    they predate the cutoff are skipped, so malformed records (which the
    watermark shouldn't hide) still fail.
    """
    from datetime import datetime

    if not isinstance(ts_value, str) or not ts_value:
        return False
    try:
        ts = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
    except ValueError:
        return False
    # Make both sides timezone-aware to avoid naive-vs-aware comparison errors.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return ts < cutoff


def _match_inside_inline_code(line: str, pos: int) -> bool:
    return line.count("`", 0, pos) % 2 == 1


def check_event_log_bypass_writes(cfg: ConfigManager) -> int:
    """Flag any ``.cataforge/`` markdown/YAML that appends to EVENT-LOG.jsonl
    via shell redirection (must use ``cataforge event log`` instead)."""
    pattern = re.compile(r">>\s*[^\s`\"']*EVENT-LOG\.jsonl")

    scan_roots = (
        cfg.paths.agents_dir,
        cfg.paths.skills_dir,
        cfg.paths.rules_dir,
        cfg.paths.hooks_dir,
        cfg.paths.commands_dir,
    )
    suffixes = {".md", ".yaml", ".yml"}
    hits: list[tuple[str, int, str]] = []
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                text = path.read_text()
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                m = pattern.search(line)
                if not m or _match_inside_inline_code(line, m.start()):
                    continue
                try:
                    rel = path.relative_to(cfg.paths.root).as_posix()
                except ValueError:
                    rel = str(path)
                hits.append((rel, lineno, line.strip()[:120]))

    if not hits:
        click.echo("  (no heredoc/redirect writes to EVENT-LOG.jsonl found)")
        return 0

    click.echo(f"  FAIL {len(hits)} bypass write(s) — must use `cataforge event log`:")
    for rel, lineno, snippet in hits[:5]:
        click.echo(f"    - {rel}:{lineno}  {snippet}")
    if len(hits) > 5:
        click.echo(f"    - ... and {len(hits) - 5} more")
    return len(hits)
