"""AuthorityPolicy maps drift states to remediation directions per authoring mode."""

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
    AuthorityPolicy,
)

GRAPH = AuthorityPolicy(strategy="kg-first", authoring="graph")
MD = AuthorityPolicy(strategy="kg-first", authoring="md")


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
    assert GRAPH.graph_is_source is True
    assert GRAPH.remediation_for(state) == expected


@pytest.mark.parametrize(
    "state,expected",
    [
        (DRIFT_IN_SYNC, REMEDIATE_NONE),
        (DRIFT_CONFLICT, REMEDIATE_MANUAL),
        # Markdown is canonical: any one-sided divergence re-syncs the graph.
        (DRIFT_GRAPH_AHEAD, REMEDIATE_INGEST),
        (DRIFT_HUMAN_EDIT, REMEDIATE_INGEST),
        (DRIFT_NEVER_EXPORTED, REMEDIATE_INGEST),
    ],
)
def test_md_authority_directions(state: str, expected: str) -> None:
    assert MD.graph_is_source is False
    assert MD.remediation_for(state) == expected
