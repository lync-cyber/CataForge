# ADR: KG 写入门守卫与 SHACL shapes 发布

状态：accepted。审计依据：2026-07 SDLC harness 审查（`docs/proposals/sdlc-harness-audit-2026-07.md`）。

## 问题

三条相互放大的缺口让 KG 的"schema 强约束"停留在文档层：

1. **SHACL 管线三重失效**：`core_shapes.ttl` 因 LinkML ShaclGenerator 输出非确定性被 gitignore，fresh clone / wheel 安装环境下 shapes 恒缺失，`kg validate --shacl` 静默跳过且 exit 0；写入门 `validate()` 调用从未传 `run_shacl=True`；且即使 shapes 存在，真实 ingest 管线产物也不 conform（`Document` 未声明 `content_hash` 槽、`Section --contains_entity-->` 对从属实体（AcceptanceCriteria）指向悬空扁平 IRI、`acceptance_text` 必填但从未填充）——"SHACL 已验证"仅由内联玩具 shapes 的桥接测试背书。
2. **枚举槽零校验**：`update_entity` 不校验槽名与枚举值，任何字符串可写入 `task_status` / `status` / `test_result`；SPARQL 过滤静默失配，下游检查全部读到"未设置"。
3. **prompt ↔ schema 漂移**：tdd-engine SKILL 指示 `--slot status=done`——把 TaskStatusEnum 的值写进 ArtifactStatusEnum 槽位，`task_status` 纹丝不动，且无任何机制发现。

任务状态（`TaskStatusEnum`）只有枚举、没有转换合法性模型：`todo → done` 跳变、终态复活均不可检测。

## 方案比较

**shapes 确定性**：(a) 运行时从 LinkML 现生成（引入 linkml 运行时重依赖，弃）；(b) 提交非确定产物并豁免 freshness 守卫（守卫失义，弃）；(c，选定) codegen 后规范化——`sh:order`（SHACL 非校验性展示属性）剥离 + `sh:ignoredProperties`/`sh:in` 集合语义 list 排序 + `rdflib.compare.to_canonical_graph` 规范空节点标签 + 排序 N-Triples 输出（Turtle 子集，下游解析面不变）。两次生成字节相同（`tests/kg/test_codegen.py::test_shacl_shapes_byte_identical_on_rerun`），从而可提交、受 `check_codegen_fresh` 守卫、随 wheel 发布。

**SHACL 执法面**：写入门全量 SHACL（每写一次全图桥接 + pyshacl，实测约 40ms/次 + shapes 解析 218ms，authoring 密集测试与批量事务下延迟放大、且爆炸半径未知）对比选定的三面组合——`kg validate --require-shacl`（CI 强制门，跳过即失败）+ doctor `KG SHACL conformance` gating 检查（extras 存在时全量跑，缺失时打印跳过原因，绝不静默）+ golden fixture conformance 回归测试（真实 shapes × 真实管线，schema↔管线对齐从此被 CI 锁死）。写入门保留 orphan/xref 校验 + 新增确定性槽守卫，覆盖最高频腐化类（枚举越范围、状态跳变）且零延迟负担。写入门全量 SHACL 留作后续可选项（配置开关），不在本 ADR 落地。

**枚举事实源**：手维护枚举表（第三份拷贝，必漂移，弃）对比选定的生成物内省——`slot_guard.enum_values_for` 从 `_generated/core_pydantic.py` 的字段类型注解提取枚举全集（单一事实源 `schemas/core.yaml` 经 codegen），codegen 缺失时守卫降级为 no-op（有 `TASK_STATUS_TRANSITIONS` 键集兜底 ingest 提取器）。

## 决策

1. `core_shapes.ttl` 规范化生成、提交、守卫、随 wheel 发布；`kg validate` 增 `--require-shacl` 与结构化 `shacl_skip_reason`；doctor 增 gating 的 `KG SHACL conformance` 检查。
2. 修复三处 schema↔管线漂移：`Document` 声明 `content_hash`；`contains_entity` 经 store/事务内 `entity_id` 反查解析到从属 IRI（兼修 `_stored_contains` 对从属实体静默丢边）；`AcceptanceCriteria` ingest 提取器自动填充 `acceptance_text`。
3. 事务层写入门（`add_entity` / `update_entity`）执行枚举槽校验；`task_status` 更新执行状态机 `TASK_STATUS_TRANSITIONS`（`todo → in_progress ⇄ review → done`，任意态 ↔ `blocked`，`done`/`cancelled` 终态），越迁经 `--ack-status-jump` 显式确认（与 `phase transition` 的 `--ack-*` 决策模式同族）。创建时任意枚举成员合法（bulk ingest / authoring 从文档回填历史状态）；存量非法值任意改出即修复。
4. tdd-engine SKILL 的任务收口命令修正为 `--slot task_status=done`。

## 后果

- 下游安装 `shacl` extra 后，`doctor` 开始对存量 store 执行 shapes 校验；历史 store 若有存量违规会显性暴露（修复路径：re-ingest 或 `kg repair`）。这是把既有腐化从不可见变为可见，属预期。
- `context update` / `kg update` 对枚举槽的非法值从静默写入变为 exit 1——依赖旧行为写入非枚举词汇（如 PriorityEnum 之外的 `P0`）的调用方会失败并得到合法值列表。PRD 模板 P0/P1/P2 词汇与 `PriorityEnum`（critical/high/medium/low）的双轨漂移记入 backlog，本 ADR 不改枚举定义。
- 层级归属：枚举/状态机守卫位于 domain 层事务门（T0 Kernel 级不变量——所有平台、所有模式共享）；SHACL 执法面位于 CLI/doctor（T3 Gate 层）；prompt 资产修正位于 skill（T1）。
