### Fixed

- **viz tasks 的 KG 数据源补渲染无依赖任务** —— KG 路径此前只返回 Task 间 depends_on 边，
  没有内部依赖边的项目即使 Task 实体已入图，dashboard tasks tile 与 `viz status` 也报 empty，
  而 `viz tasks --edges`（authoring 附件路径）却能出图。KG 收集器现单独返回 Task id 集合，
  孤立任务以独立节点声明行进入 Graph，dashboard / status / CLI 三条链路同源。
