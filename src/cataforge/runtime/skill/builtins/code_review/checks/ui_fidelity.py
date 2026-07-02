"""UI fidelity static checks — code-review Layer 1 (cross-file).

Three set-difference checks over a project's style + markup corpus,
catching defects that a green unit suite renders broken:

* ``dead_token`` (FAIL) — a declared CSS custom property with zero
  ``var()`` consumers anywhere in the corpus.
* ``unloaded_font`` (WARN) — a referenced named ``font-family`` with no
  ``@font-face`` / fontsource / Google-Fonts loader.
* ``ghost_class`` (WARN) — a class referenced in markup with no matching
  CSS selector; suppressed entirely when a utility-CSS framework is in
  use (Tailwind ``@apply`` / ``@tailwind`` generate classes off-corpus).

Consumers, loaders and class definitions resolve over the whole corpus
so a usage in another file is never a false positive; declarations are
checked only in the target files so a per-task review flags what the
reviewed change introduces, not pre-existing debt elsewhere. A file
carrying ``cataforge: allow(ui_fidelity, reason="...")`` is skipped.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding as EngineFinding
from cataforge.runtime.skill.builtins.code_review.engine.fs import iter_files
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import file_allowance
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.builtins.code_review.engine.xref import collect_keys

CHECK_ID = "code_review.ui_fidelity"

CSS_EXTS = frozenset({".css", ".scss", ".sass", ".less"})
MARKUP_EXTS = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".html", ".htm", ".astro"})
JS_EXTS = frozenset({".ts", ".js", ".tsx", ".jsx", ".mjs", ".cjs"})
UI_EXTS = CSS_EXTS | MARKUP_EXTS | JS_EXTS

# font-family keywords that name no real face and so are never "unloaded".
GENERIC_FAMILIES = frozenset(
    {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
        "ui-serif",
        "ui-sans-serif",
        "ui-monospace",
        "ui-rounded",
        "math",
        "emoji",
        "fangsong",
        "inherit",
        "initial",
        "unset",
        "revert",
        "revert-layer",
        "-apple-system",
        "blinkmacsystemfont",
    }
)

_DECL_TOKEN = re.compile(r"(?<![\w-])(--[A-Za-z0-9_-]+)\s*:")
_USE_TOKEN = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}{]+)", re.IGNORECASE)
_FONT_FACE = re.compile(r"@font-face\s*\{[^}]*\}", re.IGNORECASE | re.DOTALL)
_FONTSOURCE = re.compile(r"@fontsource(?:-variable)?/([a-z0-9-]+)", re.IGNORECASE)
_GFONT_FAMILY = re.compile(r"family=([^&:'\"\)]+)", re.IGNORECASE)
_CLASS_REF = re.compile(r"class(?:Name)?\s*=\s*[\"']([^\"']+)[\"']")
_CLASS_DEF = re.compile(r"\.(-?[A-Za-z_][A-Za-z0-9_-]*)")
_STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_UTILITY_MARKER = re.compile(r"@tailwind\b|@apply\b|tailwindcss", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    """One UI-fidelity defect. ``token`` is set only for ``dead_token``."""

    severity: str  # "fail" | "warn"
    code: str  # "dead_token" | "unloaded_font" | "ghost_class"
    detail: str
    token: str = ""


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _css_text(path: str, text: str) -> str:
    """CSS-bearing portion of a file: whole text for stylesheets, ``<style>``
    blocks for markup, empty for plain JS/TS (no CSS selectors there)."""
    ext = _ext(path)
    if ext in CSS_EXTS:
        return text
    if ext in MARKUP_EXTS:
        return "\n".join(_STYLE_BLOCK.findall(text))
    return ""


def _norm_font(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().strip("\"'").replace("-", " ")).lower()


def _family_names(decl: str) -> list[str]:
    """Concrete family names in one ``font-family`` value list."""
    out: list[str] = []
    for raw in decl.split(","):
        name = raw.strip()
        if not name or "var(" in name or name.lower() in GENERIC_FAMILIES:
            continue
        out.append(name.strip("\"'"))
    return out


def _split_class_group(group: str) -> list[str]:
    if "{" in group or "$" in group:
        return []
    return [tok for tok in group.split() if tok]


def declared_tokens(text: str) -> set[str]:
    return collect_keys(text, (_DECL_TOKEN,))


def consumed_tokens(text: str) -> set[str]:
    return collect_keys(text, (_USE_TOKEN,))


def font_refs(text: str) -> set[str]:
    """Named font families referenced in ``font-family`` declarations."""
    return collect_keys(text, (_FONT_FAMILY,), normalize=_family_names)


def font_loaders(text: str) -> set[str]:
    """Normalised font names loaded via @font-face / fontsource / Google Fonts."""
    out: set[str] = set()
    for block in _FONT_FACE.findall(text):
        out |= collect_keys(block, (_FONT_FAMILY,), normalize=lambda d: [_norm_font(d)])
    out |= collect_keys(text, (_FONTSOURCE,), normalize=lambda p: [_norm_font(p)])
    out |= collect_keys(
        text, (_GFONT_FAMILY,), normalize=lambda f: [_norm_font(f.replace("+", " "))]
    )
    return {n for n in out if n}


def class_refs(text: str) -> set[str]:
    return collect_keys(text, (_CLASS_REF,), normalize=_split_class_group)


def class_defs(css_text: str) -> set[str]:
    return collect_keys(css_text, (_CLASS_DEF,))


def has_utility_framework(text: str) -> bool:
    return bool(_UTILITY_MARKER.search(text))


def analyze(target_files: dict[str, str], corpus_files: dict[str, str]) -> list[Finding]:
    """Return UI-fidelity findings.

    ``target_files`` are the files under review (declarations checked here);
    ``corpus_files`` is the resolution scope for consumers/loaders/defs.
    """
    consumed: set[str] = set()
    loaders: set[str] = set()
    defined_classes: set[str] = set()
    utility = False
    for path, text in corpus_files.items():
        consumed |= consumed_tokens(text)
        loaders |= font_loaders(text)
        defined_classes |= class_defs(_css_text(path, text))
        utility = utility or has_utility_framework(text)

    findings: list[Finding] = []
    for path, text in target_files.items():
        allowance = file_allowance(text, CHECK_ID)
        if allowance is not None:
            if not allowance.reason:
                findings.append(
                    Finding(
                        "warn",
                        "allow_missing_reason",
                        f"allow(ui_fidelity) in {path} 缺 reason — 豁免生效但须补充理由",
                    )
                )
            continue
        for tok in sorted(declared_tokens(text) - consumed):
            findings.append(
                Finding("fail", "dead_token", f"{tok} declared in {path}, 0 var() consumers", tok)
            )
        for fam in sorted(font_refs(text)):
            if _norm_font(fam) not in loaders:
                detail = f"{fam} referenced in {path}, no @font-face/import"
                findings.append(Finding("warn", "unloaded_font", detail))
        if not utility and _ext(path) in MARKUP_EXTS:
            for cls in sorted(class_refs(text) - defined_classes):
                findings.append(Finding("warn", "ghost_class", cls))
    return findings


def _collect(root: Path, exts: frozenset[str]) -> dict[str, str]:
    root = Path(root)
    files: dict[str, str] = {}
    candidates = [root] if root.is_file() else iter_files(root)
    for p in candidates:
        if p.suffix.lower() in exts:
            try:
                files[str(p)] = p.read_text(errors="replace")
            except OSError:
                continue
    return files


def scan_ui_fidelity(target: Path, corpus_root: Path) -> list[Finding]:
    """File-IO entry: collect UI files under *target* and *corpus_root*, analyze."""
    target_files = _collect(target, UI_EXTS)
    if not target_files:
        return []
    corpus_files = _collect(corpus_root, UI_EXTS)
    corpus_files.update(target_files)
    return analyze(target_files, corpus_files)


def _run_check(ctx: CheckContext) -> list[EngineFinding]:
    """Engine adapter: cross-file scan, ``dead_token`` gates, the rest WARN."""
    if ctx.fix:
        return []
    corpus_root = ctx.project_root or ctx.target
    return [
        EngineFinding(
            check_id=CHECK_ID,
            severity="fail" if f.severity == "fail" else "warn",
            category="visual-fidelity",
            detail=f"{f.code}: {f.detail}",
        )
        for f in scan_ui_fidelity(ctx.target, corpus_root)
    ]


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "UI 保真跨文件扫描 (.css/.scss/markup) — 死 token（声明的 CSS "
            "自定义属性零 var() 消费）FAIL；未加载字体（引用的 font-family "
            "无 @font-face/fontsource 加载）与幽灵类（markup 引用零定义 class，"
            "检测到 utility 框架则跳过）WARN；豁免文件级 "
            'cataforge: allow(ui_fidelity, reason="...")'
        ),
        severity="fail-on-error",
        category="visual-fidelity",
        modes=frozenset({"review", "scan"}),
        run=_run_check,
    )
)
