# context · consistency(跨文档一致性)

对已完成的文档全集(PRD/ARCH/UI-SPEC/DEV-PLAN)交叉校验,检测语义漂移、覆盖缺口、契约矛盾。单文档结构审查由 review 分支负责;本分支专注文档间关系。

## 入口
```bash
cataforge skill run doc-consistency -- <docs_dir> [--scope full|incremental]
```
AC 追踪等关系类检查由框架按当前可用的最高保真后端执行,消除字面 ID 在代码块/注释/跨分卷上的假阳性;结构类检查(NFR 映射、优先级对齐、端点契约、孤立组件)依文档结构。Agent 无需感知后端。

## 校验维度
- **PRD→ARCH**: AC 覆盖追踪、非功能需求映射、优先级一致
- **ARCH→DEV-PLAN**: 接口契约对齐、模块-任务完整映射、实体字段传播
- **PRD→UI-SPEC**(若存在): 功能-页面映射、AC 可视化覆盖
- **PRD→DEV-PLAN**: AC 完整传播到 tdd_acceptance、AC 粒度一致
- **全集**: 孤立模块/组件、跨文档 ID 冲突

## 报告
产出 `docs/reviews/doc/CONSISTENCY-REPORT-r{N}.md`(追踪矩阵 + 问题清单 + stale deps 摘要);exit 0=通过,1=有 CRITICAL/HIGH,2=仅 MEDIUM/LOW。结论 consistent / consistent_with_notes / inconsistent。Layer 2 AI 交叉审查在 Layer 1 报非零且文档规模较大时追加,经 navigate 按需加载文档对。
