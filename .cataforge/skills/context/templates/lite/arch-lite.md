---
id: "arch-lite-{project}"
version: "{ver}"
doc_type: arch
author: architect
status: draft
deps: ["prd-lite-{project}"]
consumers: [tech-lead, implementer]
volume: main
mode: agile-lite
required_sections:
  - "## 1. 架构与技术栈"
  - "## 2. 模块清单"
  - "## 3. 关键接口"
---
# Architecture-Lite: {项目名称}

<!--
  Arch-Lite 适用于 agile-lite 执行模式。
  全文目标 ≤100 行；仅记录关键技术决策和接口契约，不需要 ADR、完整数据模型、详细目录结构。
  若内容在 150 行内仍无法表达清楚核心架构决策，提示用户切换到 standard 模式。
-->

[NAV]
- §1 架构与技术栈 → 架构图 + 技术栈表
- §2 模块清单 → M-001..M-{NNN}
- §3 关键接口 → API-001..API-{NNN}
[/NAV]

## 1. 架构与技术栈

### 架构图
```
{简单 ASCII 或 mermaid 图，说明主要模块及其交互}
```

### 技术栈
| 类别 | 选型 | 备注 |
|------|------|------|
| 语言/运行时 | {如 Python 3.12} | {简述理由} |
| 核心框架 | {如 FastAPI} | {简述理由} |
| 数据存储 | {如 SQLite / 无} | {简述理由} |

## 2. 模块清单

### M-001: {模块名}
- **职责**: {一句话}
- **对应功能**: F-001, F-002

### M-002: {模块名}
- **职责**: ...
- **对应功能**: F-003

## 3. 关键接口

### API-001: {接口名}
- **签名**: `{函数/HTTP 路径 + 参数 + 返回类型}`
- **模块**: M-001
- **说明**: {一句话说明业务含义}

### API-002: ...
