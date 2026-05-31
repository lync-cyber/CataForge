# CataForge 实现审查报告

## 执行摘要

本轮对抗性审查共确认 **26 条 findings**，覆盖 interface/cli（Click 命令层）、domain/kg（知识图谱）、runtime（hook/mcp/deploy）、.cataforge/ 元资产一致性、Python 引擎 ↔ .cataforge 契约、以及框架自审元工具盲区六大子系统。

**Severity 分布**：CRITICAL 0 · HIGH 6 · MEDIUM 14 · LOW 6。

每条 finding 均经第二轮证据复核，其中 5 条原始 severity 被对抗性下调（HIGH→MEDIUM 或 MEDIUM→LOW），3 条描述细节被纠偏后仍维持主体成立，无凑数项。

**最值得优先的 5 项**（均为 HIGH，且影响面跨越「守卫静默失效」与「dogfood 环境当前已漂移」两类即时风险）：

1. **[R-006] SparqlRegistry.has() 永远返回 True** — KG 渲染层的早退守卫彻底失效，未知 entity_type 不再被拦截，是纯死代码且无任何机制缓解。
2. **[R-012] framework.json 迁移检查指向已废弃路径 + allow_missing:true** — session_context.py 行为约束守卫结构性空转，任何回归向该文件引入禁用模式都会无声通过 CI。
3. **[R-013] framework.json 常量表与 COMMON-RULES SSOT 漂移：8 个常量未收录** — 自称 SSOT 的表缺 8 个常量定义，其中 5 个已有真实调用方，常量名可发现性断裂。
4. **[R-018] Dogfood deploy drift** — `.claude/skills/` 当前活跃 4 个已删除的 doc-* skill，且统一替代品 `context` 与 `framework-walkthrough` 未部署，dogfood LLM 正运行在陈旧 skill 集上。
5. **[R-022] / [R-024] framework-review B3 自审盲区** — testing skill 公开承诺「B3 自动对账，不一致即 FAIL」但 builtin_map 中根本无 testing；doc-review 的 18 条 CHECKS_MANIFEST 因 source SKILL.md 缺失被 B3 静默跳过。最常用质量门禁的 manifest 可与部署 SKILL.md 无声漂移而永不被检出。

一条共性观察：HIGH 级问题中 4 条同属「守卫/承诺存在但执行层缺席」——死守卫（R-006/R-012）、SSOT 自称但不可查（R-013）、自审工具承诺但未实现（R-022/R-024）。元工具盲区子系统（R-021~R-026）系统性揭示 framework-review 与 doctor 对 migration_checks 路径完整性、builtin-only skill manifest 对账、常量值同步三个维度的结构性失明。

---

## HIGH

### [R-006] HIGH: SparqlRegistry.has() 永远返回 True，render_entity 守卫失效
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: `src/cataforge/domain/kg/export/registry.py:40-42` 中 `SparqlRegistry.has(entity_type)` 的实现是 `return GENERIC_SPARQL_KEY in self._templates`，完全忽略传入的 `entity_type` 参数。构造函数（registry.py:27-31）已强制校验 `_artifact.sparql` 存在（否则 raise KeyError），因此构造成功后 has() 对任何输入恒返回 True。`render.py:80` 用 `if not registry.has(entity_type): return None` 作为防护门禁，但该门禁永远不会触发，使 render_entity 失去对未知 entity_type 的早退语义，掩盖配置错误。无任何测试或机制缓解。
- **建议**: 将 has() 改为 `return entity_type.lower() in self._templates or GENERIC_SPARQL_KEY in self._templates`，与 get() 的回落逻辑保持一致；或删除 has() 调用改为直接 try/get 并在 None context 返回 None。单点改动。

### [R-012] HIGH: framework.json 迁移检查 mc-0.1.5-session-context-simplified 指向已废弃路径，allow_missing:true 使其永久静默通过
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: `.cataforge/framework.json:244-252` 中迁移检查 `mc-0.1.5-session-context-simplified` 的 `path` 字段指向 `src/cataforge/hook/scripts/session_context.py`，该文件在分层重构后已迁移到 `src/cataforge/runtime/hook/scripts/session_context.py`。旧路径在重构后的仓库中不存在，`allow_missing:true` 让检查永远通过，导致本应保护 session_context.py 行为约束（禁用 `_detect_pkg_env` / `additionalContext` / `deploy`）的守卫彻底失效。任何向该文件引入这些模式的提交都会无声通过 CI。当前真实文件确认存在且干净，故无活跃回归，但守卫结构性空转。
- **建议**: 将 path 更新为 `src/cataforge/runtime/hook/scripts/session_context.py`；同时评估 `allow_missing` 是否仍需要（dogfood editable install 下文件存在，可移除该豁免）。注意 `deprecate_after: 0.2.0` 已过期（当前 0.6.0），另一条 finding [R-020] 主张直接删除该 check——二者择一收敛即可。单点改动。

### [R-013] HIGH: framework.json 常量表与 COMMON-RULES §框架配置常量 SSOT 漂移：8 个常量未收录
- **category**: consistency
- **root_cause**: self-caused
- **描述**: COMMON-RULES §框架配置常量表（`.cataforge/rules/COMMON-RULES.md:24-44`，列 15 个常量）自称「框架级参数的单一事实来源」并要求「禁止硬编码同一数值，应直接引用常量名」。但 `.cataforge/framework.json:49-88`（共 23 个条目）中有 8 个常量未在该表定义：`AGENT_MODEL_DEFAULTS`、`AGENT_MODEL_TIER_HEAVY_WHITELIST`、`ANTI_PATTERN_MIN_COUNT_SKILL`、`ANTI_PATTERN_MIN_COUNT_AGENT`、`EVENT_LOG_DRIFT_MIN_EVENTS`、`PRE_DEPLOY_DEMO_REQUIRED`、`PRE_DEPLOY_DEMO_MIN_ACS`、`SKILL_RUNNER_TIMEOUT_DEFAULT_SECS`。其中 5 个已有真实调用方：`framework-review/SKILL.md:25` 引用 `AGENT_MODEL_DEFAULTS` + `AGENT_MODEL_TIER_HEAVY_WHITELIST`，`SKILL.md:57` 引用 `EVENT_LOG_DRIFT_MIN_EVENTS`，`workflow-framework-generator/SKILL.md:412` 引用 `ANTI_PATTERN_MIN_COUNT_SKILL/AGENT`，runner.py docstring 引用 `SKILL_RUNNER_TIMEOUT_DEFAULT_SECS`。Agent/Skill 作者无法通过 COMMON-RULES 索引到这些常量，只能直接读 framework.json，可发现性断裂。
- **建议**: 将 8 个常量补入 COMMON-RULES §框架配置常量表，格式与已有条目一致（常量名 | 值 | 说明 | 引用方）。`PRE_DEPLOY_DEMO_REQUIRED/MIN_ACS` 若确认是死常量（见 [R-014]）则同步从 framework.json 删除而非补入。

