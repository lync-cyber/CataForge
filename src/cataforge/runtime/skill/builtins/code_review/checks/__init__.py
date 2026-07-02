"""Layer 1 checks — importing this package populates the registry.

Import order is execution order: gating external linters first, then the
wiring / UI-fidelity pattern checks, then the informational scan probes.
"""

from cataforge.runtime.skill.builtins.code_review.checks import (  # noqa: F401
    arch_guard,
    external_tools,
    probes,
    ui_fidelity,
    wiring,
)
