"""Canonical programming-language registry — the language-context SSOT.

One place defines every language CataForge knows about: its canonical id
(the same string the wiring/e2e rule YAMLs put in their ``language:`` field),
root-level detection markers, and source extensions. Everything that needs to
reason about "which languages" — project declaration in ``framework.json``
(``project.languages``), auto-detection, and (downstream) language-aware rule
selection — reads from here so the set never drifts.

A parity test (``tests/core/test_languages.py``) asserts every builtin rule
YAML's ``language`` id and extensions stay consistent with this registry, so
adding a rule for a new language fails loudly until the registry is updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


@dataclass(frozen=True)
class Language:
    """One supported language. ``id`` is canonical and matches rule YAMLs."""

    id: str
    display: str
    markers: tuple[str, ...]
    extensions: frozenset[str]


# Canonical ids MUST match the ``language:`` field used by the builtin
# wiring/e2e rule YAMLs (e.g. ``js-ts``, ``python``). The parity test enforces
# this. Markers are matched at the project root (glob patterns allowed).
LANGUAGES: dict[str, Language] = {
    "python": Language(
        "python", "Python",
        ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"),
        frozenset({".py", ".pyi"}),
    ),
    "js-ts": Language(
        "js-ts", "JavaScript / TypeScript",
        ("package.json", "tsconfig.json", "deno.json"),
        frozenset({".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}),
    ),
    "go": Language("go", "Go", ("go.mod",), frozenset({".go"})),
    "rust": Language("rust", "Rust", ("Cargo.toml",), frozenset({".rs"})),
    "csharp": Language("csharp", "C#", ("*.csproj", "*.sln"), frozenset({".cs"})),
    "java": Language(
        "java", "Java",
        ("pom.xml", "build.gradle", "build.gradle.kts"),
        frozenset({".java"}),
    ),
}

# User-facing synonyms → canonical id. A declaration of ``typescript`` or
# ``golang`` normalises to the canonical ``js-ts`` / ``go`` so the rest of the
# system only ever sees registry ids.
ALIASES: dict[str, str] = {
    "py": "python", "python3": "python",
    "ts": "js-ts", "typescript": "js-ts", "js": "js-ts", "javascript": "js-ts",
    "node": "js-ts", "nodejs": "js-ts",
    "golang": "go",
    "rs": "rust",
    "cs": "csharp", "c#": "csharp", "dotnet": "csharp", ".net": "csharp",
}


def known_languages() -> list[str]:
    """Sorted canonical language ids in the registry."""
    return sorted(LANGUAGES)


def canonical_id(name: str) -> str:
    """Normalise one language token to its canonical id (unknowns pass through)."""
    key = name.strip().lower()
    return ALIASES.get(key, key)


def normalize(names: list[str]) -> list[str]:
    """Canonicalise + de-duplicate *names*, preserving first-seen order.

    Unknown ids are kept (lowercased) rather than dropped, so a project can
    declare a language the registry does not cover yet without silent loss.
    """
    out: list[str] = []
    for name in names:
        cid = canonical_id(name)
        if cid and cid not in out:
            out.append(cid)
    return out


def detect_languages(root: Path) -> list[str]:
    """Detect languages by their root-level marker files. Sorted, deterministic."""
    found: list[str] = []
    for lang in LANGUAGES.values():
        if any(_marker_present(root, marker) for marker in lang.markers):
            found.append(lang.id)
    return sorted(found)


def active_languages(cfg: ConfigManager) -> list[str]:
    """The project's languages: explicit declaration, else marker detection.

    ``framework.json``'s ``project.languages`` is authoritative when non-empty
    (normalised to canonical ids); otherwise fall back to detecting markers
    under the project root.
    """
    declared = cfg.languages
    if declared:
        return normalize(declared)
    return detect_languages(cfg.paths.root)


def _marker_present(root: Path, marker: str) -> bool:
    if any(ch in marker for ch in "*?["):
        return any(root.glob(marker))
    return (root / marker).exists()
