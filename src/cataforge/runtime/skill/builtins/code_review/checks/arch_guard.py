"""Architecture layering guard — code-review Layer 1 (cross-file).

Judges import edges against a project-declared layer model:

* ``scope: project`` ``arch.yaml`` declares ``layers`` (path globs +
  optional ``modules`` import-specifier prefixes), a ``rules`` direction
  matrix and ``enforce: warn|fail`` (default ``fail``).
* ``scope: language`` ``arch-{lang}.yaml`` files declare the
  ``import_patterns`` that extract that language's import edges (capture
  group 1 = the imported module specifier).

Edge judgment: a file's layer comes from matching its project-relative
path against layer ``paths`` globs; an import's target layer comes from
resolving relative specifiers against the source directory (matched on
``paths``) or matching absolute specifiers against layer ``modules``
prefixes. Unassigned sources/targets (third-party, stdlib, unlayered
code) are ignored. Same-layer imports are always allowed.

No declared model → the check is silently inactive (scan emits one INFO
pointing at the shipped template). Exemption is line-scoped:
``cataforge: allow(arch_guard, reason="...")`` on the offending import
line. Known blind spots (dynamic specifiers, re-export chains) are
Layer 2 territory — see ``.cataforge/references/arch-checks.md``.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import line_allowances
from cataforge.runtime.skill.builtins.code_review.engine.registry import (
    CheckSpec,
    register_check,
)
from cataforge.runtime.skill.rules.loader import RuleSpec, compile_flags, discover_rules

_BUILTIN_MODULE = "cataforge.runtime.skill.builtins.code_review"
_SKILL_ID = "code-review"

CHECK_ID = "code_review.arch_guard"

_MODULE_SEPARATORS = (".", "/", "::")
_DOTTED_RELATIVE = re.compile(r"^(\.+)([\w.]*)$")

_NO_MODEL_HINT = (
    "arch 层模型未声明，架构守护未激活 — 在 <project>/.cataforge/skills/code-review/rules/"
    "arch.yaml 声明 layers/rules 即启用（模板随包发运，细则见 "
    ".cataforge/references/arch-checks.md）"
)


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Segment-aware glob → regex: ``**`` crosses ``/``, ``*``/``?`` do not.

    A trailing ``/**`` also matches the directory itself, so an
    extension-less resolved import path like ``src/app/infra`` hits
    ``src/app/infra/**``.
    """
    suffix = ""
    if glob.endswith("/**"):
        glob = glob[:-3]
        suffix = "(?:/.*)?"
    parts: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**", i):
            parts.append(".*")
            i += 2
        elif glob[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(parts) + suffix + "$")


@dataclass(frozen=True)
class Layer:
    name: str
    paths: tuple[re.Pattern[str], ...]
    modules: tuple[str, ...]


@dataclass(frozen=True)
class ArchModel:
    """Compiled project layer model (declaration order = match priority)."""

    layers: tuple[Layer, ...]
    allowed: dict[str, frozenset[str]]  # layer -> allowed targets (incl. self)
    enforce: str

    def layer_of_path(self, rel_path: str) -> str | None:
        for layer in self.layers:
            if any(p.match(rel_path) for p in layer.paths):
                return layer.name
        return None

    def layer_of_module(self, specifier: str) -> str | None:
        for layer in self.layers:
            for prefix in layer.modules:
                if specifier == prefix or (
                    specifier.startswith(prefix)
                    and specifier[len(prefix) :].startswith(_MODULE_SEPARATORS)
                ):
                    return layer.name
        return None


@dataclass(frozen=True)
class LangImports:
    """Compiled import-edge extractors for one language."""

    extensions: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]


def _compile_model(spec: RuleSpec) -> ArchModel:
    layers = tuple(
        Layer(
            name=entry["name"],
            paths=tuple(_glob_to_regex(g) for g in entry["paths"]),
            modules=tuple(entry.get("modules") or ()),
        )
        for entry in spec.raw["layers"]
    )
    allowed = {name: frozenset(targets) | {name} for name, targets in spec.raw["rules"].items()}
    return ArchModel(layers=layers, allowed=allowed, enforce=spec.raw.get("enforce", "fail"))


def load_arch_rules(
    project_root: Path | None = None,
) -> tuple[ArchModel | None, dict[str, LangImports]]:
    """Discover + compile arch rules for *project_root* (None → defaults only)."""
    specs = discover_rules(_SKILL_ID, builtin_module=_BUILTIN_MODULE, project_root=project_root)
    model: ArchModel | None = None
    langs: dict[str, LangImports] = {}
    for (rule_type, language), spec in specs.items():
        if rule_type != "arch":
            continue
        if spec.scope == "project":
            model = _compile_model(spec)
        else:
            langs[language] = LangImports(
                extensions=spec.extensions,
                patterns=tuple(
                    re.compile(p["regex"], compile_flags(p.get("flags")))
                    for p in spec.raw["import_patterns"]
                ),
            )
    return model, langs


