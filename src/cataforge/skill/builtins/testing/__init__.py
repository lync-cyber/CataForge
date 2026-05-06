"""Built-in testing skill.

Layer 1 (e2e backdoor scan + real-input presence) + Layer 2 (semantic,
in SKILL.md prose). ``CHECKS_MANIFEST`` is the contract for
``framework-review`` to verify that the skill's prose
``## Layer 1 检查项`` section stays in lockstep with what the script
actually runs.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "e2e_backdoor_scan",
        "title": (
            "e2e 后门正则扫描 — window.__*__ / ?e2e=1 / setStore / "
            "setAst(JSON.parse) 等命中 → WARN"
        ),
        "severity": "warn",
    },
    {
        "id": "e2e_real_input_presence",
        "title": (
            "e2e 套件至少含一处真实交互调用 (keyboard.type / page.fill / "
            "page.click / .type)；无任何 → WARN"
        ),
        "severity": "warn",
    },
)
