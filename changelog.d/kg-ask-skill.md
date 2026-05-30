### Added

- **`kg-ask` 知识图谱自然语言查询 skill** —— 把自然语言问题翻译为只读 SPARQL，对项目知识图谱（需求/模块/任务/测试的追溯关系）检索并用中文回答。新增 `cataforge kg schema-context` 子命令输出 schema card（实体类 / 追溯谓词 / 标量 slot / 示例查询，从 ontology 注册表派生，零 store 依赖）；翻译由宿主 agent 据 card 完成，执行与写守卫 / LIMIT 注入复用既有 `cataforge kg query`，无新增运行时依赖。
