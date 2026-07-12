# 无人值守 building 覆写 — headless overrides

> `cataforge unattended build [sprint]` 每轮以「无人值守 building 模式」拉起 orchestrator（PROMPT 显式声明并链接本文档）。按 §项目信息.执行模式 自动路由 building 目标：`standard` / `agile-lite` 驱动一个已冻结 sprint（**目标 ref** `dev-plan#{sprint}`）；`agile-prototype` 无 sprint 分组，驱动 brief.md §5 开发任务（**目标 ref** `brief#tasks`，sprint 参数忽略）。本文档仅在 headless 运行时按需加载，不进常驻 ORCHESTRATOR-PROTOCOLS，故非 loop 项目零成本。
>
> 此模式无人应答，下列行为覆写默认协议，其余门禁（TDD + code-review）不变。下文「目标 ref」按上述模式取 `dev-plan#{sprint}` 或 `brief#tasks`。

1. **needs_input → blocked**：禁止 AskUserQuestion；任何 needs_input 视同 blocked，`cataforge event log --event circuit_open --phase development --agent orchestrator --ref <目标 ref>` 后交还外壳。任务卡自足性由启动前置（`cataforge doctor`）保证。
2. **占位符字段视同已确认**：Startup Protocol 中「占位符字段 → 向用户确认」一步跳过，不产生 needs_input。
3. **卡级熔断覆写请求人工**：同一任务卡累计 needs_revision 达 `UNATTENDED_CARD_REVISION_CEILING` 时标该卡 `blocked`、emit `circuit_open`（`ref` 为任务卡）、跳下一张可并行卡（依赖图无后继则本目标收敛于熔断）；覆写 ORCHESTRATOR-PROTOCOLS §needs_revision 计数规范「N≥2 请求人工」与 §TDD Blocked Recovery「第 2 次 blocked 请求人工」。
4. **完成契约**：目标全部任务卡 code-review `approved` 时 emit `sprint_complete`（`ref=<目标 ref>`），作外壳确定性退出依据；该信号仅由真实门禁结果驱动，不由 building agent 自评。
5. **工作单元**：每会话最多完成一张任务卡（大卡至多推进一个 TDD 相并 Mid-Progress 落盘），完成即 git commit 后干净退出，由外壳拉起新会话继续；不连做多卡。干净退出无冷启动损耗，也让外壳的存活监督（流静默判据）保持纯异常探测本职。

> **circuit_open 的 ref 语义**：卡级熔断（item 3）`ref` 为任务卡，外壳据此**不停整个循环**、只让 orchestrator 跳下一张卡；needs_input 终局（item 1）`ref=<目标 ref>`（目标级），外壳据此停循环交还人工。两者必须用 `ref` 区分。
>
> **护栏强制边界**：`git merge` / `gh pr merge` / push main 由 `guard_dangerous` PreToolUse hook 在 `CATAFORGE_UNATTENDED` 下拦截（容忍 `git -C <path> …` 等全局 flag 变体）。此 hook 是 shell-string 正则，**本质 best-effort**：`bash -c …` 之类 wrapper、以及依赖 upstream 恰为 main 的裸 `git push`（命令字面不含 main）无法拦——真正保障是 sandbox + PR-only 合并策略 + 人工晨检 + fail-closed preflight（非 feature 分支一律拒跑）。**禁止改 PRD/ARCH/UI-SPEC/DEV-PLAN 及 agile-prototype 的 brief** 由 `guard_frozen_docs` PreToolUse hook 在 `CATAFORGE_UNATTENDED` 下按 `docs/{type}/` 路径拦 `Write`/`Edit`（file_edit matcher）。任务卡 status 更新按 `context.mode` 分流：graph 模式走 `cataforge context update`（非 file_edit）不受此拦；markdown 模式文档即任务状态事实源，hook 仅放行 dev-plan/brief 中 status 字段行 / 状态表单元格的最小 `Edit`，其余改动（含整文件 `Write`）仍拦。同为 best-effort speed-bump，真正保障仍是 sandbox + PR-only + 人工晨检。
>
> **preflight 分支门**：只在确认的 feature 分支上跑（`git symbolic-ref --short HEAD` 非空且非 `main`）；detached HEAD / 空仓 unborn-main / 无 git 一律拒。受保护主干硬编码为 `main`，非 main 主干的下游项目暂不适配（已知缺口）。
