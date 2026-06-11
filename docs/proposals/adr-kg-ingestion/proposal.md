# Proposal: decision 文档（ADR）端到端入图

> 来源：下游 Keel 项目 Phase 1 实测反馈（GitHub issue #241 第 2 项）。
> 现状：KG 本体已有 `ArchitectureDecision` 一等类（`ADR` 前缀注册于 `ENTITY_PREFIX_TO_CLASS`，见 `src/cataforge/domain/kg/ingest/iri.py`），但摄入链路对 decision 文档不可达——业务文档裸引用 `ADR-XXXX` 必然触发 doctor 悬挂引用告警，只能 inline-code 化绕过，丢失图谱溯源价值。

## 1. 缺口清单（实证）

| # | 缺口 | 位置 | 后果 |
|---|------|------|------|
| 1 | `DEFAULT_DOC_TYPE_MAP` 无 `decision` doc_type | `src/cataforge/domain/docs/index_ops.py` | `docs/decisions/` 不被 docs 索引识别为类型化文档 |
| 2 | `DEFAULT_KG_ACTIVE_DOC_TYPES` 不含 `decision` | `src/cataforge/domain/kg/_config.py`（= `BUSINESS_DOC_TYPES`） | `kg import` / reconcile / doctor 不扫描 decision 源 |
| 3 | 实体提取无 ADR 标题模式 | `src/cataforge/domain/kg/ingest/entity_extract.py` | ADR 文档标题形如 `# 0002. xxx`，不匹配 `### ADR-NNNN 标题` 的 heading-anchored 定义检测，提取不出实体 |
| 4 | 无 decision 文档模板 | `.cataforge/skills/context/templates/` | 下游各自发明 ADR 格式，提取模式无锚定目标 |

## 2. 方案

按依赖顺序四步，可单 PR 或两 PR（3 为主体）：

1. **doc_type 注册**：`DEFAULT_DOC_TYPE_MAP` 增加 `"decision": "decisions"`；`BUSINESS_DOC_TYPES` 增加 `decision`（联动 `DEFAULT_KG_ACTIVE_DOC_TYPES`）。升级兼容：`_merge_framework_json` 已保留用户 `kg_active_doc_types`，存量项目不受默认值变化影响。
2. **模板**：新增 `templates/utility/decision.md`——frontmatter（id `adr-{NNNN}-{slug}` / doc_type `decision`）+ 首个 `### ADR-NNNN {标题}` 章节承载 status / context / decision / consequences。标题即实体定义锚点，复用现有 heading-anchored 提取，无需新提取模式（优先）。
3. **提取兼容（备选）**：若须兼容社区惯用 `# NNNN. 标题` 裸格式，再在 `entity_extract.py` 增加 decision 文档专属标题模式（`^#\s+(\d{4})\.\s+`→ `ADR-{NNNN}`）。仅在模板路线验证不足时做。
4. **守门联动**：doctor `kg_ingestion_completeness` 对 ADR 前缀的悬挂引用提示文案改为指向本 doc_type 的启用方式（当前已按"非 active doc_type"给 WARN + 指引）。

## 3. 决策记录

- **考虑过的选项**：(a) 模板锚定 + 复用现有提取（推荐）；(b) 提取器加裸格式模式（侵入提取器、每种社区格式都要适配）；(c) 维持 inline-code 豁免现状（丢失 `cf:depends_on` ADR 溯源边，下游已实证为痛点）。
- **选 (a) 的理由**：零提取器改动、与 F/M/API 等既有实体定义机制同构、模板即规范。
- **重新评估条件**：若 ≥2 个下游项目反馈存量 ADR 库迁移到模板格式成本过高，再启用 (b)。

## 4. 验收标准

- `cataforge kg import --doc-type decision` 从模板格式 ADR 文档提取 `ArchitectureDecision` 实体
- PRD 正文裸引用 `ADR-0002`（decision 已 active）时 doctor 不再告警，且 `prd#§N.ADR-0002` xref 产出追溯边
- 回归：decision 未启用的项目行为不变
