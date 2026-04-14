# Phase 2: 目录结构重构 — `.claude/` 解耦

> 前置条件：Phase 1 完成（Override 机制、profile.yaml、runtime 工具层已就绪）
> 预计工时：3-5 天
> 目标：建立 `.cataforge/` 为源定义目录，`.claude/` 降级为 deploy 产物

---

## 动机

`.claude/` 混合了 87 个框架核心文件和 1 个平台专属配置（settings.json）。Phase 2 将框架核心迁移到 `.cataforge/`，`.claude/` 仅保留 `settings.json` + deploy 生成的产物。

与 v1 方案的关键差异：

- Phase 1 的 Override 机制和 runtime 包已就绪，迁移后即可运行 deploy
- 源 AGENT.md 迁移时同步改为能力标识符（v1 在 Phase 1 做，现合并到 Phase 2）
- `PROJECT-STATE.md` 在本 Phase 从 `CLAUDE.md` 提取生成

---

## Step 2.1: 创建 `.cataforge/` 并迁移框架文件

```bash
mkdir -p .cataforge

# 移动框架核心文件（保留 git 历史）
git mv .claude/framework.json .cataforge/
git mv .claude/agents .cataforge/
git mv .claude/skills .cataforge/
git mv .claude/rules .cataforge/
git mv .claude/schemas .cataforge/
git mv .claude/scripts .cataforge/
git mv .claude/hooks .cataforge/
git mv .claude/integrations .cataforge/

# settings.json 和 settings.local.json 留在 .claude/
```

同时移入 Phase 1 已创建的文件：

```bash
# Phase 1 产出已在 .cataforge/ 下，无需移动:
# .cataforge/platforms/
# .cataforge/runtime/
# .cataforge/hooks/hooks.yaml
```

### 迁移后验证

```bash
# .claude/ 仅剩 settings.json 类文件
ls .claude/
# 预期: settings.json  settings.local.json

# .cataforge/ 包含所有框架文件
ls .cataforge/
# 预期: agents  framework.json  hooks  integrations  platforms  rules  runtime  schemas  scripts  skills
```

---

## Step 2.2: 源 AGENT.md 能力标识符化

迁移到 `.cataforge/agents/` 后，将 13 个 AGENT.md 的 `tools:` 和 `disallowedTools:` 从 Claude Code 原生工具名改为能力标识符。

**这是安全操作**：源文件使用能力标识符，deploy 翻译为原生名后写入 `.claude/agents/`。Claude Code 永远只看到原生名。

### 映射表


| Claude Code 工具名   | 能力标识符            |
| ----------------- | ---------------- |
| `Read`            | `file_read`      |
| `Write`           | `file_write`     |
| `Edit`            | `file_edit`      |
| `Glob`            | `file_glob`      |
| `Grep`            | `file_grep`      |
| `Bash`            | `shell_exec`     |
| `WebSearch`       | `web_search`     |
| `WebFetch`        | `web_fetch`      |
| `AskUserQuestion` | `user_question`  |
| `Agent`           | `agent_dispatch` |


### 变更清单


| AGENT.md                             | 旧 `tools:`                                                                  | 新 `tools:`                                                                                                 |
| ------------------------------------ | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| orchestrator                         | `Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion`               | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question`        |
| architect                            | `Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion` | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question` |
| product-manager                      | `Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, AskUserQuestion`       | `file_read, file_write, file_edit, file_glob, file_grep, web_search, web_fetch, user_question`             |
| implementer                          | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       |
| test-writer                          | 同 implementer                                                               | 同 implementer                                                                                              |
| refactorer                           | 同 implementer                                                               | 同 implementer                                                                                              |
| reviewer                             | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       |
| （其余 6 个类推，完整清单见 v1 Phase 1 Step 1.6） |                                                                             |                                                                                                            |


`disallowedTools:` 同样替换，如 `Agent` → `agent_dispatch`、`Bash` → `shell_exec` 等。

### 内文变更

`orchestrator/AGENT.md` L22:

```
旧: 你作为主线程Agent运行，可使用Agent tool启动子代理
新: 你作为主线程Agent运行，可通过调度接口启动子代理
```

---

## Step 2.3: 源 SKILL.md 平台无关化

### agent-dispatch/SKILL.md 变更


| 段落                       | 变更                                                                                                                                |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| frontmatter L5           | `suggested-tools: Read, Glob, Grep, Bash, Agent` → `suggested-tools: file_read, file_glob, file_grep, shell_exec, agent_dispatch` |
| §claude-code 实现 (L38-44) | 替换为 §平台调度实现（引用 profile.yaml 和 runtime/adapters/）                                                                                  |
| §返回值解析 (L47)             | 添加 Python 实现引用: `.cataforge/runtime/result_parser.py`                                                                             |
| §注意事项 (L71)              | `子代理无法使用Agent tool` → `子代理无法使用调度工具`                                                                                               |
| §运行时支持 (L74)             | 更新为支持多平台，引用 profile.yaml                                                                                                          |
| L35 grep 命令              | `.claude/agents/` → `.cataforge/agents/`                                                                                          |


### tdd-engine/SKILL.md 变更


