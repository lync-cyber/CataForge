"""Single pipeline serving both operation modes (review / scan).

Checks run in registration order (gating lint before informational
probes). ``--focus`` semantics differ by mode: review converges every
check onto the requested categories; scan never disables gating checks —
focus only filters the informational probes.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import PipelineResult
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CATEGORIES,
    checks_for_mode,
)


class FocusError(ValueError):
    """Raised when --focus carries a token outside the category taxonomy."""


def validate_focus(focus: list[str] | None) -> None:
    if not focus:
        return
    invalid = [c for c in focus if c not in CATEGORIES]
    if invalid:
        raise FocusError(f"无效的 --focus 值: {invalid}; 可选: {sorted(CATEGORIES)}")


def execute(
    mode: str,
    target: Path,
    *,
    fix: bool = False,
    focus: list[str] | None = None,
    project_root: Path | None = None,
    tool_cache: dict[str, bool] | None = None,
) -> PipelineResult:
    """Run every registered check for *mode* over *target*.

    Raises :class:`FocusError` on an invalid focus token; the caller maps
    it to exit 2. Target existence is the caller's concern (exit 2 there
    too) so this stays a pure orchestration function.
    """
    validate_focus(focus)
    selected = checks_for_mode(mode)
    if focus:
        wanted = set(focus)
        if mode == "review":
            selected = [c for c in selected if c.category in wanted]
        else:
            selected = [
                c for c in selected if c.severity != "informational" or c.category in wanted
            ]

    ctx = CheckContext(
        target=target,
        project_root=project_root,
        mode=mode,
        fix=fix,
        tool_cache=tool_cache if tool_cache is not None else {},
    )
    result = PipelineResult(mode=mode, target=str(target))
    for check in selected:
        result.checks_run.append(check.id)
        result.findings.extend(check.run(ctx))
    return result
