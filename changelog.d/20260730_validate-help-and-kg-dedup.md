### Changed

- `kg validate` 与 `context validate` 的 `--help` 各自点明校验对象（前者校验 live KG store
  的 orphan/断裂边，后者校验 `docs/.doc-index.json` 索引完整性），并互相交叉指路，消除同名命令的
  概念混淆。
