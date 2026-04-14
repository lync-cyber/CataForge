# Manual Verification Guide

本指南用于手动验证 `CataForge` 的核心能力是否按预期工作，面向开发者、测试人员与开源贡献者。

## 1) 验证目标定义

本项目建议优先验证以下核心能力：

1. **平台适配**：同一套框架配置可切换 `claude-code/cursor/codex/opencode`。
2. **部署编排**：`deploy` 能按平台生成/合并 agents、rules、hooks、降级策略。
3. **技能与代理发现**：`skill list`、`agent list`、`agent validate` 可稳定运行。
4. **Hook 桥接**：`hooks.yaml` 能转换为平台 hook 配置，降级策略可见。
5. **MCP 生命周期**：MCP 声明可被发现，且可 start/stop。
6. **工程可回归**：`pytest` 全量通过。

---

## 2) 环境准备（Environment Setup）

### Step 1: 创建并激活 Python 虚拟环境

- 操作说明：在项目根目录创建 venv，激活后安装依赖。
- 输入：

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
```

- 预期输出（Expected Result）：
  - `pip install` 成功，`cataforge` 可被 `python -m cataforge --help` 调用。
- 失败时可能原因（Failure Hint）：
  - Python 版本过低（需 `>=3.10`）。
  - 网络或镜像源不可用导致依赖安装失败。

### Step 2: 设定 UTF-8 运行环境（Windows 强烈建议）

- 操作说明：避免 Windows 默认编码导致 Unicode 字符输出失败。
- 输入：

```bash
export PYTHONUTF8=1
export PYTHONPATH=src
```

- 预期输出（Expected Result）：
  - 后续执行 `deploy --check` 不再出现 `UnicodeEncodeError`。
- 失败时可能原因（Failure Hint）：
  - 未在当前 shell 会话中生效；请在同一终端再次执行。

### Step 3: 基础健康检查

- 操作说明：验证框架目录、依赖、外部工具可见性。
- 输入：

```bash
python -m cataforge doctor
```

- 预期输出（Expected Result）：
  - 包含 `Diagnostics complete.`
  - `framework.json`、`hooks.yaml`、平台 profiles 显示 `OK`
- 失败时可能原因（Failure Hint）：
  - 当前目录不是包含 `.cataforge/` 的项目根目录。
  - 缺失 `PyYAML`/`click` 依赖。

---

## 3) 分 IDE 验证流程（重点）

> 每个平台均采用同一结构：初始化 -> 加载项目 -> 执行任务 -> 观察输出 -> 判定成功。

## 3.1 Claude Code

### Step 1: 初始化
- 操作说明：切换运行平台到 `claude-code`。
- 输入：
```bash
python -m cataforge setup --platform claude-code
```
- 预期输出（Expected Result）：
  - 输出 `Platform set to: claude-code` 和 `Setup complete.`
- 失败时可能原因（Failure Hint）：
  - `.cataforge/` 缺失，setup 会直接报错退出。

### Step 2: 加载项目
- 操作说明：检查代理与技能是否可被发现。
- 输入：
```bash
python -m cataforge agent list
python -m cataforge skill list
```
- 预期输出（Expected Result）：
  - `agent list` 至少包含 `orchestrator`、`implementer`
  - `skill list` 至少包含 `code-review`、`sprint-review`
- 失败时可能原因（Failure Hint）：
  - `.cataforge/agents` 或 `.cataforge/skills` 目录结构不完整。

### Step 3: 执行测试任务
- 操作说明：干运行部署到 Claude Code 目标路径。
- 输入：
```bash
python -m cataforge deploy --check --platform claude-code
```
- 预期输出（Expected Result）：
  - 出现 `would write CLAUDE.md ← PROJECT-STATE.md`
  - 出现 `.mcp.json` 相关 MCP 合并动作（若有声明式 MCP）
  - 最后出现 `Deploy complete.`
- 失败时可能原因（Failure Hint）：
  - 终端编码错误（先设置 `PYTHONUTF8=1`）。
  - profile 文件损坏或 YAML 不合法。

### Step 4: 观察输出
- 操作说明：重点检查 Hook 事件数量与规则部署动作。
- 输入：
```bash
python -m cataforge hook list
```
- 预期输出（Expected Result）：
  - 可见 `PreToolUse`、`PostToolUse`、`Stop`、`Notification`、`SessionStart`
- 失败时可能原因（Failure Hint）：
  - `hooks.yaml` 解析失败，或字段命名被误改。

### Step 5: 判断是否成功
- 操作说明：确认 Claude 平台关键能力全部通过。
- 输入：无（人工判定）
- 预期输出（Expected Result）：
  - 初始化成功 + 干运行输出完整 + hook 列表完整。
- 失败时可能原因（Failure Hint）：
  - 若仅部分 hook 缺失，先检查平台 profile 的 `degradation` 是否被意外修改。

## 3.2 Cursor

### Step 1: 初始化
- 操作说明：切换到 Cursor 平台。
- 输入：
```bash
python -m cataforge setup --platform cursor
```
- 预期输出（Expected Result）：
  - 输出 `Platform set to: cursor` 和 `Setup complete.`
- 失败时可能原因（Failure Hint）：
  - 与 Claude 相同，通常是 `.cataforge/` 不存在。

### Step 2: 加载项目
- 操作说明：确认环境与 profiles 正常。
- 输入：
```bash
python -m cataforge doctor
```
- 预期输出（Expected Result）：
  - `cursor: OK`
- 失败时可能原因（Failure Hint）：
  - `.cataforge/platforms/cursor/profile.yaml` 缺失。

### Step 3: 执行测试任务
- 操作说明：执行 Cursor 干运行部署。
- 输入：
```bash
python -m cataforge deploy --check --platform cursor
```
- 预期输出（Expected Result）：
  - 包含 `.cursor/hooks.json`
  - 包含 `.cursor/rules/*.mdc` 生成动作
  - 含降级提示：`SKIP: detect_correction`
- 失败时可能原因（Failure Hint）：
  - 终端编码不是 UTF-8。
  - `.cataforge/rules` 为空导致规则转换项缺失。

### Step 4: 观察输出
- 操作说明：检查降级行为是否符合 Cursor profile。
- 输入：
```bash
python -m cataforge hook list
```
- 预期输出（Expected Result）：
  - canonical hooks 列表完整；Cursor 的降级由 deploy 输出体现。
- 失败时可能原因（Failure Hint）：
  - hook 列表为空通常表示 `hooks.yaml` 未加载。

### Step 5: 判断是否成功
- 操作说明：判定 Cursor 路径与 MDC 适配是否符合预期。
- 输入：无（人工判定）
- 预期输出（Expected Result）：
  - 出现 `.cursor/hooks.json` + `.cursor/rules/*.mdc` + `Deploy complete.`
- 失败时可能原因（Failure Hint）：
  - 若没有 `.mdc` 相关动作，检查 `additional_outputs` 配置。

## 3.3 CodeX

### Step 1: 初始化
- 操作说明：切换到 CodeX 平台。
- 输入：
```bash
python -m cataforge setup --platform codex
```
- 预期输出（Expected Result）：
  - 输出 `Platform set to: codex`
- 失败时可能原因（Failure Hint）：
  - 配置文件不可写，导致 runtime 平台未持久化。

### Step 2: 加载项目
- 操作说明：校验 profile 可读。
- 输入：
```bash
python -m cataforge doctor
```
- 预期输出（Expected Result）：
  - `codex: OK`
- 失败时可能原因（Failure Hint）：
  - `profile.yaml` 语法错误。

### Step 3: 执行测试任务
- 操作说明：验证 Codex 原生指令与配置路径。
- 输入：
```bash
python -m cataforge deploy --check --platform codex
```
- 预期输出（Expected Result）：
  - 出现 `would write AGENTS.md ← PROJECT-STATE.md`
  - 出现 `.codex/config.toml` 的 MCP 合并动作（若有声明式 MCP）
- 失败时可能原因（Failure Hint）：
  - `.cataforge/platforms/codex/profile.yaml` 配置损坏。

### Step 4: 观察输出
- 操作说明：核对 MCP 原生支持状态。
- 输入：
```bash
python -m cataforge mcp list
```
- 预期输出（Expected Result）：
  - 若无声明式 MCP，会输出 `No MCP servers registered.`
- 失败时可能原因（Failure Hint）：
  - 若你已经新增了 MCP YAML，却仍为空，检查路径是否为 `.cataforge/mcp/*.yaml`。

### Step 5: 判断是否成功
- 操作说明：判定 CodeX 的关键适配（AGENTS + config.toml）是否生效。
- 输入：无（人工判定）
- 预期输出（Expected Result）：
  - 看到 `AGENTS.md` 与 `.codex/config.toml` 相关动作即可判定核心路径有效。
- 失败时可能原因（Failure Hint）：
  - profile 的 `instruction_file.targets` 或 MCP 适配配置被误改。

## 3.4 OpenCode

### Step 1: 初始化
- 操作说明：切换到 OpenCode 平台。
- 输入：
```bash
python -m cataforge setup --platform opencode
```
- 预期输出（Expected Result）：
  - 输出 `Platform set to: opencode`
- 失败时可能原因（Failure Hint）：
  - 同上，通常是项目结构异常。

### Step 2: 加载项目
- 操作说明：确认 OpenCode profile 可见。
- 输入：
```bash
python -m cataforge doctor
```
- 预期输出（Expected Result）：
  - `opencode: OK`
- 失败时可能原因（Failure Hint）：
  - `opencode/profile.yaml` 缺失或损坏。

### Step 3: 执行测试任务
- 操作说明：执行 OpenCode 干运行部署，检查原生目录与降级策略。
- 输入：
```bash
python -m cataforge deploy --check --platform opencode
```
- 预期输出（Expected Result）：
  - 出现 `.opencode/agents/*.md` 投放动作
  - 出现 `opencode.json` 指令与 MCP 合并动作（若有声明式 MCP）
  - 出现多个 `SKIP`（例如 `lint_format`, `notify_done`）
  - 出现 `would write rules_injection` 动作
- 失败时可能原因（Failure Hint）：
  - 如果没有 `rules_injection`，检查 `hooks.yaml` 的降级模板是否存在。

### Step 4: 观察输出
- 操作说明：确认 OpenCode 以 `.opencode` 原生目录为主。
- 输入：
```bash
python -m cataforge deploy --check --platform opencode
```
- 预期输出（Expected Result）：
  - 看到 `.opencode/agents` 与 `opencode.json` 相关动作。
- 失败时可能原因（Failure Hint）：
  - 项目路径权限不足，无法准备目标目录。

### Step 5: 判断是否成功
- 操作说明：判定“无原生 hook 平台”下的可运行性。
- 输入：无（人工判定）
- 预期输出（Expected Result）：
  - 降级信息完整且包含安全规则注入动作。
- 失败时可能原因（Failure Hint）：
  - 降级行为缺失通常由 `degradation` 配置变更引起。

---

## 4) 标准测试用例（Test Cases）

以下测试用例可按优先级执行（建议至少覆盖前 6 项）：

### Case 1：基础环境健康检查
- 输入：
```bash
python -m cataforge doctor
```
- 预期行为：关键目录与平台 profile 全部 `OK`。
- 判定标准：输出包含 `Diagnostics complete.` 且无 `MISSING`。

### Case 2：Agent 发现能力
- 输入：
```bash
python -m cataforge agent list
```
- 预期行为：返回多个核心 agent（如 `orchestrator`）。
- 判定标准：返回条目数 > 0。

### Case 3：Skill 发现能力
- 输入：
```bash
python -m cataforge skill list
```
- 预期行为：返回 `code-review`、`sprint-review` 等技能。
- 判定标准：返回条目数 > 0 且包含关键技能 ID。

### Case 4：Hook 规范加载
- 输入：
```bash
python -m cataforge hook list
```
- 预期行为：按事件分组输出 hook 列表。
- 判定标准：至少包含 `PreToolUse` 和 `PostToolUse` 两组。

### Case 5：Cursor 平台适配与 MDC 生成（干运行）
- 输入：
```bash
python -m cataforge deploy --check --platform cursor
```
- 预期行为：出现 `.cursor/hooks.json` 与 `.cursor/rules/*.mdc` 动作。
- 判定标准：输出同时命中 `hooks.json` 与 `.mdc` 关键字。

### Case 6：CodeX 原生指令/配置（干运行）
- 输入：
```bash
python -m cataforge deploy --check --platform codex
```
- 预期行为：出现 `AGENTS.md` 与 `.codex/config.toml` 动作。
- 判定标准：输出同时包含 `AGENTS.md` 与 `config.toml` 关键字。

### Case 7：OpenCode 降级注入（干运行）
- 输入：
```bash
python -m cataforge deploy --check --platform opencode
```
- 预期行为：出现 `SKIP` 与 `rules_injection`。
- 判定标准：输出包含 `SKIP:` 与 `would write rules_injection`。

### Case 8：自动化回归
- 输入：
```bash
pytest -q
```
- 预期行为：测试全部通过。
- 判定标准：退出码为 0（当前基线：`67 passed`）。

### Case 9：MCP 注册与生命周期
- 输入：
```bash
mkdir -p .cataforge/mcp
cat > .cataforge/mcp/echo.yaml <<'EOF'
id: echo-mcp
name: Echo MCP
description: Test MCP server for lifecycle verification
transport: stdio
command: python
args:
  - -c
  - "import time; time.sleep(60)"
EOF

python -m cataforge mcp list
python -m cataforge mcp start echo-mcp
python -m cataforge mcp stop echo-mcp
```
- 预期行为：
  - `mcp list` 输出 `echo-mcp`
  - `mcp start` 输出 `Started: echo-mcp (pid=...)`
  - `mcp stop` 输出 `Stopped: echo-mcp`
- 判定标准：start/stop 均返回成功状态且无异常堆栈。

---

## 5) 故障排查（Troubleshooting）

### 安装失败
- 原因分析：Python 版本不满足或依赖下载失败。
- 解决方案：
  - 确认 `python --version >= 3.10`
  - 先升级 pip：`python -m pip install -U pip`
  - 使用稳定镜像源后重试安装。

### 工具未识别（例如 ruff/npx/docker）
- 原因分析：可执行文件不在 `PATH`。
- 解决方案：
  - 通过 `doctor` 查看工具检测结果。
  - 安装工具后重开终端，确保 PATH 生效。

### deploy/命令输出乱码或 UnicodeEncodeError
- 原因分析：Windows 终端默认编码非 UTF-8。
- 解决方案：
  - 在当前会话设置 `PYTHONUTF8=1`
  - 如有需要，切换终端编码到 UTF-8。

### agent 无响应 / 列表为空
- 原因分析：`.cataforge/agents` 目录不完整或不在项目根目录执行。
- 解决方案：
  - 在项目根运行命令。
  - 检查 `agents/*/AGENT.md` 是否存在。

### skill 调用失败
- 原因分析：技能未发现、技能 ID 错误、脚本依赖缺失。
- 解决方案：
  - 先执行 `skill list`，确认可用 ID。
  - 若是脚本型技能，补齐依赖后重试。

### MCP 调用失败
- 原因分析：未声明 MCP YAML、命令不可执行、环境变量缺失。
- 解决方案：
  - 在 `.cataforge/mcp/` 放置合法 `*.yaml`。
  - 用 `mcp list` 验证是否可见，再 `mcp start/stop`。

---

## 6) 验证结果反馈模板

建议复制以下模板提交验证结果：

```md
## CataForge Manual Verification Report

- 日期：
- 验证人：
- 操作系统：
- Python 版本：
- 验证分支/提交：

### 环境准备
- [ ] venv 创建成功
- [ ] 依赖安装成功
- [ ] doctor 通过

### 平台验证结果
- [ ] Claude Code
- [ ] Cursor
- [ ] CodeX
- [ ] OpenCode

### 测试用例结果
- Case 1:
- Case 2:
- Case 3:
- Case 4:
- Case 5:
- Case 6:
- Case 7:
- Case 8:
- Case 9:

### 失败项与日志
- 失败步骤：
- 实际输出：
- 预期输出：
- 初步定位：

### 改进建议
- 
```
