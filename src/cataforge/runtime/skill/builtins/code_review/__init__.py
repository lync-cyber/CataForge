"""Built-in code-review skill.

Layer 1 (engine + checks packages) + Layer 2 (semantic, in SKILL.md
prose) + review/scan operation modes behind ``code_check.py``.

``CHECKS_MANIFEST`` is the contract for `framework-review` to verify that
the skill's prose ``## Layer 1 检查项`` section stays in lockstep with
what the script actually runs. It is derived from the check registry —
never add hand-written entries here; register a :class:`CheckSpec` in the
``checks`` package instead.
"""

from __future__ import annotations

from cataforge.runtime.skill.builtins.code_review import checks as _checks  # noqa: F401
from cataforge.runtime.skill.builtins.code_review.engine.registry import derive_manifest

CHECKS_MANIFEST: tuple[dict[str, str], ...] = derive_manifest()

__all__ = ["CHECKS_MANIFEST"]
