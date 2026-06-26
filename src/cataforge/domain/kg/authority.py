"""Authority policy: which side owns the truth, and how to remediate drift.

The document drift-state vocabulary (``DRIFT_*``) and the remediation
direction live here so reconcile, finalize and the Phase Transition gate
share one decision point instead of each re-encoding md-vs-graph authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Document-level drift states, decided by a three-way hash comparison between
# the on-disk file, the last-export baseline, and a fresh in-memory render.
DRIFT_NEVER_EXPORTED = "never_exported"
DRIFT_IN_SYNC = "in_sync"
DRIFT_HUMAN_EDIT = "human_edit"
DRIFT_GRAPH_AHEAD = "graph_ahead"
DRIFT_CONFLICT = "conflict"

# Remediation directions for a drifted document.
REMEDIATE_NONE = "none"
REMEDIATE_EXPORT = "export"  # graph → md (cataforge context finalize)
REMEDIATE_INGEST = "ingest"  # md → graph (cataforge context ingest)
REMEDIATE_MANUAL = "manual"  # both sides changed — needs a human decision


@dataclass(frozen=True)
class ModePolicy:
    """The single decision point for every mode-dependent behaviour.

    ``mode`` is the project's :data:`~cataforge.domain.kg._dispatch.context_mode`
    (``markdown`` / ``graph``). Authorization gates, finalize / ingest /
    reconcile direction, and drift remediation all route through this one
    object so no gate re-encodes md-vs-graph authority on its own.
    """

    mode: str

    @classmethod
    def for_project(cls, project_root: str | Path) -> ModePolicy:
        from cataforge.domain.kg._dispatch import context_mode

        return cls(mode=context_mode(project_root))

    @property
    def graph_enabled(self) -> bool:
        """True under ``graph`` mode: the graph is the canonical backend that
        ``context write*`` authors into and finalize exports from. ``markdown``
        has no graph at all.
        """
        return self.mode == "graph"

    def remediation_for(self, drift_state: str) -> str:
        """Recommend how to close a document's drift under this authority.

        Graph authority regenerates the view (``export``) or absorbs a human
        edit (``ingest``); a two-sided ``conflict`` needs a human. Markdown
        authority treats the files as canonical, so any divergence re-syncs
        the graph from Markdown (``ingest``).
        """
        if drift_state == DRIFT_IN_SYNC:
            return REMEDIATE_NONE
        if drift_state == DRIFT_CONFLICT:
            return REMEDIATE_MANUAL
        if self.graph_enabled:
            if drift_state in (DRIFT_GRAPH_AHEAD, DRIFT_NEVER_EXPORTED):
                return REMEDIATE_EXPORT
            if drift_state == DRIFT_HUMAN_EDIT:
                return REMEDIATE_INGEST
            return REMEDIATE_MANUAL
        return REMEDIATE_INGEST
