# 新平台接入评估流程 (evaluate)

适用于评估一个新的 AI IDE 是否可以接入 CataForge。**不修改仓库内任何文件**，输出可行性报告供决策。

---

## Step 1: 能力调研

WebSearch + WebFetch 调研目标平台:
- 是否提供 tool/function calling 机制
- 是否支持 hook/lifecycle 事件
- agent/task 系统如何工作
- 配置文件格式和路径
- CLI 工具和 SDK

## Step 2: 核心 Capability 映射评估

逐一评估 10 个核心 Capability ID 的可映射性:

| Capability | 可映射 | 平台工具名 | 备注 |
|-----------|--------|-----------|------|
| file_read | Y/N/部分 | ... | ... |
| file_write | Y/N/部分 | ... | ... |
| file_edit | Y/N/部分 | ... | ... |
| file_glob | Y/N | ... | ... |
| file_grep | Y/N | ... | ... |
| shell_exec | Y/N | ... | ... |
| web_search | Y/N | ... | ... |
| web_fetch | Y/N | ... | ... |
| user_question | Y/N | ... | ... |
| agent_dispatch | Y/N | ... | ... |

## Step 3: 扩展能力评估

| Capability | 可映射 | 平台工具名 | 备注 |
|-----------|--------|-----------|------|
| notebook_edit | Y/N | ... | ... |
| browser_preview | Y/N | ... | ... |
| image_input | Y/N | ... | ... |
| code_review | Y/N | ... | ... |

## Step 4: Agent 配置评估

逐一评估 17 个 frontmatter 字段（清单见 `src/cataforge/core/types.py::AGENT_FRONTMATTER_FIELDS`）:

| 字段 | 支持 | 平台名称 | 备注 |
|------|------|---------|------|
| name | Y/N | ... | ... |
| ... | | | |

## Step 5: 平台特性评估

逐一评估 17 个 platform features（清单见 `src/cataforge/core/types.py::PLATFORM_FEATURES`）:

| 特性 | 支持 | 备注 |
|------|------|------|
| cloud_agents | Y/N | ... |
| ... | | |

## Step 6: Hook 支持评估

评估 5 个 hook 事件（PreToolUse / PostToolUse / Stop / SessionStart / Notification）:
- 原生支持 → `native`
- 可通过插件/脚本实现 → `degraded`（注明降级方式）
- 不可实现 → `null`

## Step 7: 接入可行性报告

输出:
- **可行性判定**: 推荐接入 / 有条件接入 / 不建议接入
- **核心能力覆盖率**: N/10 capabilities, M/5 hook events
- **扩展能力覆盖率**: N/4 extended capabilities
- **Agent 配置覆盖率**: N/17 frontmatter fields
- **平台特性覆盖率**: N/17 features
- **接入工作量估算**
- **需新建的文件清单**: adapter 类、profile.yaml、overrides 模板
