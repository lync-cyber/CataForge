---
name: sprint-review
description: "Sprint 完成度审查 — 计划 vs 实际对比、AC 覆盖验证、范围偏移检测 (gold-plating / drift / 缺失)。当一个 Sprint 全部任务卡完成、需要进入下一 Sprint 或发布前的完成度评估时使用此 skill。本 skill 做 Sprint 级聚合：单任务 code-review 由 code-review review 负责，项目级腐化扫描由 code-review scan 负责，文档评审由 doc-review 负责。"
argument-hint: "<sprint_number: 1|2|3...>"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# Sprint完成度审查 (sprint-review)
## 能力边界
- 能做: Sprint交付完成度审查、AC覆盖验证、范围偏移检测(gold-plating/drift/缺失)、质量聚合
- 不做: 修改代码或文档(仅报告问题)、单个任务的code-review(由code-review skill负责)

## 审查档位（standard / lite / merged-review）

| 档位 | 触发 | per-task code-review | 适用 |
|------|------|---------------------|------|
| **standard** | 默认 | 每任务一份 `docs/reviews/code/CODE-REVIEW-T-NNN-*.md` | 大多数 sprint，任务异质（feature / fix / docs / config 混合） |
| **lite** | `SPRINT_REVIEW_MICRO_TASK_COUNT` 触发（详见 COMMON-RULES） | 每任务一份，但 sprint-review 只跑 Layer 1 | 任务数 ≤ 阈值的小型 sprint |
| **merged-review** | dev-plan frontmatter `project_features.merged_review: true` | **跳过** per-task CODE-REVIEW；sprint-review 报告承担 per-task Layer 2 职责 | 任务同质（如同模块批量路由 / 同 adapter 系列），N 个任务的 N 份 CODE-REVIEW 冗余 |

### merged-review 模式行为

启用 `merged_review: true` 后：Layer 1 `code_review_present` 自动短路（缺 CODE-REVIEW 不 FAIL）；单任务 CODE-REVIEW 可省略，亦可按需混合补充。sprint-review 报告**必须**包含 §per-task L2 维度表（structure / error-handling / test-quality / duplication / dead-code / complexity / coupling / security 八列，每任务一行），作为 per-task Layer 2 的等价交付。跨任务模式（重复 helper / 同型 bug）天然进入横截面视角，比 N 份独立 CODE-REVIEW 更易识别。

## 输入规范
- dev-plan 文档路径 (含Sprint任务表)
- Sprint编号 (N)
- 该Sprint所有任务的CODE-REVIEW报告路径 (docs/reviews/code/CODE-REVIEW-T-*.md)
- arch文档 (用于验证接口契约一致性)
- dev-plan 主卷 frontmatter 可选 `project_features` 块（详见 §project_features schema），影响 Layer 1 行为

## 输出规范
- Sprint审查报告 `SPRINT-REVIEW-s{N}-r{M}.md` (问题列表 + 严重等级: CRITICAL/HIGH/MEDIUM/LOW)
- 审查结论: approved/approved_with_notes/needs_revision

## 操作指令: 执行Sprint审查 (review)

### Step 1: Layer 1 — Python脚本结构检查

```
cataforge skill run sprint-review -- {N} \
  --dev-plan docs/dev-plan/ --src-dir src/ \
  --test-dir tests/ --reviews-dir docs/reviews/code/
```

入口必须走 `cataforge skill run`（不得直接 `python .../scripts/*.py`，路径不稳定）；返回码语义见 §Layer 1 调用协议。`--src-dir` 可重复用于 monorepo 缩范围。

可选参数（gold-plating 噪声治理）：

| 参数 | 默认 | 作用 |
|---|---|---|
| `--ignore PAT` / `--ignore-file PATH` | — | 追加 gitignore 风格规则（可重复） |
| `--no-respect-gitignore` | off | 关闭 `git ls-files --exclude-standard` 集成，回落 `os.walk` |
| `--no-default-ignores` | off | 关闭内建忽略（`node_modules/` `dist/` `build/` `.next/` `*.tsbuildinfo` `*.map` `__pycache__/` `.venv/` 等） |
| `--warn-cap N` | 50 | unplanned WARN 超出折叠为 top-dir 摘要；`0` 不折叠 |
| `--unplanned-log PATH` | — | 完整 unplanned 列表落盘（配合 `--warn-cap` 审计） |
| `--format {text,json}` | text | `json`：结构化 issues，供 framework-review / CI 机读 |

