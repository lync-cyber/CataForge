# context · generate(生成与写入)

模板实例化、章节填充、定稿持久化、超长拆分。持久化由框架按上下文方案路由,Agent 完成填充后只需定稿,不应自行调度后端命令。

## 创建骨架
1. 查注册表 `Read .cataforge/skills/context/templates/_registry.yaml`,据 `{template_id}` 取 `path`,读模板
2. 替换占位符;设文档头(`id` 为 slug `[a-z0-9-]`、不含版本号,版本归 `version:` 字段;author/status=draft/deps/consumers)
3. `Write docs/{doc_type}/{template_id}-{project}.md`
4. 返回目标路径 + 必填章节清单(从 [NAV] 块提取)

> `id` 与文件名只允许 slug;版本号、点号、空格塞进 id 会被 `cataforge docs validate` FAIL 并阻塞 doctor/CI。

## 写入章节
用 `cataforge docs load` 取目标章节定位,`Edit` 写入;引用其他文档条目时检查目标存在。

## 定稿
1. 结构完整性检查(必填章节非空、文档头齐全);不通过则返回缺失项清单,不继续
2. 拆分判断: 超过 `DOC_SPLIT_THRESHOLD_LINES` 按下方拆分
3. 持久化: 调框架定稿命令(`cataforge docs` 定稿面)将最终文档写入权威存储——后端由配置方案决定,Agent 无需感知
4. 返回最终路径 + 持久化确认

## 拆分
超过 `DOC_SPLIT_THRESHOLD_LINES` 时按 doc_type 拆主卷 + 分卷:主卷保留全局概览与交叉引用目录,分卷 YAML Front Matter 含 `volume_type` 与 `split_from`,分卷间按 ID 引用,拆分不改 ID 编号。分卷与主卷同目录 `docs/{doc_type}/`,各自走定稿持久化。

完整模板映射与拆分表见 `.cataforge/skills/context/templates/_registry.yaml` 与 context 模板目录。
