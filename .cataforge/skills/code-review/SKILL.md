---
name: code-review
description: "代码评审 — 任务粒度评审 (review) 与项目级健康度扫描 (scan) 双入口；代码质量检查、规范合规验证、安全漏洞检测、腐化指标扫描。"
argument-hint: "<代码文件路径或目录> | scan <path> [--focus <category[,...]>]"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 代码评审 (code-review)
## 能力边界
- 能做: 代码质量审查、命名/风格规范检查、安全漏洞检测、架构合规验证、测试质量审查、项目级腐化指标扫描（重复/死码/复杂度）
- 不做: 修改代码(仅报告问题)、需求评审；任务依赖图由 task-dep-analysis 负责

## 输入规范
- 代码文件或目录(DEV产出)
- arch#§7开发约定(命名/风格/Git约定)
- arch#§5非功能架构(安全/错误处理)

## 输出规范
- 任务粒度审查: `CODE-REVIEW-{task_id}-r{N}.md`（问题列表 + 严重等级: CRITICAL/HIGH/MEDIUM/LOW）
- 项目级扫描: `CODE-SCAN-{YYYYMMDD}-r{N}.md`（腐化指标聚合 + 严重等级）
- 审查结论: approved/approved_with_notes/needs_revision

## 操作指令: 任务粒度评审 (review)

### Step 1: Layer 1 — Lint脚本自动检查
**前置判断**: 读取当前平台 Hook 配置（Claude: `.claude/settings.json`；Cursor: `.cursor/hooks.json`），检查是否存在 matcher 为 `Edit|Write`（Cursor 可为 `Write`/`StrReplace`）且 command 包含 `lint_format.py` 的条目:
- **已配置 lint hook** → 编码阶段已通过 hook 以 `--fix` 模式实时修复格式/lint问题，跳过 Layer 1，直接进入 Step 2 Layer 2，并在审查报告标题下标注 `Layer 1 delegated to hook`
- **未配置 lint hook** → 执行: `cataforge skill run code-review -- {file_or_dir}`

**调用约定（单一入口）**: Layer 1 一律通过 `cataforge skill run <skill-id> -- <args>` 触发，由框架解析 SKILL.md 元数据并派发到内置脚本或项目覆写脚本。**不得**直接 `python .cataforge/skills/.../scripts/*.py`——该路径为框架内部实现细节，不保证存在。返回码语义按 §Layer 1 调用协议处理（exit 1 时可追加 `--fix` 自动修复后重新检查）。

支持语言: JavaScript/TypeScript(ESLint+Prettier), Python(Ruff), C#(dotnet format), Go(golangci-lint), Rust(clippy)
工具不存在时自动跳过并WARN，不阻断检查流程。

### Step 2: Layer 2 — AI语义审查

**Layer 2 短路条件**（降低轻量任务的审查开销，类比 doc-review §Layer 2 短路）:

满足以下任一条件且 Layer 1 exit 0 时**跳过 Layer 2** 直接判定为 `approved`:

1. 任务卡 `task_kind ∈ CODE_REVIEW_L2_SKIP_TASK_KINDS`（默认 `[chore, config, docs]`）
2. 任务卡 `tdd_mode: light` + AC 数 ≤ `CODE_REVIEW_L2_SKIP_LIGHT_MAX_AC`（默认 2） + Layer 1 输出无 security/error-handling 类 finding
3. 调用方传入 `--layer1-only` 标志（由 ORCHESTRATOR-PROTOCOLS §Adaptive Review 反向降级触发）

**短路豁免**（即使命中上述条件也强制跑 Layer 2）:
- 任务卡 `security_sensitive: true`
- Layer 1 输出含任一 finding 涉及 security / error-handling / 注入 / 鉴权 / 加密 / 输入校验

命中短路时仍需按 Step 3/4 产出 `CODE-REVIEW-{task_id}-r{N}.md` 报告，front matter `status: approved`，并在报告标题下标注 `Layer 2 skipped (short-circuit: <触发条件>)`。降级场景（Layer 1 异常 / FAIL）不适用短路。

通过doc-nav加载 arch#§7开发约定 和 arch#§5非功能架构，按以下维度审查（括号内为对应的 category 枚举值）:
- 命名规范(convention): 文件/变量/接口命名是否符合arch约定
- 代码结构(structure): 模块组织、职责划分是否合理
- 安全漏洞(security): OWASP Top 10 检查(注入/XSS/认证/敏感数据暴露等)
- 接口一致性(consistency): 实现是否与arch接口契约匹配
- 错误处理(error-handling): 是否符合arch§5.3错误处理策略
- 测试质量(test-quality, 仅当审查范围包含 tests/ 目录时; AC 覆盖完整度由 sprint-review 负责，此处不重复):
  - 断言有效性: 每个测试是否包含对被测系统返回值/状态/副作用的有效断言
  - 测试逻辑: 断言的期望值是否与接口契约一致，测试是否验证了声称的行为
  - 边界覆盖: 是否覆盖关键边界条件（空值、异常输入等）