| 段落             | 变更                                                       |
| -------------- | -------------------------------------------------------- |
| frontmatter L5 | 工具名 → 能力标识符                                              |
| 架构图 (L20-26)   | `通过Agent tool启动` → `通过调度接口启动`                            |
| 调度模板 (L78-170) | `Agent tool:` / `subagent_type:` → `调度请求:` / `agent_id:` |


### 框架内部路径引用更新

所有 `.claude/` 路径更新为 `.cataforge/`（`.claude/settings.json` 例外，保持原样）:

```
.claude/scripts/framework/  → .cataforge/scripts/framework/
.claude/scripts/docs/        → .cataforge/scripts/docs/
.claude/skills/              → .cataforge/skills/
.claude/agents/              → .cataforge/agents/
.claude/schemas/             → .cataforge/schemas/
.claude/hooks/               → .cataforge/hooks/
.claude/integrations/        → .cataforge/integrations/
.claude/framework.json       → .cataforge/framework.json
.claude/rules/               → .cataforge/rules/
.claude/learnings/           → .cataforge/learnings/
```

影响文件：8 个 AGENT.md + 12 个 SKILL.md + ORCHESTRATOR-PROTOCOLS.md + COMMON-RULES.md + setup.py + README.md

---

## Step 2.4: 生成 PROJECT-STATE.md 并首次 deploy

### 从 CLAUDE.md 提取 PROJECT-STATE.md

```bash
# 手动或脚本: 从 CLAUDE.md 提取平台无关内容，生成 PROJECT-STATE.md
# 1. 复制 CLAUDE.md 到 .cataforge/PROJECT-STATE.md
# 2. 替换 "运行时: claude-code" → "运行时: {platform}"
# 3. 更新所有 .claude/ 路径为 .cataforge/
# 4. 移除 Claude Code 专属说明
```

### 首次 deploy

```bash
# 生成 .claude/ 部署产物
python .cataforge/scripts/framework/deploy.py --platform claude-code
```

deploy 执行：

1. 翻译 `.cataforge/agents/*/AGENT.md` → `.claude/agents/*/AGENT.md`（能力标识符 → 原生名）
2. 渲染 `PROJECT-STATE.md` → `CLAUDE.md`（填入 `运行时: claude-code`）
3. 创建 `.claude/rules/` → `.cataforge/rules/` 链接

### 更新 `.claude/settings.json`

Hook 命令路径更新为指向 `.cataforge/hooks/`:

```json
"command": "python \"$CLAUDE_PROJECT_DIR/.cataforge/hooks/guard_dangerous.py\""
```

permissions 路径同理：

```json
"Bash(python .cataforge/scripts/framework/*.py*)",
"Bash(python .cataforge/scripts/docs/*.py*)",
"Bash(python .cataforge/skills/*/scripts/*.py*)"
```

### 更新 .gitignore

```gitignore
# Deploy-generated platform directories
.claude/agents/
.claude/rules/

# Keep only settings files in .claude/
!.claude/settings.json
!.claude/settings.local.json

# CLAUDE.md is generated from PROJECT-STATE.md
# 可选: 提交 CLAUDE.md 以便不运行 deploy 也能用
# CLAUDE.md
```

### 更新测试快照

```bash
python -m pytest tests/ --snapshot-update
```

---

## 验收标准


| #      | 标准                                                    | 验证方式                                                         |
| ------ | ----------------------------------------------------- | ------------------------------------------------------------ |
| AC-2.1 | `.cataforge/` 包含所有框架核心文件                              | `ls .cataforge/`                                             |
| AC-2.2 | `.claude/` 仅含 `settings.json` + deploy 产物             | `ls .claude/`                                                |
| AC-2.3 | 所有源 AGENT.md 使用能力标识符                                  | `grep -r "tools: Read" .cataforge/agents/` 返回 0              |
| AC-2.4 | deploy 后 `.claude/agents/` 使用原生工具名                    | `grep "tools: Read" .claude/agents/orchestrator/AGENT.md` 匹配 |
| AC-2.5 | `PROJECT-STATE.md` 存在且包含项目状态                          | 内容检查                                                         |
| AC-2.6 | `CLAUDE.md` 由 deploy 生成，`运行时: claude-code`            | 内容检查                                                         |
| AC-2.7 | `deploy.py --check` 通过                                | exit code 0                                                  |
| AC-2.8 | `pytest tests/` 全部通过                                  | CI 运行                                                        |
| AC-2.9 | Claude Code 的 `Agent(subagent_type="architect")` 正常工作 | 手动验证                                                         |


---

## 风险项


| 风险                               | 影响                     | 缓解                            |
| -------------------------------- | ---------------------- | ----------------------------- |
| Windows directory junction 失败    | `.claude/rules/` 链接断裂  | deploy 自动回退到复制模式              |
| Git clone 后 deploy 产物不存在         | Claude Code 无法找到 Agent | setup.py 初始化流程自动运行 deploy     |
| CLAUDE.md 与 PROJECT-STATE.md 不同步 | orchestrator 读到过期状态    | SessionStart hook 自动触发 deploy |
| 升级脚本 (upgrade.py) 路径假设           | 升级脚本仍假设 .claude/       | 升级脚本同步更新路径映射                  |


