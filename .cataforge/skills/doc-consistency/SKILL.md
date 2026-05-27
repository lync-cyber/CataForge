---
name: doc-consistency
description: "跨文档一致性验证 — 对已完成的文档全集(PRD/ARCH/UI-SPEC/DEV-PLAN)执行交叉语义校验，检测文档间的语义漂移、覆盖缺口和契约矛盾。单文档结构审查由 doc-review 负责；本 skill 专注文档间关系。"
argument-hint: "<docs_dir: 文档根目录，默认 docs/>"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 跨文档一致性验证 (doc-consistency)

## 能力边界
- 能做: 跨文档交叉验证(AC追踪、字段一致、API契约对齐、覆盖矩阵生成)、产出一致性报告
- 不做: 单文档结构审查(由 doc-review 负责)、修改文档(仅报告问题)

## 输入规范
- docs_dir: 文档根目录（默认 `docs/`）
- 可选 `--scope`: `full`（全量校验）| `incremental`（仅校验 stale_deps 涉及的文档对）

## 输出规范
- `docs/reviews/doc/CONSISTENCY-REPORT-r{N}.md`（问题列表 + 追踪矩阵 + 严重等级）
- 退出语义: 0 = 全部通过, 1 = 存在 CRITICAL/HIGH, 2 = 仅 MEDIUM/LOW

## 操作指令: 执行跨文档一致性验证 (validate)

### Step 1: 文档集发现
通过 doc-nav 加载 `.doc-index.json`，提取所有 status=approved 或 status=draft 的业务文档（prd/arch/ui-spec/dev-plan）。若 `--scope incremental`，仅加载 `cataforge docs validate` 报告 stale_deps 涉及的文档对。

### Step 2: Layer 1 — 自动化交叉校验

调用入口: `cataforge skill run doc-consistency -- <docs_dir> [--scope full|incremental]`

校验维度（按文档对组织）:

**PRD → ARCH 一致性**:
- AC 覆盖追踪: PRD 中每个 AC-NNN 是否在 ARCH 的模块描述或接口定义中有对应的设计承接。检查 ARCH 正文是否引用了该 AC 编号，或该 AC 所属 F-NNN 的对应模块是否包含语义等价的设计描述
- 非功能需求映射: PRD §3 非功能需求的每个约束（性能指标、安全要求）是否在 ARCH §5 非功能架构中有对应设计决策
- 优先级一致: PRD 标记 P0 的功能对应的 ARCH 模块不应标记为可选或低优先级

**ARCH → DEV-PLAN 一致性**:
- 接口契约对齐: ARCH API-NNN 定义的端点路径、HTTP 方法、请求/响应字段是否与 DEV-PLAN 任务卡的 AC 描述一致（端点路径字面匹配）
- 模块-任务完整映射: 每个 ARCH M-NNN 至少对应一个 DEV-PLAN T-NNN（已由 doc-review 双向覆盖检查保障），此处补充检查 M-NNN 的接口数与 T-NNN 的 deliverables 数是否匹配量级
- 实体字段传播: ARCH E-NNN 定义的字段列表是否在 DEV-PLAN 的对应任务 deliverables 或 AC 中被引用

**PRD → UI-SPEC 一致性** (若 UI-SPEC 存在):
- 功能-页面映射: PRD 每个 user-facing F-NNN 是否在 UI-SPEC 中有对应的 P-NNN 页面或 C-NNN 组件承接
- AC 可视化覆盖: PRD 中描述用户可见行为的 AC（含"显示""渲染""导航"等动词）是否在 UI-SPEC 的组件/页面中有对应的视觉描述

**PRD → DEV-PLAN AC 追踪**:
- AC-NNN 完整传播: PRD 中定义的每个 AC-NNN 是否在 DEV-PLAN 的某个 T-NNN 的 tdd_acceptance 中被引用或语义覆盖
- AC 粒度一致: 若 PRD 一个 F-NNN 有 5 个 AC，但对应 DEV-PLAN 任务的 tdd_acceptance 仅列 2 个 AC，标记 MEDIUM 警告

**全集校验**:
- 孤立模块: ARCH M-NNN 未被任何 DEV-PLAN T-NNN 引用（已由双向覆盖保障，此处交叉确认）
- 孤立组件: UI-SPEC C-NNN 未被任何 P-NNN 页面引用
- ID 冲突: 跨文档检查无重复 ID（如 PRD 和 ARCH 不应同时定义 F-001 含义不同的条目）

### Step 3: 追踪矩阵生成
从校验结果生成需求追踪矩阵:

```markdown
| PRD Feature | AC Count | ARCH Module | ARCH API | DEV-PLAN Task | UI-SPEC Page | Coverage |
|-------------|----------|-------------|----------|---------------|--------------|----------|
| F-001       | 3        | M-001       | API-001  | T-001, T-002  | P-001        | full     |
| F-002       | 2        | M-002       | API-002  | T-003         | —            | partial  |
| F-003       | 4        | —           | —        | —             | —            | missing  |
```

Coverage 判定: `full` = 所有下游文档均覆盖; `partial` = 至少一个下游文档缺失; `missing` = 无任何下游覆盖。

### Step 4: 产出一致性报告
产出 `CONSISTENCY-REPORT-r{N}.md`，包含:
- §1 追踪矩阵（Step 3 产出）
- §2 问题清单（按严重等级分组: CRITICAL / HIGH / MEDIUM / LOW）
- §3 stale deps 摘要（引用 `cataforge docs validate` 结果）

严重等级判定:
- **CRITICAL**: PRD P0 功能在 ARCH 或 DEV-PLAN 中完全缺失
- **HIGH**: AC-NNN 未传播到 DEV-PLAN tdd_acceptance; API 契约路径不匹配
- **MEDIUM**: 非功能需求未在 ARCH 中有对应设计; AC 数量不匹配; 孤立组件
- **LOW**: 优先级标记不一致; 字段命名风格差异

### Step 5: 判定结论
- 存在 CRITICAL/HIGH → `inconsistent`（建议阻塞 Phase Transition）
- 仅 MEDIUM/LOW → `consistent_with_notes`
- 无问题 → `consistent`

## Layer 2 — AI 语义交叉审查

当 Layer 1 报告 `consistent_with_notes` 且文档总行数 > 500 时，追加 AI 语义审查:

通过 doc-nav 按需加载文档对的相关章节，按以下维度交叉审查:
- 语义等价性: ARCH 对 PRD 功能的设计是否语义覆盖了原始需求意图（不仅仅是 ID 引用）
- 契约传播完整性: PRD 的约束条件（边界值、异常流程、并发场景）是否在下游文档中保留
- 设计决策一致: ARCH 的技术选型是否与 PRD 的非功能需求兼容（如 PRD 要求 <200ms 响应，ARCH 选用的方案是否可行）

## Anti-Patterns
- 禁止: 替代 doc-review 的单文档审查职能 — 本 skill 只做跨文档关系，单文档结构和质量由 doc-review 负责
- 禁止: 在文档首次创建时运行 — 跨文档一致性要求至少两个文档已存在，在 Phase 2+ 才有意义
- 避免: 对 agile-prototype 模式运行 — brief.md 是单一文档，无跨文档关系可校验

## 效率策略
- `--scope incremental` 仅校验 stale_deps 涉及的文档对，避免全量扫描
- 通过 doc-nav 按需加载章节，不全量读取所有文档
- Layer 2 仅在 Layer 1 报告非零问题且文档规模较大时触发