### [R-018] HIGH: Dogfood deploy drift — 4 个陈旧 skill 目录仍活跃，2 个新 skill 未部署
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `.claude/skills/` 当前暴露 4 个在 `.cataforge/skills/` source 中已不存在的目录（`doc-gen`、`doc-nav`、`doc-review`、`doc-consistency`），同时缺失 source 中存在的 2 个目录（`context`、`framework-walkthrough`，二者 frontmatter 均为 `maintainer-only: false`）。`.cataforge/.deploy-manifest.json` 的 `owned_paths` 列出全部 4 个陈旧 skill 路径。Claude Code 读取已部署的 `.claude/skills/` 状态，故活跃 LLM skill 集陈旧：统一替代品 `context`（吸收了四个旧 doc-* skill）对 Claude Code 不可见，而四个被取代的 skill 仍活跃。prune 逻辑 `src/cataforge/adapter/platform/_deploy_mixins/skills.py:92-108` 会在下次 deploy 自愈，但当前 dogfood 环境确已在陈旧 skill 集上运行。
- **建议**: 在 dogfood 仓运行 `cataforge deploy --platform claude-code`。skills.py:96-108 的 prune 逻辑会移除 4 个陈旧目录（在 prior_manifest 中且不在 source_names 中）并添加 context + framework-walkthrough。无需改代码，缺口纯粹是 rename 后缺一次 deploy 调用。

### [R-022] HIGH: testing SKILL.md 声称 framework-review B3 自动对账但实现中完全缺席
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `.cataforge/skills/testing/SKILL.md:84` 对用户和 LLM 公开承诺「权威清单见 CHECKS_MANIFEST（framework-review 自动对账，本段与 manifest 不一致即 FAIL）」，但 `src/cataforge/runtime/skill/builtins/framework_review/checks/b3.py:73-78` 的 `builtin_map` 仅含 code-review / doc-review / sprint-review / framework-review，testing 完全缺失。testing builtin（`builtins/testing/__init__.py:12`）确有 CHECKS_MANIFEST（2 条目：e2e_backdoor_scan、e2e_real_input_presence）。实跑 `framework-review skills` 返回 0 FAIL，testing CHECKS_MANIFEST 未参与校验。这意味着 testing 的 Layer 1 检查项段可与 builtin 实现无声漂移而永不被检出——正是 B3 被设计来防止的腐化场景，用户可见承诺「不一致即 FAIL」categorically false。补充：testing SKILL.md 用 delegation marker（非 anchor 模式），即使加入 builtin_map，B3 也只会校验 CHECKS_MANIFEST 存在性，不做逐条 prose 对比。
- **建议**: 将 testing 加入 b3.py 的 builtin_map：`{'testing': 'cataforge.runtime.skill.builtins.testing'}`。单点改动（b3.py:73-78），delegation 模式走快路径，确认 manifest 存在即可。

### [R-024] HIGH: doc-review builtin 的 18 条 CHECKS_MANIFEST 因 source SKILL.md 缺失被 B3 静默跳过
- **category**: completeness
- **root_cause**: self-caused
- **描述**: B3-α 从 `.cataforge/skills/<id>/SKILL.md` 读取 Layer 1 检查项段进行对账（`b3.py:81-83`：`skill_md = ProjectPaths(root).skill_dir(skill_id) / 'SKILL.md'; if not skill_md.is_file(): continue`）。doc-review 的 source SKILL.md 已整体迁入 Python 包（`builtins/doc_review/`，CHECKS_MANIFEST 含 18 条目），`.cataforge/skills/doc-review/` 目录不存在，导致 b3.py 在 `is_file()` 为 False 时直接 continue——18 条 CHECKS_MANIFEST 条目永远不会被 B3 校验。LLM 可读到 `.claude/skills/doc-review/SKILL.md`（上次 deploy 产物）但 B3 看不到它。doc-review 是主要质量门禁，其 manifest 可与部署 SKILL.md 漂移而无任何自动检测。
- **建议**: B3 需感知 builtin-only 技能：当 `.cataforge/skills/<id>/SKILL.md` 不存在时，尝试从 Python 包内 SKILL.md（`importlib.resources.files(module) / 'SKILL.md'`）取文档对账；或在 `.cataforge/skills/doc-review/` 保留一份 SKILL.md 作为 data-driven 覆盖层。涉及 b3.py 的 check_b3_manifest_drift，新增 fallback 路径查找分支。

---

## MEDIUM

### [R-001] MEDIUM: context_cmd.py 用 raw SystemExit 绕过 CataforgeGroup 错误处理器
- **category**: error-handling
- **root_cause**: self-caused
- **描述**: `context_cmd.py:120`（finalize 出错时 `raise SystemExit(2)`）和 `context_cmd.py:148`（reconcile 漂移时 `raise SystemExit(3)`）直接抛 SystemExit 而非走 CataforgeError + err.exit_code 路径。`errors.py:22-28` 的 `CataforgeGroup.invoke` 只 catch CataforgeError，不 catch SystemExit，导致：stderr 不显示统一的 'Error: …' banner；退出码 2 与项目约定（2 = Click usage error）冲突，finalize 的逻辑错误本应为 exit 1;与同子系统其他命令（docs_cmd / hook_cmd / skill_cmd 均转为 CataforgeError）行为不一致。注：`context_cmd.py:57` 的 `raise SystemExit(read_main(argv))` 是委托给 sub-CLI 入口的标准模式，保留 sub-CLI 退出码，属有意为之，不计入缺陷。
- **建议**: 将 line 120 / 148 两处 `raise SystemExit(N)` 替换为 `CataforgeError(...); err.exit_code = N; raise err` 模式，与 docs_cmd.py 的 _raise_on_nonzero 对齐；finalize 出错码由 2 改为 1。单点改动，仅涉及 context_cmd.py。