def _extract_imports(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[tuple[int, str]]:
    """Deduped ``(line, specifier)`` edges, sorted by position."""
    edges: set[tuple[int, str]] = set()
    for pattern in patterns:
        for m in pattern.finditer(text):
            specifier = m.group(1)
            if specifier:
                edges.add((text.count("\n", 0, m.start(1)) + 1, specifier))
    return sorted(edges)


def _as_relative_path(specifier: str, src_dir: str) -> str | None:
    """Project-relative path form of a relative import, else None.

    Handles path-style (``../infra/db``) and dotted-relative
    (``..infra.db`` / ``.infra``) specifiers; absolute specifiers return
    None and are matched via layer ``modules`` prefixes instead.
    """
    if specifier.startswith(("./", "../")) or specifier in (".", ".."):
        resolved = posixpath.normpath(posixpath.join(src_dir, specifier))
    else:
        m = _DOTTED_RELATIVE.match(specifier)
        if m is None:
            return None
        dots, rest = m.groups()
        up = "../" * (len(dots) - 1)
        resolved = posixpath.normpath(posixpath.join(src_dir, up + rest.replace(".", "/")))
    return None if resolved.startswith("..") else resolved


def _target_layer(model: ArchModel, specifier: str, src_dir: str) -> str | None:
    rel = _as_relative_path(specifier, src_dir)
    if rel is not None:
        return model.layer_of_path(rel)
    return model.layer_of_module(specifier)


def _scan_file(
    model: ArchModel,
    lang: LangImports,
    text: str,
    rel: str,
    display_path: str,
    src_layer: str,
    severity: str,
) -> list[Finding]:
    src_dir = posixpath.dirname(rel)
    allowances = line_allowances(text, CHECK_ID)
    out: list[Finding] = []
    for lineno, specifier in _extract_imports(text, lang.patterns):
        target = _target_layer(model, specifier, src_dir)
        if target is None or target in model.allowed.get(src_layer, frozenset({src_layer})):
            continue
        allowance = allowances.get(lineno)
        if allowance is not None:
            if allowance.reason:
                continue
            out.append(
                Finding(
                    check_id=CHECK_ID,
                    severity="warn",
                    category="arch",
                    detail="allow(arch_guard) 缺 reason — 豁免生效但须补充理由",
                    file=display_path,
                    line=lineno,
                )
            )
            continue
        out.append(
            Finding(
                check_id=CHECK_ID,
                severity=severity,
                category="arch",
                detail=(
                    f"层 {src_layer} 依赖 {target}（import {specifier}）"
                    f"越出方向矩阵 rules.{src_layer}"
                ),
                file=display_path,
                line=lineno,
            )
        )
    return out


def run(ctx: CheckContext) -> list[Finding]:
    """Judge every layered file's import edges against the direction matrix."""
    model, langs = load_arch_rules(ctx.project_root)
    if model is None:
        if ctx.mode == "scan":
            return [
                Finding(check_id=CHECK_ID, severity="info", category="arch", detail=_NO_MODEL_HINT)
            ]
        return []
    root = ctx.project_root or (ctx.target if ctx.target.is_dir() else ctx.target.parent)
    severity = "fail" if model.enforce == "fail" else "warn"
    all_exts = (
        frozenset().union(*(li.extensions for li in langs.values())) if langs else frozenset()
    )
    findings: list[Finding] = []
    for path in ctx.files(all_exts):
        lang = next((li for li in langs.values() if path.suffix.lower() in li.extensions), None)
        if lang is None:
            continue
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        src_layer = model.layer_of_path(rel)
        if src_layer is None:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        findings.extend(_scan_file(model, lang, text, rel, str(path), src_layer, severity))
    return findings


register_check(
    CheckSpec(
        id=CHECK_ID,
        title=(
            "架构分层守护（项目级 arch.yaml 声明 layers/rules/enforce，arch-{lang}.yaml 提供 "
            "import_patterns）— import 边违反方向矩阵按 enforce 出 FAIL/WARN；未声明模型静默"
            '不激活（scan 一条 INFO）；行级豁免 cataforge: allow(arch_guard, reason="...")'
        ),
        severity="fail-on-error",
        category="arch",
        modes=frozenset({"review", "scan"}),
        run=run,
    )
)
