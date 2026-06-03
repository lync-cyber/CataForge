"""Reproduce and classify the #210 entity_id collisions in a downstream project.

Run from a kg-first project root (or pass it as argv[1]):

    PYTHONUTF8=1 python repro_diag.py [PROJECT_ROOT]

Reuses the live ingest extractor so the numbers track the real
`kg import` collision gate. Emits per-collision section attribution and a
3-way classification (pollution_only / genuine_multi / no_owner) that
separates defect (1) "mention-as-definition" from defect (2) "subordinate
entity flat IRI". No store is touched.
"""

import io
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cataforge.domain.kg.ingest.entity_extract import (
    detect_entity_id_collisions,
    extract_entities,
)
from cataforge.domain.kg.ingest.scan import scan_business_docs

DOC_TYPES = ["prd", "arch", "ui-spec", "dev-plan", "test-report", "deploy-spec"]
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

parsed = scan_business_docs(root, DOC_TYPES)
all_entities = [e for doc in parsed for e in extract_entities(doc)]

by_id: dict[str, dict[str, tuple[str, int]]] = defaultdict(dict)
for e in all_entities:
    by_id[e.entity_id].setdefault(e.source_doc, (e.source_section.strip(), e.section_line_start))

collisions = detect_entity_id_collisions(all_entities)
collision_ids = {c.entity_id for c in collisions}


def title_defines(entity_id: str, title: str) -> bool:
    """A heading that carries the id is a genuine definition; else a mention."""
    return entity_id in title


print("scanned doc_ids:", sorted({d.doc_id for d in parsed}))
print("total entity occurrences:", len(all_entities))
print("distinct entity_ids:", len(by_id))
print("collision entity_ids:", len(collisions))
print()

pollution_only, genuine_multi, no_owner = [], [], []
for cid in sorted(collision_ids):
    owners = [d for d, (t, _) in by_id[cid].items() if title_defines(cid, t)]
    if len(owners) >= 2:
        genuine_multi.append((cid, owners))
    elif len(owners) == 1:
        pollution_only.append((cid, owners[0]))
    else:
        no_owner.append(cid)

print("=== classification ===")
print("  pollution_only (1 def + rest mentions):", len(pollution_only))
print("  genuine_multi  (>=2 headings carry id):", len(genuine_multi))
print("  no_owner       (no heading carries id):", len(no_owner))
print()

print("=== per-collision detail ===")
for cid in sorted(collision_ids):
    print("### " + cid)
    for doc, (title, ln) in sorted(by_id[cid].items()):
        flag = "DEF " if title_defines(cid, title) else "ment"
        print("    [%s] %-12s L%-5d %s" % (flag, doc, ln, title[:60]))
