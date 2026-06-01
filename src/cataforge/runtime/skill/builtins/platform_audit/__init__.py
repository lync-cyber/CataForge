"""Built-in offline subset of the platform-audit skill.

The full ``platform-audit`` skill is an LLM playbook (fetch live IDE docs, diff
against profiles, patch). This package is its statically-checkable core — the
no-network checks that run in CI without an LLM. See :mod:`.offline`.
"""
