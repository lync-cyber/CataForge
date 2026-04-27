---
name: sprint-review
description: "Sprint完成度审查 — 计划vs实际对比、AC覆盖验证、范围偏移检测。"
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

## 输入规范
- dev-plan 文档路径 (含Sprint任务表)
- Sprint编号 (N)
- 该Sprint所有任务的CODE-REVIEW报告路径 (docs/reviews/code/CODE-REVIEW-T-*.md)
- arch文档 (用于验证接口契约一致性)

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

## 效率策略
- Layer 1先行: 脚本快速检查结构性问题，不通过则跳过AI审查
- Layer 2聚焦语义: AI审查专注于脚本无法覆盖的行为偏移和质量模式
- 通过doc-nav按需加载，不全量读取dev-plan
