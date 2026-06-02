---
description: Bootstrap or refresh CataForge for this project — idempotent, upgrade-aware framework reconcile + project init/resume.
---

Bring this project's CataForge framework **and** project scaffolding to a
current, verified state. Idempotent and upgrade-aware: re-running on an
already-bootstrapped project refreshes whatever is stale (e.g. after
`pip install -U cataforge` / `uv tool upgrade cataforge`) and otherwise just
re-verifies.

The orchestrator must execute the following in order.

## 1. Reconcile the framework lifecycle (always)

Preview the idempotent package→scaffold pipeline:

```bash
cataforge bootstrap --dry-run
```

It decides each step from on-disk state:

- **setup** — skipped when `.cataforge/` is already present.
- **upgrade** — runs when the installed package version is newer than the
  recorded scaffold version, or manifest drift exists (scaffold refresh).
- **deploy** — runs when the scaffold was refreshed, the platform changed, or
  the project was never deployed.
- **doctor** — always runs as the verification gate.

If only `doctor` runs, report "already current". If any other step is `run`,
show the plan, confirm with the user, then apply:

```bash
cataforge bootstrap --yes
```

If it reports a fresh install needs a platform, ask the user (`claude-code`
default) and rerun `cataforge bootstrap --platform <id> --yes`. If
`cataforge upgrade check` flags a CHANGELOG `### BREAKING` entry inside the
upgrade range, summarise it for the user before applying.

## 2. Initialise or resume the project

Branch on `{INSTRUCTION_FILE}`:

- **Absent — from-scratch project.** Execute the full Project Bootstrap protocol
  in `{AGENTS_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md` §Project Bootstrap
  (collect project info, select execution mode, create `docs/` structure, write
  `{INSTRUCTION_FILE}`, wire env + permissions, enter the initial phase). The
  target platform is already reconciled by step 1 — read it from
  `framework.json` `runtime.platform` rather than re-selecting or re-deploying.
- **Present — already initialised.** Do not re-run Project Bootstrap. If
  `{INSTRUCTION_FILE}` §执行环境 is still a placeholder or the stack changed, wire
  it now:

  ```bash
  cataforge setup --emit-env-block      # inject §执行环境; exit code 2 = no known stack
  cataforge setup --apply-permissions   # tighten permissions.allow to the stack
  ```

  On exit code 2, write `- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）`
  and ask the user for the package manager + test command. Then hand off to
  `/start-orchestrator continue` for phase resume.

## 3. Report

Summarise: the framework reconciliation (scaffold vs installed version, which
steps ran), the init/resume decision, the detected stack and wired commands,
and any manual follow-ups the user still needs to perform.
