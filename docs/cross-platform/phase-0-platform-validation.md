# Phase 0: 平台假设验证 — Cursor 最小端到端

> 前置条件：无（最先执行）
> 预计工时：3-5 天
> 目标：用最小代价验证跨平台设计的关键假设，产出 go/no-go 决策

---

## 动机

v1 方案前置了 87 文件迁移（Phase 0）和 26 个新文件的抽象层（Phase 1），但多项核心假设未经验证。Phase 0 改为在当前目录结构下（不动 `.claude/`），用 Cursor 作为第二平台做最小验证。

## 需要验证的假设


| #   | 假设                                                           | 风险等级   | 验证方式                |
| --- | ------------------------------------------------------------ | ------ | ------------------- |
| H-1 | Cursor 的 `Task` tool 能加载 `.claude/agents/` 下的 AGENT.md       | HIGH   | 在 Cursor 中实际调用 Task |
| H-2 | Cursor 的 AGENT.md frontmatter 中非标准字段（`skills`, `hooks`）被安全忽略 | HIGH   | 实际调用后观察行为           |
| H-3 | Cursor 的 Hook stdin JSON 格式与 Claude Code 兼容（字段名、结构）          | MEDIUM | 写一个测试 Hook 打印 stdin |
| H-4 | Cursor 对 `.cursor/rules/*.mdc` 的 `alwaysApply: true` 行为符合预期  | MEDIUM | 创建测试 MDC 文件验证       |
| H-5 | Cursor 中子代理的返回值格式可被 `<agent-result>` 解析                      | MEDIUM | 调用一个简单 Agent 检查返回值  |
| H-6 | Cursor 环境变量中可区分平台（`CURSOR_PROJECT_DIR` 等）                    | LOW    | `env                |


## 执行步骤

### Step 0.1: 环境准备

在 Cursor 中打开 CataForge 项目（当前 `.claude/` 结构不变）。

```bash
# 确认 Cursor 能识别 .claude/agents/
ls .claude/agents/
```

### Step 0.2: 验证 H-1 — Agent 加载

在 Cursor 中运行一个最简 Task 调用，验证 `.claude/agents/architect/AGENT.md` 是否被正确加载：

```
# 在 Cursor Agent 模式中执行:
Task(subagent_type="architect", prompt="读取你的 AGENT.md frontmatter 中的 name 和 skills 字段并原样返回。不执行任何其他操作。")
```

**预期结果**：子代理返回 `name: architect` 和 `skills: [arc-design, doc-gen, doc-nav, ...]`。
**如果失败**：记录 Cursor 扫描 Agent 定义的实际机制，调整 deploy 策略。

### Step 0.3: 验证 H-2 — Frontmatter 容忍度

在 `.claude/agents/architect/AGENT.md` 中临时添加一个虚构字段：

```yaml
---
name: architect
...
test_custom_field: "validation-marker"
---
```

再次调用 Task 验证子代理正常启动、虚构字段被忽略。**测试后还原文件。**

### Step 0.4: 验证 H-3 — Hook stdin 格式

创建临时测试 Hook：

```python
# .cursor/hooks/test_stdin_dump.py
import json, sys, os
raw = sys.stdin.buffer.read()
path = os.path.join(os.path.dirname(__file__), "stdin_dump.json")
with open(path, "w", encoding="utf-8") as f:
    f.write(raw.decode("utf-8", errors="replace"))
sys.exit(0)
```

在 `.cursor/hooks.json` 中注册到 `preToolUse` 事件，触发后检查 `stdin_dump.json` 的结构。

**关键字段对比**：


| 字段           | Claude Code 预期                          | Cursor 实际（待验证）         |
| ------------ | --------------------------------------- | ---------------------- |
| `tool_name`  | `"Bash"` / `"Agent"`                    | `"Shell"` / `"Task"` ? |
| `tool_input` | `{...}`                                 | `{...}` ?              |
| 顶层结构         | `{"tool_name": ..., "tool_input": ...}` | 待确认                    |


### Step 0.5: 验证 H-5 — 返回值解析

调用一个简单 Agent 并要求其返回 `<agent-result>` 格式，检查 orchestrator 能否解析：

```
Task(subagent_type="reviewer", prompt="不执行任何审查。直接返回以下固定内容作为你的最终回复：\n<agent-result>\n<status>completed</status>\n<outputs>test-output.md</outputs>\n<summary>验证返回值解析</summary>\n</agent-result>")
```

检查 Task tool 的返回值中是否包含 `<agent-result>` 标签。

### Step 0.6: 验证 H-6 — 环境变量

```bash
# 在 Cursor 终端中
env | grep -i cursor
env | grep -i claude
```

记录可用于平台检测的环境变量。

---

## 验证结果记录模板

完成验证后，在本文件的 §验证结论 中记录：

```markdown
## 验证结论

执行日期: YYYY-MM-DD
Cursor 版本: x.x.x

| # | 假设 | 结果 | 备注 |
|---|------|------|------|
| H-1 | Agent 加载 | PASS/FAIL | ... |
| H-2 | Frontmatter 容忍 | PASS/FAIL | ... |
| H-3 | Hook stdin 格式 | PASS/FAIL | 实际格式: {...} |
| H-4 | MDC rules | PASS/FAIL | ... |
| H-5 | 返回值解析 | PASS/FAIL | ... |
| H-6 | 环境变量 | PASS/FAIL | 可用变量: ... |

### 设计影响

根据验证结果需要调整的设计决策：
- D-2 Override: ...
- D-5 能力标识符: ...
- profile.yaml cursor 段: ...

### Go/No-Go 决策

- [ ] 所有 HIGH 假设通过 → GO, 进入 Phase 1
- [ ] HIGH 假设部分失败 → 记录调整方案，修订 Phase 1 后 GO
- [ ] HIGH 假设全部失败 → NO-GO, 重新评估跨平台策略
```

---

## 验收标准


| #      | 标准                                          | 验证方式                  |
| ------ | ------------------------------------------- | --------------------- |
| AC-0.1 | 6 项假设均有明确的 PASS/FAIL 记录                     | 检查 §验证结论              |
| AC-0.2 | Cursor 的 Hook stdin 格式已文档化                  | 检查 stdin_dump.json 分析 |
| AC-0.3 | profile.yaml cursor 段的 tool_map 基于实际 API 校正 | 对比验证结果                |
| AC-0.4 | 测试 Hook 和临时文件已清理                            | `git status` 干净       |


---

## 风险项


| 风险                              | 影响                            | 缓解                                   |
| ------------------------------- | ----------------------------- | ------------------------------------ |
| Cursor 版本更新改变 Agent 加载行为        | 验证结论失效                        | 记录版本号，定期回归                           |
| Cursor 不支持 `.claude/agents/` 扫描 | 需要 deploy 到 `.cursor/agents/` | Phase 1 profile.yaml 的 scan_dirs 需调整 |
| Hook stdin 格式完全不同               | _hook_base.py 需要更大改造          | Phase 4 设计需根据实际格式调整                  |


