# CataForge 文档

> 本目录集中管理 CataForge 的项目文档。采用 **入门 → 指南 → 架构 → 参考** 四层结构，按任务而非按文件组织。

## 文档地图（Docs Map）

### 🚀 Getting Started · 入门

| 文档 | 适用读者 | 内容 |
|------|---------|------|
| [安装](./getting-started/installation.md) | 初次接触 | 装上 `cataforge` CLI 并跑通 `doctor` |
| [快速开始](./getting-started/quick-start.md) | 初次接触 | 3 条命令跑通干运行部署 |
| [故障排查](./getting-started/troubleshooting.md) | 遇错时 | 按症状索引的常见问题 |

### 📘 Guide · 使用指南（任务导向）

| 文档 | 适用读者 | 内容 |
|------|---------|------|
| [平台适配指南](./guide/platforms.md) | 用户 | 4 个 IDE 的原生支持、产物路径、最小配置 |
| [执行模式](./guide/execution-modes.md) | 用户 | standard / agile-lite / agile-prototype 如何选 |
| [TDD 工作流](./guide/tdd-workflow.md) | 开发者 | RED→GREEN→REFACTOR 三阶段引擎使用 |
| [升级与脚手架刷新](./guide/upgrade.md) | 用户 / 维护者 | 包管理器驱动的升级模型 |
| [手动验证](./guide/manual-verification.md) | 评估者 / 贡献者 | 四平台端到端真实验证流程 |

### 🏗️ Architecture · 架构设计（原理导向）

| 文档 | 适用读者 | 内容 |
|------|---------|------|
| [架构概览](./architecture/overview.md) | 深入者 | 五层架构、模块职责、关键设计原则 |
| [运行时工作流](./architecture/runtime-workflow.md) | 深入者 | Bootstrap / 阶段执行 / 中断恢复 / 修订协议 |
| [平台适配机制](./architecture/platform-adaptation.md) | 深入者 | Adapter 抽象、能力矩阵、降级策略 |
| [质量闸与学习系统](./architecture/quality-and-learning.md) | 深入者 | doc-review / code-review / On-Correction Learning / Reflector |

### 📖 Reference · 参考（查阅导向）

| 文档 | 适用读者 | 内容 |
|------|---------|------|
| [速查卡](./reference/quick-reference.md) | 所有人 | 一页纸：平台矩阵 + CLI 速查 + 产物路径 |
| [CLI 参考](./reference/cli.md) | 用户 | `cataforge` 全部子命令与参数 |
| [配置参考](./reference/configuration.md) | 用户 / 开发者 | framework.json / profile.yaml / hooks.yaml 字段 |
| [Agent & Skill 清单](./reference/agents-and-skills.md) | 用户 | 13 个 Agent + 25 个 Skill 详细说明 |
| [状态码与引用格式](./reference/status-codes.md) | 开发者 | 统一状态码、文档引用、事件日志 |

### ❓ 其它

| 文档 | 适用读者 | 内容 |
|------|---------|------|
| [常见问题](./faq.md) | 所有人 | 安装、使用、平台、升级、TDD、MCP 高频问题 |
| [贡献指南](./contributing.md) | 贡献者 | 开发环境、规范、测试、文档维护、发布流程 |

---

## 视觉资产（`assets/`）

所有文档图表以 SVG 形式放在 [`assets/`](./assets/) 下，统一遵循 [design tokens](./assets/design-tokens.md)（暖纸色 + 琥珀点缀 + 等宽字体的 "技术蓝图" 风格）。

<details>
<summary>图表资产索引（10 项 · 点击展开）</summary>

| 资产 | 用途 |
|------|-----|
| [`assets/design-tokens.md`](./assets/design-tokens.md) | 图表 design tokens 单一事实源 |
| [`assets/hero-banner.svg`](./assets/hero-banner.svg) | README 顶部主视觉 |
| [`assets/key-features.svg`](./assets/key-features.svg) | 核心特性拼图（供营销/介绍页复用） |
| [`assets/verification-flow.svg`](./assets/verification-flow.svg) | 手动验证五步流水线（FIG. 01） |
| [`assets/artifact-map.svg`](./assets/artifact-map.svg) | 四平台部署产物对照（FIG. 02） |
| [`assets/architecture-stack.svg`](./assets/architecture-stack.svg) | 五层架构栈（FIG. 03） |
| [`assets/execution-modes.svg`](./assets/execution-modes.svg) | 三种执行模式对比（FIG. 04） |
| [`assets/phase-execution.svg`](./assets/phase-execution.svg) | 阶段执行流程（FIG. 05） |
| [`assets/tdd-engine.svg`](./assets/tdd-engine.svg) | TDD 引擎流程（FIG. 06） |
| [`assets/adapter-translation.svg`](./assets/adapter-translation.svg) | 平台适配器翻译关系（FIG. 07） |

</details>

新增图表前请先阅读 `design-tokens.md`，严格使用其中声明的色板、尺寸、字体与组件约定。

---

## 文档分层原则

| 层 | 职责 | 何时阅读 |
|---|------|---------|
| `README.md` | 吸引与引导 | 首次了解项目 |
| `getting-started/` | 能快速跑通 | 零基础上手 |
| `guide/` | 任务导向 | 解决具体问题 |
| `architecture/` | 原理导向 | 深入理解、做扩展 |
| `reference/` | 查阅导向 | 查字典 |
