"""Deploy-method mixins for :class:`PlatformAdapter`.

Each mixin is a thin shell whose ``deploy_*`` method delegates to the matching
function in :mod:`cataforge.runtime.deploy.steps`, passing ``self`` as the
adapter. The deploy algorithms live in the runtime step modules; these mixins
keep ``adapter.deploy_*`` callable for direct callers.
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
