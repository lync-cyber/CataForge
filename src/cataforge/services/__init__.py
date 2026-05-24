"""Service layer — orchestrates IO-heavy collectors that core/ must not
import directly.

Why this layer exists: ``core/`` holds pure assemblers (feedback bundles,
event records, corrections parsing) that downstream skills, CLI commands,
and tests all depend on. When ``core/`` imports from ``cli/``, the
dependency graph inverts and ``cli/`` ends up indirectly depending on
itself via ``core/`` — that's hard to test in isolation and easy to break
with circular-import errors during a refactor.

``services/`` is the seam where ``cli/``-aware orchestration lives. A
service module is allowed to import from ``cli/`` (e.g. to invoke a Click
command in-process via ``CliRunner``); ``core/`` is not.
"""
