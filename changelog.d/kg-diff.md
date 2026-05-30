### Added

- **`cataforge kg diff SNAPSHOT_A SNAPSHOT_B`** —— 对两份 `kg snapshot` 产物做实体/关系级语义 diff（added / removed / content-modified 实体 + added / removed 追踪关系），`--json` 输出，差异时退出非零；bootstrap 子类公理不计入。
