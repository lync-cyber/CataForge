# CataForge

[![PyPI](https://img.shields.io/pypi/v/cataforge?color=b45309)](https://pypi.org/project/cataforge/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-1c1917.svg)](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)
[![Tests](https://github.com/lync-cyber/CataForge/actions/workflows/test.yml/badge.svg)](https://github.com/lync-cyber/CataForge/actions/workflows/test.yml)
[![Platforms](https://img.shields.io/badge/platforms-Claude%20Code%20%7C%20Cursor%20%7C%20CodeX%20%7C%20OpenCode-b45309)](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/platforms.md)

**一份 `.cataforge/` 规范，跨四个 AI IDE 一键落地。**

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/hero-banner.svg" alt="CataForge — AI Engineering Workflow Framework" width="100%">
</p>

---

## 功能亮点

- **写一次，处处运行** — Agent / Skill / Hook / MCP 的声明式规范，`cataforge deploy` 翻译为 Claude Code、Cursor、CodeX、OpenCode 各自的原生产物
- **不支持即降级** — `PlatformAdapter` 维护能力矩阵，能力缺失时优雅回退（`rules_injection` / `prompt_check` / `skip`），规范永远是唯一事实源
- **开箱即用的 SDLC** — 内置 13 个 Agent、26 个 Skill，覆盖需求 → 架构 → 设计 → TDD → 评审全流程
- **升级可回滚** — `cataforge upgrade apply` 自动快照，`upgrade rollback` 一键回退；用户编辑的 `runtime.platform`、`PROJECT-STATE.md` 始终保留
- **元框架生成器** — `workflow-framework-generator` Skill 按工作流类型（软件开发 / 内容创作 / 研究分析…）与目标 IDE 生成一套新的 CataForge 兼容框架

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/artifact-map.svg" alt="四平台部署产物对照图" width="100%">
</p>

---

## 快速开始

```bash
# 1. 安装（推荐 uv）
uv tool install cataforge

# 2. 一键跑通：setup → upgrade → deploy → doctor（每步按产物状态智能跳过）
cataforge bootstrap --platform cursor       # 或 claude-code / codex / opencode
```

看到 `Diagnostics complete.` 即成功。在对应 IDE 中打开项目即可使用。`cataforge bootstrap --dry-run` 可在写入前预览每步的 skip/run 决策。

> 零安装体验：`uvx cataforge bootstrap --platform cursor --dry-run` 直接临时运行，不全局装包。
>
> 想单步执行（setup / deploy / upgrade 各自独立可用），见 [CLI 参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/cli.md)。

其它安装方式（pip / 项目 venv / Windows 最小清单）见 [docs/getting-started/installation.md](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/installation.md)。

---

## 文档导航

| 我想…… | 去这里 |
|---|---|
| 5 分钟跑通第一个部署 | [快速开始](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/quick-start.md) |
| 一页纸速查（平台 / CLI / 产物路径） | [速查卡](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/quick-reference.md) |
| 在我的 IDE 中真实落地 | [平台适配指南](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/platforms.md) · [手动验证](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/manual-verification.md) |
| 升级到新版本 / 回滚 | [升级与脚手架刷新](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/upgrade.md) |
| 查某个 CLI 命令 | [CLI 参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/cli.md) |
| 改配置 | [配置参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/configuration.md) |
| 定制 Agent / Skill | [Agent & Skill 清单](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/agents-and-skills.md) |
| 了解内部如何工作 | [架构概览](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/overview.md) |
| 解决报错 | [FAQ](https://github.com/lync-cyber/CataForge/blob/main/docs/faq.md) · [故障排查](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/troubleshooting.md) |

[完整文档索引 →](https://github.com/lync-cyber/CataForge/blob/main/docs/README.md)

---

## 贡献 · License

- 欢迎 Issue 与 PR。开发环境、代码规范、测试基线、发布流程见 [CONTRIBUTING.md](https://github.com/lync-cyber/CataForge/blob/main/docs/contributing.md)
- 社区行为准则：[CODE_OF_CONDUCT.md](https://github.com/lync-cyber/CataForge/blob/main/CODE_OF_CONDUCT.md)
- MIT License — 详见 [LICENSE](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)
