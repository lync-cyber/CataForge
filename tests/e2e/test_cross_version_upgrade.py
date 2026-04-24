"""End-to-end: upgrade from an older PyPI-released cataforge to the current wheel.

This test is the real deal: it installs the last released version from PyPI
into an isolated venv, scaffolds a project with it, then overlays the
locally-built wheel and runs ``cataforge upgrade apply`` — the sequence a
real user follows when ``pip install --upgrade cataforge`` lands a new
version on their machine.

Gated by ``CATAFORGE_E2E_NETWORK=1`` because it requires PyPI access.
CI sets the env var; local dev can opt in when making release-facing
changes, and skip it by default to keep ``pytest -m slow`` offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.conftest import make_venv, pip_install, run_cataforge

pytestmark = [pytest.mark.slow, pytest.mark.network]


# Last released version that predates the scaffold manifest (which landed in
# the release-integrity PR). Pinning to a known release guarantees the test
# exercises the no-manifest → [drift] path; bump this when the baseline moves.
BASELINE_VERSION = "0.1.7"


def _network_enabled() -> bool:
    return os.environ.get("CATAFORGE_E2E_NETWORK", "").strip() not in ("", "0", "false")


@pytest.mark.skipif(
    not _network_enabled(),
    reason="set CATAFORGE_E2E_NETWORK=1 to run PyPI-fetching e2e tests",
)
def test_cross_version_upgrade_from_baseline(
    tmp_path: Path, built_wheel: Path
) -> None:
    """Install v0.1.7, scaffold, overlay current wheel, verify drift surfaces."""
    py = make_venv(tmp_path / "venv")

    # 1. Install the older released version from PyPI.
    pip_install(py, f"cataforge=={BASELINE_VERSION}")

    project = tmp_path / "proj"
    project.mkdir()

    # 2. Scaffold with the older version. v0.1.7 predates the manifest, so
    #    ``.scaffold-manifest.json`` must NOT exist after setup.
    setup_result = run_cataforge(py, "setup", "--platform", "claude-code", cwd=project)
    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr
    assert not (project / ".cataforge" / ".scaffold-manifest.json").is_file(), (
        f"baseline {BASELINE_VERSION} unexpectedly wrote a scaffold manifest — "
        "update BASELINE_VERSION to a release that really predates the manifest."
    )

    # 3. Overlay the locally-built wheel (simulates `pip install --upgrade`).
    pip_install(py, "--force-reinstall", str(built_wheel))

    # 4. Dry-run: without a manifest, every changed file should classify as
    #    [drift] (or [unchanged] if the scaffold file is byte-identical
    #    across versions). We expect at least one [drift] entry because the
    #    two versions differ substantively.
    dry = run_cataforge(py, "upgrade", "apply", "--dry-run", cwd=project)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "[drift]" in dry.stdout, (
        f"cross-version dry-run should classify at least one file as [drift] "
        f"when no manifest exists. Output:\n{dry.stdout}"
    )

    # 5. Real apply: after it runs, the manifest must exist and
    #    ``upgrade check`` must report parity.
    apply_result = run_cataforge(py, "upgrade", "apply", cwd=project)
    assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr
    assert (project / ".cataforge" / ".scaffold-manifest.json").is_file()

    check = run_cataforge(py, "upgrade", "check", cwd=project)
    assert check.returncode == 0, check.stdout + check.stderr
    assert "Scaffold is up to date" in check.stdout, check.stdout
