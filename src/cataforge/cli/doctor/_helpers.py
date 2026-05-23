"""Small printer + path utilities shared by doctor sub-checks."""

from __future__ import annotations

from pathlib import Path

import click


def check_file(label: str, path: Path) -> None:
    status = "OK" if path.is_file() else "MISSING"
    click.echo(f"  {label}: {status}")


def check_dir(label: str, path: Path) -> None:
    status = "OK" if path.is_dir() else "MISSING"
    click.echo(f"  {label}: {status}")


def check_import(module: str, display: str) -> None:
    try:
        __import__(module)
        click.echo(f"  {display}: OK")
    except ImportError:
        click.echo(f"  {display}: MISSING")


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
