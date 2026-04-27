<!-- 变更原因：原文档同时承担 Tutorial / How-to / Reference 三类内容（24 KB 单文件）；本文保留 Tutorial 部分（5 步流水线 + 前置 + 反馈模板），How-to 与 Reference 拆到 verify-per-platform.md / verify-topics.md / verify-cases.md。删除"最简单的"等模糊副词 -->
# 手动验证 · 流水线总览

带你从 0 出发，在 Claude Code / Cursor / CodeX / OpenCode 四个 IDE 下完整安装、部署并在 IDE 内真实跑通 CataForge，验证其核心能力是否按预期工作。

<div align="center">
  <img src="../assets/verification-flow.svg" alt="CataForge 手动验证五步流水线 INSTALL → SETUP → DRY-RUN → DEPLOY → VERIFY" width="100%">
</div>

## 目录

- [本指南的使用方法](#本指南的使用方法)
- [前置准备](#前置准备)
- [五步流水线](#五步流水线)
- [验证结果反馈模板](#验证结果反馈模板)
- [拆分文档导航](#拆分文档导航)

---

## 本指南的使用方法

### 验证目标

| # | 目标 | 判定依据 |
|---|------|---------|
| 1 | 平台适配 | 同一套 `.cataforge/` 可切到 4 个 IDE |
| 2 | 部署编排 | `deploy` 生成对应 IDE 的产物并可合并已有配置 |
| 3 | 能力发现 | `agent list` / `skill list` / `hook list` 稳定运行 |
| 4 | Hook 桥接 | `hooks.yaml` → 平台 hook 配置，降级可见 |
| 5 | MCP 生命周期 | 声明可发现，start / stop 可控 |
| 6 | IDE 内生效 | 在 IDE 真实会话中能看到 Agent / Rules / Hook / MCP 被加载 |
| 7 | 回归通过 | `pytest -q` 全量通过 |

### 适用读者

- 评估者 / 贡献者：先从零跑通一遍再决定是否深入。
- 迁移团队：在多 IDE 间切换同一套工作流。
- 验收方：复现环境、出具 Verification Report。

---

## 前置准备

### 系统要求

| 条件 | 版本 / 说明 |
|------|-------------|
| OS | Windows 10+ / macOS 12+ / Linux（主流发行版） |
| Python | `>=3.10`（必需）；已验证 3.10 / 3.11 / 3.12 / 3.13 / 3.14；3.14 free-threaded（PEP 703）未系统验证 |
| pip 或 uv | `pip>=23`；或 `uv>=0.4`（推荐） |
| Git | 近期版本（CataForge 依赖 git 元信息） |
| 可选工具 | `ruff`、`docker`、`npx` — `doctor` 会检测但不强制 |

> CLI 启动时已自动切换 stdout/stderr 到 UTF-8（`cataforge.utils.common.ensure_utf8_stdio`）。多数情形下无需手动设置 `PYTHONUTF8=1` 或 `chcp 65001`；若仍在 legacy 代码页（cp936/cp1252）下出现 `UnicodeEncodeError`，参照 [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md) §CLI 乱码。

### 安装 CataForge

完整安装方式（uv tool / 项目 venv / 纯 pip / Windows 最小清单）见 [`../getting-started/installation.md`](../getting-started/installation.md)。本指南后续步骤假设你已跑通 `cataforge --version`。

> 若要跑 [`verify-topics.md`](./verify-topics.md) §自动化回归 的 `pytest -q`，必须使用"项目 venv + `uv pip install -e '.[dev]'`"方式安装。`uv tool install` 的全局 CLI 环境里没有 `pytest` 等测试依赖。

### 安装目标 IDE 客户端

下表为四个 IDE 的常见安装渠道与最小可用校验。具体命令以各 IDE 官方文档为准，CataForge 不随版本绑定客户端。

| IDE | 常见安装渠道 | 最小可用校验 |
|-----|-------------|-------------|
| Claude Code | `npm i -g @anthropic-ai/claude-code`（官方 npm 包） | 终端跑 `claude --version` 能输出版本号；首次需登录 Anthropic 账号 |
| Cursor | 从 [cursor.com](https://cursor.com) 下载桌面客户端（Windows/macOS/Linux） | 能打开客户端、完成登录；命令面板可见 "Cursor: ..." 命令 |
| CodeX | 通过 OpenAI Codex CLI 官方渠道安装（典型为 `npm i -g @openai/codex`） | 终端跑 `codex --version`；首次需 OpenAI 鉴权 |
| OpenCode | 从 [opencode.ai](https://opencode.ai) 获取安装命令（npm / curl 脚本） | 终端跑 `opencode --version`；按其指引配置模型 provider |

> Claude Code / CodeX / OpenCode 均为 CLI，启动方式是 `cd` 到项目根目录后执行客户端命令。Cursor 是 GUI，"打开文件夹"指向项目根目录即可。

### 登录态与鉴权

| IDE | 鉴权需求 | 怎样确认已登录 |
|-----|---------|---------------|
| Claude Code | Anthropic 账号（`/login` 或首次启动引导） | 启动后不再弹登录提示 |
| Cursor | Cursor 账号（GUI 引导） | 左下角可见账号头像 |
| CodeX | OpenAI API Key 或官方登录 | `codex` 启动后不再提示鉴权 |
| OpenCode | 依据所选 provider（OpenAI / Anthropic / 其它） | `opencode auth list`（或类似）能列出凭证 |

> 鉴权失败不是 CataForge 的问题；先在 IDE 里独立跑通一次"Hello"对话再回来做部署验证。

### 健康检查

```bash
cataforge doctor
```

预期：

- 末行：`Diagnostics complete.`
- `framework.json` / `hooks.yaml` 标记 `OK`
- `claude-code / cursor / codex / opencode` 四个 profile 均 `OK`
- `Framework migration checks` 段显示 `N/N passed`（可能伴随 `M skipped`）；退出码 0
- 任一 FAIL 时退出码 1（可用于 CI gate）
- 未 deploy 前，依赖 IDE 产物的检查（如 `mc-0.7.0-detect-correction-registered`）会 SKIP 而非 FAIL

失败提示：

- 当前目录非含 `.cataforge/` 的项目根 → `cd` 到项目根重跑
- 缺 `PyYAML` / `click` → 确认用的是项目 venv
- Windows 下命令找不到 → `which cataforge`（Git Bash）/ `where cataforge`（cmd）检查 PATH

---

## 五步流水线

按顺序执行；任何一步不通过都应回到上一步而非跳过。

| # | 阶段 | 做什么 | 详细文档 |
|---|------|--------|---------|
| 1 | INSTALL | 装好 Python、CataForge、IDE 客户端 | 上方 §前置准备 |
| 2 | SETUP | `cataforge setup --platform <ide>` 切到目标平台 | [`verify-per-platform.md`](./verify-per-platform.md) Step 1 |
| 3 | DRY-RUN | `deploy --dry-run` 预览产物，核对无误 | [`verify-per-platform.md`](./verify-per-platform.md) Step 2 |
| 4 | DEPLOY | `cataforge deploy` 实际写入 IDE 产物 | [`verify-per-platform.md`](./verify-per-platform.md) Step 3 |
| 5 | VERIFY | 启动 IDE，在真实会话中观测 Agent / Hook / MCP 被使用 | [`verify-per-platform.md`](./verify-per-platform.md) Step 4 + [`verify-topics.md`](./verify-topics.md) |

完成全部 5 步后用 [`verify-cases.md`](./verify-cases.md) 的 10 项 Case 做合规判定。

---

## 验证结果反馈模板

> 复制下方模板填写，作为 Verification Report 附在 issue / PR 中。

<details>
<summary>点击展开完整模板</summary>

```md
## CataForge Manual Verification Report

- 日期：
- 验证人：
- 操作系统：
- Python 版本：
- 验证分支 / commit：

### 环境准备
- [ ] venv 创建成功
- [ ] CataForge 安装成功（`cataforge --version` 可用）
- [ ] doctor 通过

### IDE 客户端
- [ ] Claude Code 已登录
- [ ] Cursor 已登录
- [ ] CodeX 已鉴权
- [ ] OpenCode 已配置 provider

### 分 IDE 端到端
|            | Setup | Dry-run | Deploy | In-IDE Verify |
|------------|:-----:|:-------:|:------:|:-------------:|
| Claude Code|       |         |        |               |
| Cursor     |       |         |        |               |
| CodeX      |       |         |        |               |
| OpenCode   |       |         |        |               |

### 标准测试用例
- Case 1–10：

### 失败项与日志
- 步骤：
- 实际输出：
- 预期输出：
- 初步定位：

### 改进建议
-
```

</details>

---

## 拆分文档导航

| 想做的事 | 去这里 |
|---------|------|
| 在某个 IDE 跑完整 6 步操作 | [`verify-per-platform.md`](./verify-per-platform.md) |
| 单独验证 Hook / MCP / pytest / 升级 / deploy 幂等 | [`verify-topics.md`](./verify-topics.md) |
| 拿一份 10 项 Case 清单跑合规判定 | [`verify-cases.md`](./verify-cases.md) |
| 卡住了 | [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md) |
