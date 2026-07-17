### Fixed

- **`context write-doc` 重复 author 不再丢失变更实体的追溯边** —— `add_relation` 的幂等判断
  改为对账事务后状态：实体整节点 replace 已把出边压入待删集时，同边重新声明会照常补写，
  commit 先删后加净保留；同一事务内重复声明同一条边只入栈一次。此前内容有变更的实体在
  re-author 后其全部既有追溯边被静默删除（幂等重跑一次才自愈）。
- **`context write-narrative` 修订路径与 write-doc 全同源** —— 重写节文本后按 ingest / write-doc
  同一套提取语义做差异合并：实体维度新增建节点（含 part_of 父链）、变更整节点刷新、被删除的
  定义连同其节点级联清理、contains 集合重算；关系维度对重写域内主体同源重提取——文本声明的
  边建立、不再声明的边清除，自洽的「删实体 + 删依赖行」修订可整体通过。跨 tile 同名 anchor
  的实体归属有歧义，此类 anchor 保守豁免清理不做跨 tile 误删。写后对涉及实体跑 SHACL 校验，
  违规时整笔（节 + 实体 + 边）补偿回滚；`transact` 的 write_narrative op 走同一条链路并并入
  批级补偿。heading 锚定实体的 content hash 忽略尾部空行，两条提取路径对同一内容判同。
  此前修订只改节文本，新增 AC 无实体、变更 AC 不更新，KG 与导出视图静默漂移。
- **reconcile 增补「unabsorbed section entities」图内对账维度** —— 对每个 Document 的
  level-2 tile narrative 跑同源实体提取，节文本定义了而全图不存在的 scope key 记入
  `unabsorbed_entities`；graph 模式下计入 `ok` 门禁与 gate_summary，命中且无其他
  remediation 时标 manual。此前该类漂移在三向 hash triage 全绿时完全不可见。
