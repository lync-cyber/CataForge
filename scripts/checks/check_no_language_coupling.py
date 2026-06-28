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
move language-specific identification patterns into `.cataforge/references/`
(one topic per file, e.g. `wiring-checks.md`). The body links to the
reference; the reference grows as new languages are added without
re-touching skill prompts.

Whitelist:
    - Lines containing `<!-- allow-language-coupling: <reason> -->`
      (escape hatch for cases where the term is unavoidable in the body).
    - Lines inside fenced code blocks (```...```) — code examples and
      YAML rule snippets legitimately contain language-specific tokens.
    - Lines that are pure markdown links pointing at .cataforge/references/
      (the link text may legitimately mention the language).

Exit:
    0 — clean
    1 — at least one violation
"""

from __future__ import annotations

import re
import sys

from _common import (
    REPO_ROOT,
    ensure_utf8,
    is_whitelisted_for,
    iter_asset_files,
    iter_scannable_lines,
    make_escape_hatch,
)

ensure_utf8()

# Scope is intentionally the role-prompt *bodies* only. Skill `references/`
# (especially `lang-*.md`) are the sanctioned home for language keywords —
# the whole point of this guard is to push keywords out of the body into
# those files, so scanning them would flag the very content they exist to
# hold. docs/reference/ likewise documents the framework (which is Python)
# and is out of scope for the same reason.
SCAN_GLOBS = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/SKILL.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
]

# Tight keyword set — each entry targets a *business* pattern the LLM is
# likely to hallucinate into a prompt, anchored enough that it doesn't
# fire on incidental mentions. Tool-adapter lists (ESLint / Ruff / golangci-lint)
# are deliberately NOT here — those are legitimate capability declarations.
#
# To add a language family, ship a `.cataforge/references/<topic>-<lang>.md`
# first, then add the keyword here with a hint pointing at it.
FORBIDDEN: list[tuple[str, re.Pattern[str], str]] = [
    (
        "python-web-framework",
        re.compile(r"\b(?:FastAPI|Starlette|Django|Flask|Pyramid|Tornado)\b"),
        ".cataforge/references/wiring-checks.md §Python (or a new per-language file)",
    ),
    (
        "python-async-runtime",
        re.compile(r"\basyncio[.:]\w"),
        ".cataforge/references/python-runtime.md (create as needed)",
    ),
    (
        "python-orm",
        re.compile(r"\b(?:SQLAlchemy|Tortoise|Peewee|PonyORM)\b"),
        ".cataforge/references/python-persistence.md (create as needed)",
    ),
    (
        "python-signal-binding",
        re.compile(r"\bsignal\.connect\s*\(|@\w*receiver\b|\bblinker\b", re.IGNORECASE),
        ".cataforge/references/wiring-checks.md §Python.signal",
    ),
    (
        "python-lifespan-hook",
        re.compile(r"\blifespan_context\b|\badd_event_handler\s*\(", re.IGNORECASE),
        ".cataforge/references/wiring-checks.md §Python.lifespan",
    ),
    (
        "python-di-container",
        re.compile(
            r"\bdependency_injector\b|\binject\.Binder\b|providers\.(?:Singleton|Factory|Resource)\b",
        ),
        ".cataforge/references/wiring-checks.md §Python.DI",
    ),
    (
        "react-hook",
        re.compile(r"\buse(?:Effect|State|Memo|Callback|Ref|Context)\s*\("),
        ".cataforge/references/wiring-checks.md §JS-TS (or a new per-language file)",
    ),
    (
        "redux-store-action",
        re.compile(r"\b(?:Redux|Zustand|Vuex|Pinia)\b|\bstore\.dispatch\s*\("),
        ".cataforge/references/wiring-checks.md §JS-TS.store-action",
    ),
    (
        "spring-stereotype",
        re.compile(
            r"@(?:Autowired|Component|Service|Bean|SpringBootApplication)\b|\bSpring\s+Boot\b"
        ),
        ".cataforge/references/wiring-checks.md §Java (or a new per-language file)",
    ),
    (
        "node-web-framework",
        re.compile(r"\b(?:Express|Koa|Fastify|NestJS)\b"),
        ".cataforge/references/wiring-checks.md §JS-TS (or a new per-language file)",
    ),
    (
        "go-concurrency",
        re.compile(r"\bgoroutine\b|\bsync\.WaitGroup\b"),
        ".cataforge/references/wiring-checks.md §Go (or a new per-language file)",
    ),
    (
        "rust-tokio",
        re.compile(r"\btokio::spawn\b|#\[tokio::main\]"),
        ".cataforge/references/wiring-checks.md §Rust (or a new per-language file)",
    ),
    (
        "test-mock-module",
        re.compile(r"\b(?:vi|jest)\.mock\b|\bunittest\.mock\b"),
        ".cataforge/references/test-and-e2e-apis.md §module-mock API",
    ),
    (
        "e2e-driver-input",
        re.compile(
            r"\bpage\.(?:fill|click|type|goto|press)\b|\bcy\.[a-z]|"
            r"\bkeyboard\.(?:type|press)\b|\bsend_keys\b"
        ),
        ".cataforge/references/test-and-e2e-apis.md §e2e 真实用户输入原语",
    ),
]

ALLOW = make_escape_hatch("allow-language-coupling")
# Markdown reference link to .cataforge/references/ — when the only language
# mention on a line is inside such a link, treat the line as a legitimate
# reference jump rather than a coupling.
REFERENCE_LINK = re.compile(r"\[([^\]]+)\]\([^)]*references/[^)]+\)")


def strip_reference_links(line: str) -> str:
    """Remove `[…](.cataforge/references/…)` link bodies so the link text
    (which may legitimately mention a language to label the jump target)
    doesn't trigger the scanner.
    """
    return REFERENCE_LINK.sub("", line)


def main() -> int:
    fails: list[tuple[str, str]] = []
    scanned = 0
    for path in iter_asset_files(SCAN_GLOBS):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in iter_scannable_lines(text):
            if is_whitelisted_for(line, ALLOW):
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
            ".cataforge/references/, link from the body. CLAUDE.md §Agent / Skill "
            "撰写约定 has the full rule. If unavoidable, append "
            "`<!-- allow-language-coupling: <reason> -->` to the line.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no language coupling in agent/skill bodies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
