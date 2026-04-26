"""cataforge doctor — environment diagnostics."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.cli.main import cli

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


@cli.command("doctor")
@click.pass_context
def doctor_command(ctx: click.Context) -> None:
    """Run environment diagnostics and report issues.

    Exits with a non-zero status when any migration_check fails, so CI can
    treat doctor as a gate.
    """
    from cataforge.cli.helpers import get_config_manager

    click.echo("CataForge Doctor")
    click.echo("=" * 40)

    cfg = get_config_manager()

    # Python
    click.echo(f"\nPython: {sys.version}")
    click.echo(f"  Executable: {sys.executable}")

    # Framework
    click.echo(f"\nProject root: {cfg.paths.root}")
    _check_file("framework.json", cfg.paths.framework_json)
    _check_file("PROJECT-STATE.md", cfg.paths.project_state_md)
    _check_dir(".cataforge/agents", cfg.paths.agents_dir)
    _check_dir(".cataforge/skills", cfg.paths.skills_dir)
    _check_dir(".cataforge/rules", cfg.paths.rules_dir)
    _check_dir(".cataforge/hooks", cfg.paths.hooks_dir)
    _check_file("hooks.yaml", cfg.paths.hooks_spec)
    _check_dir(".cataforge/platforms", cfg.paths.platforms_dir)

    # Config
    click.echo(f"\nFramework version: {cfg.version}")
    click.echo(f"Runtime platform: {cfg.runtime_platform}")

    # Dependencies
    click.echo("\nDependencies:")
    _check_import("yaml", "PyYAML")
    _check_import("click", "click")

    # External tools
    click.echo("\nExternal tools:")
    for tool in ("ruff", "npx", "docker", "git"):
        path = shutil.which(tool)
        status = f"found ({path})" if path else "not found"
        click.echo(f"  {tool}: {status}")

    # Platform profiles
    click.echo("\nPlatform profiles:")
    for pid in ("claude-code", "cursor", "codex", "opencode"):
        path = cfg.paths.platform_profile(pid)
        status = "OK" if path.is_file() else "MISSING"
        click.echo(f"  {pid}: {status}")

    # runtime_api_version contract — framework.json declares it, but until
    # this check landed nothing read it back. Drift between scaffold-shipped
    # value and on-disk value means the user's framework.json was authored
    # against a different runtime API revision than the package can serve.
    click.echo("\nruntime_api_version contract:")
    failed_count = _check_runtime_api_version(cfg)

    # Framework migration checks — defined in framework.json, verified here so
    # scaffold/repo drift surfaces automatically instead of only at upgrade time.
    click.echo("\nFramework migration checks:")
    failed_count += _run_migration_checks(cfg)

    # Protocol script references — markdown/YAML files inside .cataforge/
    # routinely invoke ``python .cataforge/scripts/...`` commands. If one of
    # those scripts is missing, every call site silently fails at runtime
    # (each orchestrator [EVENT] line, every TDD phase transition, the
    # agent_dispatch hook, ...), with no signal until someone reads the
    # hook error log. Scanning statically catches the rot at diagnostic time.
    click.echo("\nProtocol script references:")
    failed_count += _check_protocol_script_references(cfg)

    click.echo("\nDeprecated protocol references:")
    failed_count += _check_deprecated_references(cfg)

    click.echo("\nDocs index completeness:")
    failed_count += _check_orphan_docs(cfg)

    click.echo("\nHook script importability:")
    failed_count += _check_hook_script_importability(cfg)

    click.echo("\nBuilt-in skill reachability:")
    failed_count += _check_builtin_skill_reachability(cfg)

    click.echo("\nEVENT-LOG schema sample:")
    failed_count += _check_event_log_schema(cfg)

    click.echo("\nEVENT-LOG bypass guard:")
    failed_count += _check_event_log_bypass_writes(cfg)

    # Deployment provenance — shows which platform-specific directories would
    # have been written by the last successful deploy. Lets users see at a
    # glance which ``.claude/`` / ``.cursor/`` / etc. are CataForge-managed
    # vs user/IDE-native, which was confusing in the Cursor verification.
    click.echo("\nDeployment provenance:")
    _report_deployment_provenance(cfg)

    # Recent hook execution failures — logged by hook_main() so silent
    # observer-hook crashes don't stay invisible.
    click.echo("\nHook execution log:")
    _report_hook_errors(cfg)

    click.echo("\nDiagnostics complete.")

    if failed_count:
        ctx.exit(1)


def _check_hook_script_importability(cfg: ConfigManager) -> int:
    """Verify each hooks.yaml script resolves to an importable module.

    Uses ``find_spec`` (no execution). ``custom:`` scripts are excluded —
    those are covered by the protocol-script-reference scan.
    """
    import importlib.util

    try:
        from cataforge.hook.bridge import load_hooks_spec
    except ImportError as e:
        click.echo(f"  FAIL cannot import cataforge.hook.bridge: {e}")
        return 1

    spec_path = cfg.paths.hooks_spec
    if not spec_path.is_file():
        click.echo(f"  (no hooks.yaml at {spec_path} — skipping)")
        return 0

    try:
        spec = load_hooks_spec(spec_path)
    except Exception as e:
        click.echo(f"  FAIL cannot parse {spec_path}: {e}")
        return 1

    declared: list[str] = []
    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            script = str(entry.get("script", "")).replace(".py", "")
            if not script or script.startswith("custom:"):
                continue
            declared.append(script)

    if not declared:
        click.echo("  (no built-in hook scripts declared)")
        return 0

    missing: list[str] = []
    for name in declared:
        module = f"cataforge.hook.scripts.{name}"
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)

    present = len(declared) - len(missing)
    click.echo(f"  {present}/{len(declared)} declared scripts importable")
    for name in missing:
        click.echo(
            f"  FAIL cataforge.hook.scripts.{name} — IDE invocations will "
            "ImportError before @hook_main can log them. "
            "Reinstall with `pip install -e .` (or the wheel) to resolve."
        )

    _report_runtime_degradation(cfg, declared)
    return len(missing)


def _check_builtin_skill_reachability(cfg: ConfigManager) -> int:
    """Verify every built-in skill is reachable via ``cataforge skill run``.

    Built-in skills ship Python entry points under
    ``cataforge.skill.builtins.<pkg>``. Projects may override a skill by
    placing their own SKILL.md under ``.cataforge/skills/<id>/``; when the
    override carries no ``scripts/`` directory the loader borrows the
    builtin scripts (see ``SkillLoader._merge_builtin_fallback``). This
    check enumerates **all** discovered builtins (not a hardcoded subset)
    so a future builtin can't slip through the way ``dep-analysis`` did
    after the original review-skill fix.
    """
    from cataforge.skill.loader import SkillLoader

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
            missing.append((
                skill_id,
                "SKILL.md found but no executable scripts — project override "
                "shadowing the builtin. Delete .cataforge/skills/"
                f"{skill_id}/SKILL.md or add scripts/ alongside it.",
            ))

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


def _report_runtime_degradation(cfg: ConfigManager, declared: list[str]) -> None:
    """List each declared script's degradation status on the current platform."""
    try:
        from cataforge.platform.registry import get_adapter

        adapter = get_adapter(cfg.runtime_platform)
    except Exception as e:
        click.echo(f"  (cannot load adapter for {cfg.runtime_platform!r}: {e})")
        return

    degradation = getattr(adapter, "hook_degradation", {}) or {}

    statuses: dict[str, str] = {}
    for name in declared:
        statuses[name] = str(degradation.get(name, "native"))

    skipped = sorted(n for n, s in statuses.items() if s == "skip")
    other_degraded = sorted(
        n for n, s in statuses.items() if s not in ("native", "skip")
    )
    native_count = sum(1 for s in statuses.values() if s == "native")

    summary = f"  Runtime degradation on {cfg.runtime_platform}: {native_count} native"
    if skipped:
        summary += f", {len(skipped)} skipped"
    if other_degraded:
        summary += f", {len(other_degraded)} degraded"
    click.echo(summary)
    for name in skipped:
        click.echo(
            f"    SKIP {name} — will not fire at runtime "
            "(platform lacks native hook event)"
        )
    for name in other_degraded:
        click.echo(f"    {statuses[name].upper()} {name}")


