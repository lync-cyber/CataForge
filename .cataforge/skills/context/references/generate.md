# context · generate(生成与写入)

取模板结构、authoring 落图、定稿导出。图后端就绪时图谱是事实源,`docs/` 由 `cataforge context finalize` 导出供人审,不直写后端、不 `Write`/`Edit` `docs/` 文件;doc-only 项目无图后端,authoring 命令会提示直接编辑 `docs/`。

## 取模板
查注册表 `Read .cataforge/skills/context/templates/_registry.yaml`,据 `{template_id}` 取 `path` 读模板,得必填章节([NAV] 块)、实体类型与占位符语义。

## authoring 落图
设文档头(`id` 为 slug `[a-z0-9-]`、不含版本号,版本归 `version:` 字段;author/status=draft/deps/consumers)。按内容规模选写入面,引用其他文档条目前检查目标存在:

- 整文档原子写入: `cataforge context write-doc`(stdin 或 `--file` 传含 frontmatter + 章节 + 实体 + 关系的 markdown,单事务落图,校验失败整体回滚)
- 批量 ops: `cataforge context transact`(stdin/`--file` 传 add_entity / add_relation / write_narrative 的 JSON,单事务)
- 单实体增量: `cataforge context write --class {C} --entity-id {ID} --title … [--slot K=V] [--parent {ID}] [--relation {pred}={obj}] [--narrative-stdin]`(仅限不隶属文档的独立实体;文档域实体的修订走 write-narrative / update,写入门对 Document 覆盖范围内的实体拒写指路)
- 单节叙事: `cataforge context write-narrative --doc-id {id} --anchor "{章节}" --narrative …`
- 文档头补丁: `cataforge context write-meta {doc_id} --status … --version …`

> `id` 与文件名只允许 slug;版本号、点号、空格塞进 id 会被 `cataforge context validate` FAIL 并阻塞 doctor/CI。

## 定稿
1. 结构完整性自检(必填章节非空、文档头齐全);不通过则补全 authoring,不继续
2. 持久化导出: 调 `cataforge context finalize` 从图导出 `docs/` 人审视图;人改导出文件后经 `cataforge context ingest` 回流——后端由框架按 `context.mode` 路由,Agent 无需分支
3. 返回导出路径 + 必填章节清单(从 [NAV] 块提取)

## 精简
一个 doc_type 一个逻辑文档(整篇),不拆分为物理分卷。超过 `DOC_SPLIT_THRESHOLD_LINES` 时优先精简内容或拆为多个各自独立 `id` 的逻辑文档,每个逻辑文档各自走定稿导出。

完整模板映射见 `.cataforge/skills/context/templates/_registry.yaml` 与 context 模板目录。
