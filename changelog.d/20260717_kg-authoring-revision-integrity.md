### Fixed

- **`context write-doc` 重复 author 不再丢失变更实体的追溯边** —— `add_relation` 的幂等判断
  改为对账事务后状态：实体整节点 replace 已把出边压入待删集时，同边重新声明会照常补写，
  commit 先删后加净保留；同一事务内重复声明同一条边只入栈一次。此前内容有变更的实体在
  re-author 后其全部既有追溯边被静默删除（幂等重跑一次才自愈）。
- **`context write-narrative` 修订路径同步子实体** —— 重写节文本后按 ingest / write-doc
  同源的提取语义做差异合并：新增实体定义建节点（含 part_of 父链）、变更定义整节点刷新并
  保留既有出边、被删除的定义连同其节点级联清理；contains 集合按提取结果重算。写后对涉及
  实体跑 SHACL 校验，违规时整笔（节 + 实体）补偿回滚。`transact` 的 write_narrative op
  走同一条链路并并入批级补偿。此前修订只改节文本，新增 AC 无实体、变更 AC 不更新，
  KG 与导出视图静默漂移。
- **reconcile 增补「unabsorbed section entities」图内对账维度** —— 对每个 Document 的
  level-2 tile narrative 跑同源实体提取，节文本定义了而全图不存在的 scope key 记入
  `unabsorbed_entities`；graph 模式下计入 `ok` 门禁与 gate_summary，命中且无其他
  remediation 时标 manual。此前该类漂移在三向 hash triage 全绿时完全不可见。
