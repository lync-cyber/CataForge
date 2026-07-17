### Added

- **SHACL shapes 发布 + 强制门** —— codegen 规范化（`sh:order` 剥离、集合语义 list 排序、canonical 空节点 + 排序 N-Triples）使 `core_shapes.ttl` 字节稳定，从 gitignore 转为提交、`check_codegen_fresh` 守卫、随 wheel 发布；`kg validate` 新增 `--require-shacl`（SHACL 无法运行即失败）与结构化 `shacl_skip_reason`；`doctor` 新增 gating 的 `KG SHACL conformance` 检查（extras 缺失时打印跳过原因，不再有静默跳过路径）。
- **KG 写入门槽守卫** —— `context update` / `kg update` / authoring 事务对枚举域 slot 按 schema 校验（越范围值报错并列出合法值）；`task_status` 更新执行任务状态机（`todo → in_progress ⇄ review → done`，任意态 ↔ `blocked`，`done`/`cancelled` 终态），越迁需显式 `--ack-status-jump`；新增 `tests/context/test_task_lifecycle.py` 覆盖合法链、非法跳变拒绝、终态复活确认与 CLI 表面。
- **schema ↔ 管线 conformance 回归锁** —— `tests/kg/test_shacl_conformance.py` 用真实生成 shapes 校验真实 ingest 管线在两个 golden 工作流变体上的产物，schema 或管线单边演进即失败。

### Fixed

- **Section→从属实体追溯边悬空** —— `contains_entity` 对 AcceptanceCriteria 等从属实体曾指向无数据的扁平 IRI，修订清理逻辑（`_stored_contains`）静默丢失包含关系；现经 store / 事务内 `entity_id` 反查解析到真实（parent-scoped）IRI。
- **AcceptanceCriteria 缺失必填 `acceptance_text`** —— ingest 提取器现从 AC 自身文本切片自动填充，闭合 schema `required: true` 与管线的漂移。
- **`Document` 未声明 `content_hash` 槽** —— reconcile 三向哈希依赖的该槽已入 schema，closed-shape 校验不再拒绝管线产物。
- **tdd-engine 任务收口命令槽位漂移** —— `--slot status=done`（把任务执行态写进 ArtifactStatusEnum 生命周期槽）修正为 `--slot task_status=done`。
- **git 测试对环境全局 gitconfig 不设防** —— `test_git_cmd.py` 屏蔽 user/system git 配置（URL insteadOf 重写代理环境下 ensure-policy 测试误判）。
