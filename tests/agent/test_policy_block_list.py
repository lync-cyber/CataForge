from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.agent.translator import translate_agent_md


def test_codex_block_list_policy_compiles_to_read_only() -> None:
    source = (
        "---\n"
        "name: reviewer\n"
        "tools:\n"
        "  - file_read\n"
        "  - file_grep\n"
        "disallowedTools:\n"
        "  - file_write\n"
        "  - file_edit\n"
        "---\n"
        "Review only.\n"
    )

    translated = translate_agent_md(source, get_adapter("codex"))

    assert "sandbox_mode: read-only" in translated
    assert "  - file_write" not in translated
    assert "  - file_edit" not in translated