### [R-002] MEDIUM: kg/ 子命令 --db-path 选项内联重复，exists= 约束不一致
- **category**: duplication
- **root_cause**: self-caused
- **描述**: `--db-path` 选项在 kg/ 四个文件内联重复了相同的 `type=click.Path(..., path_type=Path), default=KG_STORE_REL, show_default=True` 模板（ingest.py、store.py、write.py、query.py），且 `exists=` 约束在同类操作间不统一：`kg_validate`（只读）有 exists=True，而 `kg_query`、`kg_trace`（同为只读）没有——语义相似的读操作约束分歧。若将来修改 KG_STORE_REL 默认值或 path_type，需在多处同步。
- **建议**: 在 kg/__init__.py 或新建 kg/_options.py 中定义工厂函数 `_db_path_option(exists=False)` 和 `_db_path_rw_option()`，按「命令是否要求 store 已存在」区分 exists=，统一应用到各子命令。涉及 4 个文件，重构成本明确。

### [R-003] MEDIUM: check_docs_validate 与 docs_validate 渲染逻辑重复且已发生语义漂移
- **category**: duplication
- **root_cause**: self-caused
- **描述**: `doctor/skill_health.py:58-199` 的 `check_docs_validate`（约 142 行）与 `docs_cmd.py:118-252` 的 `docs_validate`（约 135 行）各自独立渲染 validate_docs 结果。`check_docs_validate` 的 docstring（line 60-63）声称两者共享 validate_docs 使「新检查器自动流入两条门禁」，但该声明 false：`docs_cmd.py:159` 读 `stale_deps = result.get('stale_deps', [])` 并有完整渲染块（170-184、233-244），而 skill_health.py 的 check_docs_validate（97-102）完全不读 stale_deps。结果是 stale_deps 告警只出现在 `cataforge docs validate` 而非 `cataforge doctor` 报告中——真实行为分歧。约 250 行等价输出散布两文件，每次给 validate_docs 加新返回键都需同步两处。另：skill_health.py:192-193 嵌入中文用户提示而 docs_cmd 用英文，属次要风格不一致。
- **建议**: 将渲染逻辑提取为 domain.docs.indexer 或单独模块中的 `format_validation_result(result)` 函数，doctor 和 docs_validate 均调用同一函数，消除重复并自动对齐。多文件重构。

### [R-007] MEDIUM: repair() 直接操作裸 store 而非 TransactionContext，故障中途不可回滚
- **category**: error-handling
- **root_cause**: self-caused
- **描述**: `domain/kg/repair.py:103-132` 的 `_remove_entity_quads` / `_remove_relation_quad` 直接在裸 pyoxigraph.Store 上 `store.remove()`，`_reingest_doc_type → write_entities → _atomic_replace_entity`（142-154）同样操作裸 store，与同仓 TransactionContext（两阶段 staged-adds/removes + commit/rollback）不一致。若 reingest 阶段抛异常，代码经 `_restore_ghosts()` 回滚，但其内部用 `contextlib.suppress(Exception)` 静默忽略所有添加错误，且 `stats.ghosts_removed` 被提前错误计数后再减。结果是 ghost 已删、missing 未补的混合状态。修正描述一处过度声称：`_restore_ghosts` 实际已接收 `ghost_relation_snapshots`（line 132），并非「不覆盖」；且 repair() 本身幂等可重跑——故主体成立但 severity 由 HIGH 降为 MEDIUM。
- **建议**: repair() 中每个 per-doc_type 的 ghost 删除 + reingest 统一包装在 `with TransactionContext(store, config)` 中执行，利用已有原子提交/回滚语义代替手写 _restore_ghosts。

### [R-008] MEDIUM: KGConfig 中 query_timeout / max_transaction_retries 字段被读取但从未被任何执行路径使用
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: `domain/kg/_config.py:48-49` 声明 `query_timeout: float | None = 30.0` 和 `max_transaction_retries: int = 3`，`_dispatch.py:112-115` 从 framework.json 读入并传给 KGConfig 构造函数，但全仓 Grep 确认 _ask.py / query.py / trace.py / transaction.py / facade.py 中无任何一处读取这两个字段施加超时或重试。它们是公开配置接口上的无效承诺：用户在 framework.json 调整这两个参数行为不会有任何变化。
- **建议**: 二选一：(A) 在 `_ask.ask()` 和 `TransactionContext.commit()` 中实际使用 query_timeout（pyoxigraph Store.query 无原生超时，可用 threading.Timer / concurrent.futures 包装）和 max_transaction_retries（在 facade.transaction() 循环重试）；(B) 从 KGConfig 和 _dispatch.py 删除这两个字段，CHANGELOG 标 breaking change。

### [R-009] MEDIUM: export/_entity_meta 中 4 个已知 ingest 类型未映射 doc_type，export 时静默落入 misc/ 目录
- **category**: consistency
- **root_cause**: self-caused
- **描述**: ingest 管道 `ingest/iri.py:22-58` 的 `ENTITY_PREFIX_TO_CLASS` 注册了 ChangeRequest(CHG)、ReviewReport(REV)、SprintReviewIssue(SR)、Phase 四个类，但 `export/_entity_meta.py:14-46` 的 `_ENTITY_TYPE_TO_DOC_TYPE` 缺少这四类映射（Python 运行时验证集合差为 `['ChangeRequest', 'Phase', 'ReviewReport', 'SprintReviewIssue']`）。`compile_to_markdown` 遇到这些实体时 `_entity_type_to_doc_type()` 返回 'misc'，文件写到 `output_dir/misc/{entity_id}.md`，不符合任何 KG-active doc_type 路径，reconcile/diff 对这些路径的 drift 检测失效。
- **建议**: 在 `_ENTITY_TYPE_TO_DOC_TYPE` 为这四类补充合适 doc_type 映射（ChangeRequest→prd 或 arch，ReviewReport→review，SprintReviewIssue→dev-plan，Phase→arch），同时在 SparqlRegistry 和 templates 目录添加对应 `.sparql` 和 `.md.j2` 文件或确认 generic fallback 覆盖满足需求。

