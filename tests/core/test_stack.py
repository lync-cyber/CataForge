"""Tests for primary-stack detection (core.stack)."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.stack import detect_primary_stack, render_env_block


def test_no_markers_returns_none(tmp_path: Path) -> None:
    assert detect_primary_stack(tmp_path) is None


def test_python_uv_when_lockfile_present(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    assert stack.language == "python"
    assert stack.package_manager == "uv"
    assert stack.install_cmd == "uv sync"
    assert stack.test_cmd == "uv run pytest"
    assert stack.bash_allow == ("uv ", "python ", "pytest", "ruff ")


def test_python_pip_without_lockfile(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    assert stack.package_manager == "pip"
    assert stack.install_cmd == "pip install -e ."
    assert stack.bash_allow == ("pip ", "python ", "pytest", "ruff ")


def test_node_package_manager_from_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("x", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    assert stack.language == "js-ts"
    assert stack.display == "node"
    assert stack.package_manager == "pnpm"
    assert stack.test_cmd == "pnpm test"


def test_node_defaults_to_npm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    assert stack.package_manager == "npm"
    assert stack.test_cmd == "npm run test"


def test_python_wins_over_node_by_priority(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    assert stack.language == "python"


def test_registry_language_without_toolchain_yields_none(tmp_path: Path) -> None:
    # java is in the registry but has no command derivation here.
    (tmp_path / "pom.xml").write_text("x", encoding="utf-8")
    assert detect_primary_stack(tmp_path) is None


def test_rust_and_go(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("x", encoding="utf-8")
    rust = detect_primary_stack(tmp_path)
    assert rust is not None and rust.language == "rust" and rust.bash_allow == ("cargo ",)

    (tmp_path / "Cargo.toml").unlink()
    (tmp_path / "go.mod").write_text("x", encoding="utf-8")
    go = detect_primary_stack(tmp_path)
    assert go is not None and go.language == "go" and go.test_cmd == "go test ./..."


def test_render_env_block_shape(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    stack = detect_primary_stack(tmp_path)
    assert stack is not None
    block = render_env_block(stack)
    assert block.startswith("- 技术栈: python\n")
    assert "- 包管理器: uv\n" in block
    assert "- 安装命令: `uv sync`\n" in block
    assert block.endswith("- Lint 命令: `uv run ruff check`\n")
