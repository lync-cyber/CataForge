# Sprint Review: Sprint {N} — {项目名称}
<!-- id: sprint-review-s{N}-{project}-{ver} | author: reviewer | status: draft -->
<!-- deps: dev-plan-{project}-{ver}, arch-{project}-{ver} | consumers: orchestrator -->

[NAV]
- §1 计划 vs 实际 → 任务完成度、交付物、AC覆盖率
- §2 范围分析 → Gold-plating、Scope Drift、缺失交付物
- §3 质量聚合 → CODE-REVIEW问题模式汇总
- §4 结论 → 判定结果与建议
[/NAV]

## 1. 计划 vs 实际

| 任务ID | 计划交付物 | 实际状态 | 交付物完成度 | AC覆盖率 | 备注 |
|--------|-----------|---------|-------------|---------|------|
| T-{NNN} | {deliverables列表} | done/todo | {N}/{M} | {X}/{Y} | |

## 2. 范围分析

### 2.1 Gold-plating (计划外代码)
{列出不属于任何任务deliverables的新增文件，或无WARN则写"未发现计划外代码"}

### 2.2 Scope Drift (偏离架构契约)
{列出实现与arch接口契约/数据模型不一致的地方，或写"实现与设计一致"}

### 2.3 Missing Deliverables (缺失交付物)
{列出任务卡中声明但未产出的交付物，或写"所有交付物已完成"}

## 3. 质量聚合

### 3.1 CODE-REVIEW问题模式
{聚合Sprint内所有CODE-REVIEW报告，按category分类统计问题数量}

| category | CRITICAL | HIGH | MEDIUM | LOW |
|----------|----------|------|--------|-----|
| {分类} | {数量} | {数量} | {数量} | {数量} |

### 3.2 反复出现的问题
{同一category出现>=2次的问题模式描述}

## 4. 结论

**verdict**: {approved | approved_with_notes | needs_revision}

### 问题列表
{按COMMON-RULES审查报告规范格式列出问题，前缀[SR-{NNN}]}

### 建议
{针对needs_revision标记的具体任务ID和修复建议}
