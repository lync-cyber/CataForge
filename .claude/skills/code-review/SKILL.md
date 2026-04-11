---
name: code-review
description: "代码评审 — 代码质量检查、规范合规验证、安全漏洞检测。"
argument-hint: "<代码文件路径或目录>"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 代码评审 (code-review)
## 能力边界
- 能做: 代码质量审查、命名/风格规范检查、安全漏洞检测、架构合规验证、测试质量审查
- 不做: 修改代码(仅报告问题)、需求评审

## 输入规范
- 代码文件或目录(DEV产出)
- arch#§7开发约定(命名/风格/Git约定)
- arch#§5非功能架构(安全/错误处理)

## 输出规范
- 代码审查报告 CODE-REVIEW-{task_id}-r{N}.md (问题列表 + 严重等级: CRITICAL/HIGH/MEDIUM/LOW)
- 审查结论: approved/approved_with_notes/needs_revision

## 操作指令: 执行代码审查 (review)

### Step 1: Layer 1 — Lint脚本自动检查
**前置判断**: 读取 `.claude/settings.json`，检查 PostToolUse hooks 中是否存在 matcher 为 `Edit|Write` 且 command 包含 `lint_format.py` 的条目:
- **已配置 lint hook** → 编码阶段已通过 hook 以 `--fix` 模式实时修复格式/lint问题，跳过 Layer 1，直接进入 Step 2 Layer 2，并在审查报告标题下标注 `Layer 1 delegated to hook`
- **未配置 lint hook** → 执行: `python .claude/skills/code-review/scripts/code_lint.py {file_or_dir}`

未配置 hook 时的处理结果(三种情况):
- **exit 0** (检查通过) → 进入Step 2 Layer 2
- **exit 1** (有lint错误) → 返回错误列表；可选传入 `--fix` 自动修复后重新检查
- **脚本执行异常** (Python错误/超时) → 标注"lint检查跳过"，降级进入Layer 2

支持语言: JavaScript/TypeScript(ESLint+Prettier), Python(Ruff), C#(dotnet format), Go(golangci-lint), Rust(clippy)
工具不存在时自动跳过并WARN，不阻断检查流程。

### Step 2: Layer 2 — AI语义审查
通过doc-nav加载 arch#§7开发约定 和 arch#§5非功能架构，审查:
- 命名规范: 文件/变量/接口命名是否符合arch约定
- 代码结构: 模块组织、职责划分是否合理
- 安全漏洞: OWASP Top 10 检查(注入/XSS/认证/敏感数据暴露等)
- 接口一致性: 实现是否与arch接口契约匹配
- 错误处理: 是否符合arch§5.3错误处理策略
- 测试质量 (仅当审查范围包含 tests/ 目录时; AC 覆盖完整度由 sprint-review 负责，此处不重复):
  - 断言有效性: 每个测试是否包含对被测系统返回值/状态/副作用的有效断言
  - 测试逻辑: 断言的期望值是否与接口契约一致，测试是否验证了声称的行为
  - 边界覆盖: 是否覆盖关键边界条件（空值、异常输入等）

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 CODE-REVIEW-{task_id}，目录 docs/reviews/code/。

### Step 4: 产出审查报告
产出 `CODE-REVIEW-{task_id}-r{N}.md`，问题格式、category 和 root_cause 枚举按 COMMON-RULES §审查报告规范。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。

## 效率策略
- Hook去重: 已配置 PostToolUse lint hook 时跳过 Layer 1，避免与编码阶段的实时 lint 重复检查
- Layer 1兜底: 未配置 hook 的项目仍执行 Layer 1 作为质量门禁
- Layer 2聚焦语义: AI审查专注于lint无法覆盖的逻辑/安全/架构问题
- 按严重等级排序问题
