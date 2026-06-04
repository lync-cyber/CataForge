"""Pure tally helpers for scaffold-classification results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any


def classify_tallies(classified: Iterable[tuple[Any, str]]) -> Counter[str]:
    """Tally the *status* component of a ``classify_scaffold_files`` result.

    The accepted-status set (``update`` / ``user-modified`` / ``drift`` /
    ``new`` / ``ok`` etc.) is enforced by the upstream classifier, not by this
    helper — we just tally whatever statuses arrive.
    """
    return Counter(status for _, status in classified)
