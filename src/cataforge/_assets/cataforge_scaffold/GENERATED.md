# GENERATED — DO NOT EDIT

This directory is a **generated mirror** of the canonical scaffold at
`<repo-root>/.cataforge/`, regenerated on every sdist/wheel build by
`scripts/hatch_build.py` and kept in sync at commit time by
`scripts/sync_scaffold.py`.

Editing files in this directory directly will:

- be reverted the next time `scripts/sync_scaffold.py` runs, or
- be flagged as drift by `.github/workflows/scaffold-sync.yml` and block
  the PR.

## Where to edit

- Skill / agent / hook / rule changes → `<repo-root>/.cataforge/`
- Then run `python scripts/sync_scaffold.py` to update this mirror.

## Why this mirror exists

The wheel ships a copy of the scaffold so `cataforge setup` /
`cataforge upgrade apply` can drop a working `.cataforge/` into a fresh
project without network access. Hatchling cannot package files outside
`src/cataforge/`, hence the in-tree mirror.

This `GENERATED.md` is intentionally **not** mirrored back to
`.cataforge/`; it lives only here, marked as a target-only file in
`scripts/sync_scaffold.py`.
