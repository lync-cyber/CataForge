from __future__ import annotations

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.agent.translator import translate_agent_md


def test_translation_does_not_invent_missing_permission_fields() -> None:
    source = """---
name: reviewer
description: Reviews code without an explicit tool policy.
---

Review the requested change.
"""

    translated = translate_agent_md(source, get_adapter("codex"))

    assert "\ntools:" not in translated
    assert "\ndisallowedTools:" not in translated
