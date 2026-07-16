---
name: code-review
description: "代码评审 — 任务粒度评审 (review) 与项目级健康度扫描 (scan) 双入口；代码质量检查、规范合规验证、安全漏洞检测、腐化指标扫描。当任务卡 GREEN 完成 / Sprint 发布前 / 用户要求扫描代码腐化时使用此 skill。审查范围限 src/ 业务代码：文档审查由 doc-review 负责；框架元资产 (.cataforge/) 审查由 framework-review 负责；Sprint 完成度由 sprint-review 负责。"
argument-hint: "review <path> [--fix] [--focus <category[,...]>] | scan <path> [--focus <category[,...]>]"
suggested-tools: file_read, file_glob, file_grep, shell_exec
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# 代码评审 (code-review)
## 能力边界
- 能做: 功能正确性对照（实现 vs AC/契约）、代码质量审查、命名/风格规范检查、安全漏洞检测、架构合规验证、测试质量审查、项目级腐化指标扫描（重复/死码/复杂度）
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
- **未配置 lint hook** → 执行: `cataforge skill run code-review -- review {file_or_dir}`

**调用约定**: 入口与返回码语义按 COMMON-RULES §Layer 1 调用协议。本 skill 增量：exit 1 时可追加 `--fix` 自动修复后重新检查——`--fix` 就地改写被审文件，执行权属仅限 implementer（continuation）/ tdd-engine / lint hook 语境，reviewer 角色（禁改被审对象）禁用，遇 convention 类 finding 记入报告由 implementer continuation 修复；未知参数与非法 `--focus` 值为用法错误（exit 2）；两个模式均支持 `--format json` 输出结构化 finding（Layer 2 与报告聚合的机读输入）。

工具适配与检查清单见 §Layer 1 检查项；工具不存在时自动跳过并 WARN，不阻断检查流程。

### Step 2: Layer 2 — AI语义审查

> **语言细则**: 进入语义审查前，根据 `framework.json` `project.languages`，按需载入本 skill `references/lang-<lang>.md`（仅 active 语言，逐个 Read），作为该语言的评审细则（坏味道、安全陷阱、缺陷模式、性能反模式、评审 checklist）。这是散文评审参考，与 §Plugin-style rules 的 `rules/*.yaml`（Layer 1 机检 wiring）互补、不重复。

**Layer 2 短路条件**（降低轻量任务的审查开销，类比 doc-review §Layer 2 短路）:

满足以下任一条件且 Layer 1 exit 0 时**跳过 Layer 2** 直接判定为 `approved`:

1. 任务卡 `task_kind ∈ CODE_REVIEW_L2_SKIP_TASK_KINDS`（默认 `[chore, config, docs]`）
2. 任务卡 `tdd_mode: light` + AC 数 ≤ `CODE_REVIEW_L2_SKIP_LIGHT_MAX_AC` + Layer 1 输出无 security/error-handling 类 finding
3. 调度方声明 layer1-only 降级（由 ORCHESTRATOR-META-PROTOCOLS §Adaptive Review 反向降级触发；这是 Layer 2 编排参数，不传入 Layer 1 CLI——CLI 只认 `review|scan` 子命令与 `--fix`/`--focus`/`--format`，未知参数报 exit 2）

**短路豁免**（即使命中上述条件也强制跑 Layer 2）:
- 任务卡 `security_sensitive: true`
- 任务卡 `user_facing_critical_path: true`（页面/路由/UI 可达性 — 形式契约对但 handler 留白会被全档 light 短路放过；详见 §integration-wiring）
- 任务卡 `consumer_components` 字段非空（声明了下游 wiring 消费点 → 隐式 user-facing critical path）
- Layer 1 输出含任一 finding 涉及 security / error-handling / 注入 / 鉴权 / 加密 / 输入校验

命中短路时仍需按 Step 3/4 产出 `CODE-REVIEW-{task_id}-r{N}.md` 报告，front matter `status: approved`，并在报告标题下标注 `Layer 2 skipped (short-circuit: <触发条件>)`。降级场景（Layer 1 异常 / FAIL）不适用短路。

