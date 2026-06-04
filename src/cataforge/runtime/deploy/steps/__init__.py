"""Deployment step functions consumed by :class:`~cataforge.runtime.deploy.deployer.Deployer`.

Each step is a module-level function taking the :class:`PlatformAdapter` as
its first argument and reading the adapter's config / strategy surface to do
the per-resource deploy work (agents / instructions / skills / commands+rules /
mcp). The deployer wires them into its ordered pipeline.
"""

from __future__ import annotations

from cataforge.runtime.deploy.steps.agents import deploy_agents
from cataforge.runtime.deploy.steps.commands_rules import (
    deploy_additional_outputs,
    deploy_commands,
    deploy_overrides_rules,
    deploy_rules,
)
from cataforge.runtime.deploy.steps.instructions import deploy_instruction_files
from cataforge.runtime.deploy.steps.mcp import inject_mcp_config
from cataforge.runtime.deploy.steps.skills import deploy_skills

__all__ = [
    "deploy_additional_outputs",
    "deploy_agents",
    "deploy_commands",
    "deploy_instruction_files",
    "deploy_overrides_rules",
    "deploy_rules",
    "deploy_skills",
    "inject_mcp_config",
]