**维度收敛**: 调用方可传 `--focus <category[,...]>`（值取自 COMMON-RULES §统一问题分类体系），仅审查指定维度。不传时跑全维度。例如：`cataforge skill run code-review -- {path} --focus security,error-handling`。

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 CODE-REVIEW-{task_id}，目录 docs/reviews/code/。

### Step 4: 产出审查报告
产出 `CODE-REVIEW-{task_id}-r{N}.md`，**首行必须为 YAML front matter**（按 COMMON-RULES §报告 Front Matter 约定），缺失会导致 `cataforge docs index` 跳过该文件并被 `cataforge doctor` 计为 orphan。最小模板：

```yaml
---
id: "code-review-{task_id}-r{N}"
doc_type: code-review
author: reviewer
status: draft               # 出 verdict 后改 approved
deps: ["{task_id}"]
---
```

front matter 之后按 COMMON-RULES §问题格式 列出问题，§归因分类 / §统一问题分类体系 提供 root_cause / category 枚举。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。判定后把本审查报告 front matter 的 `status` 由 `draft` 改为 `approved`（无论 verdict 类型）。

## 操作指令: 项目级健康度扫描 (scan)

适用于：用户提出"扫一下整个 src/"、"看下这个项目代码腐化情况"、定期巡检等不与具体 task_id 绑定的需求。**默认按需触发**（用户手动 / `cataforge doctor --deep` 可选附带），不进入 TDD 主循环。

签名: `cataforge skill run code-review -- scan <path> [--focus <category[,...]>]`

### Step 1: Layer 1 — Lint + 腐化指标
执行: `cataforge skill run code-review -- scan {path} [--focus duplication,dead-code,complexity]`

脚本内部按以下顺序执行:
1. 通用 lint pass（同 review 模式）
2. 按 `--focus` 指定的腐化维度调用对应 probe（jscpd / vulture / ts-prune / radon / gocyclo 等）
3. 工具不存在 → WARN 跳过，不 FAIL

返回码语义按 §Layer 1 调用协议；scan 默认不因腐化 finding 而 FAIL（仅 lint error 时 FAIL），rot 信号视作 informational，由 Layer 2 做严重度判定。

### Step 2: Layer 2 — AI 模式聚合
读取 Step 1 的 finding 列表，按 category 聚合并打严重等级:
- 同一文件的重复块跨阈值 → MEDIUM/HIGH（按重复行数判定）
- vulture 报死码 + 该文件未被任何引用 → HIGH
- 圈复杂度 ≥20 → HIGH，≥15 → MEDIUM
- ts-prune 未引用导出 → LOW（可能是公共 API）

### Step 3: 产出扫描报告
报告路径: `docs/reviews/code/CODE-SCAN-{YYYYMMDD}-r{N}.md`（编号规则：当日同前缀已存在 r1 则递增到 r2）。Front matter 模板:

```yaml
---
id: "code-scan-{YYYYMMDD}-r{N}"
doc_type: code-review
author: reviewer
status: draft
deps: []
---
```

问题列表按 COMMON-RULES §问题格式；可用 category: structure / duplication / dead-code / complexity / coupling / performance / error-handling / security。

### Step 4: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。scan 模式默认不阻塞流程（不进 needs_revision 自动重试），仅产出报告供后续重构决策。

## Layer 1 检查项 (code_lint.py)

> 权威清单见 `cataforge.skill.builtins.code_review.CHECKS_MANIFEST`（framework-review 自动对账，本段与 manifest 不一致即 FAIL）。

review 模式（按文件类型自动选择工具）:
- ESLint (.js/.ts/.jsx/.tsx)
- Prettier 格式化检查 (.js/.ts/.jsx/.tsx)
- Ruff check + format (.py)
- dotnet format --verify-no-changes (.cs)
- golangci-lint run (.go)
- cargo clippy -D warnings (.rs)
- 工具未安装时跳过并 WARN，不阻断检查流程

scan 模式额外的腐化 probe（按 --focus 选择性执行）:
- duplication: jscpd（多语言：JS/TS/Py/Go/C#/Rust/Java/Kotlin/Swift）/ pmd-cpd (.java)
- dead-code: vulture (.py) / ts-prune (.ts/.tsx) / cargo-machete (.rs, 检测未使用 Cargo 依赖)
- complexity: radon cc (.py) / gocyclo (.go)
- probe 工具未安装 → WARN 跳过；scan 不会因 probe 缺失而 FAIL

## 效率策略
- Hook去重: 已配置 PostToolUse lint hook 时跳过 Layer 1，避免与编码阶段的实时 lint 重复检查
- Layer 1兜底: 未配置 hook 的项目仍执行 Layer 1 作为质量门禁
- Layer 2聚焦语义: AI审查专注于lint无法覆盖的逻辑/安全/架构问题
- **Layer 2 短路**: light 模式小任务 / chore / Adaptive Review 反向降级时跳过 Layer 2，由 sprint-review 兜底（见 §Step 2 短路条件）
- scan 模式按需触发: 不在 TDD 主循环内自动执行，避免每次任务评审都跑 jscpd/vulture
- 按严重等级排序问题
