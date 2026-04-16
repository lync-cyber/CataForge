# CataForge

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/cataforge?color=b45309)](https://pypi.org/project/cataforge/)
[![License: MIT](https://img.shields.io/badge/license-MIT-1c1917.svg)](./LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Claude%20Code%20%7C%20Cursor%20%7C%20CodeX%20%7C%20OpenCode-b45309)](./docs/guide/platforms.md)

> 一套 `.cataforge/` 规范，同时驱动 **Claude Code / Cursor / CodeX / OpenCode** 的 Agent、Skill、Hook、MCP 与多 IDE 适配。

CataForge 解决的是 "同一套 AI 工程流程在不同 IDE/Agent 运行时重复建设、配置分裂、行为不一致" 的问题。**写一次，跑在四个 IDE 上**。

---

## ✨ 核心特性

- **🎯 多平台统一** — 同一份 `.cataforge/` 规范投放到 Claude Code / Cursor / CodeX / OpenCode，能力差异由 `PlatformAdapter` 屏蔽，不支持时自动降级。
- **📦 声明即部署** — `cataforge deploy` 一键翻译并注入 agents / rules / hooks / MCP；幂等、自动清理孤儿产物。
- **🤖 13 Agent + 24 Skill** — 覆盖产品经理、架构师、TDD 三阶段、评审员、QA、DevOps 等角色，开箱即用。
- **🧪 TDD 内建** — 内置 RED→GREEN→REFACTOR 引擎，按微任务 LOC 自动切换 standard / light 模式。
- **🚦 多层质量闸** — 文档双层审查（脚本 + AI）、代码双层审查（lint + AI）、Sprint 完成度检查。
- **🧠 跨项目学习** — On-Correction Learning 钩子自动捕获用户纠正，Reflector Agent 提取经验跨项目复用。
- **🪆 套娃式框架生成** — 内置 `workflow-framework-generator` 这个 "用框架生成框架" 的元 Skill：给定工作流类型（软件开发 / 内容创作 / 电商运营 / 研究分析 / 教育培训 / 项目管理 ...）与目标 IDE，自动产出一套完整的 CataForge 兼容框架（agents / skills / workflows / platform profile）。

## 🚀 快速开始

**安装**（推荐 `uv`）：

```bash
uv tool install cataforge
cataforge --version
```

**3 条命令跑通干运行**：

```bash
cataforge doctor                                # 健康诊断
cataforge setup --platform cursor               # 选目标平台
cataforge deploy --check --platform cursor      # 干运行查看产物
```

**真部署**（写入 IDE 产物）：

```bash
cataforge deploy --platform cursor
```

👉 更多安装选项：[`docs/getting-started/installation.md`](./docs/getting-started/installation.md)
👉 端到端真实跑通 4 个 IDE：[`docs/guide/manual-verification.md`](./docs/guide/manual-verification.md)

## 🧩 适用场景

- ✅ 需要在 **Claude Code / Cursor / CodeX / OpenCode** 间迁移或共用工作流的团队
- ✅ 有 "子 Agent 调度 + 可复用 Skill + 安全钩子 + MCP 服务" 落地需求的项目
- ✅ 希望把 AI 协作流程**产品化、可审计、可验证**的开源项目
- ✅ 中文工程团队（规则与流程文档对中文提示词场景友好）

## 📚 文档

| 文档 | 内容 |
|------|------|
| 📂 [**文档总览**](./docs/README.md) | 完整文档地图 |
| 🚀 [安装](./docs/getting-started/installation.md) · [快速开始](./docs/getting-started/quick-start.md) | 零基础上手 |
| 📘 [平台适配](./docs/guide/platforms.md) · [执行模式](./docs/guide/execution-modes.md) · [TDD 工作流](./docs/guide/tdd-workflow.md) | 使用指南 |
| 🏗️ [架构概览](./docs/architecture/overview.md) · [运行时流程](./docs/architecture/runtime-workflow.md) · [平台适配机制](./docs/architecture/platform-adaptation.md) | 原理深入 |
| 📖 [CLI 参考](./docs/reference/cli.md) · [配置参考](./docs/reference/configuration.md) · [Agent & Skill 清单](./docs/reference/agents-and-skills.md) | 查阅字典 |
| ❓ [FAQ](./docs/faq.md) · [贡献指南](./docs/contributing.md) | 其它 |

## 🏗️ 架构一瞥

<p align="center">
  <img src="./docs/assets/artifact-map.svg" alt="CataForge 四平台部署产物对照图" width="100%">
</p>

高层组件：

- **`core`** — 配置、路径、事件总线
- **`platform`** — `PlatformAdapter`（屏蔽 IDE 差异的核心抽象）
- **`deploy`** — 统一部署编排
- **`agent` / `skill` / `hook` / `mcp`** — 规范资产的发现、翻译、执行
- **`cli`** — 统一命令入口

深入了解：[`docs/architecture/overview.md`](./docs/architecture/overview.md)

## 🤝 贡献

欢迎 Issue 与 PR。开发环境、代码规范、测试要求、文档维护约定见 [`docs/contributing.md`](./docs/contributing.md)。

## 📄 License

MIT — 详见 [LICENSE](./LICENSE)。