### [R-014] MEDIUM: PRE_DEPLOY_DEMO_REQUIRED / PRE_DEPLOY_DEMO_MIN_ACS：声明于 framework.json 但零实现、零调用方
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: `.cataforge/framework.json:67-68` 的 `PRE_DEPLOY_DEMO_REQUIRED`（值 null）和 `PRE_DEPLOY_DEMO_MIN_ACS`（值 1）在 src/**/*.py、.cataforge/**/*.md、.cataforge/**/*.yaml 全量 grep 中无任何引用——仅命中 framework.json 定义本身、CHANGELOG.md:498（仅记录「新增」无后续实现提交）、调研文档（非调用点）。这两个常量声明了「pre_deploy 阶段 demo 演示门禁」语义，但读取代码和 SKILL/AGENT 消费逻辑从未实现，null 默认值意味着即使有代码读它功能也是关闭的。属于「已注册常量名但从未实现对应逻辑」的 dead configuration entry。
- **建议**: 若 pre_deploy demo 功能仍在计划中，需在 orchestrator Manual Review Checkpoint 或 ORCHESTRATOR-PROTOCOLS.md 添加读取逻辑;若功能取消，直接从 framework.json#/constants 删除这两个常量，并同步从 COMMON-RULES 表（一旦补入后，见 [R-013]）删除。

### [R-015] MEDIUM: runner.py 文档声称读 SKILL_RUNNER_TIMEOUT_DEFAULT_SECS，但实际硬编码 300
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `runtime/skill/runner.py:61` 的 docstring 写「Defaults to SKILL_RUNNER_TIMEOUT_DEFAULT_SECS from framework constants (300 s)」，但 runner.py:97 `effective_timeout = _DEFAULT_TIMEOUT_SECS`，而 `_DEFAULT_TIMEOUT_SECS = 300` 是模块级常量（line 19），从不读取 framework.json（runner.py 内 imports 无 config/framework loader，全文 grep framework/constants/config 只命中 docstring 那一行）。结果：下游项目通过 framework.json 修改 `SKILL_RUNNER_TIMEOUT_DEFAULT_SECS` 不会生效；docstring 契约与实现不一致。违反 COMMON-RULES「应直接引用常量名」。
- **建议**: 在 SkillRunner.__init__ 中通过 ConfigManager 加载 framework.json 的 `constants.SKILL_RUNNER_TIMEOUT_DEFAULT_SECS` 赋给实例属性，run() 在 timeout=None 时使用该属性；若不打算支持覆盖，则将 docstring 改为「defaults to 300 s」并考虑从 framework.json 删除该常量。涉多文件但单方向改动。

### [R-016] MEDIUM: 活跃 migration_checks 描述中遗留 doc-gen（已更名为 context）stale 引用
- **category**: convention
- **root_cause**: self-caused
- **描述**: commit 90be4fd 将 `.cataforge/skills/doc-gen/` 全量重命名为 `.cataforge/skills/context/`（D doc-gen/SKILL.md + A context/SKILL.md），agents/ 和 skills/ 目录内 doc-gen 引用已清理（grep 0 匹配）。但 framework.json 两条无 `deprecate_after`（永久活跃）的 migration_check 描述仍用旧名：`framework.json:325` 的 mc-0.1.10-event-logger-shim 描述「orchestrator/tdd-engine/doc-gen 等十几处」;`framework.json:333` 的 mc-0.5.0-kg-config 描述「doc-gen finalize / cataforge docs load / orchestrator Phase Transition」。这两条 description 出现在 `cataforge doctor` 输出中，向用户展示不存在的 skill 名，违反 COMMON-RULES「直接覆盖陈述当前状态」。
- **建议**: 将两条 description 中 doc-gen 替换为 context。mc-0.1.10 改为「orchestrator/tdd-engine/context 等十几处」;mc-0.5.0 改为「context generate/finalize / cataforge docs load / orchestrator Phase Transition 都按此分流」。单点改动。

### [R-019] MEDIUM: PermissionMode enum 是死代码 — 从未被导入，且与 profile camelCase 值不一致
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `core/types.py:160-174` 声明 `PermissionMode` enum（snake_case 值：`accept_edits`、`dont_ask`、`bypass`）作为平台无关 SSOT，但全 src/ 与 tests/ 中从未被导入（grep 仅命中 types.py:160 定义处）。同时 `claude-code/profile.yaml:134` 声明原生 camelCase 字符串（`acceptEdits`、`dontAsk`、`bypassPermissions`），与 enum 值不匹配。conformance checker（`conformance.py:83-85` 的 check_extended_conformance）只检查 `if not modes:`（modes 非空），从不交叉校验值与 enum。enum 与 profile.yaml 互相矛盾且无一方强制另一方。docstring 声称「platform-agnostic SSOT」但无任何 consumer。因无运行时行为依赖该 enum（从不被求值），无正确性破坏，severity 为 MEDIUM 而非 HIGH。
- **建议**: 二选一：(a) 让 enum 值匹配平台原生字符串并新增 conformance 校验 `set(modes) <= {m.value for m in PermissionMode}`——但这破坏平台无关 SSOT 意图；(b) 删除 enum（单点声明无任何 consumer，无强制价值），将合法 mode 集内联文档化到各 profile.yaml。Option (b) 成本更低。

### [R-020] MEDIUM: Migration check mc-0.1.5-session-context-simplified 经错误路径 + allow_missing 永久旁路
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: 与 [R-012] 同源，从 deprecate 角度补充。`.cataforge/framework.json` 的 mc-0.1.5-session-context-simplified 引用 `src/cataforge/hook/scripts/session_context.py`（runtime/ 重构后已不存在，真实文件在 `src/cataforge/runtime/hook/scripts/session_context.py`）。配合 `allow_missing: true`，`migration.py:149-150` 在文件不存在时返回 `(True, '')`——守卫永远静默通过，从不校验真实文件是否含禁用模式。`deprecate_after: 0.2.0` 也已过期（当前 0.6.0）。真实文件已确认干净（无禁用模式），故无活跃回归，但守卫结构性失效。
- **建议**: 直接从 framework.json 删除此 migration check——`deprecate_after: 0.2.0` 已过期、禁用模式已确认从真实文件清除、`allow_missing:true` 使其结构上不可强制。删除是单点改动无副作用。若意图是在当前路径加新守卫，应另建一条 path 正确且 `allow_missing: false` 的 migration check。注：本条与 [R-012] 互斥收敛——「改 path」或「删除」择一即可。

