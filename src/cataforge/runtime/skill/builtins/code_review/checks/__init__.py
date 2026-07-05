"""Layer 1 checks — importing this package populates the registry.

Import order is execution order: gating external linters first, then the
wiring / UI-fidelity pattern checks, then the informational scan probes.
"""

from cataforge.runtime.skill.builtins.code_review.checks import (  # noqa: F401
    api_surface,
    arch_guard,
    complexity,
    config_keys,
    duplication,
    external_tools,
    pragma_inventory,
    probes,
    ui_fidelity,
    wiring,
)
