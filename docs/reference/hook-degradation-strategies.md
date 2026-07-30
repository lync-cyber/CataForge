# Hook Policies and Fallback Strategies

Hook 的平台策略由各 `profile.yaml#hooks.policies.<script>` 独立声明；`.cataforge/hooks/hooks.yaml` 只保存平台无关的事件、matcher capability 与脚本定义。

```yaml
hooks:
  policies:
    detect_correction:
      mode: hybrid
      fallback:
        strategy: prompt_instruction
        coverage: partial
        reason: "结构化路径只覆盖 request_user_input"
        asset: fallbacks/correction-record.md
```

## Mode

| mode | 原生 hook | fallback | 用途 |
|---|:---:|:---:|---|
| `native` | 是 | 否 | 平台原生行为完整 |
| `hybrid` | 是 | 是 | 原生行为有条件可用，fallback 补充未覆盖路径 |
| `degraded` | 否 | 是 | 平台没有可用原生事件或工具 |
| `unsupported` | 否 | 否 | 明确不可用；deploy 输出诊断 |

`hybrid` 和 `degraded` 必须提供 `fallback`。旧 `hooks.degradation`、`hooks.tool_overrides` 与全局 `degradation_templates` 已删除，不提供兼容解析。

## Fallback

| 字段 | 说明 |
|---|---|
| `strategy` | `rules_injection` / `prompt_instruction` / `prompt_checklist` / `skip` |
| `coverage` | `equivalent` / `partial` / `none`；不得把缺失或启发式 fallback 标为 equivalent |
| `reason` | 为什么需要 fallback，以及覆盖边界 |
| `asset` | 相对 `.cataforge/platforms/<id>/` 的源资产路径 |
| `content` | 小型内联文本；与 `asset` 二选一即可 |

策略输出：

| strategy | 输出 |
|---|---|
| `rules_injection` | 临时 staging 的 `auto-safety-degradation.md`，随后渲染到平台规则目录 |
| `prompt_instruction` | 临时 staging 的 `auto-prompt-instructions.md`，随后渲染到平台规则目录 |
| `prompt_checklist` | 临时 staging 的 `auto-prompt-checklists.md`，随后渲染到平台规则目录 |
| `skip` | 不写文件，只输出带 reason 的 SKIP 诊断 |

三个文本策略按 hook 名聚合，每段带 `## <hook_name>` 标题以便追溯。staging
目录由 deploy 持有并在结束时清理，因此生成 fallback 不会反向污染 `.cataforge`
源资产。策略枚举由 profile schema 与 `bridge.KNOWN_DEGRADATION_STRATEGIES` 共同约束。

## 平台消费差异

fallback 资产最终是否自动进入模型上下文，仍取决于平台的 rule 分发能力：

| 平台 | 行为 |
|---|---|
| Cursor | `overrides/rules/` 转成 `.cursor/rules/*.mdc`，alwaysApply |
| Claude Code | 通过 `.claude/rules` 分发；activation 由 profile 声明 |
| Codex | 规则分发为 `manual_read`；当前 correction fallback 明确仅为 partial 人工记录指令 |
| OpenCode | plugin hook 与 fallback 规则互补 |

Codex `detect_correction` 使用 `hybrid`：结构化 `request_user_input` 响应由原生 `PostToolUse` hook 解析；用户直接在文本里纠正时，仅提供明确的人工记录指令，不用文本启发式猜测纠偏。

## 新增策略

新增 strategy 必须同步：

1. 扩展 `HookFallback.strategy` schema；
2. 在 `bridge.py` 注册生成逻辑与聚合输出；
3. 增加 native/hybrid/degraded/unsupported 与 coverage 的 conformance 测试；
4. 更新本文档。
