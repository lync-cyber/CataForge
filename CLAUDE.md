# CataForge — Claude Code 项目指令

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
