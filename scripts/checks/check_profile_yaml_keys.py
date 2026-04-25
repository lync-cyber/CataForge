#!/usr/bin/env python3
"""Anti-rot guard: docs/reference/configuration.md §profile.yaml example
top-level keys match real profile.yaml.

Catches the failure mode that audit round 2 found: §profile.yaml
documented `paths:` / `degradation:` / `capabilities:` keys that are
absent from every real profile (real keys are platform_id / tool_map /
extended_capabilities / agent_definition / skill_definition /
command_definition / agent_config / instruction_file / dispatch /
hooks / features / permissions / model_routing / context_injection /
rules). A user authoring a new profile from the docs would have most
of it silently ignored by PlatformAdapter.

Method:
    - load .cataforge/platforms/cursor/profile.yaml as the canonical
      schema (it uses every documented key)
    - extract the first ``platform_id: cursor`` example block from
      docs/reference/configuration.md (greedy until the closing ```)
    - compare top-level keys

Fails (exit 1) if the doc example uses any key absent from the real
profile, or omits any required key. Optional keys may be omitted in
the example for brevity (warned, not failed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "reference" / "configuration.md"
SCHEMA = REPO_ROOT / ".cataforge" / "platforms" / "_schema.yaml"
REAL_PROFILE = REPO_ROOT / ".cataforge" / "platforms" / "cursor" / "profile.yaml"

# Keys that may legitimately be elided from the doc example (purely
# optional sections — the example doesn't have to enumerate them).
OPTIONAL_OMISSIONS: set[str] = {
    "rules",            # cross-platform mirror flag — almost always default false
    "permissions",      # listed inline in feature matrix
    "model_routing",    # documented in a separate matrix
    "extended_capabilities",  # often null-only on minimal platforms
}


def extract_doc_example_keys() -> set[str] | None:
    text = DOC.read_text(encoding="utf-8")
    # Find the first yaml fence after the §platforms/<id>/profile.yaml header
    section_start = text.find("\n## platforms")
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
    if not isinstance(loaded, dict):
        return None
    return set(loaded.keys())


def real_profile_keys() -> set[str]:
    return set(yaml.safe_load(REAL_PROFILE.read_text(encoding="utf-8")).keys())


def schema_required_keys() -> set[str]:
    """Required-fields set per _schema.yaml (best-effort string scrape)."""
    text = SCHEMA.read_text(encoding="utf-8")
    in_required = False
    keys: set[str] = set()
    for line in text.splitlines():
        if line.startswith("required_fields:"):
            in_required = True
            continue
        if line.startswith("optional_fields:"):
            in_required = False
            continue
        if in_required and re.match(r"^  ([a-z_]+):", line):
            keys.add(re.match(r"^  ([a-z_]+):", line).group(1))
    return keys


def main() -> int:
    doc_keys = extract_doc_example_keys()
    if doc_keys is None:
        print(
            f"ERROR: could not extract a yaml example from §profile.yaml in {DOC}",
            file=sys.stderr,
        )
        return 1

    real_keys = real_profile_keys()
    required = schema_required_keys()

    invented = doc_keys - real_keys
    missing_required = required - doc_keys
    fails: list[str] = []

    if invented:
        fails.append(
            "§profile.yaml example uses keys absent from real profile / schema: "
            + ", ".join(sorted(invented))
            + " — readers authoring new profiles will get these silently ignored."
        )
    if missing_required:
        fails.append(
            "§profile.yaml example omits required keys: "
            + ", ".join(sorted(missing_required))
            + " — example must show enough to be a working starting point."
        )

    if fails:
        print("Anti-rot: profile.yaml schema drift", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        print(
            f"\nFix: edit §profile.yaml in {DOC.relative_to(REPO_ROOT)} so "
            f"the example matches the real schema (cursor profile + _schema.yaml).",
            file=sys.stderr,
        )
        return 1

    omitted_optional = (real_keys - doc_keys) & OPTIONAL_OMISSIONS
    extra_in_doc = (real_keys - doc_keys) - OPTIONAL_OMISSIONS
    msg = (
        f"OK: §profile.yaml example covers {len(doc_keys)} top-level keys "
        f"(real profile has {len(real_keys)})"
    )
    if extra_in_doc:
        msg += (
            f"; note: {len(extra_in_doc)} non-optional real keys not shown "
            f"({', '.join(sorted(extra_in_doc))})"
        )
    if omitted_optional:
        msg += f"; optional keys legitimately omitted: {', '.join(sorted(omitted_optional))}"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