### [R-021] MEDIUM: migration_checks 路径完整性从未被任何检查器审查
- **category**: completeness
- **root_cause**: self-caused
- **描述**: framework.json 的 migration_checks 是框架 scaffold/runtime 契约的执行层，但当前工具链对该数组内容完全不做结构审查：路径是否实际存在、allow_missing 是否被滥用于掩盖路径漂移、deprecate_after 是否在 check 真正完成使命前提前退休——三维度全盲。证据：`migration.py:148-155` 在 allow_missing=true 且文件不存在时直接返回 `(True, '')` 不报错;`framework_review/checks/` 下 b1.py~b8.py 无任何函数引用 migration_checks（实跑 `framework-review all` → 0 FAIL 0 WARN）;`doctor` 对 mc-0.1.5 输出 `SKIP …: deprecated since 0.2.0`，deprecate_after 掩盖了路径错误这一设计缺陷。该结构性缺口对全部 migration checks 持续存在。原始 HIGH 下调为 MEDIUM：具体的 mc-0.1.5 已 deprecated 且 skip、无活跃执行的 check 在错误路径上静默通过，未来风险局限于新 migration check 被错误撰写。
- **建议**: 在 framework-review 新增 B9 子检查（或扩展 B5）：遍历 migration_checks[*]，对 `file_must_not_contain` + `allow_missing:true` 的条目校验 path 是否实际存在于 editable install 路径（src/ 下）；路径既不存在又无 deprecate_after → FAIL（死守卫）。建议新增 `framework_review/checks/b9.py`，检查：(1) path 存在性 vs allow_missing 合理性;(2) deprecate_after 到期前 path 是否已正确;(3) 已 deprecate 但 path 从未有效的条目 → 安全删除提示。

### [R-023] MEDIUM: deploy drift — .claude/skills/ 中有 manifest 记录但 source 已消失的陈旧目录，doctor 无法在 deploy 前检出
- **category**: completeness
- **root_cause**: self-caused
- **描述**: doctor 的 `deploy_integrity.py:76-88` 只检查已部署路径是否 dangle/missing，不检查 manifested 路径是否还有 source 与之对应。`.deploy-manifest.json` 的 owned_paths 含 `.claude/skills/doc-consistency/doc-gen/doc-nav/doc-review`，但 `.cataforge/skills/` 中这四个目录均不存在（source 迁入 Python builtins），而 `.claude/skills/doc-gen/SKILL.md` 等实体文件真实存在（旧版内容）。实跑 `cataforge doctor` → 「Deploy integrity: 5 owned path(s) verified」通过，未报任何 stale。在下次 `cataforge deploy` 前，LLM 会持续读到陈旧 SKILL.md（内容可能与当前 builtins 实现不同步），形成文档与行为隐性分歧。注：doctor 的 `_OWNED_DIRS_BY_PLATFORM` 仅做目录级检查，且 doctor 根本不读 .deploy-manifest.json。本条与 [R-018] 互为表里：R-018 是 dogfood 状态本身漂移，R-023 是 doctor 缺乏检出该漂移的能力。
- **建议**: 在 doctor 的 check_deploy_integrity 增加逆向检查：对 owned_paths 中每个 `.claude/skills/<name>` 条目，验证 `.cataforge/skills/<name>/` 或对应 Python builtin 仍存在;不存在则 WARN（非 FAIL，因 deploy 可自愈）并提示运行 `cataforge deploy`。涉及 deploy_integrity.py，需引入 `SkillLoader._scan_builtins()` 或直接查 skills_dir。

### [R-025] MEDIUM: B4 CONSTANT_LITERALS 是 framework.json 常量值的静态副本，无同步守卫
- **category**: completeness
- **root_cause**: self-caused
- **描述**: B4 检查项设计目标是防止 .cataforge/agents/skills/rules 中出现应用常量名代替的裸数值，但执行该检查的 `framework_review/_constants.py:67-74` 的 `CONSTANT_LITERALS` 本身是静态硬编码副本：只覆盖 6/24 常量（≤3 问、>300 行、<200 行、150 LOC、≥5 条、≤3 个任务），且将数值嵌入正则 pattern 字符串，与 framework.json 权威值完全解耦。改 framework.json 中 MAX_QUESTIONS_PER_BATCH 为 4 后，B4 仍匹配 '≤3 问' 模式，无法检测文档中 '≤4 问'。同模块 `_framework_data.py` 的 read_anti_pattern_floor / read_event_log_threshold 等已从 framework.json 动态读值，但 CONSTANT_LITERALS 未采用同一模式;grep tests/ 确认无专项同步验证测试。当前值与硬编码一致故暂无实际影响，属结构性技术债。
- **建议**: 将 CONSTANT_LITERALS 重构为从 framework.json 动态读取（复用 `_framework_data.read_framework_data()`），按常量类型自动生成数值 regex pattern;同时补齐其余高优先级常量（ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS、META_DOC_SPLIT_THRESHOLD_LINES 等）。涉及 _constants.py 与 checks/b4.py。

---

## LOW

### [R-004] LOW: setup --check 别名与 deploy --check 语义冲突，未完成废弃清理
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `setup_cmd.py:32-39` 注册 `--check-prereqs/--check/--check-only`（义为「只检查先决条件，不写文件」），`deploy_cmd.py:53-58` 注册 hidden `--check`（义为「干跑，--dry-run 别名」）。两个相邻子命令同名 flag 语义完全不同。两者均声称 v0.3 移除但 v0.3 未推进，别名仍活跃。setup_cmd 帮助文本声明废弃理由时甚至引用了 deploy 的行为（help string 里的 inter-command coupling）。实际风险被缓解：deploy 的 `--check` 是 hidden（不出现在 --help），且两者均标注 deprecated。原始 MEDIUM 下调为 LOW。
- **建议**: 跟进 v0.3 废弃承诺，在 setup_cmd 移除 `--check` 别名（保留 `--check-prereqs` 和 `--check-only`），在 deploy_cmd 移除 hidden `--check`;或在当前版本将 deprecate_after 写入 framework.json migration_checks 结构化追踪。逐文件删除各自的 hidden/deprecated 声明。

