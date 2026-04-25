---
description: Run the CataForge orchestrator Bootstrap protocol for this project.
---

Invoke the orchestrator agent with instructions to execute the full Bootstrap
protocol defined in `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`.

The orchestrator must:

1. Detect the project's execution environment (package manager, install /
   test / lint commands) by running `cataforge setup --emit-env-block`
   and injecting the result into `CLAUDE.md` §执行环境.
2. Apply minimal permissions to `.claude/settings.json` by running
   `cataforge setup --apply-permissions`.
3. Report back the detected stack, the commands wired in, and any manual
   follow-ups the user still needs to perform.

If no stack is auto-detected (exit code 2), ask the user for the package
manager and test command before continuing.
