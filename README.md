# CataForge

**AI 驱动的全生命周期软件开发工作流框架**

CataForge 通过 12 个专业化 AI Agent 和 21 个可复用 Skill 的协作，将软件开发从需求到部署的全流程结构化、自动化。每个阶段产出标准化文档，经双层质量门禁（Python 脚本检查 + AI 语义审查）审查后方可推进。

---

## 核心特性

- **全链路工作流** — 需求 → 架构 → UI 设计 → 开发规划 → TDD 开发 → 测试 → 部署，7 阶段 + 回顾
- **文档驱动** — 每阶段产出标准化文档（PRD / ARCH / UI-SPEC / DEV-PLAN / TEST-REPORT / DEPLOY-SPEC），文档间通过 ID 交叉引用
- **双层质量门禁** — Layer 1: Python 脚本结构检查；Layer 2: AI 语义审查。脚本异常时自动降级为 AI-only
- **TDD 三子代理** — 开发阶段采用 RED（test-writer）→ GREEN（implementer）→ REFACTOR（refactorer），每个阶段独立上下文窗口
- **按需加载** — 通过 NAV-INDEX 导航索引精准加载最小必要上下文
- **安全隔离** — 每个 Agent 声明 `allowed_paths`，agent-dispatch 通过 `git diff` 后置校验写入范围
- **跨平台** — Hook 脚本均为 Python，支持 Windows / macOS / Linux

---

## 框架架构

### 工作流总览

```
用户需求
  │
  ▼
┌───────────────────────────────────────────────────────┐
│                 Orchestrator (主编排)                    │
│  项目状态管理 · 阶段路由 · 质量门禁 · 变更请求处理        │
└───┬───────┬───────┬───────┬───────┬───────┬───────┬──┘
    │       │       │       │       │       │       │
    ▼       ▼       ▼       ▼       ▼       ▼       ▼
 Phase 1 Phase 2 Phase 3 Phase 4 Phase 5 Phase 6 Phase 7
  需求     架构   UI设计  开发规划  TDD开发   测试    部署
  (PM)     (AR)   (UI)    (TL)    (DEV×3)  (QA)   (OPS)
    │       │       │       │       │       │       │
    ▼       ▼       ▼       ▼       ▼       ▼       ▼
  PRD    ARCH    UI-SPEC DEV-PLAN CODE    TEST    DEPLOY
                                  +TESTS  REPORT  SPEC
    └───────┴───────┴───────┴───────┴───────┴───────┘
                          │
                   Reviewer (跨阶段门禁)
                          │
                   Reflector (项目回顾)
```

### Agent 分层

| 层级 | Agent | 阶段 | 主要产出 |
|------|-------|------|----------|
| **规划层** | product-manager | Phase 1 | PRD（F-NNN, AC-NNN） |
| | architect | Phase 2 | ARCH（M-NNN, API-NNN, E-NNN）+ 分卷 |
| | ui-designer | Phase 3 | UI-SPEC（P-NNN, C-NNN）[可跳过] |
| | tech-lead | Phase 4 | DEV-PLAN（T-NNN, Sprint 规划） |
| **执行层** | test-writer | Phase 5 RED | 失败测试用例 |
| | implementer | Phase 5 GREEN | 最小实现代码 |
| | refactorer | Phase 5 REFACTOR | 优化后的代码 |
| **质量层** | reviewer | 跨阶段 | 文档/代码审查报告 |
| | qa-engineer | Phase 6 | 集成/E2E 测试报告 |
| **元协调层** | orchestrator | 全程 | CLAUDE.md 状态管理 |
| | devops | Phase 7 | DEPLOY-SPEC, CHANGELOG |
| | reflector | 项目完成后 | RETRO 回顾报告 |

### 关键设计模式

**文档生命周期**: draft → review → approved（或 needs_revision → 返工循环）。`doc-gen` skill 负责模板实例化、超 500 行自动拆分、NAV-INDEX 注册。