### [R-005] LOW: doctor check_docs_validate 返回值计算混入 warnings（非 gate 失败）
- **category**: error-handling
- **root_cause**: self-caused
- **描述**: `doctor/skill_health.py:196-199` 返回 `len(orphans) + len(stale) + len(xref_errors) + len(alias_conflicts) + len(invalid_ids)` 线性累加，`doctor_cmd.py:53` 以 `gating=True` 将其直接计入 failed_count。该函数未用结构化 (passed, skipped, failed) 元组（与 run_migration_checks 设计不一致），返回不透明整数和无 severity 拆分。最具体的缺陷是 stale_deps（docs_validate 视为 WARN 非 FAIL）在 check_docs_validate 中完全缺席——既不计数也不显示（与 [R-003] 同源）。修正描述一处过度声称：alias_conflicts 在两条命令中实际均被当作 FAIL（均触发 exit 3），并非「mixed severity」;missing-index WARN 路径返回 0 是正确行为非 bug。故 severity LOW。
- **建议**: 将 check_docs_validate 返回值拆分为 hard_fail_count 和 warn_count，或与 run_migration_checks 对齐用结构化 (passed, skipped, failed) 元组替换单整数返回。单文件改动。优先级低于 [R-003] 的渲染去重。

### [R-010] LOW: _triple_exists() 在 write_relations 中未对 IRI 调用 assert_safe_iri，SPARQL 注入面存在
- **category**: security
- **root_cause**: self-caused
- **描述**: `ingest/writer.py:146-153` 的 `_triple_exists(store, subject_iri, predicate_iri, object_iri)` 直接将三个 IRI 字符串拼入 `ASK { <{subject}> <{predicate}> <{obj}> }` 而不调用 `assert_safe_iri()`。数据流分析：subject/object_iri 来自 `entity_iri()`（内部 `escape_iri_component()` 已安全），predicate_iri 来自 `build_relation_quad().predicate.value`，由 `_slot_iri(predicate_curie, namespace)` 生成，predicate_curie 来自 PREDICATE_MAP / DEFAULT_PREDICATE（全部硬编码安全常量如 'cf:implements'）。当前调用路径无用户控制输入流入，注入无法实际触发。但 `_triple_exists` 函数签名接受任意 str 缺乏防御层，且对比同路径 `_content_hash_matches()` 和 `TransactionContext.add_relation()` 均调用了 assert_safe_iri——不一致的安全习惯。属防御性编程规范问题而非当前可利用漏洞，故 LOW。
- **建议**: 在 `_triple_exists()` 函数开头对三个参数统一调用 `assert_safe_iri()`，与 `_content_hash_matches` 保持一致。单点改动。

### [R-011] LOW: TransactionContext.commit() 非原子：removes 与 adds 之间的部分失败导致 store 处于中间状态
- **category**: error-handling
- **root_cause**: self-caused
- **描述**: `transaction.py:250-260` 的 commit() 先循环 staged_removes（`store.remove(q)`）再循环 staged_adds（`store.add(q)`），两循环之间或循环内若 pyoxigraph 抛异常，已执行的 removes 不被补偿，store 处于旧数据已删、新数据未写的半提交态。rollback() 只丢弃暂存列表，无法撤销已写入 RocksDB 的 removes。`ingest/writer.py` 的 `_atomic_replace_entity()` 通过 try/except + 逐条 store.add(prior) 做了局部补偿，但 commit() 无类似机制。修正：pyoxigraph 0.5.x RocksDB 后端在单进程内极少在 remove/add 级别抛受检异常（磁盘满会 panic 而非 Python 异常），且 _atomic_replace_entity 的存在说明仓库已意识到该限制——这是已知后端约束而非可纯代码修复的 bug，故 severity 由 MEDIUM 降为 LOW。
- **建议**: commit() 中先 snapshot prior quads（对 staged_removes 中每个 quad 检查是否存在），若 adds 循环抛异常在 except 分支逐条重新 add 已删除的 quad（参考 _atomic_replace_entity 模式）;或等待 pyoxigraph 提供真正 begin/commit API 后升级。

### [R-017] LOW: 5 条 migration_checks 描述包含设计阶段叙事残留（命中 CLAUDE.md 硬约束 1 检测 regex）
- **category**: convention
- **root_cause**: self-caused
- **描述**: CLAUDE.md §硬约束 1 明确将「配置」纳入禁止范围，要求不写「旧值 X 已废弃」「已被 Y 取代」「已从 N 放宽至 M」等变更叙事。5 条 migration_check 描述命中：`framework.json:176` mc-0.2.0-tdd-light-default「旧值 50/standard-default 已废弃」（永久活跃）;`:188` mc-0.2.0-model-tier-migration「取代 legacy model 字面量」「无过渡期」（永久活跃）;`:200` mc-0.2.0-dispatcher-skills「endswith('-engine') 命名硬编码已删除」（永久活跃）;`:211` mc-0.1.0-no-legacy-constant「MIN_REVIEW_SOURCES 已被 RETRO_TRIGGER_SELF_CAUSED 取代」（deprecate_after=0.2.0 已过期跳过）;`:285` mc-0.1.5-retro-threshold-relaxed「已从 2 放宽至 5」（同已过期）。前三条仍在 doctor 输出中，后两条已是死代码。LOW：description 字段不参与 LLM 调度，仅 CLI 输出，腐化代价远小于 SKILL/AGENT 主体。
- **建议**: 将 description 改写为陈述当前强制条件而非历史对比，例：mc-0.2.0-tdd-light-default 改为「COMMON-RULES.md 必须声明 TDD_LIGHT_LOC_THRESHOLD=150、TDD_DEFAULT_MODE=light、SPRINT_REVIEW_MICRO_TASK_COUNT=3」;mc-0.1.0-no-legacy-constant 改为「COMMON-RULES.md 不得含 MIN_REVIEW_SOURCES」。后两条可选同步添加 deprecate_after 或直接删除（已过期且路径永远通过）。

