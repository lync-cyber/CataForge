"""Deploy drift detection.

Two baselines recorded at deploy time in ``.deploy-manifest.json`` let a
later run tell whether the deployed IDE artefacts have gone stale:

* ``source_digest`` — a deterministic hash over every ``.cataforge/`` file
  that feeds a deploy. A changed / added / removed source file shifts it.
* ``package_version`` — the ``cataforge`` version that ran the deploy. A
  newer installed package means the bundled base assets may have changed
  without a redeploy.

Neither is a failure: both just mean "run ``cataforge deploy``". The doctor
check and the SessionStart hook both consume :func:`detect_drift` to nudge.

Runtime state under ``.cataforge/`` (``.deploy-state``,
``.deploy-manifest.json``, ``.mcp-state``, ``kg/``, ``.backups`` …) is
excluded from the digest via a source-dir whitelist — it is written by the
framework itself and would otherwise make every deploy self-trigger drift.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from cataforge.core.paths import ProjectPaths
from cataforge.runtime.deploy.manifest import load_prior_baseline

# Source dirs (relative to ``.cataforge/``) that feed a deploy. A change to
# any file under these should prompt a redeploy. Keep aligned with the
# source surface the deployer reads (see ``Deployer._deploy``).
_SOURCE_DIRS: tuple[str, ...] = (
    "agents",
    "skills",
    "rules",
    "hooks",
    "commands",
    "platforms",
    "schemas",
    "mcp",
    "overrides",
)
_SOURCE_FILES: tuple[str, ...] = ("framework.json",)


def _iter_source_files(paths: ProjectPaths) -> Iterator[Path]:
    cf = paths.cataforge_dir
    for name in _SOURCE_FILES:
        p = cf / name
        if p.is_file():
            yield p
    for d in _SOURCE_DIRS:
        root = cf / d
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                yield p


def compute_source_digest(paths: ProjectPaths) -> str:
    """Deterministic sha256 over all deploy-input source files.

    Hashes ``(relative_path, bytes)`` pairs in sorted path order so the
    result is stable across runs and platforms.
    """
    cf = paths.cataforge_dir
    items = sorted(_iter_source_files(paths), key=lambda p: p.relative_to(cf).as_posix())
    h = hashlib.sha256()
    for p in items:
        rel = p.relative_to(cf).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


@dataclass(frozen=True)
class DriftReport:
    """Outcome of comparing the working tree against the deploy baseline."""

    deployed: bool
    source_drift: bool
    version_drift: bool
    prior_version: str | None
    current_version: str
    prior_digest: str | None
    current_digest: str

    @property
    def any_drift(self) -> bool:
        return self.source_drift or self.version_drift


def detect_drift(paths: ProjectPaths, *, current_version: str | None = None) -> DriftReport:
    """Compare current ``.cataforge/`` source + package version vs the baseline.

    ``deployed`` is False (and no drift reported) when no manifest baseline
    exists — a pre-deploy or pre-baseline project is legitimate, not stale.
    """
    if current_version is None:
        from cataforge import __version__

        current_version = __version__
    prior_digest, prior_version = load_prior_baseline(paths.root)
    current_digest = compute_source_digest(paths)
    deployed = prior_digest is not None
    source_drift = deployed and prior_digest != current_digest
    version_drift = prior_version is not None and prior_version != current_version
    return DriftReport(
        deployed=deployed,
        source_drift=source_drift,
        version_drift=version_drift,
        prior_version=prior_version,
        current_version=current_version,
        prior_digest=prior_digest,
        current_digest=current_digest,
    )


def drift_hint_lines(report: DriftReport) -> list[str]:
    """Human-facing nudge lines for a drifted report — shared by doctor + hook."""
    lines: list[str] = []
    if report.source_drift:
        lines.append(
            ".cataforge/ source changed since last deploy — "
            "run `cataforge deploy` to refresh IDE artefacts"
        )
    if report.version_drift:
        lines.append(
            f"cataforge upgraded ({report.prior_version} → {report.current_version}) "
            "since last deploy — run `cataforge deploy`"
        )
    return lines
