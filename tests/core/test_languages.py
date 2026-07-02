"""Tests for the language registry SSOT (core.languages), incl. anti-drift parity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.config import ConfigManager
from cataforge.core.languages import (
    LANGUAGES,
    active_languages,
    canonical_id,
    detect_languages,
    known_languages,
    normalize,
)
from cataforge.runtime.skill.rules.loader import discover_rules


def test_known_languages_include_rule_ids() -> None:
    # The ids the wiring/e2e rules use must be registered.
    assert {"python", "js-ts"} <= set(known_languages())


@pytest.mark.parametrize(
    "marker,expected",
    [
        ("pyproject.toml", "python"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("package.json", "js-ts"),
        ("pom.xml", "java"),
    ],
)
def test_detect_by_marker(tmp_path: Path, marker: str, expected: str) -> None:
    (tmp_path / marker).write_text("x", encoding="utf-8")
    assert detect_languages(tmp_path) == [expected]


def test_detect_glob_marker_csharp(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").write_text("<Project/>", encoding="utf-8")
    assert detect_languages(tmp_path) == ["csharp"]


def test_detect_multiple_sorted(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[x]", encoding="utf-8")
    assert detect_languages(tmp_path) == ["go", "python"]


def test_detect_none(tmp_path: Path) -> None:
    assert detect_languages(tmp_path) == []


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("typescript", "js-ts"),
        ("TypeScript", "js-ts"),
        ("javascript", "js-ts"),
        ("golang", "go"),
        ("py", "python"),
        ("c#", "csharp"),
        ("rs", "rust"),
        ("elixir", "elixir"),  # unknown passes through lowercased
    ],
)
def test_canonical_id(raw: str, canonical: str) -> None:
    assert canonical_id(raw) == canonical


def test_normalize_dedupes_and_orders() -> None:
    assert normalize(["TypeScript", "ts", "python", "js"]) == ["js-ts", "python"]


def _project(tmp_path: Path, languages: list[str] | None) -> ConfigManager:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    fw: dict = {"version": "0.1.0", "runtime": {"platform": "claude-code"}}
    if languages is not None:
        fw["project"] = {"languages": languages}
    (cf / "framework.json").write_text(json.dumps(fw), encoding="utf-8")
    return ConfigManager(tmp_path)


def test_active_languages_declared_wins(tmp_path: Path) -> None:
    # Declared (with a synonym) is authoritative and normalised; markers ignored.
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    cfg = _project(tmp_path, ["TypeScript"])
    assert active_languages(cfg) == ["js-ts"]


def test_active_languages_detect_fallback(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
    cfg = _project(tmp_path, [])  # declared empty → fall back to detection
    assert active_languages(cfg) == ["rust"]


def test_active_languages_empty_when_nothing(tmp_path: Path) -> None:
    cfg = _project(tmp_path, None)
    assert active_languages(cfg) == []


# ---- anti-drift parity: builtin rules ⟷ registry --------------------------


@pytest.mark.parametrize(
    "skill_id,module",
    [
        ("code-review", "cataforge.runtime.skill.builtins.code_review"),
        ("testing", "cataforge.runtime.skill.builtins.testing"),
    ],
)
def test_builtin_rule_languages_match_registry(skill_id: str, module: str) -> None:
    """Every builtin rule YAML's language id + extensions must live in the
    registry, so adding a rule for a new language can't silently drift from
    the language SSOT."""
    rules = discover_rules(skill_id, builtin_module=module)
    assert rules, f"expected builtin rules for {skill_id}"
    for (rule_type, language), spec in rules.items():
        if spec.scope == "project":
            continue  # project-scope specs are language-agnostic by contract
        assert language in LANGUAGES, (
            f"{skill_id}/{rule_type}: rule language {language!r} is not in the "
            f"registry (cataforge.core.languages.LANGUAGES) — add it there"
        )
        unknown_exts = spec.extensions - LANGUAGES[language].extensions
        assert not unknown_exts, (
            f"{skill_id}/{rule_type}/{language}: rule declares extensions "
            f"{sorted(unknown_exts)} that the registry does not map to "
            f"{language!r}; reconcile cataforge.core.languages.LANGUAGES"
        )


# ---- lang-ref skills ship language references (anti-empty-shell) -----------

# Skills whose responsibility is language-shaped — each ships per-language
# ``references/lang-<lang>.md`` that its SKILL.md loads for the active language.
_LANG_REF_SKILLS = (
    "arc-design",
    "code-review",
    "testing",
    "tdd-engine",
    "debug",
    "deploy-config",
)
# Languages with shipped builtin references. Must stay a subset of the registry.
_BUILTIN_FRAGMENT_LANGS = ("python", "js-ts", "go", "rust", "csharp", "java")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_builtin_fragment_langs_are_registry_ids() -> None:
    assert set(_BUILTIN_FRAGMENT_LANGS) <= set(known_languages())


@pytest.mark.parametrize("skill_id", _LANG_REF_SKILLS)
def test_lang_ref_skill_ships_all_builtin_references(skill_id: str) -> None:
    refs_dir = _REPO_ROOT / ".cataforge" / "skills" / skill_id / "references"
    for lang in _BUILTIN_FRAGMENT_LANGS:
        ref = refs_dir / f"lang-{lang}.md"
        assert ref.is_file(), f"missing reference {ref}"
        assert ref.read_text(encoding="utf-8").strip(), f"empty reference {ref}"
