### BREAKING

- **从属实体改用父限定复合 IRI（KG 快照格式变更）** —— `AcceptanceCriteria`（`AC-NNN`）等从属实体的实例 IRI 由扁平 `instance/AC-001` 改为父限定 `instance/{parent_id}/AC-001`，使同号 AC 在不同 Feature/Task 下成为不同节点而非坍缩。既有 `.nq` 快照与新 IRI 不兼容，下游需重新导入。迁移：

  | 如果你曾依赖 | 改为 |
  |------------|------|
  | 扁平 `instance/AC-001` 实例 IRI | 父限定 `instance/{parent_id}/AC-001`（普通实体 IRI 不变） |
  | 旧 KG `.nq` 快照 | 删除后 `cataforge kg init && cataforge kg import` 重新导入 |
  | 按裸 `entity_id` 查从属实体 | 仍可用（facade 回退到 `cf:entity_id` 字面量解析），但同号多父时取首个匹配 |

### Fixed

- **`cataforge kg import` 不再坍缩跨父 / 跨文档的同号从属实体** —— 从属实体按 `(parent_id, entity_id)` 去重并铸父限定 IRI，dev-plan 各任务卡的局部 `AC-001` 与 prd 各 Feature 的 `AC-001` 各自成节点；`kg reconcile` 按 scope key（普通实体 = `entity_id`，从属实体 = `parent/entity_id`）对账，跨父同号不再永久 divergence。父链经 `cf:part_of` 边记录，对账时排除该结构边。

### Changed

- **实体定义判定收紧为标题锚定** —— 非从属实体仅当 entity-id 是其所属 section 标题的主语（标题首个 entity-id token）才算定义；他处裸提及不再铸节点，仅 xref 提及经 `relation_extract` 成边。消除"提及即定义"导致的虚假跨文档碰撞。

- **KG 读侧 facade 解析从属实体 IRI** —— `query.entity/exists/depends_on` 与 `trace.coverage/from_requirement` 在扁平 IRI 不存在时回退到按 `cf:entity_id` 字面量解析实际节点，使按裸 id 访问 `AC-NNN` 仍可命中父限定节点。
