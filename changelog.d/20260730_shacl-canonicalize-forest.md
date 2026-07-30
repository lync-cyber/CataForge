### Changed

- SHACL codegen 的 blank-node 规范化改用森林结构快路径（`_canonicalize_shacl`），
  在 ShaclGenerator 输出的树状图上以确定性路径+内容标签取代 rdflib `to_canonical_graph`
  的全图同构算法（保留非森林图的 fallback）。单次 codegen 从 ~70s 降到 ~4s，输出与旧版
  图同构且字节稳定；`core_shapes.ttl` 因 blank-node 标签重排而重新生成。
- `tests/kg/test_codegen.py` 改为 in-process 调用 codegen（复用 linkml 冷 import），
  codegen 相关测试从 ~230s 降到 ~17s。
