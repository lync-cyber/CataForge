# Hook Degradation Strategies

各平台 `profile.yaml#hooks.degradation` 把 canonical hook 标记为 `native` / `degraded` / 缺失。`native` 表示直接生成平台 hook 配置；`degraded` 表示走 [hooks.yaml#degradation_templates](../../.cataforge/hooks/hooks.yaml) 中的降级策略；缺失等同于 `native`。

本文档列出 `cataforge.runtime.hook.bridge.apply_degradation` 当前实装的降级策略。策略集合的权威定义是模块常量 [`KNOWN_DEGRADATION_STRATEGIES`](../../src/cataforge/runtime/hook/bridge.py)。

## 策略一览

| strategy | 输出文件 | 适用场景 |
|---|---|---|
| `rules_injection` | `overrides/rules/auto-safety-degradation.md` | 把安全规则注入为常驻 alwaysApply rule（如 `guard_dangerous` 在缺失 PreToolUse 的平台上的兜底） |
| `prompt_instruction` | `overrides/rules/auto-prompt-instructions.md` | 把"agent 应主动执行某命令"的指令注入为常驻规则（如 `log_agent_dispatch` 在 hook matcher 不支持 agent 类型时的审计日志命令） |
| `prompt_checklist` | `overrides/rules/auto-prompt-checklists.md` | 把"返回前自检"的检查清单注入为常驻规则（如 `validate_agent_result` 在缺失子代理 PostToolUse 的平台上的兜底） |
| `skip` | — | 该 hook 在当前平台无降级补偿；deploy 输出一行 `SKIP: <hook> — <reason>` 让丢失可见，不写任何文件 |

未列入上表的 strategy 会被 bridge.apply_degradation 视为**未知策略**，emit 一行 `WARN: <hook> — unrecognised degradation strategy '<X>'; nothing emitted.`。这是防呆兜底：未来在 hooks.yaml 加新 strategy 但忘了在 bridge.py 实装时，deploy / doctor 会立刻报告，而不是悄无声息丢弃。

## 输出文件格式

三个 `*-injection`/`*-instruction`/`*-checklist` 文件结构一致：

```markdown
# {Heading}

## {hook_name_1}

{content_1}

## {hook_name_2}

{content_2}
```

每个 fragment 带 `## {hook_name}` 二级标题以便追溯来源。同一 strategy 多个 hook 聚合到同一文件，不同 strategy 不混写。

## 平台消费规则注入的差异

文件被写到 `.cataforge/platforms/{platform}/overrides/rules/` 后，是否进一步注入到 agent 上下文取决于平台 adapter：

| 平台 | adapter 行为 |
|---|---|
| **cursor** | `CursorAdapter._generate_mdc_rules` 扫描 `overrides/rules/`，把每个 `.md` wrap 成 `.cursor/rules/*.mdc`，frontmatter `alwaysApply: true`。规则文件常驻每次会话 |
| **claude-code** | rules 通过 `.claude/rules` 目录（`context_injection.rules_distribution`），activation 由 agent 自行 Read。当前实装 deploy 不主动 wire `overrides/rules/` 到 `.claude/rules` |
| **codex** | `instruction_file.additional_outputs: []`，`context_injection.rules_distribution.activation: manual_read`。`overrides/rules/` 文件**会被写盘但不自动注入** — agent 需通过 AGENTS.md 提示或人工 Read 才能见到 |
| **opencode** | 通过 plugin 文件（`emit_plugin_hooks`）独立处理 hook，per-hook degradation strategy 与 plugin 互补 |

也就是说：本机制保证**所有 degraded hook 的降级内容都能被写盘**，但**实际是否对 agent 生效**与平台 adapter 的 rule 消费策略耦合。如需让 Codex 等平台真正常驻这些规则，需要单独 PR 扩展该平台 adapter 的 `overrides/rules/` wiring（目前只有 Cursor 做了这件事）。

## 何时新增 strategy

新增 strategy 必须**同步**修改三处：

1. `.cataforge/hooks/hooks.yaml` 在 `degradation_templates` 下定义模板
2. `src/cataforge/runtime/hook/bridge.py` 把新 key 加入 `KNOWN_DEGRADATION_STRATEGIES`，并在 `_AGGREGATE_OUTPUTS` 注册输出文件名（除非该 strategy 不写文件）
3. 本文档 §策略一览 表追加一行

模块级守卫测试 [tests/hook/test_bridge_degradation.py](../../tests/hook/test_bridge_degradation.py) 的 `test_known_strategies_set_matches_aggregate_outputs_plus_skip` 断言 `KNOWN_DEGRADATION_STRATEGIES == set(_AGGREGATE_OUTPUTS keys) | {"skip"}`；不同步会立刻 FAIL。
