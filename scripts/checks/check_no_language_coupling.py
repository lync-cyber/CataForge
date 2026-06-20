#!/usr/bin/env python3
"""Anti-rot guard: no language-specific business keywords in agent / skill bodies.

`.cataforge/skills/**/SKILL.md` and `.cataforge/agents/**/AGENT.md` are
loaded into LLM context every time the corresponding role is dispatched.
A skill's theme is its responsibility (review / TDD / wiring check / …)
— not its programming language. When language-specific business keywords
(FastAPI lifespan, Spring @Autowired, Redux dispatch, …) leak into the
main body, every project that doesn't use that language still pays the
token cost on every load.

The fix is structural: keep the skill / agent body language-agnostic, and
move language-specific identification patterns into `docs/reference/`
(one topic per file, e.g. `wiring-checks.md`). The body links to the
reference; the reference grows as new languages are added without
re-touching skill prompts.

Whitelist:
    - Lines containing `<!-- allow-language-coupling: <reason> -->`
      (escape hatch for cases where the term is unavoidable in the body).
    - Lines inside fenced code blocks (```...```) — code examples and
      YAML rule snippets legitimately contain language-specific tokens.
    - Lines that are pure markdown links pointing at docs/reference/
      (the link text may legitimately mention the language).

Exit:
    0 — clean
    1 — at least one violation
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Reconfigure stdio to UTF-8 so Chinese characters in error messages don't
# crash on Windows cp1252 terminals.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/SKILL.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
]

# Tight keyword set — each entry targets a *business* pattern the LLM is
# likely to hallucinate into a prompt, anchored enough that it doesn't
# fire on incidental mentions. Tool-adapter lists (ESLint / Ruff / golangci-lint)
# are deliberately NOT here — those are legitimate capability declarations.
#
# To add a language family, ship a `docs/reference/<topic>-<lang>.md`
# first, then add the keyword here with a hint pointing at it.
FORBIDDEN: list[tuple[str, re.Pattern[str], str]] = [
    (
        "python-web-framework",
        re.compile(r"\b(?:FastAPI|Starlette|Django|Flask|Pyramid|Tornado)\b"),
        "docs/reference/wiring-checks.md §Python (or a new docs/reference/python-*.md)",
    ),
    (
        "python-async-runtime",
        re.compile(r"\basyncio[.:]\w"),
        "docs/reference/python-runtime.md (create as needed)",
    ),
    (
        "python-orm",
        re.compile(r"\b(?:SQLAlchemy|Tortoise|Peewee|PonyORM)\b"),
        "docs/reference/python-persistence.md (create as needed)",
    ),
    (
        "python-signal-binding",
        re.compile(r"\bsignal\.connect\s*\(|@\w*receiver\b|\bblinker\b", re.IGNORECASE),
        "docs/reference/wiring-checks.md §Python.signal",
    ),
    (
        "python-lifespan-hook",
        re.compile(r"\blifespan_context\b|\badd_event_handler\s*\(", re.IGNORECASE),
        "docs/reference/wiring-checks.md §Python.lifespan",
    ),
    (
        "python-di-container",
        re.compile(
            r"\bdependency_injector\b|\binject\.Binder\b|providers\.(?:Singleton|Factory|Resource)\b",
        ),
        "docs/reference/wiring-checks.md §Python.DI",
    ),
    (
        "react-hook",
        re.compile(r"\buse(?:Effect|State|Memo|Callback|Ref|Context)\s*\("),
        "docs/reference/wiring-checks.md §JS-TS (or a new docs/reference/react-*.md)",
    ),
    (
        "redux-store-action",
        re.compile(r"\b(?:Redux|Zustand|Vuex|Pinia)\b|\bstore\.dispatch\s*\("),
        "docs/reference/wiring-checks.md §JS-TS.store-action",
    ),
    (
        "spring-stereotype",
        re.compile(
            r"@(?:Autowired|Component|Service|Bean|SpringBootApplication)\b|\bSpring\s+Boot\b"
        ),
        "docs/reference/wiring-checks.md §Java (or a new docs/reference/spring-*.md)",
    ),
    (
        "node-web-framework",
        re.compile(r"\b(?:Express|Koa|Fastify|NestJS)\b"),
        "docs/reference/wiring-checks.md §JS-TS (or a new docs/reference/node-*.md)",
    ),
    (
        "go-concurrency",
        re.compile(r"\bgoroutine\b|\bsync\.WaitGroup\b"),
        "docs/reference/wiring-checks.md §Go (or a new docs/reference/go-*.md)",
    ),
    (
        "rust-tokio",
        re.compile(r"\btokio::spawn\b|#\[tokio::main\]"),
        "docs/reference/wiring-checks.md §Rust (or a new docs/reference/rust-*.md)",
    ),
    (
        "test-mock-module",
        re.compile(r"\b(?:vi|jest)\.mock\b|\bunittest\.mock\b"),
        "docs/reference/test-and-e2e-apis.md §module-mock API",
    ),
    (
        "e2e-driver-input",
        re.compile(
            r"\bpage\.(?:fill|click|type|goto|press)\b|\bcy\.[a-z]|"
            r"\bkeyboard\.(?:type|press)\b|\bsend_keys\b"
        ),
        "docs/reference/test-and-e2e-apis.md §e2e 真实用户输入原语",
    ),
]

ALLOW_MARKER = re.compile(r"<!--\s*allow-language-coupling")
CODE_FENCE = re.compile(r"^\s*```")
# Markdown reference link to docs/reference/ — when the only language
# mention on a line is inside such a link, treat the line as a legitimate
# reference jump rather than a coupling.
REFERENCE_LINK = re.compile(r"\[([^\]]+)\]\([^)]*docs/reference/[^)]+\)")


def is_whitelisted(line: str) -> bool:
    return bool(ALLOW_MARKER.search(line))


def strip_reference_links(line: str) -> str:
    """Remove `[…](docs/reference/…)` link bodies so the link text
    (which may legitimately mention a language to label the jump target)
    doesn't trigger the scanner.
    """
    return REFERENCE_LINK.sub("", line)


def iter_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root, pattern in SCAN_GLOBS:
        if not root.exists():
            continue
        for p in root.glob(pattern):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return files


def main() -> int:
    fails: list[tuple[str, str]] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        in_code_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if CODE_FENCE.match(line):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
                continue
            if is_whitelisted(line):
                continue
            stripped = strip_reference_links(line)
            for label, pattern, hint in FORBIDDEN:
                if pattern.search(stripped):
                    rel = path.relative_to(REPO_ROOT)
                    fails.append((f"{rel}:{lineno}: [{label}] {line.strip()}", hint))
                    break  # one violation per line is enough

    if fails:
        print(
            "Anti-rot: language-specific keywords in agent / skill body",
            file=sys.stderr,
        )
        for msg, hint in fails:
            print(f"  {msg}", file=sys.stderr)
            print(f"    → move to: {hint}", file=sys.stderr)
        print(
            "\nFix: agent / skill subject is the responsibility, not a "
            "language. Move language-specific identification rules to "
            "docs/reference/, link from the body. CLAUDE.md §Agent / Skill "
            "撰写约定 has the full rule. If unavoidable, append "
            "`<!-- allow-language-coupling: <reason> -->` to the line.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no language coupling in agent/skill bodies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
