"""``cataforge kg`` subcommand modules.

Importing this package is a side-effect: each submodule defines Click
commands that decorate the ``kg_group`` (defined in
``cataforge.cli.kg_cmd``). The top-level ``kg_cmd.py`` imports this
package so the decorators run at startup and the commands appear under
``cataforge kg --help``.

Module layout:

* :mod:`cataforge.cli.kg._common`  — shared helpers (project-root option,
  store loader, CURIE shorteners, GraphML / mermaid serializers)
* :mod:`cataforge.cli.kg.query`    — read-only commands (query, validate,
  conflicts, coverage, infer, impact, explain, viz)
* :mod:`cataforge.cli.kg.ingest`   — content → graph (ingest, migrate,
  export, render, template-lint, benchmark)
* :mod:`cataforge.cli.kg.crud`     — store mutations (init, add/update/
  delete entity, add/remove relation, resolve, adapter subgroup)
"""
