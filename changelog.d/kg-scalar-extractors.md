### Added

- **Page / Task 标量 slot ingest 抽取器** —— ingest 现从 section 内行内标签（`- Route:` / `- Layout:` / `- Status:`）抽取 `ui_route` / `layout_spec` / `task_status`，填入实体 `extra_slots`；`task_status` 归一化到 `TaskStatusEnum` 并丢弃非法值。此前这些标量从不被 ingest 产出，专用导出模板对应章节对真实 ingest 永远为空。
