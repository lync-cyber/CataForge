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


def check_import(module: str, display: str, *, required: bool = False) -> int:
    """Report whether *module* imports. Returns 0 on success.

    When *required* is True a missing import returns 1 so ``doctor``
    can fold it into ``failed_count`` the same way ``check_file`` /
    ``check_dir`` already do. Default ``required=False`` preserves
    the historic "MISSING" tone and zero-return for optional deps so
    pre-existing callers that ignore the return value behave exactly
    as before this change.
    """
    try:
        __import__(module)
    except ImportError:
        if required:
            click.echo(f"  {display}: FAIL (missing — required import)")
            return 1
        click.echo(f"  {display}: MISSING")
        return 0
    click.echo(f"  {display}: OK")
    return 0


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
