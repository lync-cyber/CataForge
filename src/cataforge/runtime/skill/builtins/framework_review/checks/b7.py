"""B7 — model_tier audit across AGENT.md and platform tier_map."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_yaml
from cataforge.core.paths import ProjectPaths
from cataforge.utils.frontmatter import split_yaml_frontmatter

from .._constants import VALID_MODEL_TIERS
from .._discover import discover_agents
from .._framework_data import agent_model_defaults, heavy_whitelist
from .._types import Report


def check_b7_model_tier(root: Path, report: Report) -> None:
    """B7: model_tier audit across AGENT.md and platform tier_map.

    Three sub-checks:

    * ``B7_model_tier_value`` (FAIL on bad enum, WARN on default mismatch) —
      every AGENT.md ``model_tier:`` value must be in
      :data:`VALID_MODEL_TIERS`; if the agent has an entry in
      ``constants.AGENT_MODEL_DEFAULTS`` and the declared tier diverges, WARN.
      Agents with no ``model_tier:`` line at all are accepted.
      ``heavy`` requires being listed in
      ``constants.AGENT_MODEL_TIER_HEAVY_WHITELIST``.
    * ``B7_legacy_model_field`` (FAIL) — source AGENT.md still uses
      ``model: <id>`` instead of ``model_tier:``. Deploy drops legacy
      ``model:`` lines, so leaving one in source makes the model selection
      silently disappear at deploy time.
    * ``B7_platform_tier_map`` (WARN) — every platform profile.yaml that
      declares ``per_agent_model: true`` and ``user_resolved: false`` must
      declare ``tier_map`` covering ``light``, ``standard``, and ``heavy``.
      Provider-agnostic (``user_resolved: true``) and shared-model platforms
      (``per_agent_model: false``) are skipped.
    """
    agents = discover_agents(root)
    defaults = agent_model_defaults(root)
    heavy_ok = heavy_whitelist(root)

    for aid, path in sorted(agents.items()):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _body = split_yaml_frontmatter(content)
        if not fm:
            continue

        tier = fm.get("model_tier")
        legacy_model = fm.get("model")

        if tier is not None:
            tier_str = str(tier).strip()
            if tier_str not in VALID_MODEL_TIERS:
                report.add(
                    "B7_model_tier_value",
                    "FAIL",
                    f"agents/{aid}",
                    f"model_tier={tier_str!r} not in {sorted(VALID_MODEL_TIERS)}",
                )
            elif tier_str == "heavy" and aid not in heavy_ok:
                report.add(
                    "B7_model_tier_value",
                    "FAIL",
                    f"agents/{aid}",
                    f"model_tier=heavy requires {aid!r} ∈ "
                    "constants.AGENT_MODEL_TIER_HEAVY_WHITELIST "
                    "(heavy tier is explicitly opt-in to control cost)",
                )
            elif aid in defaults and defaults[aid] != tier_str:
                report.add(
                    "B7_model_tier_value",
                    "WARN",
                    f"agents/{aid}",
                    f"model_tier={tier_str!r} diverges from "
                    f"AGENT_MODEL_DEFAULTS[{aid!r}]={defaults[aid]!r}; "
                    "either update the constant or restore the default",
                )

        if legacy_model is not None and tier is None:
            report.add(
                "B7_legacy_model_field",
                "FAIL",
                f"agents/{aid}",
                f"AGENT.md uses legacy 'model: {legacy_model}' but no "
                "'model_tier:' — deploy drops legacy model lines "
                "(direct migration, no transition), so the model selection "
                "would silently disappear. Replace with "
                "'model_tier: light|standard|heavy'",
            )

    platforms_dir = ProjectPaths(root).platforms_dir
    if not platforms_dir.is_dir():
        return
    for plat_dir in sorted(platforms_dir.iterdir()):
        if not plat_dir.is_dir():
            continue
        profile_path = plat_dir / "profile.yaml"
        if not profile_path.is_file():
            continue
        try:
            profile = read_yaml(profile_path)
        except ConfigError:
            continue
        if not isinstance(profile, dict):
            continue
        routing = profile.get("model_routing") or {}
        if not isinstance(routing, dict):
            continue
        if not routing.get("per_agent_model"):
            continue
        if routing.get("user_resolved"):
            continue
        tier_map = routing.get("tier_map") or {}
        if not isinstance(tier_map, dict):
            tier_map = {}
        missing = [t for t in ("light", "standard", "heavy") if t not in tier_map]
        if missing:
            report.add(
                "B7_platform_tier_map",
                "WARN",
                f"platforms/{plat_dir.name}",
                f"model_routing.tier_map missing tier(s) {missing}; deploy "
                "will silently omit `model:` for agents requesting these tiers",
            )