通过context加载 arch#§7开发约定 和 arch#§5非功能架构，按以下维度审查（括号内为对应的 category 枚举值；排序即注意力优先级——实质缺陷在前；Layer 1 lint 已机检的形式面不复报）:
- 功能正确性(correctness): 实现语义与任务卡 AC / arch 契约逐条对照——每条 AC 的 Then 由实现路径真实兑现，不以测试绿等价（弱断言可让缺陷带绿通过）；算法与边界（空集合/极值/差一/非法状态转换）；数据完整性（静默吞错、部分写入、丢失更新）。与 test-quality 分工：test-quality 审测试本身，correctness 直接审实现
- 安全漏洞(security): OWASP Top 10 检查(注入/XSS/认证/敏感数据暴露等)
- 集成连线(integration-wiring): 接线对象在生产路径有真实调用点、不是空 stub / 占位返回 / 仅满足类型契约的形式。仅 tests/ 内构造调用不算落地。各语言反例与正则候选见 [`wiring-checks.md`](../../references/wiring-checks.md)；CHECKS_MANIFEST `wiring_empty_handler` 与 plugin-style YAML (`wiring-{lang}.yaml`) 承载具体识别规则。下游声明 `wiring_placeholder: true` + 关联 backlog ID 则豁免
- 错误处理(error-handling): 是否符合arch§5.3错误处理策略
- 接口一致性(consistency): 实现是否与arch接口契约匹配
- 代码结构(structure): 模块组织、职责划分是否合理。项目声明 arch 层模型时以 Layer 1 `arch_guard` 报告为输入，聚焦无 import 信号的语义越层（职责错置、接口层内嵌业务规则），不复查已机械判定的 import 方向违规
- 性能(performance): 热路径上的循环内 I/O、重复计算、明显劣化的复杂度量级；细则见各语言 `references/lang-<lang>.md` 性能反模式段。仅报可指认触发场景的问题，不做投机性微优化建议
- 视觉保真(visual-fidelity, 仅 `user_facing_critical_path: true` 且含样式/标记的 UI 任务): Layer 1 `ui_fidelity` 已机械抓死 token / 未加载字体 / 幽灵类；此处补静态抓不到的渲染缺陷——内容/图标是否被渲染成字面文本、激活与状态视觉是否真出现、计算样式（computed-style）是否等于设计值。收口须有**渲染证据**（截图或运行期计算样式读数），不以绿单测代替。无头 / 沙盒环境取不到渲染证据时**不**以 `[ENV-LIMITATION]` / `[ASSUMPTION]` 豁免，按 COMMON-RULES §verdict_blocking_semantics 出 `conditional_release` + 非空 `blocking_conditions`（条件=补一次真实渲染核验）驱动闭环
- 模拟器证据资格(simulator-evidence, 仅当审查证据引用外部系统模拟器/mock 结论时): 按保真度契约核对（[`external-truth-first.md`](../../references/external-truth-first.md)），`placeholder` / 未声明者按证据不存在处理
- 测试质量(test-quality, 仅当审查范围包含 tests/ 目录时; AC 覆盖完整度由 sprint-review 负责，此处不重复):
  - 断言有效性: 每个测试是否包含对被测系统返回值/状态/副作用的有效断言
  - 断言强度: 断言必须绑定真实可观测属性（契约定义的返回值字段 / 状态变化 / 外部副作用）。仅校验 mock/spy 调用计数 / 对象存在性 / 常量真值的"弱断言"视为测试 bug；若 mock 中诡异条件让弱断言 PASS（永远返回常量 / 永远 raise / 强行短路真实路径），视为 implementation bug 假阳性而非测试问题。与 implementer §Assertion Strength Guard 同源
  - 测试逻辑: 断言的期望值是否与接口契约一致，测试是否验证了声称的行为
  - 边界覆盖: 是否覆盖关键边界条件（空值、异常输入等）
