"""framework.json schema v1 → v2 migration.

v2 layout: ``deployment.default_platform`` + ``deployment.targets`` replace
``runtime.platform``; ``upgrade.state`` lives in ``.cataforge/state/upgrade.json``
(run-state, gitignored) instead of the shared config file; ``schema_version``
stamps the layout. Migration is idempotent, backs up the original, and
refuses configs written by a newer runtime.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.utils.atomic_write import atomic_write_text

CONFIG_SCHEMA_VERSION = 2

UPGRADE_STATE_REL = Path(".cataforge") / "state" / "upgrade.json"


@dataclass
class MigrationResult:
    migrated: bool
    actions: list[str] = field(default_factory=list)
    backup: Path | None = None


def needs_migration(raw: dict[str, Any]) -> bool:
    declared = raw.get("schema_version")
    if isinstance(declared, int) and declared > CONFIG_SCHEMA_VERSION:
        # Not migratable by this runtime — callers surface the version error.
        return False
    if declared != CONFIG_SCHEMA_VERSION:
        return True
    runtime = raw.get("runtime")
    if isinstance(runtime, dict) and "platform" in runtime:
        return True
    upgrade = raw.get("upgrade")
    return isinstance(upgrade, dict) and "state" in upgrade


def reject_newer_schema(raw: dict[str, Any]) -> None:
    """Raise when the config was written by a newer runtime (invariant:
    forward-incompatible files fail loudly, not half-work)."""
    declared = raw.get("schema_version")
    if isinstance(declared, int) and declared > CONFIG_SCHEMA_VERSION:
        raise ConfigError(
            f"framework.json schema_version={declared} is newer than this "
            f"cataforge supports ({CONFIG_SCHEMA_VERSION}); upgrade the "
            "cataforge package first."
        )


def split_v1_fields(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure v1→v2 transform: returns ``(migrated_config, extracted_state)``.

    ``runtime.platform`` moves to ``deployment.default_platform`` (winning
    over any scaffold-default deployment block); ``targets`` is seeded with
    the default when absent. ``upgrade.state`` is popped out for the caller
    to persist into the run-state file. Unknown keys pass through verbatim.
    """
    out = dict(raw)

    runtime = out.get("runtime")
    legacy_platform: str | None = None
    if isinstance(runtime, dict) and "platform" in runtime:
        runtime = dict(runtime)
        legacy_platform = str(runtime.pop("platform"))
        if runtime:
            out["runtime"] = runtime
        else:
            out.pop("runtime", None)

    deployment = out.get("deployment")
    deployment = dict(deployment) if isinstance(deployment, dict) else {}
    if legacy_platform is not None:
        deployment["default_platform"] = legacy_platform
    if deployment.get("default_platform") and not deployment.get("targets"):
        deployment["targets"] = [deployment["default_platform"]]
    if deployment:
        out["deployment"] = deployment

    extracted_state: dict[str, Any] = {}
    upgrade = out.get("upgrade")
    if isinstance(upgrade, dict) and "state" in upgrade:
        upgrade = dict(upgrade)
        state = upgrade.pop("state")
        if isinstance(state, dict):
            extracted_state = state
        if upgrade:
            out["upgrade"] = upgrade
        else:
            out.pop("upgrade", None)

    out["schema_version"] = CONFIG_SCHEMA_VERSION
    return out, extracted_state


def merge_upgrade_state(root: Path, extracted: dict[str, Any], *, dry_run: bool = False) -> Path:
    """Fold *extracted* into the run-state file; existing file keys win
    (the state file is the newer truth once it exists)."""
    state_path = root / UPGRADE_STATE_REL
    current: dict[str, Any] = {}
    if state_path.is_file():
        try:
            data = read_json(state_path)
            if isinstance(data, dict):
                current = data
        except ConfigError:
            current = {}
    merged = {**extracted, **current}
    if not dry_run and (not state_path.is_file() or merged != current):
        atomic_write_text(state_path, json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    return state_path


def migrate_framework_json(root: Path, *, dry_run: bool = False) -> MigrationResult:
    """Migrate ``<root>/.cataforge/framework.json`` in place. Idempotent."""
    fw_path = root / ".cataforge" / "framework.json"
    if not fw_path.is_file():
        return MigrationResult(migrated=False, actions=["framework.json not found"])

    raw = read_json(fw_path)
    if not isinstance(raw, dict):
        raise ConfigError(f"{fw_path} is not a JSON object")
    reject_newer_schema(raw)

    if not needs_migration(raw):
        return MigrationResult(migrated=False, actions=["already at schema v2"])

    migrated, extracted_state = split_v1_fields(raw)
    actions: list[str] = []
    if "deployment" in migrated and "runtime" not in migrated:
        actions.append("runtime.platform -> deployment.default_platform")
    if extracted_state:
        actions.append(f"upgrade.state -> {UPGRADE_STATE_REL.as_posix()}")
    actions.append(f"schema_version = {CONFIG_SCHEMA_VERSION}")

    backup: Path | None = None
    if not dry_run:
        backup_dir = root / ".cataforge" / ".backups" / f"config-migrate-{int(time.time())}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / "framework.json"
        backup.write_bytes(fw_path.read_bytes())

        if extracted_state:
            merge_upgrade_state(root, extracted_state)
        atomic_write_text(fw_path, json.dumps(migrated, indent=2, ensure_ascii=False) + "\n")

    return MigrationResult(migrated=True, actions=actions, backup=backup)
