"""Hook bridge degradation strategy materialisation.

Pins :func:`cataforge.runtime.hook.bridge.apply_degradation` behaviour for the four
supported strategies and the unknown-strategy fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import cataforge.runtime.hook.bridge as bridge


class _StubAdapter:
    """Minimal surface used by :func:`apply_degradation`.

    Mirrors the stub in ``test_bridge_skips.py`` but is local so changes to
    one suite cannot accidentally break the other.
    """

    platform_id = "test"

    def __init__(self, degradation: dict[str, str]) -> None:
        self._degradation = degradation


def _patch_templates(
    monkeypatch: pytest.MonkeyPatch,
    templates: dict[str, dict[str, str]],
) -> None:
    monkeypatch.setattr(
        bridge,
        "get_degraded_hooks",
        lambda _adapter: [
            {
                "name": name,
                "strategy": template.get("strategy", "skip"),
                "coverage": "none",
                "content": template.get("content", ""),
                "asset": None,
                "reason": template.get("reason", ""),
            }
            for name, template in templates.items()
        ],
    )


def test_unknown_strategy_emits_warn_not_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: prior versions silently dropped any strategy other
    than ``rules_injection`` / ``skip``. Surface it as a WARN action so the
    deploy log makes the gap observable."""
    _patch_templates(
        monkeypatch,
        {
            "fictional_hook": {
                "strategy": "bogus_strategy",
                "content": "anything",
                "reason": "",
            }
        },
    )

    adapter = _StubAdapter(degradation={"fictional_hook": "degraded"})
    actions = bridge.apply_degradation(
        adapter, tmp_path, output_dir=tmp_path / "generated", dry_run=False
    )

    warn_lines = [a for a in actions if a.startswith("WARN:")]
    assert len(warn_lines) == 1, actions
    assert "fictional_hook" in warn_lines[0]
    assert "bogus_strategy" in warn_lines[0]
    assert "Known strategies" in warn_lines[0]

    # No file should be created for an unknown strategy.
    assert not (tmp_path / ".cataforge" / "platforms" / "test" / "overrides" / "rules").exists()


def test_prompt_instruction_writes_aggregate_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``prompt_instruction`` content should land in
    ``overrides/rules/auto-prompt-instructions.md`` with per-hook section
    headers so the deploy artefact is self-describing."""
    _patch_templates(
        monkeypatch,
        {
            "log_agent_dispatch": {
                "strategy": "prompt_instruction",
                "content": "run: cataforge event log --event agent_dispatch",
                "reason": "",
            }
        },
    )

    adapter = _StubAdapter(degradation={"log_agent_dispatch": "degraded"})
    output_dir = tmp_path / "generated"
    actions = bridge.apply_degradation(adapter, tmp_path, output_dir=output_dir, dry_run=False)

    out_path = output_dir / "auto-prompt-instructions.md"
    assert out_path.is_file()
    body = out_path.read_text(encoding="utf-8")
    assert "# Auto-generated Agent Instructions" in body
    assert "## log_agent_dispatch" in body
    assert "cataforge event log --event agent_dispatch" in body
    assert any("prompt_instruction →" in a for a in actions), actions


def test_prompt_checklist_writes_aggregate_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``prompt_checklist`` content should land in its own file separate
    from ``prompt_instruction`` so the deploy artefacts are categorised."""
    _patch_templates(
        monkeypatch,
        {
            "validate_agent_result": {
                "strategy": "prompt_checklist",
                "content": "- [ ] outputs lists every produced file",
                "reason": "",
            }
        },
    )

    adapter = _StubAdapter(degradation={"validate_agent_result": "degraded"})
    output_dir = tmp_path / "generated"
    actions = bridge.apply_degradation(adapter, tmp_path, output_dir=output_dir, dry_run=False)

    out_path = output_dir / "auto-prompt-checklists.md"
    assert out_path.is_file()
    body = out_path.read_text(encoding="utf-8")
    assert "Self-check Checklists" in body
    assert "## validate_agent_result" in body
    assert "outputs lists every produced file" in body
    assert any("prompt_checklist →" in a for a in actions), actions


def test_each_strategy_writes_distinct_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three file-producing strategies must not share an output file —
    mixing safety rules with self-check checklists would erase the
    distinction the strategy names exist to make."""
    _patch_templates(
        monkeypatch,
        {
            "guard_dangerous": {
                "strategy": "rules_injection",
                "content": "rule A",
                "reason": "",
            },
            "log_agent_dispatch": {
                "strategy": "prompt_instruction",
                "content": "instruction B",
                "reason": "",
            },
            "validate_agent_result": {
                "strategy": "prompt_checklist",
                "content": "checklist C",
                "reason": "",
            },
        },
    )

    adapter = _StubAdapter(
        degradation={
            "guard_dangerous": "degraded",
            "log_agent_dispatch": "degraded",
            "validate_agent_result": "degraded",
        }
    )
    output_dir = tmp_path / "generated"
    actions = bridge.apply_degradation(adapter, tmp_path, output_dir=output_dir, dry_run=False)

    base = output_dir
    assert (base / "auto-safety-degradation.md").is_file()
    assert (base / "auto-prompt-instructions.md").is_file()
    assert (base / "auto-prompt-checklists.md").is_file()

    # Each output file gets exactly one action line announcing it.
    assert sum(1 for a in actions if "rules_injection →" in a) == 1
    assert sum(1 for a in actions if "prompt_instruction →" in a) == 1
    assert sum(1 for a in actions if "prompt_checklist →" in a) == 1


def test_dry_run_writes_no_files_but_reports_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dry_run keeps behaviour previewable for ``cataforge deploy --dry-run``."""
    _patch_templates(
        monkeypatch,
        {
            "log_agent_dispatch": {
                "strategy": "prompt_instruction",
                "content": "x",
                "reason": "",
            }
        },
    )

    adapter = _StubAdapter(degradation={"log_agent_dispatch": "degraded"})
    output_dir = tmp_path / "generated"
    actions = bridge.apply_degradation(adapter, tmp_path, output_dir=output_dir, dry_run=True)

    assert any("would stage prompt_instruction" in a for a in actions), actions
    assert not output_dir.exists()


def test_known_strategies_set_matches_aggregate_outputs_plus_skip() -> None:
    """If a new file-producing strategy is added, both
    :data:`KNOWN_DEGRADATION_STRATEGIES` and
    :data:`_AGGREGATE_OUTPUTS` must be updated together."""
    aggregate_keys = {item[0] for item in bridge._AGGREGATE_OUTPUTS}
    assert aggregate_keys | {"skip"} == bridge.KNOWN_DEGRADATION_STRATEGIES
