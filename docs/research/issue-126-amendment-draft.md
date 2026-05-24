---
id: research-issue-126-amendment-draft
doc_type: research-note
author: architect
status: draft
deps: ["research-kg-feature-upgrade-design"]
consumers: [orchestrator]
---

# Issue #126 amendment draft (supersession notice)

This file holds the text that will be posted to GitHub Issue #126 +
the body of the new tracking issue. Both are committed to the repo
first (this file is the canonical source); the maintainer posts them
verbatim via `gh issue comment` / `gh issue create` once the KG cutover
PR lands. Keeping the text in-tree means future readers can trace
*why* #126 was closed without spelunking GitHub's API.

## 1 · Comment to append to #126

```markdown
**Amendment (supersession notice)**

This issue was scoped as an incremental metadata layer on top of
`.doc-index.json`. The follow-up
[`docs/research/kg-feature-upgrade-design.md`](https://github.com/lync-cyber/CataForge/blob/main/docs/research/kg-feature-upgrade-design.md)
escalated the scope to a full KG-first reorganisation (RDF/OWL/SPARQL/SHACL,
KGAdapter layer, `cataforge kg` CLI surface, render-from-KG markdown
pipeline). The new scope subsumes everything this issue tracked, plus:

- L0/L1/L2/L3 ontology with SHACL validation
- 6 built-in KGAdapter classes + plugin registration mechanism
- 3-way merge (kg / file / render) for safe PostToolUse auto-ingest
- Render idempotency contract (template-lint + render --check gates)
- Coverage matrices (RTM / risk / test / interface presets)
- oxigraph plugin as backend swap when rdflib's perf budget runs out

Closing this issue **as superseded by the KG design + cutover** (this
repo's `claude/loving-einstein-86008e` branch lands the implementation
across waves A–F). Existing comments and discussion remain in scope for
historical context.

New tracking issue: TBD (URL to be linked once the maintainer creates it
from the §2 template below).
```

## 2 · New tracking issue body (epic)

```markdown
**Title:** epic: KG-first documentation system rollout (supersedes #126)

**Body:**

Tracks the rollout of the KG-first documentation system designed in
[`docs/research/kg-feature-upgrade-design.md`](https://github.com/lync-cyber/CataForge/blob/main/docs/research/kg-feature-upgrade-design.md).
Supersedes #126.

### Status (post-PR)

- [x] Wave A · Ontology + storage foundation (kernel/process/artifact .ttl + SHACL + reasoning + benchmark)
- [x] Wave B · Ingest + migrate + 3-way delta
- [x] Wave C · Query, render, CLI, template-lint, PoC templates
- [x] Wave D · Adapter layer + 24-frontmatter migration + escape hatch
- [x] Wave E · CLI infer/viz, plugin loader, oxigraph plugin, cookbook
- [x] Wave F · PostToolUse hook, doctor integration, pre-commit, PR CI, upgrade auto-migrate
- [ ] v0.5 release cutover · delete legacy `cataforge.docs.indexer` / `cataforge.docs.loader`, switch `cataforge docs *` to thin alias delegating to `cataforge kg *`

### Open follow-ups (v0.6+)

- L3 ontology editor skill (so downstream PM/Dev don't have to learn Turtle)
- KG diff GH Action for PR review (mitigates R-14 reviewer fatigue)
- Remote KG endpoint for multi-repo shared KG
- SPARQL Federation across project KGs
- `cataforge kg viz --serve` interactive web viewer
- Reverse codegen — OpenAPI / GraphQL schema generation from KG

### References

- Design note: [`docs/research/kg-feature-upgrade-design.md`](https://github.com/lync-cyber/CataForge/blob/main/docs/research/kg-feature-upgrade-design.md)
- Migration cookbook: [`docs/reference/kg-cookbook.md`](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/kg-cookbook.md)
- SPARQL recipes: [`docs/reference/kg-sparql-recipes.md`](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/kg-sparql-recipes.md)
- Risk register: design note §9 (R-01 through R-21)
```

## 3 · Maintainer action checklist

After the KG cutover PR merges to main:

1. `gh issue comment 126 --body-file docs/research/issue-126-amendment-draft.md` —
   then trim the rendered comment to only §1 above.
2. `gh issue create --title "epic: KG-first documentation system rollout (supersedes #126)" --body-file …` —
   use §2 verbatim.
3. `gh issue close 126 --reason "not planned" --comment "Superseded by #<new-issue>"`.
4. Update §1's "New tracking issue: TBD" line with the new issue URL and
   amend the closing comment if needed.