### Step 2: Layer 2 — AI语义审查
通过doc-nav加载dev-plan Sprint任务详情、arch接口契约、CODE-REVIEW报告，审查:
- 完成度(completeness): 所有计划交付物是否存在且功能完整，非空壳文件
- AC覆盖(ac-coverage): 每个AC-NNN是否有对应测试且测试逻辑有效（非仅grep匹配）
- 范围偏移(scope-drift): 实现是否偏离arch接口契约、数据模型、模块边界
- Gold-plating(gold-plating): 是否存在计划外的额外功能、接口、文件
- 缺失交付物(missing-deliverable): 任务卡中声明的deliverables是否全部产出
- 质量聚合(quality-summary): 聚合该Sprint所有CODE-REVIEW报告中的MEDIUM/HIGH问题模式

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 SPRINT-REVIEW-s{N}，目录 docs/reviews/sprint/。

### Step 4: 产出审查报告
产出 `SPRINT-REVIEW-s{N}-r{M}.md`，问题前缀使用 `[SR-{NNN}]`，category和root_cause枚举见COMMON-RULES §审查报告规范。

Sprint审查额外category:
| category | 说明 |
|----------|------|
| ac-coverage | AC覆盖不足 |
| scope-drift | 实现偏离设计 |
| gold-plating | 计划外额外功能 |
| missing-deliverable | 缺失交付物 |

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。Sprint needs_revision 标记具体任务 ID 以便重入 TDD。

## Layer 1 检查项 (sprint_check.py)

> 权威清单见 `cataforge.skill.builtins.sprint_review.CHECKS_MANIFEST`（framework-review 自动对账，本段与 manifest 不一致即 FAIL）。anchor 模式：每条 manifest 项必须在本段以 HTML check_id 注释形式出现（见下方各条），反之亦然。

- <!-- check_id: task_status_done --> Sprint任务表中所有任务状态=done
- <!-- check_id: deliverables_exist --> 每个任务的deliverables文件路径全部存在于磁盘
- <!-- check_id: ac_coverage --> 每个任务的tdd_acceptance中AC-NNN在tests/目录下有对应引用
- <!-- check_id: unplanned_files --> 检测计划外文件 (WARN)：src 范围内、未被 `.gitignore` 与默认 ignore 列表 (`node_modules/`, `dist/`, `*.tsbuildinfo` 等) 过滤、且不在任何任务 deliverables 中的文件视为 gold-plating 信号；候选集合默认通过 `git ls-files -co --exclude-standard` 取得，monorepo 友好
- <!-- check_id: code_review_present --> 每个任务有对应的CODE-REVIEW报告(docs/reviews/code/CODE-REVIEW-{task_id}-*.md)

## project_features schema

dev-plan 主卷（非 sprint 分卷）frontmatter 可选 `project_features` 块，按项目特征声明 Layer 1 行为开关。所有键默认关闭（向后兼容；旧项目零迁移）：

```yaml
---
id: dev-plan-{project}
project_features:
  merged_review: true                    # 短路 code_review_present；启用 §合并审查模式
  deliverables_accept_alternation: true  # deliverables 行支持 "A | B" 语法（任一存在即过）
  unplanned_glob_patterns:               # fnmatch 模式列表，匹配的文件不算 gold-plating
    - "**/*.test.ts"
    - "**/*.spec.ts"
    - "**/helpers/*.ts"
    - "**/fixtures/**"
---
```

### 字段说明

| 字段 | 类型 | 默认 | 行为 |
|------|------|------|------|
| `merged_review` | bool | false | true 时 `check_code_reviews` 直接 return；详见 §合并审查模式 |
| `deliverables_accept_alternation` | bool | false | true 时 `check_deliverables` 把 `A \| B` 视为或关系（任一存在即过），同时 `check_unplanned_files` 把两候选都标为 planned（避免 gold-plating 误报） |
| `unplanned_glob_patterns` | list[str] | `[]` | 每条 fnmatch 模式应用于 `check_unplanned_files` 输出；匹配的文件被滤掉。典型用途：项目级测试/fixture/helper 命名约定 |

读取由 `cataforge.skill.builtins.sprint_review.sprint_check.load_project_features()` 完成；优先读非 sprint 分卷（不带 `-sN.md` 后缀）的第一个含 `project_features:` 的文件。

## 效率策略
- Layer 1 先行（脚本结构检查不通过即跳过 AI 审查）；Layer 2 聚焦脚本不可覆盖的行为偏移和质量模式
- 通过 doc-nav 按需加载，不全量读 dev-plan
- **merged-review**：任务同质 sprint 单份 sprint-review 替代 N 份 CODE-REVIEW，跨任务模式更易识别
