"""Load-time validation contract for :class:`HooksSpec`.

Locks the T-2 guarantee: ``load_hooks_spec`` validates the canonical
``hooks.yaml`` against :class:`HooksSpec`, so a structurally malformed spec
(``schema_version`` of the wrong type, ``hooks`` that is not an event→list
mapping, a hook entry missing ``script`` …) fails at load with a
``pydantic.ValidationError`` naming the field — while the shipped spec and a
minimal spec keep loading.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from cataforge.runtime.hook.bridge import load_hooks_spec
from cataforge.runtime.hook.hooks_schema import HooksSpec


def _write_spec(tmp_path: Path, data: dict) -> Path:
    spec_path = tmp_path / "hooks.yaml"
    spec_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return spec_path


# ---- shipped + valid specs load --------------------------------------


def test_shipped_hooks_spec_validates() -> None:
    """The real ``.cataforge/hooks/hooks.yaml`` loads as a plain mapping."""
    spec = load_hooks_spec()
    assert isinstance(spec, dict)
    assert "hooks" in spec
    assert "degradation_templates" in spec


def test_load_returns_raw_dict_unchanged(tmp_path: Path) -> None:
    """Validation gates but does not rewrite the downstream dict contract."""
    raw = {
        "schema_version": 2,
        "hooks": {"PreToolUse": [{"script": "guard_dangerous", "type": "block"}]},
    }
    spec = load_hooks_spec(_write_spec(tmp_path, raw))
    assert spec == raw


def test_minimal_spec_validates(tmp_path: Path) -> None:
    """A spec with no sections takes defaults rather than crashing."""
    spec = load_hooks_spec(_write_spec(tmp_path, {}))
    assert spec == {}
    model = HooksSpec.model_validate({})
    assert model.schema_version == 1
    assert model.hooks == {}
    assert model.degradation_templates == {}


# ---- malformed specs fail at load with a field-level error -----------


def test_bad_schema_version_type_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc:
        load_hooks_spec(_write_spec(tmp_path, {"schema_version": "two"}))
    assert "schema_version" in str(exc.value)


def test_hook_entry_missing_script_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc:
        load_hooks_spec(_write_spec(tmp_path, {"hooks": {"PreToolUse": [{"type": "block"}]}}))
    assert "script" in str(exc.value)


def test_hooks_not_a_mapping_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc:
        load_hooks_spec(_write_spec(tmp_path, {"hooks": ["guard_dangerous"]}))
    assert "hooks" in str(exc.value)


def test_degradation_template_missing_strategy_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc:
        load_hooks_spec(
            _write_spec(tmp_path, {"degradation_templates": {"guard_dangerous": {"reason": "x"}}})
        )
    assert "strategy" in str(exc.value)


def test_legacy_version_key_tolerated(tmp_path: Path) -> None:
    """A minimal/legacy spec carrying only ``version`` keeps loading — the
    bridge never reads it, so rejecting it would break older scaffolds."""
    spec = load_hooks_spec(_write_spec(tmp_path, {"version": 1}))
    assert spec == {"version": 1}
    model = HooksSpec.model_validate({"version": 1})
    assert model.schema_version == 1


def test_non_mapping_root_still_raises_value_error(tmp_path: Path) -> None:
    """A top-level non-mapping keeps the existing ``ValueError`` guard."""
    spec_path = tmp_path / "hooks.yaml"
    spec_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_hooks_spec(spec_path)
