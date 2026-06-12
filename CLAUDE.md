@.cataforge/rules/COMMON-RULES.md

# CataForge — Claude Code 项目指令

## 项目信息

- 技术栈: Python ≥3.10 · Click(CLI) · pyoxigraph/RDF/SHACL(知识图谱) · linkml(schema) · pytest + ruff + pre-commit
- 运行时: claude-code
- 框架版本: 0.8.0
  <!-- 由 cataforge deploy 自动盖入已安装包版本。SemVer: MAJOR=不兼容变更, MINOR=新功能, PATCH=修复 -->
- 语言定位: 中文框架（提示词/文档/交互用中文；代码/变量/CLI参数用英文）
- 执行模式: standard
  <!-- 可选值: standard | agile-lite | agile-prototype。矩阵见 COMMON-RULES §执行模式矩阵。模式切换由 orchestrator §Mode Routing Protocol 路由 -->
- 阶段配置: 以下阶段可在 Bootstrap 时标记为 N/A 以跳过:
  - ui_design: 后端/CLI/API-only 项目可跳过（默认行为）
  - testing: 原型/PoC 项目可跳过
  - deployment: 库/SDK 项目可跳过
  <!-- orchestrator 在 Bootstrap Step 1 收集项目信息时，向用户确认可跳过的阶段 -->
- model 继承: AGENT.md 中 `model: inherit` 继承父会话模型；可用 `model: <model-id>` 覆盖

## 执行环境 (Bootstrap 时由 `cataforge setup --emit-env-block` 填入)

<!-- 本节在 Bootstrap 步骤中生成。每次会话都会作为项目指令加载，
     权重高于 hook 注入的 additionalContext。项目生命周期内保持稳定。 -->
{执行环境检测结果 — 未填入时 orchestrator 应在 Bootstrap 时调用:
 cataforge setup --emit-env-block}

## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)

- 项目性质: CataForge 是成熟、持续迭代的 AI SDLC 框架本体（meta 项目），自身按框架工程流程演进 —— feature branch + PR + Squash merge + TDD + `run_local.py`/CI 门禁；**不运行 orchestrator 的 7 阶段 SDLC 文档管线**
- SDLC 文档管线对本仓 N/A: PRD / ARCH / UI-SPEC / DEV-PLAN / TEST-REPORT / DEPLOY-SPEC 是框架**交付给下游业务项目**的产物，对元项目本身**不需要（非"未开始"）**
- 进度事实源: git 历史 / PR / CHANGELOG / `docs/proposals/`，不在本文件维护阶段或文档状态字段
- Learnings Registry: (compacted; archive in .cataforge/learnings/registry-archive.md)
  <!-- 上限：framework.json#claude_md_limits.learnings_registry_max_entries；超限运行 `cataforge claude-md compact` -->

## 文档导航

- 导航索引: `docs/.doc-index.json`（机器索引，所有 Agent 通过 `cataforge docs load` 查询；缺失时运行 `cataforge docs index` 重建）
- 通用规则: .claude/rules/COMMON-RULES.md
- 子代理协议: .claude/rules/SUB-AGENT-PROTOCOLS.md
- 编排协议: .cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md (orchestrator专属)
- 状态码Schema: .cataforge/schemas/agent-result.schema.json
- 加载原则: 按任务需要通过 `cataforge docs load` 加载相关章节，不全量加载

## 全局约定

- 命名: Python 用 snake_case；CLI 参数 / 文档类型 / 产出文件名用 kebab-case
- Commit: conventional-commits `<type>(<scope>): <subject>`（详见 §Git 工作流）
- 分支: `main` 受保护，feature branch + PR，仅 Squash merge（详见 §Git 工作流）
- 设计工具: none
  <!-- 可选值: none | penpot。设为 penpot 时启用 Penpot MCP 集成 -->
- 人工审查检查点: [pre_dev, pre_deploy]
  <!-- 详见 COMMON-RULES §MANUAL_REVIEW_CHECKPOINTS -->
- 文档类型命名: 小写 kebab-case（prd、arch、dev-plan、test-report、ui-spec、deploy-spec…），含工具参数和产出文件名
- Shell 约定: Windows 环境优先使用 Git Bash 执行 shell 命令（POSIX 语法与引号/转义行为跨平台一致，多行参数无 heredoc 陷阱）；PowerShell 仅用于 Windows 专属操作（注册表 / 服务 / 计划任务等）
- 效率原则:
  - 最小传递: Agent间传递doc_id#section引用，非全文
  - 不确定时调研: 调用research skill，不猜测
  - 选择题优先: 需要用户输入时优先提供选项
  - 长文拆分: 文档超 `DOC_SPLIT_THRESHOLD_LINES` 行时按doc-gen拆分策略分卷

## 框架机制

