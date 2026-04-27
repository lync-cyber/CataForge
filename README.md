<!-- 变更原因：第一句改为动词主动句说清"做什么 / 解决什么问题"；删除"一键 / 智能 / 开箱即用"等禁用词；徽章只保留实质性的 4 个 -->
# CataForge

[![PyPI](https://img.shields.io/pypi/v/cataforge?color=b45309)](https://pypi.org/project/cataforge/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-1c1917.svg)](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)
[![Tests](https://github.com/lync-cyber/CataForge/actions/workflows/test.yml/badge.svg)](https://github.com/lync-cyber/CataForge/actions/workflows/test.yml)

CataForge 把同一份 `.cataforge/` 工作流规范部署到 Claude Code、Cursor、CodeX、OpenCode 四个 AI IDE，省去你为每个 IDE 重写 Agent / Skill / Hook / MCP 的工作。

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/hero-banner.svg" alt="同一份 .cataforge/ 规范同时驱动 Claude Code、Cursor、CodeX、OpenCode" width="100%">
</p>

## 60 秒跑通第一个部署

```bash
# 安装（推荐 uv tool）
uv tool install cataforge

# 在你的项目根目录下执行
cataforge bootstrap --platform cursor    # 或 claude-code / codex / opencode
```

成功标志：终端最后一行打印 `Diagnostics complete.`。在对应 IDE 中打开项目即可使用。

先看不写盘：`cataforge bootstrap --platform cursor --dry-run`。

零安装试用：`uvx cataforge bootstrap --platform cursor --dry-run`。

其它安装方式（pip / 项目 venv / Windows 最小清单）见 [安装指南](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/installation.md)。

## 它为你解决什么

<!-- 变更原因：从"功能亮点"改为问题驱动；用具体行为替换营销词 -->

| 问题 | CataForge 的做法 |
|------|------------------|
| 在 4 个 IDE 之间维护 4 套 Agent / Skill 定义 | 写一份 `.cataforge/`，`cataforge deploy` 翻译成各 IDE 的原生产物 |
| 某 IDE 不支持某个能力 | `PlatformAdapter` 按能力矩阵自动降级（`rules_injection` / `prompt_check`），而不是直接放弃 |
| 升级时怕覆盖手改的文件 | `upgrade apply` 前自动快照到 `.cataforge/.backups/<ts>/`，`upgrade rollback` 可回退 |
| 项目从零搭 SDLC 流程 | 内置 13 个 Agent + 26 个 Skill，覆盖需求 → 架构 → 设计 → TDD → 评审 |

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/artifact-map.svg" alt="一份 .cataforge/ 在四平台分别落盘的产物对照" width="100%">
</p>

## 下一步看哪里

| 你想…… | 去这里 |
|---|---|
| 5 分钟跑通第一个部署 | [快速开始](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/quick-start.md) |
| 一页纸速查（平台 / CLI / 产物路径） | [速查卡](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/quick-reference.md) |
| 在你的 IDE 中真实落地 | [平台适配指南](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/platforms.md) |
| 端到端验证四平台 | [手动验证](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/manual-verification.md) |
| 升级到新版本 | [升级指南](https://github.com/lync-cyber/CataForge/blob/main/docs/guide/upgrade.md) |
| 查 CLI 命令参数 | [CLI 参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/cli.md) |
| 改配置 | [配置参考](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/configuration.md) |
| 定制 Agent / Skill | [Agent & Skill 清单](https://github.com/lync-cyber/CataForge/blob/main/docs/reference/agents-and-skills.md) |
| 理解内部如何工作 | [架构概览](https://github.com/lync-cyber/CataForge/blob/main/docs/architecture/overview.md) |
| 解决报错 | [故障排查](https://github.com/lync-cyber/CataForge/blob/main/docs/getting-started/troubleshooting.md) · [FAQ](https://github.com/lync-cyber/CataForge/blob/main/docs/faq.md) |

[完整文档索引 →](https://github.com/lync-cyber/CataForge/blob/main/docs/README.md)

## 贡献 · License

- Issue 与 PR：见 [CONTRIBUTING.md](https://github.com/lync-cyber/CataForge/blob/main/docs/contributing.md)（开发环境、代码规范、测试基线、PR 约定、发布流程）
- 行为准则：[CODE_OF_CONDUCT.md](https://github.com/lync-cyber/CataForge/blob/main/CODE_OF_CONDUCT.md)
- MIT License：[LICENSE](https://github.com/lync-cyber/CataForge/blob/main/LICENSE)
