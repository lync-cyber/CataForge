"""Read-only ``cataforge kg`` subcommands share one ``--db-path`` policy.

``query``, ``trace`` and ``validate`` are all read-only over an existing
store. Their ``--db-path`` option must therefore reject a nonexistent path
identically at parse time (Click usage error, exit 2) — the option factory
in :mod:`cataforge.interface.cli.kg._options` is the single source of that
``exists=True`` policy.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


# (subcommand, trailing positional args required by the command)
_READ_ONLY = [
    ("query", ["SELECT * WHERE { ?s ?p ?o }"]),
    ("trace", ["F-001"]),
    ("validate", []),
]


@pytest.mark.parametrize(("sub", "extra"), _READ_ONLY)
def test_read_only_db_path_rejects_missing_store(
    sub: str, extra: list[str], tmp_path
) -> None:
    missing = tmp_path / "no-such-store"
    result = CliRunner().invoke(
        _cli(), ["kg", sub, "--db-path", str(missing), *extra]
    )
    # exists=True → Click usage error (exit 2) before the command body runs.
    assert result.exit_code == 2, result.output
    assert "does not exist" in result.output


def test_read_only_db_path_rejection_is_identical_across_subcommands(
    tmp_path,
) -> None:
    missing = tmp_path / "no-such-store"
    codes = set()
    for sub, extra in _READ_ONLY:
        result = CliRunner().invoke(
            _cli(), ["kg", sub, "--db-path", str(missing), *extra]
        )
        codes.add(result.exit_code)
    assert codes == {2}, codes
