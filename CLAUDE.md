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

## 提交前静态检查（硬约束）

`.pre-commit-config.yaml` 配的 ruff + 文档守卫只有在两步都做了之后才会自动跑：

```bash
pip install -e .[dev]    # 一次性安装 pre-commit 包到当前环境
pre-commit install        # 一次性把 git hook 挂到 .git/hooks/pre-commit
```

未挂 hook 的环境（含 Claude Code session）**提交前必须手动跑这一条**：

```bash
python scripts/checks/run_local.py
```

[`run_local.py`](scripts/checks/run_local.py) 顺序调用 7 个 repo-wide 守卫 —— ruff lint + marketing-word + design-residue + language-coupling + doc-structure + QueryBoolean-eq-True + schema-python-parity；任一非零即非零退出。CI 跑的是同一组脚本，本地通过本地这条命令 ≈ CI 不会因这些 class 报错。

不能省的原因：CI 已经多次把"本地没跑过这条命令"才漏掉的错误拦下来 —— ruff F401 / SIM108、marketing-word "simply" 都在最近的 PR 上出现过。一次性把所有 repo-wide 守卫塞进一条命令，意味着没有"我以为只改了文档不用跑 ruff"或"我以为这条不会被 marketing-word 命中"的借口。

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
