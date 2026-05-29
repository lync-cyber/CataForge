"""Deployment algorithm mixins for :class:`PlatformAdapter`.

These mixins carry the per-resource deploy logic (agents / instructions /
skills / commands+rules / mcp). They keep ``self`` semantics so concrete
adapters can override individual deploy methods and call ``super()``; the
config/capability surface stays on
:class:`~cataforge.adapter.platform.adapter.PlatformAdapter`.

Each concern lives in its own submodule; this package re-exports the mixin
classes so ``from cataforge.adapter.platform._deploy_mixins import (...)``
keeps working as a single import surface.
"""

from __future__ import annotations

from cataforge.adapter.platform._deploy_mixins.agents import AgentDeployMixin
from cataforge.adapter.platform._deploy_mixins.commands_rules import CommandRulesDeployMixin
from cataforge.adapter.platform._deploy_mixins.instructions import InstructionDeployMixin
from cataforge.adapter.platform._deploy_mixins.mcp import McpDeployMixin
from cataforge.adapter.platform._deploy_mixins.skills import SkillDeployMixin

__all__ = [
    "AgentDeployMixin",
    "CommandRulesDeployMixin",
    "InstructionDeployMixin",
    "McpDeployMixin",
    "SkillDeployMixin",
]