- 命名规范(convention): 文件/变量/接口命名是否符合arch约定；Layer 1 lint 机检面不复报，仅报机检抓不到的语义命名问题（名实不符、误导性命名）

**维度收敛**: 调用方可传 `--focus <category[,...]>`（值取自 COMMON-RULES §统一问题分类体系，另含 Layer 1 专属维度 integration-wiring / visual-fidelity / arch），仅审查指定维度。不传时跑全维度。例如：`cataforge skill run code-review -- review {path} --focus security,error-handling`。review 模式下 Layer 1 同步收敛：只执行 category 命中的检查（无命中维度的 Layer 1 检查跳过），Layer 2 按同一 focus 收敛散文维度。

**增量审查模式（revision re-review）**:

当同 task_id 已存在上一轮 CODE-REVIEW 报告（`-r{N-1}`）时——以报告文件存在为触发事实，不依赖调用方传入 revision 语境——审查范围收窄为：
- 仅审查 `git diff` 涉及的文件和函数（与上次审查的 commit baseline 比较）。Layer 1 调用无需增量参数——把收窄后的文件/目录作为 `review <path>` 目标即可；`complexity_gate` 本就只对 git diff 涉及的函数施门禁
- 上轮报告中无 CRITICAL/HIGH 的维度标注 `[previously-approved]`，不重复审查
- 上轮报告中 CRITICAL/HIGH 涉及的维度 + diff 新增代码的全维度 → 正常审查
- 上轮报告未闭环的 MEDIUM/LOW 逐条标注 `still-open` / `resolved`；still-open 项参与本轮聚类升级计数，并按本轮 finding 参与三态判定（COMMON-RULES §三态判定逻辑）
- report 中每个 `[previously-approved]` 维度附注上轮 report 编号供追溯

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 CODE-REVIEW-{task_id}，目录 docs/reviews/code/。

### Step 4: 产出审查报告
产出 `CODE-REVIEW-{task_id}-r{N}.md`，**首行必须为 YAML front matter**，字段按 COMMON-RULES §报告 Front Matter 约定（本模式 delta：`id: "code-review-{task_id}-r{N}"`、`deps: ["{task_id}"]`）；缺失会导致 `cataforge context index` 跳过该文件并被 `cataforge doctor` 计为 orphan。

front matter 之后按 COMMON-RULES §问题格式 列出问题，§归因分类 / §统一问题分类体系 提供 root_cause / category 枚举。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。判定后把本审查报告 front matter 的 `status` 由 `draft` 改为 `approved`（无论 verdict 类型）。

## 操作指令: 项目级健康度扫描 (scan)

适用于：用户提出"扫一下整个 src/"、"看下这个项目代码腐化情况"、定期巡检等不与具体 task_id 绑定的需求。**默认按需触发**（用户手动 / `cataforge doctor --deep` 可选附带），不进入 TDD 主循环。

签名: `cataforge skill run code-review -- scan <path> [--focus <category[,...]>] [--format text|json] [--verbose]`（`--format json` 输出结构化 finding 供 Layer 2 消费，读 stdout；日志走 stderr。`--verbose` 展开被截断的 info 尾）

### Step 1: Layer 1 — Lint + 腐化指标
执行: `cataforge skill run code-review -- scan {path} [--focus duplication,dead-code,complexity]`

脚本内部按以下顺序执行:
1. 门禁检查恒跑（lint / wiring / ui-fidelity，同 review 模式；scan 的 `--focus` 不筛门禁检查）
2. 按 `--focus` 指定的腐化维度：duplication 由内置行块 floor 保底 + jscpd 增强承载（见 §Layer 1 检查项），test-quality 由内置 `test_hygiene` 承载（无标签慢测候选 / 每测重建昂贵 setup 候选，pattern 集 `test-hygiene-{lang}.yaml`），其余维度调对应 informational probe（vulture / ts-prune / radon / gocyclo 等）
3. vendored / 生成文件（`*.min.*` / `*.map` / `*-lock.json` 等，及项目级 `.cataforge/skills/code-review/ignore` 声明的 glob）不参与 lint 与探针；工具不存在 → WARN 跳过，不 FAIL

