"""Static contract: ``block`` hooks never use @hook_main; ``observe`` do.

The ``hook_main`` decorator converts all uncaught exceptions into ``exit 0``
so observer hooks don't block the user's workflow when they crash.  Blocker
hooks must do the opposite: they rely on ``sys.exit(2)`` propagating to the
IDE to signal a refusal.  Wrapping a blocker in ``@hook_main`` is fine
(``SystemExit`` is re-raised) but an accidental ``raise`` inside one would
turn a block into an exit 0, silently allowing the command to run.

We enforce the rule with a static file scan rather than a runtime check so
a grep for "@hook_main" in PR review stays meaningful.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

HOOKS_YAML = (
    Path(__file__).resolve().parents[2]
    / ".cataforge"
    / "hooks"
    / "hooks.yaml"
)
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "cataforge"
    / "hook"
    / "scripts"
)


def _load_spec() -> dict:
    with open(HOOKS_YAML, encoding="utf-8") as f:
        return dict(yaml.safe_load(f))


def _uses_hook_main(script_path: Path) -> bool:
    """True when ``@hook_main`` decorates any function in the file."""
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                name = (
                    deco.id if isinstance(deco, ast.Name)
                    else deco.attr if isinstance(deco, ast.Attribute)
                    else None
                )
                if name == "hook_main":
                    return True
    return False


def _declared_scripts() -> list[tuple[str, str]]:
    """Return (script_name, type) pairs declared in hooks.yaml."""
    spec = _load_spec()
    out: list[tuple[str, str]] = []
    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            script = str(entry.get("script", "")).replace(".py", "")
            if not script or script.startswith("custom:"):
                continue
            out.append((script, str(entry.get("type", "observe"))))
    return out


def test_block_scripts_do_not_use_hook_main() -> None:
    """Exit 2 from a block script must reach the IDE — swallowing exceptions
    in @hook_main would break that path if an exception fires inside."""
    offenders: list[str] = []
    for script, hook_type in _declared_scripts():
        if hook_type != "block":
            continue
        path = SCRIPTS_DIR / f"{script}.py"
        if not path.is_file():
            continue
        if _uses_hook_main(path):
            offenders.append(script)
    assert not offenders, (
        f"block-type hook scripts must not use @hook_main: {offenders}. "
        "See tests/hook/test_script_contract.py for rationale."
    )


def test_observe_scripts_use_hook_main() -> None:
    """Observer hooks crashing without @hook_main would exit non-zero,
    which some IDEs interpret as "block the tool call" — a silent
    misbehaviour.  @hook_main guarantees exit 0 + error log."""
    offenders: list[str] = []
    for script, hook_type in _declared_scripts():
        if hook_type != "observe":
            continue
        path = SCRIPTS_DIR / f"{script}.py"
        if not path.is_file():
            continue
        if not _uses_hook_main(path):
            offenders.append(script)
    assert not offenders, (
        f"observe-type hook scripts must use @hook_main: {offenders}. "
        "Wrap `main()` with the decorator so crashes log + exit 0 instead "
        "of propagating as non-zero to the IDE."
    )
