"""code-review Layer 1 engine — registry, pipeline, findings, shared FS/proc helpers.

Checks live in :mod:`cataforge.runtime.skill.builtins.code_review.checks`;
this package holds the check-agnostic machinery. ``CHECKS_MANIFEST`` in the
skill package root is derived from :mod:`registry`, never hand-written.
"""
