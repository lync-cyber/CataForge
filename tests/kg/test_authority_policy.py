"""ModePolicy maps drift states to remediation directions per context mode."""

from __future__ import annotations

import pytest

from cataforge.domain.kg.authority import (
    DRIFT_CONFLICT,
    DRIFT_GRAPH_AHEAD,
    DRIFT_HUMAN_EDIT,
    DRIFT_IN_SYNC,
    DRIFT_NEVER_EXPORTED,
    REMEDIATE_EXPORT,
    REMEDIATE_INGEST,
    REMEDIATE_MANUAL,
    REMEDIATE_NONE,
    ModePolicy,
)

GRAPH = ModePolicy(mode="graph")
MARKDOWN = ModePolicy(mode="markdown")


def test_graph_enabled_by_mode() -> None:
    assert GRAPH.graph_enabled is True
    assert MARKDOWN.graph_enabled is False


@pytest.mark.parametrize(
    "state,expected",
    [
        (DRIFT_IN_SYNC, REMEDIATE_NONE),
        (DRIFT_CONFLICT, REMEDIATE_MANUAL),
        (DRIFT_GRAPH_AHEAD, REMEDIATE_EXPORT),
        (DRIFT_NEVER_EXPORTED, REMEDIATE_EXPORT),
        (DRIFT_HUMAN_EDIT, REMEDIATE_INGEST),
    ],
)
def test_graph_authority_directions(state: str, expected: str) -> None:
    assert GRAPH.remediation_for(state) == expected


@pytest.mark.parametrize(
    "state,expected",
    [
        (DRIFT_IN_SYNC, REMEDIATE_NONE),
        (DRIFT_CONFLICT, REMEDIATE_MANUAL),
        # Markdown is canonical: any one-sided divergence re-syncs the graph
        # from Markdown.
        (DRIFT_GRAPH_AHEAD, REMEDIATE_INGEST),
        (DRIFT_HUMAN_EDIT, REMEDIATE_INGEST),
        (DRIFT_NEVER_EXPORTED, REMEDIATE_INGEST),
    ],
)
def test_markdown_authority_directions(state: str, expected: str) -> None:
    assert MARKDOWN.remediation_for(state) == expected


@pytest.mark.parametrize(
    "state,expected",
    [
        # A never-exported document whose Markdown holds content the graph
        # lacks must not be overwritten from the poorer side.
        (DRIFT_NEVER_EXPORTED, REMEDIATE_INGEST),
        # The signal only redirects the never-exported case.
        (DRIFT_GRAPH_AHEAD, REMEDIATE_EXPORT),
        (DRIFT_HUMAN_EDIT, REMEDIATE_INGEST),
        (DRIFT_IN_SYNC, REMEDIATE_NONE),
        (DRIFT_CONFLICT, REMEDIATE_MANUAL),
    ],
)
def test_graph_authority_md_ahead_directions(state: str, expected: str) -> None:
    assert GRAPH.remediation_for(state, md_ahead=True) == expected


def test_markdown_authority_ignores_md_ahead() -> None:
    assert MARKDOWN.remediation_for(DRIFT_NEVER_EXPORTED, md_ahead=True) == REMEDIATE_INGEST
