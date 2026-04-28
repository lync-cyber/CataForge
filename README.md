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

| 问题 | CataForge 的做法 |
|------|------------------|
| 在 4 个 IDE 之间维护 4 套 Agent / Skill 定义 | 写一份 `.cataforge/`，`cataforge deploy` 翻译成各 IDE 的原生产物 |
| 某 IDE 不支持某个能力 | `PlatformAdapter` 按能力矩阵自动降级（`rules_injection` / `prompt_check`），而不是直接放弃 |
| 升级时怕覆盖手改的文件 | `upgrade apply` 前自动快照到 `.cataforge/.backups/<ts>/`，`upgrade rollback` 可回退 |
| 项目从零搭 SDLC 流程 | 内置 13 个 Agent + 26 个 Skill，覆盖需求 → 架构 → 设计 → TDD → 评审 |

<p align="center">
  <img src="https://raw.githubusercontent.com/lync-cyber/CataForge/main/docs/assets/artifact-map.svg" alt="一份 .cataforge/ 在四平台分别落盘的产物对照" width="100%">
</p>

## 特性亮点

### 中文原生 AI 编程工作流

CataForge 专为中文开发团队设计。13 个内置 Agent 的指令、26 个 Skill 的定义、全套 SDLC 文档模板（PRD、架构文档、开发计划等）均以中文撰写，Agent 之间通过中文语义传递上下文。你无需在英文 prompt 和中文需求之间反复翻译——输入中文需求，输出中文文档，代码注释和 commit 风格也遵循团队约定。

### 框架套娃：生成任意领域的 AI 工作流框架

内置 `workflow-framework-generator` skill，输入工作流类型和目标 IDE，生成一套完整的 CataForge 兼容框架（Agent 角色、Skill 流程、文档模板、平台配置），覆盖软件开发之外的任意领域（公众号写作、电商运营、研究分析……）。CataForge 本身也运行在自己的 `.cataforge/` 规范上（dogfood 模式），`framework.json` 内置 15 条迁移检查持续验证自身 scaffold 完整性。

生成的框架通过 `cataforge bootstrap` 一条命令落地（setup → upgrade → deploy → doctor 全链路，幂等，重跑无副作用）：

```bash
cataforge bootstrap --platform claude-code
cataforge bootstrap --platform claude-code --dry-run  # 先预览再写盘
```

### TDD 三阶段编排引擎

RED → GREEN → REFACTOR 三阶段流水线，每阶段由独立 SubAgent 在隔离上下文中执行；REFACTOR 仅在 implementer 自报告 `refactor_needed=true` 时触发，不对每个任务跑一次 code-review。四档执行模式按任务规模自动路由：`standard`（完整三次 dispatch）、`light-dispatch`（合并 RED+GREEN 为一次 dispatch）、`light-inline`（满足条件时主线程直产，零子代理启动）、`prototype-inline`（agile-prototype 专用，强制跳过 REFACTOR）。

### SDLC 多模式：从原型到企业级

三种工作流模式，在 orchestrator 启动时选择并写入 CLAUDE.md，无需改配置文件：

- **standard**（7 阶段）：需求 → 架构 → UI 设计 → 开发计划 → TDD 开发 → QA 测试 → 部署发布，每阶段有质量门禁（`doc-review` + `code-review`），适合交付质量要求高的项目
- **agile-lite**（精简敏捷）：PM + 架构师阶段产出 lite 文档（TDD 默认 light 模式），减少文档开销，保留质量评审
- **agile-prototype**（快速原型）：PM 产出一页 `brief.md` 合并前 4 阶段，直接进 TDD light 模式，最快路径验证想法

整个链路由 `orchestrator` Agent 在主线程调度，状态机管理阶段跃迁和质量门禁，不走 SubAgent 嵌套，避免协调链断裂。

### 纠错自学习：Hook 捕获用户偏好持续迭代

每次你覆盖 Agent 的建议（修改输出、否定方案、要求重做），`detect_correction` Hook 自动捕获这一信号并双写 `docs/reviews/CORRECTIONS-LOG.md` 和 `docs/EVENT-LOG.jsonl`。当 CORRECTIONS-LOG 中 `hard`+`review` 类条目累计达到阈值（默认 5 条），orchestrator 调度 `skill-improvement` 任务，将纠错模式内化为 Skill 定义的修订，下次同类任务不再重蹈覆辙。

用 `cataforge correction record` 手动写入 interrupt-override 通路的纠错条目；`detect_correction` hook 和 `detect_review_flag` hook 负责 option-override / review-flag 两条通路的自动捕获。

### 多平台通用规范，一份定义多处落地

同一份 `.cataforge/` 规范通过 `PlatformAdapter` 翻译成各 IDE 的原生产物：Claude Code 输出 `CLAUDE.md` + `.claude/settings.json`，Cursor 输出 `.cursor/rules/`，CodeX 输出 `AGENTS.md`，OpenCode 输出任务清单。平台缺失某项能力时自动降级（`rules_injection` / `prompt_checklist`），不报错退出。

模型选择同样平台无关：AGENT.md 用 `model_tier: light | standard | heavy` 声明算力档位，部署时按各平台 `profile.yaml.model_routing.tier_map` 翻译为原生 model id（Claude Code 走 `haiku/sonnet/opus`，Cursor 类同，Codex 与 OpenCode 因 `per_agent_model: false` / `user_resolved: true` 自动省略 `model:` 字段交由用户运行时决定）。`framework.json#/constants/AGENT_MODEL_DEFAULTS` 集中管理 12 个内置 Agent 的默认档位，`AGENT_MODEL_TIER_HEAVY_WHITELIST` 显式控制 heavy 成本面（默认仅 architect / debugger），`framework-review` 的 B7 检查在 CI 阻拦档位漂移与 heavy 滥用。

> **验证状态**：Claude Code 上经过充分验证；Cursor、CodeX、OpenCode 的适配逻辑已实现，但尚未经过等同程度的端到端验证，实际使用中可能遇到边界问题。

---

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
