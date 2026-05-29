"""Contract tests for ``cataforge.core.errors`` + the CLI render adapter.

Each subclass carries a documented ``exit_code`` that downstream CI
scripts branch on (see ``docs/reference/cli.md`` §退出码). The mapping
is part of the public CLI surface — changing a value silently would
break those scripts. These tests freeze the table and the rendering
contract provided by :class:`cataforge.interface.cli.errors.CataforgeGroup`.
"""

from __future__ import annotations

import click
import pytest

from cataforge.core.errors import (
    EXIT_GENERIC_FAILURE,
    EXIT_KG_VERIFICATION_FAILED,
    EXIT_NOT_IMPLEMENTED,
    CataforgeError,
    ConfigError,
    ExternalToolError,
    KGCLIError,
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
            (KGCLIError, EXIT_GENERIC_FAILURE),
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
    """All error types derive from ``CataforgeError`` and stay decoupled
    from Click — rendering is the CLI adapter's job, not the error's."""

    @pytest.mark.parametrize(
        "error_cls",
        [
            ConfigError,
            ExternalToolError,
            NotImplementedFeature,
            KGCLIError,
            KGStoreError,
            KGVerificationError,
        ],
    )
    def test_inherits_from_cataforge_error(self, error_cls) -> None:
        assert issubclass(error_cls, CataforgeError)
        assert not issubclass(error_cls, click.ClickException)

    def test_kg_subclasses_share_kg_base(self) -> None:
        assert issubclass(KGStoreError, KGCLIError)
        assert issubclass(KGVerificationError, KGCLIError)


class TestRaiseRendersExpectedExitCode:
    """End-to-end: a ``CataforgeError`` raised inside a command mounted
    under :class:`CataforgeGroup` renders ``Error: <msg>`` on stderr and
    exits with the error's class-level ``exit_code``.
    """

    def _run_raising(self, exc_to_raise):
        from click.testing import CliRunner

        from cataforge.interface.cli.errors import CataforgeGroup

        @click.group(cls=CataforgeGroup)
        def root() -> None:
            pass

        @root.command()
        def boom() -> None:
            raise exc_to_raise

        return CliRunner().invoke(root, ["boom"])

    def test_kg_store_error_exits_one(self) -> None:
        result = self._run_raising(KGStoreError("store not initialised"))
        assert result.exit_code == 1
        assert "store not initialised" in result.output

    def test_kg_verification_error_exits_three(self) -> None:
        result = self._run_raising(KGVerificationError("3 violations"))
        assert result.exit_code == 3
        assert "3 violations" in result.output