返回码语义按 §Layer 1 调用协议；scan 默认不因腐化 finding 而 FAIL（仅 lint error 时 FAIL），rot 信号视作 informational，由 Layer 2 做严重度判定。

### Step 2: Layer 2 — AI 模式聚合
读取 Step 1 的 finding 列表，按 category 聚合并打严重等级:
- 同一文件的重复块跨阈值 → MEDIUM/HIGH（按重复行数判定）
- vulture 报死码 + 该文件未被任何引用 → HIGH
- 复杂度严重等级委托项目级 `complexity.yaml` 阈值（`complexity_gate` finding 已按 warn/fail 标注：超 fail → HIGH，超 warn → MEDIUM），不在此处另设数值
- ts-prune 未引用导出 → LOW（可能是公共 API）
- config 死键（`config_dead_key`）→ MEDIUM；结合业务判断是否由部署基础设施等外部消费（是则建议声明文件加豁免）
- API 导出移除（`api_surface`）→ HIGH（潜在破坏性变更）；新增导出 → LOW（面扩张提示）
- 豁免盘点（`pragma_inventory`）：unknown-pragma 残留 / 缺 reason → MEDIUM；高龄豁免（长期未清理）→ LOW 并列入重构建议
- 测试套件卫生（`test_hygiene`）：无标签慢测候选 → LOW，单文件密集命中（≥3 处）→ MEDIUM；每测重建昂贵 setup 候选 → MEDIUM（改进方向按 `.cataforge/references/test-suite-performance.md`）；慢测标记豁免为文件级粒度（文件内任一处命中标记 pattern 即豁免全文件）

### Step 3: 产出扫描报告
报告路径: `docs/reviews/code/CODE-SCAN-{YYYYMMDD}-r{N}.md`（编号规则：当日同前缀已存在 r1 则递增到 r2）。Front matter 字段按 COMMON-RULES §报告 Front Matter 约定（本模式 delta：`id: "code-scan-{YYYYMMDD}-r{N}"`、`deps: []`）。

问题列表按 COMMON-RULES §问题格式；可用 category: structure / duplication / dead-code / complexity / coupling / performance / error-handling / security / consistency / convention / arch。

### Step 4: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。scan 模式默认不阻塞流程（不进 needs_revision 自动重试），仅产出报告供后续重构决策。

## Layer 1 检查项

> 权威清单见 `cataforge.runtime.skill.builtins.code_review.CHECKS_MANIFEST`（framework-review 自动对账）。每项检查的 id / 严重度 / 适用模式 / 豁免语法以 manifest 条目自述为准，本段不逐条复述。

- linter / formatter 工具适配（review + scan 门禁，按文件类型自动选择）：ESLint + Prettier (.js/.ts/.jsx/.tsx)、Ruff (.py)、dotnet format (.cs)、golangci-lint (.go)、cargo clippy (.rs)；工具未安装时跳过并 WARN，不阻断
- 声明式检查的语义细则按维度分文档承载：wiring 空 handler 见 [`wiring-checks.md`](../../references/wiring-checks.md)；架构分层守护（`arch_guard`，项目声明 `arch.yaml` 方向矩阵即激活）见 [`arch-checks.md`](../../references/arch-checks.md)；复杂度门禁与棘轮基线（`complexity_gate`）见 [`complexity-checks.md`](../../references/complexity-checks.md)
- duplication 维度（informational）：内置行块 floor（零依赖、语言通用，与 `complexity_gate` 同构保证维度不静默）保底 + jscpd token 级增强（多语言，出报告时用其精确信号）/ pmd-cpd（Java）
- scan 腐化 probe（informational，按 `--focus` 选择性执行）：dead-code（vulture / ts-prune / knip / cargo-machete / config 死键 xref）、complexity（radon / gocyclo / eslint，探针阈值统一取项目级 `complexity.yaml`）、consistency（API 面快照 diff）、convention（豁免盘点）、test-quality（`test_hygiene` 内置测试套件卫生扫描）；probe 工具缺失 WARN 跳过，scan 不因此 FAIL
- vendored / 生成文件排除（`EXCLUDE_FILE_GLOBS`：`*.min.*` / `*.map` / `*-lock.json` / `*.d.ts` 等）+ 项目级 `.cataforge/skills/code-review/ignore`：lint 遍历与探针 ignore 共享单一源，压缩第三方包不产生假阳性

