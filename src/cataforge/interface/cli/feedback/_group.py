"""The ``feedback`` Click group — subcommands attach in the family modules."""

from __future__ import annotations

from cataforge.interface.cli.main import cli


@cli.group("feedback")
def feedback_group() -> None:
    """Bundle local signals into upstream-ready feedback (bug / suggest / corrections).

    Aggregates ``cataforge doctor`` + recent EVENT-LOG + ``upstream-gap``
    corrections + ``framework-review`` Layer 1 fails into a single markdown
    body, then emits it via stdout / file / clipboard / `gh issue create`.

    Designed to close the loop from downstream usage back to CataForge
    upstream — pair with ``correction record --deviation upstream-gap``
    when you spot an upstream baseline that was wrong for your context.
    """
