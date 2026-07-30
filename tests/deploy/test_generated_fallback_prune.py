from __future__ import annotations

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy.steps.commands_rules import deploy_overrides_rules


def test_native_policy_prunes_previously_owned_generated_fallback(tmp_path) -> None:
    target_rel = ".codex/rules/auto-prompt-instructions.md"
    target = tmp_path / target_rel
    target.parent.mkdir(parents=True)
    target.write_text("stale generated fallback")

    actions = deploy_overrides_rules(
        get_adapter("codex"),
        tmp_path,
        prior_manifest={target_rel},
    )

    assert not target.exists()
    assert len(actions) == 1
    assert target_rel in actions[0]


def test_generated_fallback_pruning_never_removes_unowned_file(tmp_path) -> None:
    target_rel = ".codex/rules/auto-prompt-instructions.md"
    target = tmp_path / target_rel
    target.parent.mkdir(parents=True)
    target.write_text("user-owned content")

    actions = deploy_overrides_rules(
        get_adapter("codex"),
        tmp_path,
        prior_manifest=set(),
    )

    assert target.read_text() == "user-owned content"
    assert actions == []
