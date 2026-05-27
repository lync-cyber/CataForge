"""Contract tests for ``cataforge.cli.errors``.

Each subclass carries a documented ``exit_code`` that downstream CI
scripts branch on (see ``docs/reference/cli.md`` §退出码). The mapping
is part of the public CLI surface — changing a value silently would
break those scripts. These tests freeze the table.
"""

from __future__ import annotations

import click
import pytest

from cataforge.cli.errors import (
    EXIT_GENERIC_FAILURE,
    EXIT_KG_VERIFICATION_FAILED,
    EXIT_NOT_IMPLEMENTED,
    CataforgeError,
    ConfigError,
    ExternalToolError,
    KGError,
    KGStoreError,
    KGVerificationError,
    NotImplementedFeature,
)


class TestExitCodeContract:
    """Exit codes must match the values documented in cli.md."""

    @pytest.mark.parametrize(
        ("error_cls", "expected_code"),
        [
            (CataforgeError, EXIT_GENERIC_FAILURE),
            (ConfigError, EXIT_GENERIC_FAILURE),
            (ExternalToolError, EXIT_GENERIC_FAILURE),
            (KGError, EXIT_GENERIC_FAILURE),
            (KGStoreError, EXIT_GENERIC_FAILURE),
            (KGVerificationError, EXIT_KG_VERIFICATION_FAILED),
            (NotImplementedFeature, EXIT_NOT_IMPLEMENTED),
        ],
    )
    def test_exit_code_value(self, error_cls, expected_code) -> None:
        assert error_cls.exit_code == expected_code

    def test_exit_code_constants_match_documented_values(self) -> None:
        # Burned-in: if these change, cli.md §退出码 must change too.
        assert EXIT_GENERIC_FAILURE == 1
        assert EXIT_KG_VERIFICATION_FAILED == 3
        assert EXIT_NOT_IMPLEMENTED == 70


class TestSubclassHierarchy:
    """All error types must derive from ``CataforgeError`` so Click
    renders them via ``ClickException.show`` (single ``Error:`` prefix
    on stderr, correct exit code)."""

    @pytest.mark.parametrize(
        "error_cls",
        [
            ConfigError,
            ExternalToolError,
            NotImplementedFeature,
            KGError,
            KGStoreError,
            KGVerificationError,
        ],
    )
    def test_inherits_from_cataforge_error(self, error_cls) -> None:
        assert issubclass(error_cls, CataforgeError)
        assert issubclass(error_cls, click.ClickException)

    def test_kg_subclasses_share_kg_base(self) -> None:
        assert issubclass(KGStoreError, KGError)
        assert issubclass(KGVerificationError, KGError)


class TestRaiseRendersExpectedExitCode:
    """End-to-end: when raised inside a Click command, the runner's
    ``result.exit_code`` matches the class attribute. Pre-fix this
    held only because every kg call site manually set
    ``err.exit_code = N`` — moving the value onto the class is what
    makes call sites correct by construction.
    """

    def _run_raising(self, exc_to_raise):
        from click.testing import CliRunner

        @click.command()
        def boom() -> None:
            raise exc_to_raise

        return CliRunner().invoke(boom, [])

    def test_kg_store_error_exits_one(self) -> None:
        result = self._run_raising(KGStoreError("store not initialised"))
        assert result.exit_code == 1
        assert "store not initialised" in result.output

    def test_kg_verification_error_exits_three(self) -> None:
        result = self._run_raising(KGVerificationError("3 violations"))
        assert result.exit_code == 3
        assert "3 violations" in result.output
