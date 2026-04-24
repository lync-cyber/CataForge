# CataForge

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/cataforge?color=b45309)](https://pypi.org/project/cataforge/)
[![License: MIT](https://img.shields.io/badge/license-MIT-1c1917.svg)](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Claude%20Code%20%7C%20Cursor%20%7C%20CodeX%20%7C%20OpenCode-b45309)](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/platforms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/hero-banner.svg" alt="CataForge — AI Engineering Workflow Framework" width="100%">
</p>

---

## 为什么选择 CataForge？

你在 Claude Code 里精心调校的 Agent 定义和 Hook 规则，换到 Cursor 就失效了。每当团队引入一个新的 AI IDE，就要重新维护一套配置——结果是配置漂移、行为不一致、上下文无法复用。

**CataForge 用一套声明式规范 `.cataforge/` 解决这个问题。** 你写一次 Agent、Skill、Hook 和 MCP 定义，`cataforge deploy` 自动将其翻译成各 IDE 的原生格式并注入。不支持的能力由 `PlatformAdapter` 优雅降级，始终保持唯一事实来源。

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/artifact-map.svg" alt="四平台部署产物对照图 — Claude Code、Cursor、CodeX、OpenCode" width="100%">
</p>

---

## 核心特性

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/key-features.svg" alt="CataForge 核心特性：多平台统一、声明即部署、13 Agent + 24 Skill、TDD 内建、多层质量门禁、跨项目学习" width="100%">
</p>

除上述核心特性外，CataForge 还内置了**元框架生成器** `workflow-framework-generator` Skill：给定工作流类型（软件开发 / 内容创作 / 研究分析 / 项目管理…）与目标 IDE，自动产出一套完整的 CataForge 兼容框架（agents / skills / workflows / platform profile）——框架生成框架，从源头消除重复建设。

---

## 快速开始

### 安装

```bash
# 推荐：uv（全局可用，无需单独建环境）
uv tool install cataforge

# 或 pip
pip install cataforge

# 验证安装
cataforge --version
```

> **零安装体验** — 使用 `uvx` 临时运行，无需全局安装：
> ```bash
> uvx cataforge doctor
> ```

### 4 步部署到目标 IDE

**步骤 1** — 检测运行时环境与已安装的 IDE

```bash
cataforge doctor
```

**步骤 2** — 初始化目标平台（以 Cursor 为例）

```bash
cataforge setup --platform cursor
```

**步骤 3** — 预览部署产物，确认无误（不写入文件）

```bash
cataforge deploy --dry-run --platform cursor
```

**步骤 4** — 执行真实部署

```bash
cataforge deploy --platform cursor
```

支持的平台：`claude-code` · `cursor` · `codex` · `opencode`

更多安装选项 → [docs/getting-started/installation.md](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/installation.md)  
端到端验证全部 4 个 IDE → [docs/guide/manual-verification.md](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/manual-verification.md)

---

## 适用场景

- 需要在 Claude Code、Cursor、CodeX、OpenCode 之间迁移或共享工作流的个人与团队
- 有子 Agent 调度、可复用 Skill、安全 Hook 及 MCP 服务落地需求的项目
- 希望将 AI 协作流程**产品化、可版本化、可审计**的开源项目
- 中文工程团队（规则与流程文档对中文提示词场景原生支持）

---

## 文档

| 分类 | 内容 |
|------|------|
| [文档总览](https://github.com/lync-cyber/CataForge/blob/main/docs/README.md) | 完整文档地图与导航 |
| [安装](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/installation.md) · [快速开始](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/quick-start.md) | 零基础上手（5 分钟） |
| [平台适配](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/platforms.md) · [执行模式](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/execution-modes.md) · [TDD 工作流](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/tdd-workflow.md) | 使用指南 |
| [架构概览](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/overview.md) · [运行时流程](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/runtime-workflow.md) · [平台适配机制](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/platform-adaptation.md) | 深入原理 |
| [CLI 参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/cli.md) · [配置参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/configuration.md) · [Agent & Skill 清单](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/agents-and-skills.md) | 参考手册 |
| [FAQ](https://github.com/lync-cyber/CataForge/blob/main/docs/faq.md) · [贡献指南](https://github.com/lync-cyber/CataForge/blob/main/docs/contributing.md) | 其他 |

---

## 架构

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/architecture-stack.svg" alt="CataForge 五层架构栈" width="80%">
</p>

| 层级 | 模块 | 说明 |
|------|------|------|
| L1 命令层 | `cli` | 统一入口：`setup` `deploy` `doctor` `skill` `agent` 等 |
| L2 编排层 | Orchestrator + Agent Dispatch | 多阶段任务调度与子 Agent 生命周期管理 |
| L3 能力域 | `agent` / `skill` / `hook` / `mcp` | 规范资产的发现、翻译与执行 |
| L4 平台层 | `PlatformAdapter` | 屏蔽四个 IDE 差异的核心抽象，不支持时自动降级 |
| L5 核心层 | `core` | 配置管理、路径解析、事件总线、类型系统 |

深入了解架构 → [docs/architecture/overview.md](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/overview.md)

---

## 贡献

欢迎提交 Issue 和 PR。开发环境配置、代码规范、测试要求与文档维护约定见 [docs/contributing.md](https://github.com/lync-cyber/CataForge/blob/main/docs/contributing.md)。

## License

MIT — 详见 [LICENSE](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)。