豁免统一语法 `cataforge: allow(<check-id>, reason="...")`（reason 必填，缺失时豁免生效但记 WARN；文件级/行级生效范围随消费方）见 [`pragma-grammar.md`](../../references/pragma-grammar.md)。

### Plugin-style rules (per-language extension)

Layer 1 的声明式规则全部走 rules YAML（schema v2：`schema_version: 2` + `rule_type` + `scope: language|project`；`scope: language` 必填 `language`/`extensions`，`scope: project` 供语言无关的项目级模型且不写这两键；未知顶层键报错，防拼写失效）：

- 默认（cataforge package）：`cataforge.runtime.skill.builtins.code_review.rules/*.yaml`
- 项目 override（opt-in）：`<project>/.cataforge/skills/code-review/rules/*.yaml`，整文件替换、改完即生效；framework-review B3-β 自动校验；全注释 YAML 视为未声明（发运模板语义）

rule_type 一览：`wiring`（空 handler pattern）、`arch`（项目级 `arch.yaml` 方向矩阵 + `arch-{lang}.yaml` import pattern）、`complexity`（项目级 `complexity.yaml` 四指标阈值 + `complexity-{lang}.yaml` 代理度量 pattern）、`config_keys`（声明 × 消费 pattern）、`api_surface`（导出面 pattern + 项目级 `gating` 开关）、`test_hygiene`（慢测 / 标签 / 昂贵 setup pattern）。

## Anti-Patterns

- 禁止: 把 user-facing critical path 任务（页面/路由/UI 可达性、`consumer_components` 非空）走 Layer 2 短路 —— 形式契约对但 wiring 留白只能由 §integration-wiring 维度抓出，短路会放走 false-positive
- 禁止: 让 reviewer 直接下场写补丁 —— code-review 仅产出审查报告（problem list + 严重等级），任何修改必须由 implementer / debug skill 在独立调度中完成
- 禁止: scan 模式因为腐化 finding 直接判 needs_revision —— scan 默认不阻塞流程；rot 信号转化为重构决策的输入，是 informational 而非 gating
- 禁止: 手写或复制 CHECKS_MANIFEST 条目到本文档 —— manifest 由 `register_check()` 注册表派生，新增检查在 `checks/` 注册即自动进入 manifest 与 framework-review 对账面；散文复述必然漂移
- 禁止: 在 review 路径写 `.cataforge/baselines/` —— 基线（复杂度棘轮 / API 面快照）只能由 scan 刷新，review 只读判定；孤立的基线变更会被 framework-review B3-γ 判 FAIL
- 避免: 报告写入 `docs/reviews/doc/` 或其它非 `docs/reviews/code/` 目录 —— 与 doc-review / framework-review 报告混淆会污染 sprint-review 聚合

## 效率策略
- Hook去重: 已配置 PostToolUse lint hook 时跳过 Layer 1，避免与编码阶段的实时 lint 重复检查
- Layer 1兜底: 未配置 hook 的项目仍执行 Layer 1 作为质量门禁
- Layer 2聚焦语义: AI审查专注于lint无法覆盖的逻辑/安全/架构问题
- **Layer 2 短路**: light 模式小任务 / chore / Adaptive Review 反向降级时跳过 Layer 2，由 sprint-review 兜底（见 §Step 2 短路条件）
- scan 模式按需触发: 不在 TDD 主循环内自动执行，避免每次任务评审都跑 jscpd/vulture
- 按严重等级排序问题
