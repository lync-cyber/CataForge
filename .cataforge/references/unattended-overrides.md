# 无人值守 building 覆写 — headless overrides

> `cataforge unattended build <sprint>` 每轮以「无人值守 building 模式」拉起 orchestrator（PROMPT 显式声明并链接本文档）。仅驱动一个已冻结 sprint 的 building。本文档仅在 headless 运行时按需加载，不进常驻 ORCHESTRATOR-PROTOCOLS，故非 loop 项目零成本。
>
> 此模式无人应答，下列行为覆写默认协议，其余门禁（TDD + code-review）不变。

1. **needs_input → blocked**：禁止 AskUserQuestion；任何 needs_input 视同 blocked，`cataforge event log --event circuit_open --phase development --agent orchestrator --ref dev-plan#{sprint}` 后交还外壳。任务卡自足性由启动前置（`cataforge doctor`）保证。
2. **占位符字段视同已确认**：Startup Protocol 中「占位符字段 → 向用户确认」一步跳过，不产生 needs_input。
3. **卡级熔断覆写请求人工**：同一任务卡累计 needs_revision 达 `UNATTENDED_CARD_REVISION_CEILING` 时标该卡 `blocked`、emit `circuit_open`（`ref` 为任务卡）、跳下一张可并行卡（依赖图无后继则本 sprint 收敛于熔断）；覆写 ORCHESTRATOR-PROTOCOLS §needs_revision 计数规范「N≥2 请求人工」与 §TDD Blocked Recovery「第 2 次 blocked 请求人工」。
4. **完成契约**：目标 sprint 全部任务卡 code-review `approved` 时 emit `sprint_complete`（`ref=dev-plan#{sprint}`），作外壳确定性退出依据；该信号仅由真实门禁结果驱动，不由 building agent 自评。

> **circuit_open 的 ref 语义**：卡级熔断（item 3）`ref` 为任务卡，外壳据此**不停整个循环**、只让 orchestrator 跳下一张卡；needs_input 终局（item 1）`ref=dev-plan#{sprint}`（sprint 级），外壳据此停循环交还人工。两者必须用 `ref` 区分。
>
> **护栏强制边界**：`git merge` / `gh pr merge` / push main 由 `guard_dangerous` PreToolUse hook 在 `CATAFORGE_UNATTENDED` 下拦截（容忍 `git -C <path> …` 等全局 flag 变体）。此 hook 是 shell-string 正则，**本质 best-effort**：`bash -c …` 之类 wrapper、以及依赖 upstream 恰为 main 的裸 `git push`（命令字面不含 main）无法拦——真正保障是 sandbox + PR-only 合并策略 + 人工晨检 + fail-closed preflight（非 feature 分支一律拒跑）。**禁止改 PRD/ARCH/DEV-PLAN** 目前仅由本文档 + PROMPT 约束（`Write`/`Edit` 走 file_edit matcher，deny hook 不拦）—— 这是已知缺口，file_edit 层守卫为后续工作。
>
> **preflight 分支门**：只在确认的 feature 分支上跑（`git symbolic-ref --short HEAD` 非空且非 `main`）；detached HEAD / 空仓 unborn-main / 无 git 一律拒。受保护主干硬编码为 `main`，非 main 主干的下游项目暂不适配（已知缺口）。
