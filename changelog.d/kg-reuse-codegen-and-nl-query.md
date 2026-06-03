### Added

- **自然语言 → SPARQL 只读查询面** —— `cataforge.domain.kg.nl_query` 新增 `translate()` / `query()` / `answer()`：用调用方注入的、仅需暴露 `.invoke(prompt)` 的 LLM（不引入任何 LLM 框架依赖）把自然语言问题翻译成 SPARQL，经 SELECT/ASK 白名单门控（`read_query.assert_read_only`）后走现有只读路径执行，杜绝幻觉写操作落库；`answer()` 复用 `query()` 取数后再一次 `.invoke()` 把结果行转述为自然语言，同样受只读门控保护。
- **LinkML 生成的 Pydantic 模型可作运行时类型视图** —— `cataforge.domain.kg.models.to_model()` 把 `QueryAPI` 的标量 dict 提升为生成的 Pydantic 模型（`model_construct` 标量视图），生成产物缺失时优雅返回 `None`。生成的 `*_pydantic.py` + `subclass_axioms.ttl` 现纳入版本控制并随 wheel 分发，新增 `check_codegen_fresh` 守卫保证它们与 `schemas/*.yaml` 始终同步。

### Changed

- **`cataforge kg query` 的 SPARQL 只读策略下沉到 `domain/kg/read_query`** —— 写操作白名单与 `LIMIT` 注入提取为共享原语，CLI 与新的 NL 查询面共用同一套 SELECT/ASK 策略，不再各自实现。
- **SHACL 桥接改用序列化往返** —— `validate` 的 pyoxigraph→rdflib 桥接改为 `store.dump` + `rdflib.parse`，由两个 spec 实现负责 term 边界，移除手写的逐类型 term 映射。