- Agent编排: orchestrator 通过 agent-dispatch skill 激活子代理
- DEV阶段: orchestrator 通过 tdd-engine skill 编排 RED/GREEN/REFACTOR 三个子代理（独立上下文）
- Skill调用: Agent按SKILL.md步骤式指令执行工作流
- 状态持久化: 项目指令文件（CLAUDE.md/AGENTS.md）§项目状态 + docs/ 目录
- 子代理通信: 通过文件系统(docs/和src/)传递产出物路径
- 运行时: 由 framework.json runtime.platform 决定（deploy 自动适配）
- **写权限**: 项目指令文件 §项目状态 由 orchestrator 独占写入；其他Agent只写 docs/ 或 src/ 下的产出文件
- 统一配置 `.cataforge/framework.json`:
  - `upgrade.source` — 远程升级源配置。升级时保留用户已配置值，仅补充新字段
  - `upgrade.state` — 本地升级状态。升级时始终保留
  - `features` — 功能注册表。升级时全量覆盖
  - `migration_checks` — 迁移检查声明。升级时全量覆盖

## Git 工作流

`main` 受保护；所有变更走 feature branch + PR。仓库只允许 Squash merge，PR 标题即 main 的 commit 消息。

**PR 标题：conventional-commits**

```
<type>(<scope>): <subject>
```

- `type` ∈ `feat|fix|docs|chore|refactor|test|build|ci|perf|release`，小写
- `subject` 小写开头、祈使句
- `scope` 示例：`cli`、`scaffold`、`upgrade`、`hook`、`agent`、`skill`、`docs`、`ci`、`e2e`

反例（CI 拒绝）：`Dev`、`Pr/dev …`、`Feat/correction log …`、`Fix/orchestrator …`
正例：`fix(doc-review): ui-spec empty-token FAIL`、`feat(scaffold): manifest + per-file dry-run`、`release: v0.1.8 self-update skill`

校验：`.github/workflows/pr-title.yml`。