def _check_event_log_schema(
    cfg: ConfigManager, *, sample_size: int = 200
) -> int:
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
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        click.echo(f"  (cannot read {log_path}: {e})")
        return 0

    cutoff_raw = (
        (cfg.load().get("upgrade") or {})
        .get("state", {})
        .get("event_log_validate_since")
    )
    cutoff: datetime | None = None
    if isinstance(cutoff_raw, str) and cutoff_raw.strip():
        try:
            cutoff = datetime.fromisoformat(cutoff_raw.replace("Z", "+00:00"))
        except ValueError:
            click.echo(
                f"  (ignoring malformed event_log_validate_since={cutoff_raw!r})"
            )

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

    Unparseable or missing ``ts`` returns False — we only skip records we
    can *prove* predate the cutoff. That keeps malformed records (which the
    watermark shouldn't hide) failing instead of silently passing.
    """
    from datetime import datetime, timezone

    if not isinstance(ts_value, str) or not ts_value:
        return False
    try:
        ts = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
    except ValueError:
        return False
    # Make both sides timezone-aware to avoid naive-vs-aware comparison errors.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return ts < cutoff


def _match_inside_inline_code(line: str, pos: int) -> bool:
    return line.count("`", 0, pos) % 2 == 1


def _check_event_log_bypass_writes(cfg: ConfigManager) -> int:
    """Flag any ``.cataforge/`` markdown/YAML that appends to EVENT-LOG.jsonl
    via shell redirection (must use ``cataforge event log`` instead)."""
    import re

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
                text = path.read_text(encoding="utf-8")
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


def _report_hook_errors(cfg) -> None:
    """Surface recent entries from ``.cataforge/.hook-errors.jsonl``.

    We don't fail the doctor run on these — a crashed observer hook is
    degraded functionality, not a broken project — but we do point the user
    at the log so they know it exists.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone

    from cataforge.hook.base import HOOK_ERROR_LOG_REL

    log_path = cfg.paths.root / HOOK_ERROR_LOG_REL
    if not log_path.is_file():
        click.echo("  (no hook errors recorded)")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent: list[dict] = []
    try:
        with open(log_path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = _json.loads(raw)
                except _json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts")
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (TypeError, ValueError):
                    continue
                if ts >= cutoff:
                    recent.append(entry)
    except OSError as e:
        click.echo(f"  (could not read {log_path}: {e})")
        return

    if not recent:
        click.echo("  (no hook errors in the last 24h)")
        return

    tail = recent[-5:]
    click.echo(f"  {len(recent)} error(s) in the last 24h (showing last {len(tail)}):")
    for entry in tail:
        mod = entry.get("module", "?")
        fn = entry.get("func", "?")
        err_type = entry.get("error_type", "Error")
        err = entry.get("error", "")
        click.echo(f"  - [{entry.get('ts', '?')}] {mod}.{fn}: {err_type}: {err}")
    click.echo(f"  Full log: {log_path}  (set CATAFORGE_HOOK_DEBUG=1 for tracebacks)")


def _report_deployment_provenance(cfg) -> None:
    """Show which platform directories were created by the last deploy.

    Reads ``.cataforge/.deploy-state`` (written at the end of each
    ``cataforge deploy``) plus the target platform's profile to compute
    the directory namespace that CataForge owns, then reports which of
    those paths actually exist on disk vs which are user/IDE native.
    """
    import json as _json

    deploy_state_path = cfg.paths.cataforge_dir / ".deploy-state"
    if not deploy_state_path.is_file():
        click.echo("  (no deploy has been run yet — run `cataforge deploy`)")
        return

    try:
        state = _json.loads(deploy_state_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as e:
        click.echo(f"  (could not parse {deploy_state_path}: {e})")
        return

    platform_id = state.get("platform")
    if not platform_id:
        click.echo(f"  (malformed deploy state: {state})")
        return

    click.echo(f"  Last deploy target: {platform_id}")

    # Map platform → directories CataForge *may* own under that platform.
    # We err on the side of listing a stable, well-known subset rather than
    # introspecting every adapter (which would require instantiation).
    owned: dict[str, list[str]] = {
        "claude-code": [".claude/agents", ".claude/rules", ".claude/skills",
                        ".claude/commands", ".claude/settings.json"],
        "cursor": [".cursor/agents", ".cursor/rules", ".cursor/hooks.json",
                   ".cursor/mcp.json", ".cursor/commands"],
        "codex": [".codex/agents", ".codex/hooks.json", ".codex/config.toml"],
        "opencode": [".opencode/agents", ".opencode/plugins", "opencode.json"],
    }

    root = cfg.paths.root
    entries = owned.get(platform_id, [])
    if not entries:
        click.echo(f"  (no provenance map declared for platform {platform_id!r})")
        return

    for rel in entries:
        p = root / rel
        marker = "present" if (p.exists() or p.is_symlink()) else "absent"
        click.echo(f"  [{marker}] {rel}  (CataForge-managed)")

    # Also flag Cursor mirror state: is .claude/rules present even though the
    # mirror is off?  That usually means a stale artifact from an older deploy.
    if platform_id == "cursor":
        mirror = root / ".claude" / "rules"
        if mirror.exists() or mirror.is_symlink():
            profile_path = cfg.paths.platform_profile("cursor")
            mirror_enabled = _read_cursor_mirror_flag(profile_path)
            if not mirror_enabled:
                click.echo(
                    "  NOTE: .claude/rules exists but rules.cross_platform_mirror "
                    "is false — likely a stale artifact from a pre-M5 deploy. "
                    "Safe to delete."
                )


def _read_cursor_mirror_flag(profile_path: Path) -> bool:
    """Best-effort read of ``rules.cross_platform_mirror`` from a YAML profile."""
    if not profile_path.is_file():
        return False
    try:
        import yaml as _yaml

        data = _yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        return False
    return bool(rules.get("cross_platform_mirror", False))


SUPPORTED_RUNTIME_API_VERSION = "1.0"
"""scaffold ↔ runtime contract version.

Bumped on backwards-incompatible scaffold/runtime interface changes
(field rename, removed key, type change). Fresh installs and
``cataforge upgrade apply`` always restamp framework.json with this
value via ``_merge_framework_json``; mismatch on a Config.load() means
either:
  - user hand-edited framework.json to an unsupported version, or
  - they're running a wheel from before the contract bump against a
    framework.json from after.
"""


def _check_runtime_api_version(cfg) -> int:
    declared = cfg.load().get("runtime_api_version")
    if declared is None:
        # Field is unconditionally stamped by ``scaffold._stamp_framework_version``
        # on every ``cataforge setup`` / ``cataforge upgrade apply`` write,
        # so a real on-disk framework.json that goes through the normal
        # install path will never be missing it. Hard-fail here so the
        # contract is meaningful — users who hand-edit framework.json and
        # delete the field will be told to restamp.
        click.echo(
            f"  FAIL: runtime_api_version field missing from framework.json "
            f"(expected {SUPPORTED_RUNTIME_API_VERSION!r}); "
            "run `cataforge upgrade apply` to restamp."
        )
        return 1
    if str(declared) != SUPPORTED_RUNTIME_API_VERSION:
        click.echo(
            f"  FAIL: runtime_api_version = {declared!r}, "
            f"package supports {SUPPORTED_RUNTIME_API_VERSION!r}. "
            "Either upgrade the cataforge package (when on-disk is newer) "
            "or run `cataforge upgrade apply` (when on-disk is older) to "
            "restamp framework.json."
        )
        return 1
    click.echo(f"  OK: runtime_api_version = {declared}")
    return 0


def _run_migration_checks(cfg) -> int:
    """Run migration checks; return the number of failures.

    Checks marked ``requires_deploy: true`` are SKIPPED (not failed) when the
    project has not yet been deployed — they target deploy-produced artifacts
    like ``.claude/settings.json`` that cannot exist until the first
    ``cataforge deploy`` run.  This lets ``doctor`` stay green for a
    fresh-install flow that hasn't deployed yet, while still catching drift
    once deploy has happened at least once.

    Checks with ``deprecate_after: <semver>`` are SKIPPED once the running
    package version has caught up to that semver — closes the otherwise-
    unbounded growth of migration_checks (every release adds one, none
    are ever removed). Set deprecate_after to the version at which the
    underlying refactor is no longer reversible (i.e. nobody on a recent
    install can have the legacy state any more).
    """
    from cataforge import __version__ as pkg_version

    checks = cfg.load().get("migration_checks") or []
    if not checks:
        click.echo("  (none defined)")
        return 0

    deployed = (cfg.paths.cataforge_dir / ".deploy-state").is_file()

    passed = 0
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    for check in checks:
        cid = str(check.get("id", "?"))
        deprecate_after = check.get("deprecate_after")
        if isinstance(deprecate_after, str) and _semver_ge(pkg_version, deprecate_after):
            skipped.append(
                (cid, f"deprecated since {deprecate_after} (current {pkg_version})")
            )
            continue
        if bool(check.get("requires_deploy", False)) and not deployed:
            skipped.append((cid, "requires deploy (run `cataforge deploy` first)"))
            continue
        ok, reason = _evaluate_check(check, cfg.paths.root)
        if ok:
            passed += 1
        else:
            failed.append((cid, reason))

    parts = [f"{passed}/{len(checks)} passed"]
    if skipped:
        parts.append(f"{len(skipped)} skipped")
    click.echo("  " + ", ".join(parts))
    for cid, reason in skipped:
        click.echo(f"  SKIP {cid}: {reason}")
    for cid, reason in failed:
        click.echo(f"  FAIL {cid}: {reason}")
    return len(failed)


def _semver_ge(a: str, b: str) -> bool:
    """True iff *a* >= *b* on the leading dotted-numeric prefix.

    Both args are best-effort parsed; non-numeric inputs (e.g. "0.0.0-template",
    "0.2.0rc1") fall through with the trailing suffix ignored. We err on the
    side of False to avoid silently skipping a check that should still run.
    """
    import re

    tup_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
    ma = tup_re.match(a)
    mb = tup_re.match(b)
    if ma is None or mb is None:
        return False
    return tuple(int(x) for x in ma.groups()) >= tuple(int(x) for x in mb.groups())


def _evaluate_check(check: dict, root: Path) -> tuple[bool, str]:
    """Evaluate a single migration_check entry.  Returns (ok, reason)."""
    ctype = str(check.get("type", ""))
    rel = str(check.get("path", ""))
    target = root / rel
    patterns = list(check.get("patterns") or [])

    if ctype == "file_must_exist":
        return (target.is_file(), "" if target.is_file() else f"{rel} does not exist")

    if ctype == "file_must_contain":
        if not target.is_file():
            return False, f"{rel} does not exist"
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"cannot read {rel}: {e}"
        missing = [p for p in patterns if p not in text]
        if missing:
            return False, f"{rel} missing patterns: {missing}"
        return True, ""

    if ctype == "file_must_not_contain":
        if not target.is_file():
            # A non-existent file trivially satisfies "must not contain". An
            # ``allow_missing`` opt-out is required so guards against
            # framework-source-only paths (e.g. dogfood-only checks against
            # `src/cataforge/...`) don't quietly turn into vacuous PASS for
            # end users where the path doesn't exist.
            if check.get("allow_missing", False):
                return True, ""
            return False, (
                f"{rel} does not exist — `file_must_not_contain` cannot be "
                "vacuously asserted; either fix the path, mark the check "
                "`allow_missing: true`, or set `deprecate_after` for it"
            )
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"cannot read {rel}: {e}"
        present = [p for p in patterns if p in text]
        if present:
            return False, f"{rel} contains forbidden patterns: {present}"
        return True, ""

    if ctype == "dir_must_contain_files":
        if not target.is_dir():
            return False, f"{rel} is not a directory"
        missing = [p for p in patterns if not (target / p).is_file()]
        if missing:
            return False, f"{rel} missing files: {missing}"
        return True, ""

    return False, f"unknown check type: {ctype}"


def _check_protocol_script_references(cfg) -> int:
    """Scan ``.cataforge/`` protocol docs + hooks spec for ``python .cataforge/...``
    invocations and report any that point at a file that does not exist.

    Returns the number of distinct missing scripts (counts toward the
    ``cataforge doctor`` exit code gate).

    The scan covers any path under ``.cataforge/`` (not just
    ``.cataforge/scripts/``). The original narrower regex missed
    ``python .cataforge/skills/<id>/scripts/*.py`` and
    ``python .cataforge/integrations/...`` — exactly the patterns that
    silently broke ``dep-analysis`` and the three Penpot skills after
    their implementations moved into the cataforge package.
    """
    import re

    # Match ``python <path>`` where <path> is anywhere under ``.cataforge/``
    # and ends at the first shell-special character. We deliberately do not
    # resolve shell quoting — if a protocol ever wraps the path in quotes
    # we can revisit.
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
    # tutorial prose (e.g. ``.cataforge/hooks/custom/`` is user-extension
    # territory; its README walks readers through naming a hook script
    # that doesn't exist yet). Scoped narrowly so framework-shipped
    # protocols stay covered.
    skip_subtrees = (
        cfg.paths.hooks_dir / "custom",
    )

    suffixes = {".md", ".yaml", ".yml"}
    # script relpath → sorted list of "file:line" callers (for the error message)
    refs: dict[str, list[str]] = {}
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(_is_relative_to(path, sub) for sub in skip_subtrees):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in pattern.finditer(line):
                    rel = match.group(1)
                    # Documentation placeholders, not real invocations:
                    # ``*`` is a glob wildcard, ``...`` is an ellipsis
                    # (``.cataforge/skills/.../scripts/*.py`` is the
                    # spelling we use to *prohibit* a path, not call it).
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
        # Cap the shown callers so a widely-used missing script doesn't
        # drown the output; the count conveys the scope.
        shown = callers[:5]
        for caller in shown:
            click.echo(f"    - {caller}")
        extra = len(callers) - len(shown)
        if extra > 0:
            click.echo(f"    - ... and {extra} more call site(s)")

    return len(missing)


# ---------------------------------------------------------------------------
# Deprecated reference linter
#
# Catches the failure mode that ``_check_protocol_script_references`` misses:
# bare script names mentioned in prose (``load_section.py``), CLI subcommands
# that no longer exist, and references to artifacts that have been retired
# (``docs/NAV-INDEX.md``, ``docs/.nav/``).
#
# ANTI-ROT POLICY:
#   When deprecating any user-facing path, script, or CLI flag, add an entry
#   to ``_DEPRECATED_REFS`` below with a `replacement` field. CI then fails
#   any new agent/skill/protocol prose that uses the old name, without
#   requiring a sweep of every markdown file at deprecation time.
# ---------------------------------------------------------------------------


_DEPRECATED_REFS: tuple[dict[str, str], ...] = (
    {
        "name": "load_section.py",
        # Word-boundary match catches `load_section.py`, `load_section.py:`, etc.
        # but does not match `cataforge_load_section_py` (unlikely but cheap).
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
        # Tolerate occurrences in archive paths (``.cataforge/.archive/...``).
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
        # Catches the relative-path script invocation that breaks when an
        # agent runs from a monorepo subdirectory (cwd != project root).
        "pattern": r"python\s+\.cataforge/scripts/framework/event_logger\.py",
        "replacement": "`cataforge event log` (CLI walks up to find .cataforge/)",
        "since": "v0.1.14",
    },
)


def _check_deprecated_references(cfg) -> int:
    """Scan agent/skill/rules/hook prose for deprecated script names + artifacts.

    Returns the number of distinct deprecated references found (counts toward
    the ``cataforge doctor`` exit code gate). Self (this file) and the
    `_DEPRECATED_REFS` table itself are exempt — those are the registry, not a
    consumer.
    """
    import re

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
        # Archive directory legitimately retains historical NAV-INDEX copies.
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
            if any(_is_relative_to(path, sub) for sub in skip_subtrees):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for entry, pattern in patterns:
                    if pattern.search(line):
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


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _check_orphan_docs(cfg) -> int:
    """Surface ``docs/**/*.md`` files the indexer cannot ingest.

    A doc is "orphan" when its YAML front matter is missing, empty, or has
    an unfilled ``id`` placeholder. Such files are silently dropped by the
    indexer and never resolvable via ``cataforge docs load``. Pre-v0.1.13
    they were partially masked by hand-maintained NAV-INDEX entries; once
    the machine index became authoritative, the gap turned silent.

    Gated on ``docs/.doc-index.json`` existing — that file is only created
    by ``cataforge docs index``, so its presence is the explicit signal
    that the project opted into CataForge-managed docs. Repos whose
    ``docs/`` is plain README-style content (architecture explainers, faq,
    etc.) never built an index, so they are exempt from this check.

    Returns the number of orphans found (counts toward the doctor exit
    gate).
    """
    from cataforge.docs.indexer import INDEX_FILENAME, find_orphan_docs

    root = cfg.paths.root
    if not (root / "docs").is_dir():
        click.echo("  (no docs/ directory — skipping)")
        return 0
    if not (root / "docs" / INDEX_FILENAME).is_file():
        click.echo(
            f"  (no docs/{INDEX_FILENAME} — project has not opted into "
            "CataForge-managed docs; skipping)"
        )
        return 0

    orphans = find_orphan_docs(str(root))
    if not orphans:
        click.echo("  0 orphan documents (every docs/**/*.md is indexable)")
        return 0

    click.echo(
        f"  {len(orphans)} orphan document(s) — missing YAML front matter "
        f"(id field):"
    )
    shown = orphans[:5]
    for rel in shown:
        click.echo(f"    FAIL {rel}")
    extra = len(orphans) - len(shown)
    if extra > 0:
        click.echo(f"    - ... and {extra} more")
    click.echo(
        "  → add `id`/`doc_type` front matter and rerun `cataforge docs index`."
    )
    return len(orphans)


def _check_file(label: str, path: Path) -> None:
    status = "OK" if path.is_file() else "MISSING"
    click.echo(f"  {label}: {status}")


def _check_dir(label: str, path: Path) -> None:
    status = "OK" if path.is_dir() else "MISSING"
    click.echo(f"  {label}: {status}")


def _check_import(module: str, display: str) -> None:
    try:
        __import__(module)
        click.echo(f"  {display}: OK")
    except ImportError:
        click.echo(f"  {display}: MISSING")
