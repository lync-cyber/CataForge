"""CLI entry for document validation — implementation lives in ``checker``."""

from __future__ import annotations

from cataforge.skill.builtins.doc_review.checker import DocChecker, main

__all__ = ["DocChecker", "main"]


if __name__ == "__main__":
    main()
