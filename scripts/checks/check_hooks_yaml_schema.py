#!/usr/bin/env python3
"""Anti-rot guard: docs/reference/configuration.md §hooks.yaml example
matches real .cataforge/hooks/hooks.yaml schema.

Catches the failure mode that audit round 2 found: §hooks.yaml
documented `version: 1` flat-list (`- id: ... event: ... matcher: ...`)
schema that was never in the codebase. Real schema_version is 2;
hooks are grouped by event; entries use matcher_capability + script
short-name; degradation_templates is a top-level block.

Method:
    - load .cataforge/hooks/hooks.yaml as the canonical example
    - extract the first ``schema_version: N`` example block from
      docs/reference/configuration.md (greedy until closing ```)
    - assert: same schema_version, same top-level keys, same event
      grouping shape

Fails (exit 1) on:
  - schema_version mismatch
  - doc example uses top-level keys absent from real (e.g. "version")
  - doc example omits real top-level keys (e.g. degradation_templates)
  - doc example structure doesn't show event-grouped hooks
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "reference" / "configuration.md"
REAL_HOOKS = REPO_ROOT / ".cataforge" / "hooks" / "hooks.yaml"


def extract_doc_example() -> dict | None:
    text = DOC.read_text(encoding="utf-8")
    section_start = text.find("\n## hooks.yaml")
    if section_start < 0:
        return None
    section_text = text[section_start:]
    m = re.search(r"```yaml\n(.*?)\n```", section_text, flags=re.DOTALL)
    if m is None:
        return None
    try:
        loaded = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        print(f"ERROR: doc example is not valid YAML: {e}", file=sys.stderr)
        return None
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    real = yaml.safe_load(REAL_HOOKS.read_text(encoding="utf-8"))
    doc = extract_doc_example()
    if doc is None:
        print(
            f"ERROR: could not extract a yaml example from §hooks.yaml in {DOC}",
            file=sys.stderr,
        )
        return 1

    fails: list[str] = []

    real_sv = real.get("schema_version")
    doc_sv = doc.get("schema_version")
    if real_sv != doc_sv:
        fails.append(
            f"schema_version mismatch: doc shows {doc_sv!r}, real is {real_sv!r}"
        )

    real_top = set(real.keys())
    doc_top = set(doc.keys())

    invented = doc_top - real_top
    if invented:
        fails.append(
            "doc example uses top-level keys absent from real hooks.yaml: "
            + ", ".join(sorted(invented))
        )

    missing = real_top - doc_top
    if missing:
        fails.append(
            "doc example omits top-level keys present in real hooks.yaml: "
            + ", ".join(sorted(missing))
        )

    # Structural: hooks must be a dict (event-grouped), not a list.
    if isinstance(doc.get("hooks"), list):
        fails.append(
            "doc example uses flat-list hooks (legacy v1); real schema_version 2 "
            "groups by event (PreToolUse / PostToolUse / Stop / ...)"
        )

    # Structural: each entry should be either matcher_capability + script
    # or just script (event-only). 'event' / 'matcher' / 'id' on entries
    # would indicate the legacy v1 schema.
    bad_fields = {"event", "matcher", "id"}
    if isinstance(doc.get("hooks"), dict):
        for evt, entries in doc["hooks"].items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict):
                    leaked = bad_fields & set(entry.keys())
                    if leaked:
                        fails.append(
                            f"doc example entry under {evt} uses legacy v1 fields "
                            f"{sorted(leaked)}; current schema uses matcher_capability + script"
                        )
                        break

    if fails:
        print("Anti-rot: hooks.yaml schema drift", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        print(
            f"\nFix: edit §hooks.yaml in {DOC.relative_to(REPO_ROOT)} to match "
            f"the real schema (.cataforge/hooks/hooks.yaml).",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: §hooks.yaml example matches real schema "
        f"(schema_version={real_sv}, "
        f"top-level keys={sorted(real_top)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