### [R-026] LOW: MCPRegistry._is_trusted_command 允许 ../ 路径穿越，与注释意图不符
- **category**: security
- **root_cause**: self-caused
- **描述**: `runtime/mcp/registry.py:124` 的信任检查以「含路径分隔符」为相对路径判据（`'/' in executable or '\\' in executable`），导致 `../../evil.sh`、`../../../usr/bin/env` 等向上穿越的相对路径均通过检查。代码注释（line 111）写 `e.g. ./bin/tool` 暗示只允许向下的项目内路径，但实现未做规范化限制（实测 `../../evil.sh` 与 `./scripts/safe.sh` 同被判 TRUSTED 无区分）。LOW 的威胁模型理由：(1) 该检查只作用于 pip entry_points 和 plugins，不作用于声明式 `.cataforge/mcp/*.yaml`;(2) 利用需攻击者代码已在 Python 环境执行（pip install 恶意包）;(3) 拥有 pip install 权限者已有完整代码执行能力，借此注册 `../../evil.sh` 的增量风险极小。注释意图与实现的差距真实存在但威胁模型限制实际影响。
- **建议**: 在 `_is_trusted_command` 增加路径规范化检查：对含分隔符的相对路径调用 `PurePosixPath(executable).parts` 检查是否含 `..` 段，命中则 reject。单点改动，无需修改调用方。

### [R-027] LOW: save_manifest() 使用非原子 write_text，与 _save_state 的 os.replace 写法不一致
- **category**: error-handling
- **root_cause**: self-caused
- **描述**: `runtime/deploy/manifest.py:130` 的 `save_manifest()` 直接 `path.write_text(payload, encoding='utf-8')`，写入中途若进程被中断（Ctrl-C、OOM、磁盘满）会留下截断的 `.deploy-manifest.json`。同文件 `load_prior_manifest()`（93-101）遇 ConfigError（JSON 解析失败）返回空集合，导致下次 deploy 的 prune 步骤将所有已记录的 CataForge-owned 路径视为未知，不执行孤儿清理。`mcp/lifecycle.py:596-602` 的 `_save_state` 已实现原子写（tmp → os.replace 并附注释说明），两处实现不一致。用户文件始终安全（prune 仅删 manifest 记录的路径），但 CataForge-owned 孤儿在下次 `--rebuild` 前残留。
- **建议**: 参照 `lifecycle._save_state` 模式，用 `path.with_suffix('.tmp')` 写临时文件后 os.replace 到目标路径。单点改动，可复用 `cataforge.utils.atomic_write` 如已存在。

### [R-028] LOW: Scaffold manifest 陈旧：25 个 doc-gen + 1 个 doc-nav 条目，无 context 条目
- **category**: consistency
- **root_cause**: self-caused
- **描述**: `.cataforge/.scaffold-manifest.json` 记录了 rename 到 context 之前的 24 个 `skills/doc-gen/*` 文件和 1 个 `skills/doc-nav/SKILL.md` 的 SHA-256 哈希，零个 `skills/context/` 条目。该 manifest 被 `core/scaffold.py:303` 的 copy_scaffold_to 用于在 `upgrade --force` 时区分框架管理文件与用户修改文件。修正原始描述的机制错误：`_is_user_modified` 仅在 `iter_scaffold_files()` 循环内被调用，该循环只遍历新包中存在的文件——`skills/doc-gen/*` 不在新包中，故从不被访问，并非「被保护为 user-modified」而是变成磁盘孤儿;`context/*` 在首次 upgrade 时因 exists=False 正确作为新文件写入。真实后果较轻：下游 pip-install 用户 upgrade 后旧 `doc-gen/*`、`doc-nav/*` 文件累积为孤儿，属卫生问题而非 upgrade 正确性失败。editable install（dogfood）走 live `.cataforge/` 不受影响。故 LOW。
- **建议**: 对当前 `.cataforge/` source 跑 `cataforge upgrade --force`（或 scaffold copy 路径）重新生成 `.scaffold-manifest.json`，以当前 `context/` 哈希替换陈旧 doc-gen/doc-nav 哈希。或新增一个 upgrade 迁移步骤：删除 source 文件已不存在于 scaffold tree 的 manifest 条目（类比 deploy manifest prune 逻辑）。

### [R-029] LOW: testing builtin 的 CHECKS_MANIFEST 不在 doctor Built-in skill reachability 中被验证
- **category**: completeness
- **root_cause**: self-caused
- **描述**: doctor 的 Built-in skill reachability（`doctor/skill_health.py:26`：`targets = sorted(m.id for m in loader._scan_builtins())`）只验证每个 builtin 有可执行 entry point（meta.scripts 非空），不验证其 CHECKS_MANIFEST 内容质量或与 SKILL.md 一致性。testing 确在 targets 中（8 个 builtins 含 testing 的 e2e entry point）且因 scripts 非空通过——reachability 检查对其既定目的工作正常。缺口是 doctor 不验证 CHECKS_MANIFEST 与 B3 覆盖状态，与 B3-α 形成能力缺口（B3 覆盖 4 个 review-class builtins，testing 既有 CHECKS_MANIFEST 又声明 B3 自动对账，但两者都未真正执行）。LOW：doctor 测试做了它声称的事（脚本可调用），缺的是一个测试而非失败的守卫，且本条从属于根因 [R-022]。
- **建议**: 在 framework-review B3 的 builtin_map 补入 testing（见 [R-022] 修复方向），delegation 模式成本极低，B3 修复后即覆盖此缺口;若希望 doctor 独立覆盖，可在 check_builtin_skill_reachability 增加 CHECKS_MANIFEST 存在性与非空验证。

---

## 方法学与置信度

**对抗性验证流程**：每条候选 finding 经两轮处理。第一轮按 file:line 提取证据并形成初判;第二轮以 verify_note 形式独立复核——重读引用代码行确认证据属实、追踪实际数据流判断「可利用性 / 实际影响」、并对原始 severity 做对抗性挑战（倾向下调而非上调）。报告仅纳入 verify_note 确认主体成立的 finding。