**发版流程**
1. feature branch 上完成变更并 commit
2. `git push -u origin <branch>`
3. `gh pr create --title '<type>(<scope>): <subject>'`（必须显式 `--title`，否则 gh 用分支名）
4. 合入后在 main 打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`

**dogfood 分支 → main**：在 feature 分支跑 `.cataforge/scripts/dogfood/prepare-pr.sh`（按 `product-paths.txt` 白名单还原 dev-only 产物，交互式提示合规标题并调 `gh pr create`）。

**本地误提 main 的补救**：

```bash
git branch <new-branch>
git reset --hard origin/main
git push -u origin <new-branch>
```

## 提交前静态检查（硬约束）

`.pre-commit-config.yaml` 配的 ruff + 文档守卫只有在两步都做了之后才会自动跑：

```bash
uv sync --extra dev        # 一次性按 uv.lock 把 dev 依赖（含 pre-commit / ruff）装进受管 .venv
uv run pre-commit install  # 一次性把 git hook 挂到 .git/hooks/pre-commit
```

未挂 hook 的环境（含 Claude Code session）**提交前必须手动跑这一条**：

```bash
uv run --extra dev python scripts/checks/run_local.py
```

[`run_local.py`](scripts/checks/run_local.py) 顺序调用全部 repo-wide 静态守卫 —— 与 `.pre-commit-config.yaml` 的 no-arg 钩子同源（ruff lint + `scripts/checks/check_*.py` 系列），外加 `uv lock --check` lockfile 新鲜度校验，权威清单以脚本内 `CHECKS` 为准；任一非零即非零退出。CI 跑的是同一组脚本，本地通过本地这条命令 ≈ CI 不会因这些 class 报错。

不能省的原因：CI 已经多次把"本地没跑过这条命令"才漏掉的错误拦下来 —— ruff F401 / SIM108 都在最近的 PR 上出现过。一次性把所有 repo-wide 守卫塞进一条命令，意味着没有"我以为只改了文档不用跑 ruff"的借口。

## Dogfood：本仓的 Claude Code 调用面

CataForge 仓库自身也是 CataForge 项目。两条调用面，**clone 后无需 deploy 即可用第一条**：

**1. Slash command `/framework-issue-resolve`** —— wrapper [.claude/commands/framework-issue-resolve.md](.claude/commands/framework-issue-resolve.md) 已 git-tracked（[.gitignore](.gitignore) 加了 `!` 例外让单文件例外通过），clone 即可用。wrapper body 让 Claude Code 按 `.cataforge/skills/framework-issue-resolve/SKILL.md` 五步闭环调度。

**2. SKILL discovery via deploy**（可选，让 Claude Code 通过 SKILL.md description 自然语言发现所有 skill 包括 maintainer-only）：

```bash
cataforge deploy --include-maintainer-only
```

per-skill junction (Windows) / symlink (Unix) 把 `.cataforge/skills/` 每个子目录暴露到 `.claude/skills/`。`--include-maintainer-only` 让 SKILL.md 标 `maintainer-only: true` 的 skill（目前仅 `framework-issue-resolve`）也链进来。下游业务项目部署不应传这个 flag —— 那些 skill 操作 CataForge 自身的 `.cataforge/` 元资产，对下游只会占用 prompt 上下文。

`.claude/skills/` / `.claude/agents/` 与 `.claude/commands/` 下其他文件都在 [.gitignore](.gitignore)；只有 wrapper 单文件例外。

## Agent / Skill 撰写约定

仓库根 `.cataforge/skills/**/SKILL.md` / `.cataforge/agents/**/AGENT.md` / `.cataforge/agents/**/*PROTOCOLS*.md` 是 LLM **每次调度都重新加载**的 prompt 上下文 —— 每一行都在每次调用时消耗 token；残留越积越多，**长期一定会腐化到不可用**。下面两条硬约束都不是可选偏好，是 LLM 写这类文件时的入门门槛。

### 硬约束 1 · 最小可行修改

agent / skill 的任何修改都必须是**删到不能再删**的最小可行形式。新增一条规则只写规则本身——不写为什么加、不写来自哪里、不写跟过去对比。

禁止项：

- **溯源引用**：`(issue #NNN)` / `PR #NNN` / `(参 #NNN)` / `closeout` / `closes #N` / `fixes #N` / `landed in`
- **版本里程碑**：`v0.4.0+ 新增` / `自 vX.Y.Z 起` / `pre-v0.4.0` / `MVP 阶段`
- **过程标签**：`本次新增` / `本轮加入` / `现已支持` / `已废弃` / `为防 X 类问题再发` / `对照 PR #N 增量`
- **对比叙事**：`原方案 X 改为 Y` / `不再使用 X` / `重命名为 Y`
- **HTML 注释残留**：`<!-- 变更原因：... -->` / `<!-- diagnostic #N -->` / `<!-- prompt-version ... -->`

变更说明的合法去处是 PR 描述、commit message、CHANGELOG，**不能溢出**到 SKILL/AGENT 主体。完整自检 regex 见 [`.cataforge/rules/COMMON-RULES.md` §禁止设计阶段与变更说明残留](.cataforge/rules/COMMON-RULES.md)。

守卫：[`scripts/checks/check_no_design_residue.py`](scripts/checks/check_no_design_residue.py)（pre-commit + per-PR test.yml + anti-rot weekly sweep）。需要例外时同行附 `<!-- allow-design-residue: <reason> -->`。

### 硬约束 2 · 与编程语言解耦

agent / skill 的主题是**职责**（评审、TDD、文档生成、装配 hook …），不绑定具体语言。主体禁止嵌入特定语言业务关键字：

- Python：`FastAPI` / `Starlette` / `Django` / `SQLAlchemy` / `signal.connect` / `lifespan_context` / `dependency_injector` / `asyncio` 等
- JavaScript / TypeScript：`useEffect` / `Redux` / `Zustand` / `Vuex` / `Pinia` / `Express` / `NestJS` 等
- Java：`@Autowired` / `@Component` / `@Bean` / `Spring Boot` 等
- Go / Rust：`goroutine` / `tokio::spawn` 等

具体语言识别模式、反例清单、正则候选写入 `docs/reference/`（一文件一主题，例：[`wiring-checks.md`](docs/reference/wiring-checks.md)），SKILL / AGENT 主体以 markdown 链接引用。

合法例外（无需 escape hatch）：

- linter / formatter 工具适配清单（如 code-review §Layer 1 列 ESLint / Ruff / golangci-lint）— 工具适配是 skill 能力声明
- plugin-style YAML 加载路径声明（如 `wiring-{lang}.yaml`）
- 通用 UI / 编程概念词（prop / handler / store action / channel / hook 等抽象词）

守卫：[`scripts/checks/check_no_language_coupling.py`](scripts/checks/check_no_language_coupling.py)（pre-commit + per-PR test.yml + anti-rot weekly sweep）。需要例外时同行附 `<!-- allow-language-coupling: <reason> -->`。

### 硬约束 3 · 文档结构规范

agent / skill / rules 的 markdown 文件中，编号列表必须使用连续整数（1. 2. 3.），禁止：

- **非标准子步骤编号**：`3a.` / `4b.` / `2a)` — 子步骤合并到父步骤行内或用嵌套 bullet
- **编号跳跃**：`1. 2. 4.`（缺 3）
- **同一段落内编号重复**：两个 `4.`

守卫：[`scripts/checks/check_doc_structure.py`](scripts/checks/check_doc_structure.py)（pre-commit + per-PR test.yml）。需要例外时同行附 `<!-- allow-doc-structure: <reason> -->`。
