"""Bootstrap planning service — decides what setup/upgrade/deploy/doctor must do.

Pure inspection of on-disk product state (scaffold version, manifest hashes,
``.deploy-state``): :func:`build_plan` returns a :class:`Plan` and writes
nothing. The ``cataforge bootstrap`` command owns rendering the plan and
executing the steps; keeping the decision logic here lets it be unit-tested
without a Click context and keeps the command a thin parse→call→render layer.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING

from cataforge.adapter.platform.conformance import ALL_PLATFORMS
from cataforge.core.errors import ConfigError
from cataforge.core.version import parse_semver

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


class StepPlan:
    """One pipeline step's skip/run decision and the reason behind it.

    Kept dataclass-free to stay aligned with the plain-dict style used
    elsewhere in the CLI (cf. the ``ctx.obj`` pattern in main.py).
    """

    __slots__ = ("name", "action", "reason")

    def __init__(self, name: str, action: str, reason: str) -> None:
        self.name = name
        # action ∈ {"skip", "run", "error"} — "error" is terminal (reported
        # up-front before any writes).
        self.action = action
        self.reason = reason


class Plan:
    __slots__ = ("steps", "target_platform", "error")

    def __init__(self) -> None:
        self.steps: list[StepPlan] = []
        self.target_platform: str | None = None
        self.error: str | None = None

    def add(self, name: str, action: str, reason: str) -> None:
        self.steps.append(StepPlan(name, action, reason))

    def any_writes(self) -> bool:
        return any(s.action == "run" for s in self.steps if s.name != "doctor")


def build_plan(
    cfg: ConfigManager,
    *,
    requested_platform: str | None,
    requested_strategy: str | None = None,
) -> Plan:
    """Inspect on-disk state and decide what each step must do."""
    from cataforge.core.scaffold import classify_scaffold_files

    plan = Plan()

    try:
        installed = _pkg_version("cataforge")
    except PackageNotFoundError:
        installed = None

    scaffold_dir = cfg.paths.cataforge_dir
    scaffold_exists = scaffold_dir.is_dir() and cfg.paths.framework_json.is_file()

    # Step 1: setup (scaffold).
    if not scaffold_exists:
        if requested_platform is None:
            plan.error = (
                "Fresh install detected (no .cataforge/). "
                "Rerun with `--platform <id>`, "
                f"e.g. --platform {ALL_PLATFORMS[0]}."
            )
            plan.add("setup", "error", plan.error)
            plan.target_platform = None
            # Still enumerate downstream steps as "blocked" so the user
            # sees the full picture.
            plan.add("upgrade", "skip", "blocked on setup")
            plan.add("deploy", "skip", "blocked on setup")
            plan.add("doctor", "skip", "blocked on setup")
            return plan
        plan.add(
            "setup",
            "run",
            f"no .cataforge/ at {scaffold_dir} — fresh scaffold",
        )
        plan.target_platform = requested_platform
        plan.add("upgrade", "skip", "fresh scaffold already current")
        plan.add("deploy", "run", "fresh install — initial deploy required")
        _append_kg_init(plan, cfg, requested_strategy, scaffold_exists=False)
        if requested_platform is not None:
            _append_doctor(plan)
        return plan

    plan.add(
        "setup",
        "skip",
        f"scaffold present (version {cfg.version})",
    )

    # Decide the target platform for downstream steps — explicit flag wins,
    # else the recorded runtime.platform.
    current_platform = cfg.runtime_platform
    plan.target_platform = requested_platform or current_platform
    if (
        requested_platform is not None
        and current_platform
        and requested_platform != current_platform
    ):
        plan.error = (
            f"--platform={requested_platform!r} conflicts with "
            f"framework.json runtime.platform={current_platform!r}. "
            "Run `cataforge setup --platform <id> --show-diff` explicitly "
            "to change the target platform — bootstrap will not rewrite it."
        )
        plan.add("upgrade", "error", plan.error)
        plan.add("deploy", "error", plan.error)
        plan.add("doctor", "skip", "blocked on platform mismatch")
        return plan

    # Step 2: upgrade (scaffold refresh).
    #
    # We trigger upgrade on either:
    #   (a) manifest drift — a scaffold file disagrees with the bundled copy;
    #   (b) installed package semver > recorded scaffold version — the user
    #       just ran `pip install -U cataforge` and framework.json (a preserved
    #       file) still advertises the old version.
    #
    # NOT triggering when ``installed < scaffold`` is intentional: editable
    # dev installs often have stale package metadata below the source tree's
    # __version__, and that case is harmless.
    classified = classify_scaffold_files(scaffold_dir)
    drifted = [s for _, s in classified if s in ("update", "user-modified", "drift", "new")]
    installed_newer = installed is not None and _semver_newer(installed, cfg.version)

    if drifted or installed_newer:
        from cataforge.core.tallies import classify_tallies

        tallies = classify_tallies(classified)
        parts = [
            f"{count} {status}"
            for status, count in sorted(tallies.items())
            if status in ("update", "user-modified", "drift", "new")
        ]
        summary = ", ".join(parts) if parts else "version bump only"
        if installed_newer:
            summary = f"installed={installed} > scaffold={cfg.version}; {summary}"
        plan.add("upgrade", "run", f"scaffold refresh required ({summary})")
    else:
        plan.add("upgrade", "skip", "scaffold manifest matches bundled package")

    # Step 3: deploy.
    _plan_deploy(plan, cfg)

    _append_kg_init(plan, cfg, requested_strategy, scaffold_exists=True)
    _append_doctor(plan)
    return plan


def _plan_deploy(plan: Plan, cfg: ConfigManager) -> None:
    """Decide the deploy step from the recorded ``.deploy-state``."""
    deploy_state_file = cfg.paths.deploy_state
    upgrade_running = plan.steps[-1].action == "run"  # upgrade step just above
    if not deploy_state_file.is_file():
        plan.add("deploy", "run", "never deployed (.deploy-state missing)")
        return

    import json as _json

    # Distinguish "missing" (legitimate first-deploy signal) from "corrupted"
    # (a crash during a prior deploy that left truncated JSON). Both would
    # otherwise flow into ``state = {}`` and silently re-deploy instead of
    # telling the user the state file is busted.
    try:
        text = deploy_state_file.read_text()
    except OSError as exc:
        raise ConfigError(
            f"deploy state at {deploy_state_file} is unreadable: {exc}. "
            f"Remove it and rerun, or run `cataforge deploy --rebuild` to start clean."
        ) from exc
    try:
        state = _json.loads(text)
    except _json.JSONDecodeError as exc:
        raise ConfigError(
            f"deploy state at {deploy_state_file} is corrupted ({exc}). "
            f"Remove it and rerun, or run `cataforge deploy --rebuild` to start clean."
        ) from exc
    deployed_platform = state.get("platform")
    if deployed_platform != plan.target_platform:
        plan.add(
            "deploy",
            "run",
            f"platform changed: deployed={deployed_platform} → target={plan.target_platform}",
        )
    elif upgrade_running:
        plan.add("deploy", "run", "scaffold refreshed — IDE artefacts must be re-rendered")
    else:
        plan.add("deploy", "skip", f"{deployed_platform} already deployed")


def _append_doctor(plan: Plan) -> None:
    plan.add("doctor", "run", "verification gate")


def _append_kg_init(
    plan: Plan, cfg: ConfigManager, requested_strategy: str | None, *, scaffold_exists: bool
) -> None:
    """Preview the kg-init step for a kg-first project that lacks a store.

    Mirrors ``bootstrap_cmd._maybe_init_kg_store`` so ``--dry-run`` surfaces
    it; omitted under doc-only (no graph backend). Execution recomputes the
    decision post-setup, so this is a preview, not the authority.
    """
    from cataforge.domain.kg._dispatch import DEFAULT_CONTEXT_STRATEGY

    strategy = requested_strategy
    if strategy is None:
        strategy = DEFAULT_CONTEXT_STRATEGY
        if scaffold_exists:
            raw = cfg.load_raw()
            strategy = (raw.get("context") or {}).get("strategy") or DEFAULT_CONTEXT_STRATEGY
    if strategy != "kg-first":
        return
    if cfg.paths.kg_store_dir.exists():
        plan.add("kg-init", "skip", "store present")
    else:
        plan.add("kg-init", "run", "kg-first strategy — store absent")


def _semver_newer(a: str, b: str) -> bool:
    """True iff *a* is a semver strictly newer than *b*.

    Non-numeric versions fall back to plain string inequality — we'd rather
    be conservative (trigger upgrade) than silently skip a real release
    just because someone typed "0.2.0rc1".

    Special case: when *b* is a placeholder like ``0.0.0-template`` (used
    in source-repo framework.json that hasn't been stamped with a real
    package version yet), do NOT treat any installed version as "newer".
    Otherwise dogfood developers always see a phantom upgrade plan because
    their installed package (e.g. 0.1.12) compares > 0.0.0. The placeholder
    semantically means "this scaffold has not been materialised by setup
    yet; defer the comparison until it has".
    """
    if b.startswith("0.0.0-"):
        return False

    ta = parse_semver(a)
    tb = parse_semver(b)
    if ta is None or tb is None:
        return a != b
    return ta > tb