**被对抗性下调的 severity**（5 条）：

- [R-001] context_cmd SystemExit：原 HIGH → MEDIUM。功能行为（非零退出）正确，仅 banner 呈现不一致;且 line 57 的委托模式被识别为有意为之、剔除出缺陷范围。
- [R-004] setup/deploy --check：原 MEDIUM → LOW。deploy 的 --check 为 hidden，且双方均有 deprecation 提示，发现驱动的误用风险被缓解。
- [R-007] repair() 非原子：原 HIGH → MEDIUM。`_restore_ghosts` 提供尽力还原且 repair 幂等可重跑。
- [R-010] _triple_exists 注入：原 MEDIUM → LOW。当前所有调用路径的 predicate 均为硬编码安全常量，注入无法实际触发，属防御规范问题。
- [R-011] commit() 非原子 / [R-021] migration 路径审查盲区 / [R-028] scaffold manifest：均因「后端约束 / 已 deprecated 且 skip / 机制纠偏后后果更轻」由 MEDIUM 下调为 LOW 或维持下调。

**被纠偏但主体保留的描述错误**（3 条）：

- [R-007] 原描述称 `_restore_ghosts` 不覆盖 ghost_relation_snapshots，实际 line 132 已覆盖——纠正后主体（无原子性、失败后混合状态）仍成立。
- [R-005] 原描述称 alias_conflicts 是「mixed severity」，实际两条命令均当作 FAIL——纠正后核心缺陷收敛到 stale_deps 缺席（与 R-003 同源）。
- [R-028] 原描述称旧文件「被保护为 user-modified」，实际是从不被访问而成为孤儿——纠正后后果从「upgrade 正确性失败」降级为「磁盘卫生问题」。

**被驳回 / 已知背景（未作为 finding 上报）**：

- 「src/ 下约 12 个旧顶层包目录（agent/cli/deploy/...）看似空残留」经 git ls-files 核实为零 git 跟踪（仅本地 __pycache__，已 gitignore），不构成仓库腐化，作为假警报排除。
- context_cmd.py:57 的 `raise SystemExit(read_main(argv))` 委托给 sub-CLI 入口，是保留 sub-CLI 退出码的标准模式，从 [R-001] 缺陷范围剔除。

**置信度分布**：26 条中 high confidence 21 条、medium confidence 5 条（[R-001] 的影响面、[R-005] / [R-007] / [R-010] / [R-026] 的威胁模型/数据流判断）。medium 项的不确定性集中在「影响程度」而非「事实是否存在」——所有 file:line 证据均经直接复核确认。

**已知局限**：(1) 部分「死守卫 / 未实现常量」的历史性主张（如 [R-021]「mc-0.1.5 从引入到 deprecate 全程指向错误路径」）从当前仓库状态无法回溯验证，仅基于现状推断;(2) 运行时验证（framework-review / doctor 实跑、Python 集合差计算）在 Windows 路径下完成，与 CI 的 POSIX 路径行为假定一致但未交叉验证;(3) 本轮聚焦实现层确定性缺陷，未覆盖性能剖析、并发竞态、跨平台部署差异等需运行时压测的维度。

---

## 自审元工具盲区

本节单列来自 meta-tool-blindspot 子系统的 finding（[R-021]~[R-026] / [R-029]），它们的共性是：**框架的自审工具（framework-review B-checks / doctor）本身存在结构性失明，导致质量门禁的承诺与实际执行脱节**。这类问题比单点 bug 更危险——它们使其他腐化得以在「绿灯」下静默累积。

| finding | 盲区主体 | 失明维度 | severity |
|---------|---------|---------|----------|
| [R-022] | framework-review B3 | testing skill 公开承诺「不一致即 FAIL」但 builtin_map 中无 testing，承诺 categorically false | HIGH |
| [R-024] | framework-review B3 | doc-review（主质量门禁）的 source SKILL.md 已迁入 Python 包，b3.py `is_file()` False → continue，18 条 CHECKS_MANIFEST 永不被对账 | HIGH |
| [R-021] | framework-review（无对应 check）/ doctor | migration_checks 数组的 path 存在性、allow_missing 滥用、deprecate_after 提前退休三维度全无审查 | MEDIUM |
| [R-023] | doctor deploy_integrity | 只验证已部署路径不 dangle，不验证 manifested 路径是否还有 source，无法检出 source-removed 孤儿 | MEDIUM |
| [R-025] | framework-review B4 | CONSTANT_LITERALS 是 framework.json 常量值的静态硬编码副本（覆盖 6/24 且数值嵌入 regex），常量值变更后 B4 静默失效 | MEDIUM |
| [R-029] | doctor skill reachability | 只验证 builtin 有可执行 entry point，不验证 CHECKS_MANIFEST 内容/B3 覆盖状态（从属于 R-022 根因） | LOW |

**模式总结**：盲区集中爆发于「skill 从 data-driven（`.cataforge/skills/<id>/SKILL.md`）迁移到 Python builtin（`builtins/<id>/`）」这一架构演进的接缝处。B3 与 doctor 的检查逻辑均默认 source 在 `.cataforge/skills/` 文件树下（`is_file()` / 目录级遍历），未感知 builtin-only skill 的 SKILL.md 现位于 Python 包内或仅以 deploy 产物形式存在于 `.claude/skills/`。这条接缝同时制造了三类静默失效：B3 跳过 builtin-only skill 的 manifest 对账（R-022/R-024）、doctor 无法检出 source-removed 的 deploy 孤儿（R-023/R-018）、B4 与 migration_checks 缺乏对 framework.json 权威值的反向同步守卫（R-025/R-021）。

**收敛优先级**：根因是 R-022/R-024（B3 不感知 builtin-only skill）。修复 B3 的 builtin-only fallback（importlib.resources 读包内 SKILL.md）+ 补 testing 进 builtin_map，可一并消解 R-029。R-021 主张的 B9（migration_checks 路径审查）与 R-023 主张的 doctor 逆向检查是新增能力，建议作为同一批「自审工具对齐架构演进」的成套改进，避免单点修补后接缝仍在其他维度漏检。
