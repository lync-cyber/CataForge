"""Bundled CataForge assets.

Holds non-Python data shipped inside the wheel:

- ``cataforge_scaffold/``: the default ``.cataforge/`` project skeleton
  (agents, skills, rules, hooks, platform profiles, schemas, templates)
  copied into the user's project on ``cataforge setup``.

Access via :func:`importlib.resources.files` — do not import submodules
directly. See :mod:`cataforge.core.scaffold` for the public helper.
"""