**TDD 引擎**: orchestrator 直接驱动三个子代理，通过文件系统传递状态（非上下文内传递），确保阶段间隔离。

**变更请求处理**: change-guard skill 分析变更影响范围，按偏移等级路由: L1 直接执行 / L2 修订受影响文档 / L3 级联修订。

---

## 项目结构

```
CataForge/
├── CLAUDE.md                           # 项目状态（orchestrator 维护）
├── pyproject.toml                      # 项目元数据与框架版本号
├── .claude/
│   ├── settings.json                   # 框架配置（权限、Hook、环境变量）
│   ├── settings.local.json             # 用户本地配置（不随框架分发）
│   ├── agents/                         # 12 个 Agent 定义
│   │   ├── orchestrator/AGENT.md
│   │   ├── product-manager/AGENT.md
│   │   ├── architect/AGENT.md
│   │   ├── ui-designer/AGENT.md
│   │   ├── tech-lead/AGENT.md
│   │   ├── test-writer/AGENT.md
│   │   ├── implementer/AGENT.md
│   │   ├── refactorer/AGENT.md
│   │   ├── reviewer/AGENT.md
│   │   ├── qa-engineer/AGENT.md
│   │   ├── devops/AGENT.md
│   │   └── reflector/AGENT.md
│   ├── skills/                         # 21 个 Skill
│   │   ├── agent-dispatch/             # 子代理调度（含 prompt 模板）
│   │   ├── doc-gen/                    # 文档生成（含 15 个模板）
│   │   ├── doc-nav/                    # 文档导航与按需加载
│   │   ├── doc-review/                 # 文档审查（含 doc_check.py）
│   │   ├── code-review/               # 代码审查（含 code_lint.py）
│   │   ├── sprint-review/             # Sprint 完成度审查
│   │   ├── tdd-engine/                # TDD 三阶段编排
│   │   ├── req-analysis/              # 需求分析
│   │   ├── arc-design/                # 架构设计
│   │   ├── ui-design/                 # UI 设计
│   │   ├── task-decomp/               # 任务拆分
│   │   ├── dep-analysis/              # 依赖分析（含 dep_analysis.py）
│   │   ├── tech-eval/                 # 技术评估
│   │   ├── research/                  # 调查研究
│   │   ├── testing/                   # 测试策略与执行
│   │   ├── deploy-config/             # 部署配置
│   │   ├── change-guard/              # 变更请求分析
│   │   ├── start-orchestrator/        # 编排流程入口
│   │   ├── penpot-sync/               # Penpot 设计 Token 同步 [可选]
│   │   ├── penpot-implement/          # Penpot 组件代码生成 [可选]
│   │   └── penpot-review/             # 设计-代码一致性验证 [可选]
│   ├── rules/                          # 共享规则
│   │   ├── COMMON-RULES.md            # 所有 Agent 共享的行为规则
│   │   └── ORCHESTRATOR-PROTOCOLS.md  # 编排器专用协议
│   ├── hooks/                          # Tool Hook（Python，跨平台）
│   │   ├── guard_dangerous.py         # 阻止危险 Bash 命令
│   │   ├── lint_format.py             # 编辑后自动格式化
│   │   ├── validate_agent_result.py   # 校验 agent-result 格式
│   │   ├── session_context.py         # 会话启动注入上下文
│   │   ├── notify_done.py             # 任务完成通知
│   │   └── notify_permission.py       # 权限审批通知
│   ├── scripts/                        # 框架工具脚本
│   │   ├── upgrade.py                 # 框架升级
│   │   ├── check-upgrade.py           # 远程版本检测
│   │   ├── post_upgrade_check.py      # 升级后完整性检查
│   │   └── setup-penpot-mcp.sh        # Penpot MCP 部署
│   └── schemas/
│       └── agent-result.schema.json   # Agent 返回值 JSON Schema
└── docs/                               # 项目文档（运行时生成）
```

