<!-- 变更原因：把"四层结构"改为"按读者目的"前置；删除冗余的"分层原则"段（已与导航表重复）；视觉资产去掉无人引用的 FIG. 编号 -->
# CataForge 文档索引

按"你是谁、你想做什么"组织。每份文档只为一类读者服务，避免混写。

## 你是谁？

| 你的目标 | 入口 |
|---------|------|
| **判断要不要用** | [README](../README.md) — 60 秒判定 |
| **跑通第一个示例** | [安装](./getting-started/installation.md) → [快速开始](./getting-started/quick-start.md) |
| **完成具体任务** | 见下方 Guide 表 |
| **理解为什么这样设计** | 见下方 Architecture 表 |
| **查参数 / 接口** | 见下方 Reference 表 |
| **遇到错误** | [故障排查](./getting-started/troubleshooting.md)（按症状）→ [FAQ](./faq.md)（按主题） |

## Getting Started · 入门

| 文档 | 用途 |
|------|------|
| [安装](./getting-started/installation.md) | 装 CLI 并通过 `--version` 验证 |
| [快速开始](./getting-started/quick-start.md) | 一条命令跑通 setup → deploy → doctor |
| [故障排查](./getting-started/troubleshooting.md) | 按症状索引常见问题 |

## Guide · 任务导向

| 文档 | 解决什么问题 |
|------|------------|
| [平台适配指南](./guide/platforms.md) | 在你的 IDE 里部署，需要哪些路径和最小配置 |
| [执行模式](./guide/execution-modes.md) | standard / agile-lite / agile-prototype 怎么选 |
| [TDD 工作流](./guide/tdd-workflow.md) | RED→GREEN→REFACTOR 三阶段引擎使用 |
| [升级与脚手架刷新](./guide/upgrade.md) | 从旧版本迁到新版本，包括快照与回滚 |
| [手动验证（流水线总览）](./guide/manual-verification.md) | 在 4 个 IDE 内端到端真跑一遍的 5 步法 |
| [手动验证 · 分平台步骤](./guide/verify-per-platform.md) | 每个 IDE 的 6 步详细操作 |
| [手动验证 · 专题](./guide/verify-topics.md) | Hook / MCP / 自动化回归 / 升级幂等专题 |
| [手动验证 · 标准测试用例](./guide/verify-cases.md) | 10 项 Case 的判定清单 |

## Architecture · 原理

| 文档 | 用途 |
|------|------|
| [架构概览](./architecture/overview.md) | 五层架构、模块职责、关键设计原则 |
| [运行时工作流](./architecture/runtime-workflow.md) | Bootstrap、阶段执行、中断恢复、修订协议 |
| [平台适配机制](./architecture/platform-adaptation.md) | Adapter 抽象、能力矩阵、降级策略 |
| [质量闸与学习系统](./architecture/quality-and-learning.md) | doc-review / code-review / Reflector / On-Correction Learning |

## Reference · 查阅

| 文档 | 用途 |
|------|------|
| [速查卡](./reference/quick-reference.md) | 一页纸：平台矩阵 + CLI + 产物路径 |
| [CLI 参考](./reference/cli.md) | `cataforge` 全部子命令与参数 |
| [配置参考](./reference/configuration.md) | framework.json / profile.yaml / hooks.yaml 字段 |
| [Agent & Skill 清单](./reference/agents-and-skills.md) | 13 个 Agent + 27 个 Skill 详细说明 |
| [状态码与引用格式](./reference/status-codes.md) | 状态码、文档引用、事件日志 |

## 其它

| 文档 | 用途 |
|------|------|
| [常见问题](./faq.md) | 按主题索引 |
| [贡献指南](./contributing.md) | 开发环境、规范、测试、文档维护、发布 |
| [CHANGELOG](../CHANGELOG.md) | 版本历史，破坏性变更附迁移路径 |

## 视觉资产

所有图表存于 [`assets/`](./assets/)，遵循 [design tokens](./assets/design-tokens.md)。新图与重新生成已有图时，使用 [SVG prompt 模板](./assets/svg-prompt-template.md) 起手。

| 资产 | 用途 |
|------|------|
| [`hero-banner.svg`](./assets/hero-banner.svg) | README 顶部主视觉 |
| [`artifact-map.svg`](./assets/artifact-map.svg) | 四平台部署产物对照 |
| [`architecture-stack.svg`](./assets/architecture-stack.svg) | 五层架构栈 |
| [`adapter-translation.svg`](./assets/adapter-translation.svg) | 平台适配器翻译关系 |
| [`execution-modes.svg`](./assets/execution-modes.svg) | 三种执行模式对比 |
| [`phase-execution.svg`](./assets/phase-execution.svg) | 阶段执行流程 |
| [`tdd-engine.svg`](./assets/tdd-engine.svg) | TDD 引擎流程 |
| [`verification-flow.svg`](./assets/verification-flow.svg) | 手动验证五步流水线 |
| [`key-features.svg`](./assets/key-features.svg) | 核心特性拼图（营销介绍页可复用） |

新增图请在 SVG 文件头注释里保留生成 prompt（见 [贡献指南](./contributing.md) §SVG 资产规范）。
