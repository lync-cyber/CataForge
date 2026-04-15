---
name: doc-review
description: "统一文档评审 — Python脚本自动检查 + AI语义审查双审机制。"
argument-hint: "<doc_type: prd|arch|dev-plan|ui-spec|test-report|deploy-spec|research-note|changelog> <doc_file>"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 统一文档评审 (doc-review)
## 能力边界
- 能做: 文档结构检查(脚本)、语义审查(AI)、产出REVIEW报告、变更文档状态
- 不做: 修改被审文档(仅报告问题)、内容生成

## 操作指令: 执行双审门禁 (review)

### Step 1: Layer 1 — Python脚本自动检查

**分卷检测**: 调用前先 glob `docs/{doc_type}/` 目录检测是否存在分卷文件，对每个文件分别执行 doc_check.py。

**主卷调用**:
```
python .cataforge/skills/doc-review/scripts/doc_check.py {doc_type} docs/{doc_type}/{doc_file} --docs-dir docs/{doc_type}/
```

**分卷调用**:
```
python .cataforge/skills/doc-review/scripts/doc_check.py {doc_type} docs/{doc_type}/{vol_file} --volume-type {type} --docs-dir docs/{doc_type}/
```

**volume_type 推断规则** (也可从文件头 `<!-- volume: ... -->` 自动检测):
- `*-api.md` → api
- `*-data.md` → data
- `*-modules.md` → modules
- `*-s{N}.md` → sprint
- `*-f*-f*.md` → features
- `*-p*-p*.md` → pages
- `*-c*-c*.md` → components

**规则**: 所有分卷必须全部通过 Layer 1 才进入 Layer 2。

处理结果(三种情况):
- **exit 0** (脚本执行成功 + 检查通过) → 进入Step 2 Layer 2
- **exit 1** (脚本执行成功 + 检查不通过) → 返回失败项列表，**不进入Layer 2**，节省资源
- **脚本执行异常** (文件缺失/Python错误/超时) → 标注"脚本检查跳过(降级)"，**降级进入Layer 2**。降级后 Layer 2 的审查标准和判定规则不变（无CRITICAL/HIGH→approved），仅标记"Layer 1降级"供追溯

**Layer 2 短路条件** (降低轻量文档的审查开销):
- 若 Layer 1 exit 0、被审文档行数 < `DOC_REVIEW_L2_SKIP_THRESHOLD_LINES`、且 `doc_type ∈ DOC_REVIEW_L2_SKIP_DOC_TYPES`，则**跳过 Layer 2** 直接判定为 `approved`
- 命中短路时，仍需按 Step 3/4 产出 `REVIEW-{doc_id}-r{N}.md` 报告，并在报告标题下标注 `Layer 2 skipped (short-circuit)` 及触发条件（行数、doc_type）
- 降级场景（Layer 1 异常）不适用短路，必须完整执行 Layer 2

### Step 2: Layer 2 — AI语义审查
通过doc-nav按需加载被审文档和上游依赖，按以下维度审查（括号内为对应的 category 枚举值）:
- 完整性(completeness): 是否有逻辑遗漏、缺少必要定义
- 一致性(consistency): 与上游文档是否矛盾、内部是否自洽
- 可行性(feasibility): 设计是否可落地、技术上是否可实现
- 安全性(security): 是否存在安全漏洞或合规风险
- 规范性(convention): 命名/格式/编码规范是否符合约定
- 清晰度(ambiguity): 描述是否模糊、能否作为下游输入

**ui-spec专项审查维度**（仅当doc_type=ui-spec时追加）:
- 设计方向一致性(consistency): §0设计方向声明是否贯穿到Token选择和组件风格——如声明"专业克制"但使用了高饱和度彩色和大圆角
- 色彩体系层次(completeness): 主色/辅色/中性色是否有明确的主次关系，中性色是否有色相倾向而非纯灰
- 组件视觉可区分性(ambiguity): 各状态变体(hover/active/disabled)是否有足够的视觉差异描述，开发者能否据此实现而无需猜测
- 页面空间构成(ambiguity): 布局描述是否包含空间节奏(密集/留白)和视觉重心，而非仅列出区域名称
- 无障碍基线(feasibility): 色彩对比度是否满足WCAG AA标准，交互元素是否有足够的点击目标尺寸

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 REVIEW-{doc_id}，目录 docs/reviews/doc/。

### Step 4: 产出审查报告
产出 `REVIEW-{doc_id}-r{N}.md`，问题格式、category 和 root_cause 枚举按 COMMON-RULES §审查报告规范。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。判定后变更文档状态。

## Layer 1 检查项 (doc_check.py)

通用 (所有文档类型):
- 文档头元数据完整(id, author, status, deps, consumers)
- [NAV]块存在且与实际章节一致 (changelog除外)
- 所有必填章节非空 (按doc_type定义)
- ID编号连续无跳号 (WARN)
- 交叉引用目标文件存在 (FAIL)
- 无未处理TODO/TBD/FIXME (或已标注[ASSUMPTION])
- 文档已注册到NAV-INDEX (WARN)

专项检查:
- **prd**: 用户故事覆盖、验收标准(AC-NNN)存在、非功能需求充实度、优先级(P0/P1/P2)标注
- **arch**: 模块→功能映射(F-NNN引用)、API定义含request、实体含字段表、技术栈选型理由
- **dev-plan**: 依赖无环、tdd_acceptance、deliverables、context_load
- **ui-spec**: §0设计方向非空且非占位符、组件含变体和Props和视觉差异描述、页面含路由和组件引用和空间构成、设计系统token(色彩≥5个Token)
- **test-report**: 测试金字塔(Unit/Integration/E2E)、用例矩阵非空、覆盖率有具体数值、测试执行结果、缺陷清单、结论
- **deploy-spec**: 构建流程非空、环境含dev/prod、发布检查清单≥2项
- **research-note**: 调研方法指明模式、结论非空
- **changelog**: 版本条目存在、每版含Added/Changed/Fixed分类

## 效率策略
- Layer 1先行，失败则不进入Layer 2，节省AI资源
- AI审查通过doc-nav按需加载被审文档和上游依赖
