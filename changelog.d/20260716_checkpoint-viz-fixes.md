### Fixed

- **post_doc_freeze 检查点覆盖 ui-spec 冻结** —— `MANUAL_REVIEW_CHECKPOINTS` 可选值 `post_doc_freeze` 的触发时机补上 UI-SPEC 冻结（Phase 3→4；ui_design 标 N/A 时该点不存在）。该档位语义是「门禁冻结类文档转换」，此前枚举漏列 ui-spec，UI 项目要在 ui-spec 冻结点暂停只能升到全量 `phase_transition`。**行为变化**：已配 `post_doc_freeze` 且启用 ui_design 的下游项目升级后会在 ui-spec 冻结后多一次确认暂停；默认档位项目不受影响。

### Added

- **人工检查点摘要携带可视化附件** —— Manual Review Checkpoint 命中时，orchestrator 先按转换类型产出匹配视图（`post_doc_freeze` → `viz trace` / `viz arch`；`pre_dev` → `viz tasks`；`post_sprint` / `pre_deploy` → 复用 Sprint 收口 dashboard 产物）并在阶段摘要附产物路径。与 Sprint 收口保底焊点同语义：确定性 CLI、不阻塞推进、数据源未就绪跳过不报错。
- **viz arch 组合层级边与依赖环标注** —— 架构视图新增 `part_of` 组合边（带标签，与 `depends_on` 区分），并对 `depends_on` 子图做环检测：环上节点标 CYCLE（颜色 + 文本标记双通道），直接暴露违反 ARCH DAG 约束的模块划分；`QueryAPI` 新增 `part_of()` 查询。核实报告与决策记录见 `docs/proposals/checkpoint-viz-presentation-audit.md`。
