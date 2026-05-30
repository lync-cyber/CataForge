"""`cataforge kg schema-context` CLI command."""
from __future__ import annotations


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def test_schema_context_prints_card_without_store() -> None:
    """The card is static — the command works with no initialized store."""
    from click.testing import CliRunner

    result = CliRunner().invoke(_cli(), ["kg", "schema-context"])
    assert result.exit_code == 0, result.output
    assert "# Knowledge Graph Schema" in result.output
    assert "cf:Feature" in result.output
    assert "cf:satisfies" in result.output
    assert "```sparql" in result.output