---

## 快速开始

### 前置条件

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI 已安装
- Python 3.8+（Hook 脚本和审查脚本依赖）
- Git

### 方式一：作为模板创建新项目

```bash
git clone https://github.com/lync-cyber/CataForge.git my-project
cd my-project
rm -rf .git && git init
claude
```

### 方式二：为已有项目引入

```bash
cd your-existing-project
cp -r /path/to/CataForge/.claude .claude/
cp /path/to/CataForge/CLAUDE.md .
claude
```

### 启动工作流

在 Claude Code 中输入 `/start-orchestrator` 或直接描述需求。首次运行时 orchestrator 执行引导协议：

1. 收集项目信息（名称、技术栈、约定）
2. 创建 docs/ 目录结构和 NAV-INDEX
3. 初始化 CLAUDE.md 项目状态
4. 进入 Phase 1 — 产品经理开始需求分析

```
> 我想开发一个任务管理 Web 应用，支持看板视图和团队协作...
```

---

## 框架升级

```bash
# 本地路径升级
python .claude/scripts/upgrade.py /path/to/new-CataForge --dry-run
python .claude/scripts/upgrade.py /path/to/new-CataForge

# 远程升级（需配置 .claude/upgrade-source.json）
python .claude/scripts/check-upgrade.py --check
python .claude/scripts/check-upgrade.py --apply
```

升级会保留项目状态（CLAUDE.md、docs/、src/），仅更新框架文件。

---

## 版本规则

CataForge 遵循 [语义化版本 (SemVer)](https://semver.org/lang/zh-CN/) 规范：**MAJOR.MINOR.PATCH**

| 版本位 | 递增条件 | 示例 |
|--------|---------|------|
| **MAJOR** | 不兼容的框架变更（Agent/Skill 接口、CLAUDE.md 结构、协议格式等） | 1.0.0 → 2.0.0 |
| **MINOR** | 向后兼容的新功能（新增 Agent/Skill、新协议、新模板） | 0.1.0 → 0.2.0 |
| **PATCH** | 向后兼容的修复（Bug 修复、文档修正、脚本优化） | 0.1.0 → 0.1.1 |

**约定：**
- 版本号记录在 `pyproject.toml` 的 `[project].version` 字段中
- Git tag 格式：`v{MAJOR}.{MINOR}.{PATCH}`（如 `v0.1.0`）
- `0.x` 阶段 API 可能变化，MINOR 递增可能包含不兼容变更
- `1.0.0` 起严格遵守 SemVer 兼容性承诺

---

## 贡献指南

### 新增 Agent

1. 创建 `.claude/agents/{agent-name}/AGENT.md`，YAML frontmatter 必填: `name`, `description`, `tools`, `disallowedTools`, `allowed_paths`, `model`, `maxTurns`
2. 在 `skills:` 字段声明该 Agent 使用的 Skill
3. 参考已有 Agent（如 `architect/AGENT.md`）

### 新增 Skill

1. 创建 `.claude/skills/{skill-name}/SKILL.md`，必填: `name`, `description`；可选: `argument-hint`, `suggested-tools`, `depends`, `user-invocable`
2. 按需添加 `templates/`（文档模板）和 `scripts/`（确定性脚本）子目录
3. SKILL.md 控制在 500 行以内（渐进加载原则）

### 贡献规范

- **单一事实来源** — 规则在 COMMON-RULES.md 定义一次，其他文件通过引用使用
- **中文文档** — 框架文档和提示词使用中文；代码、变量、CLI 参数使用英文
- **解释 why** — 约束规则附带原因说明，避免无理由的"禁止"
- **Commit 格式** — `feat:` 新功能 / `fix:` 修复 / `refactor:` 重构 / `learn:` 经验应用 / `chore:` 工具变更

---

## 许可证

[MIT](LICENSE)
