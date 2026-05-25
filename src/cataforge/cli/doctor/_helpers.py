"""Small printer + path utilities shared by doctor sub-checks."""

from __future__ import annotations

from pathlib import Path

import click


def check_file(label: str, path: Path, *, required: bool = False) -> int:
    """Report a file's presence. Returns 1 when *required* and missing, else 0.

    Existing callers that ignore the return value preserve their pre-existing
    behaviour; new callers opt into gating by passing ``required=True`` and
    adding the result into ``failed_count``.
    """
    present = path.is_file()
    if present:
        click.echo(f"  {label}: OK")
        return 0
    if required:
        click.echo(f"  {label}: FAIL (missing — required source asset)")
        return 1
    click.echo(f"  {label}: MISSING")
    return 0


def check_dir(label: str, path: Path, *, required: bool = False) -> int:
    """Same contract as :func:`check_file` but for directories."""
    present = path.is_dir()
    if present:
        click.echo(f"  {label}: OK")
        return 0
    if required:
        click.echo(f"  {label}: FAIL (missing — required source asset)")
        return 1
    click.echo(f"  {label}: MISSING")
    return 0


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
