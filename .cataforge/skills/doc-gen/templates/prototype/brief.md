---
id: "brief-{project}-{ver}"
doc_type: brief
author: product-manager
status: draft
deps: []
consumers: [implementer]
volume: main
mode: agile-prototype
required_sections:
  - "## 1. 目标与用户"
  - "## 2. 核心功能"
  - "## 3. 技术选型"
  - "## 4. 接口与数据结构"
  - "## 5. 开发任务"
  - "## 6. 风险与假设"
---
# Brief: {项目名称}

<!--
  Brief 适用于 agile-prototype 执行模式（原型 / PoC / 单文件脚本）。
  全文目标 ≤200 行。合并了 standard 模式下的 PRD + ARCH + DEV-PLAN。
  §5 任务卡即作为 implementer 子代理的输入契约，tdd_mode 默认 light。
  若内容在 300 行内仍无法表达清楚，提示用户切换到 agile-lite 或 standard。
-->

[NAV]
- §1 目标与用户
- §2 核心功能 → F-001..F-{NNN}（含 AC）
- §3 技术选型
- §4 接口与数据结构 → API-001..API-{NNN}
- §5 开发任务 → T-001..T-{NNN}
- §6 风险与假设
[/NAV]

## 1. 目标与用户
- **背景**: {1-2 句话说明为什么做}
- **目标用户**: {一句话用户画像}
- **成功信号**: {1-2 条可观测信号}
- **范围边界**: {明确不做什么，防止原型无限膨胀}

## 2. 核心功能

### F-001: {功能名}
- **描述**: {一句话}
- **验收标准**:
  - [ ] AC-001: {可验证条件}
  - [ ] AC-002: {可验证条件}

### F-002: {功能名}
- **描述**: ...
- **验收标准**:
  - [ ] AC-003: ...

## 3. 技术选型
| 类别 | 选型 | 理由 |
|------|------|------|
| 语言/运行时 | {如 Python 3.12} | {一句话} |
| 核心库/框架 | {如 click + pandas} | {一句话} |
| 存储 | {如 无 / 本地 JSON} | {一句话} |
| 运行方式 | {CLI / HTTP / 脚本} | — |

## 4. 接口与数据结构

### API-001: {函数名或 HTTP 路径}
- **签名**: `{参数 + 返回类型}`
- **对应功能**: F-001
- **说明**: {一句话}

### 数据结构
```
{必要的类型定义或 JSON 结构示例}
```

## 5. 开发任务

### T-001: {任务名}
- **目标**: {一句话}
- **tdd_mode**: light
  <!-- agile-prototype 默认 light -->
- **tdd_acceptance**:
  - [ ] AC-001: {测试描述} → 预期: {结果}
- **deliverables**:
  - [ ] `src/{file}.py`
  - [ ] `tests/{file}_test.py`
- **依赖**: —

### T-002: {任务名}
- **目标**: ...
- **tdd_mode**: light
- **tdd_acceptance**:
  - [ ] AC-002: ...
- **deliverables**:
  - [ ] `src/...`
- **依赖**: T-001

## 6. 风险与假设
- **[ASSUMPTION]**: {关键假设 1}
- **[ASSUMPTION]**: {关键假设 2}
- **已知风险**: {简述 + 缓解思路}
