"""Primary-stack detection — package manager + canonical build commands.

Builds on the language registry (``cataforge.core.languages``): which languages
a project contains comes from that single marker table, and this module layers
the package-manager discriminator (lockfiles) and the derived install / test /
lint commands on top. The §执行环境 block injected into the project instruction
file and the least-privilege Bash allowlist both read from here.

A project may contain several languages; ``detect_primary_stack`` picks one by
``_PRIMARY_ORDER`` priority and returns ``None`` when no language in that order
is present, so callers can fall back to asking the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cataforge.core.languages import detect_languages

# Languages with a known command toolchain, highest priority first. A language
# in the registry but absent here (e.g. java, csharp) yields no primary stack —
# callers treat that the same as "nothing detected".
_PRIMARY_ORDER = ("python", "js-ts", "rust", "go")

# Human-facing label for the §执行环境 block, keyed by canonical registry id.
_DISPLAY = {"python": "python", "js-ts": "node", "rust": "rust", "go": "go"}


@dataclass(frozen=True)
class Stack:
    """The project's primary toolchain.

    ``language`` is the canonical registry id; ``display`` is the label shown in
    the §执行环境 block. ``bash_allow`` holds command prefixes safe to whitelist
    in the hook layer under least-privilege.
    """

    language: str
    display: str
    package_manager: str
    install_cmd: str
    test_cmd: str
    lint_cmd: str
    bash_allow: tuple[str, ...]


def detect_primary_stack(root: Path) -> Stack | None:
    """Resolve the project's primary stack, or ``None`` when none is recognized."""
    detected = set(detect_languages(root))
    for lang_id in _PRIMARY_ORDER:
        if lang_id in detected:
            return _build_stack(root, lang_id)
    return None


def render_env_block(stack: Stack) -> str:
    """Render the §执行环境 Markdown block for the project instruction file.

    Loaded as a project instruction every session, so each line spends context
    budget — kept small and declarative.
    """
    return (
        f"- 技术栈: {stack.display}\n"
        f"- 包管理器: {stack.package_manager}\n"
        f"- 安装命令: `{stack.install_cmd}`\n"
        f"- 测试命令: `{stack.test_cmd}`\n"
        f"- Lint 命令: `{stack.lint_cmd}`\n"
    )


def _build_stack(root: Path, lang_id: str) -> Stack:
    if lang_id == "python":
        is_uv = (root / "uv.lock").is_file()
        pm = "uv" if is_uv else "pip"
        allow = ([pm + " "]) + ["python ", "pytest", "ruff "]
        return Stack(
            language="python",
            display=_DISPLAY["python"],
            package_manager=pm,
            install_cmd="uv sync" if is_uv else "pip install -e .",
            test_cmd="uv run pytest" if is_uv else "pytest",
            lint_cmd="uv run ruff check" if is_uv else "ruff check",
            bash_allow=tuple(allow),
        )

    if lang_id == "js-ts":
        if (root / "pnpm-lock.yaml").is_file():
            pm, run = "pnpm", "pnpm"
        elif (root / "yarn.lock").is_file():
            pm, run = "yarn", "yarn"
        else:
            pm, run = "npm", "npm run"
        return Stack(
            language="js-ts",
            display=_DISPLAY["js-ts"],
            package_manager=pm,
            install_cmd=f"{pm} install",
            test_cmd=f"{run} test",
            lint_cmd=f"{run} lint",
            bash_allow=(f"{pm} ", "node ", "npx "),
        )

    if lang_id == "rust":
        return Stack(
            language="rust",
            display=_DISPLAY["rust"],
            package_manager="cargo",
            install_cmd="cargo build",
            test_cmd="cargo test",
            lint_cmd="cargo clippy",
            bash_allow=("cargo ",),
        )

    # go
    return Stack(
        language="go",
        display=_DISPLAY["go"],
        package_manager="go",
        install_cmd="go mod download",
        test_cmd="go test ./...",
        lint_cmd="go vet ./...",
        bash_allow=("go ",),
    )
