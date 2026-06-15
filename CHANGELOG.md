# Changelog

All notable changes to CataForge will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- 变更原因：补 Deprecated/Removed/Security 子节说明；引入独立 BREAKING 段并附迁移路径表；声明 bullet 长度上限 -->
**写作约定（自 v0.1.16 起强制）：**

- 每条 bullet 一个变更，单行 ≤ 25 英文词或 40 中文字，展开放正文段。
- 子节固定使用 `### Added` / `### Changed` / `### Deprecated` / `### Removed` / `### Fixed` / `### Security`。
- 破坏性变更必须单独写 `### BREAKING` 子节，并附迁移路径表（"如果你曾依赖 X，改为 Y"）。
- bullet 不复制 commit message；commit hash 与 PR 编号放每条末尾的方括号。

<!--
新条目从 PR #85（2026-04-27）起改为 fragment-based —— 每个 PR 在
changelog.d/{PR#}.md 加片段，发版时 scriv collect 聚合入此处。
详见 changelog.d/README.md。
-->

<!-- scriv-insert-here -->

<a id='changelog-0.11.0'></a>
## [0.11.0] — 2026-06-15

### Added

- **`context index` / `context validate`** —— 与 `context read` 组成完整的 context 读取/校验命令族，行为与原 docs 族动词一致（共用同一实现体）。
- **`context write-doc`** —— 把整篇 markdown 文本（frontmatter + preamble + 章节 + 实体 + 关系）经一个原子事务写进知识图谱（kg-first 策略），post-commit 校验失败整体补偿、零图残留；实体 title 含 `{...}` 占位符则拒绝，防模板示例污染图。
- **`context write-meta <doc_id>`** —— 图侧改写 Document 的 `status` / `version`（保留原 frontmatter 引号风格），同步图槽与 content_hash。
- **`TransactionContext.add_document`** —— Document 结构节点的图侧 authoring 入口，content_hash 幂等。
- **`context status`** —— 输出 `{strategy, authoring, store_initialized, entity_count}` JSON 探针，零副作用（store 不存在时不创建）。
- **`context.authoring` 配置开关**（`md` 缺省 / `graph`）—— kg-first 项目声明 authoring 权威方向；doc-only 项目恒 `md`。
- **reconcile 文档级漂移 triage** —— 对每个导出文档比较磁盘字节 / 导出基线（新 `cf:exported_content_hash`）/ 图侧重渲染三方哈希，判定 `in_sync` / `human_edit` / `graph_ahead` / `conflict` / `never_exported`；`ReconcileReport` 新增 `authoring` / `documents` / `document_drift_count`。

### Changed

- **prompt 资产与文档全量换用 context 动词** —— `.cataforge/` 规则/agent/skill、`CLAUDE.md`、`docs/reference/cli.md`、`docs/architecture/runtime-workflow.md` 的命令指引收敛到 `context read/index/validate`；「加载原则」措辞统一为「按章节/条目粒度按需加载」。
- **`context write-narrative` 正文规范化** —— 收敛到事务面并校验：正文首行标题须与 anchor 一致（否则拒绝，避免 ghost/missing section），无标题行则自动补标题；修正 `--anchor` help 中误导性示例（anchor 为 heading 文本如 `1. 概览`）。
- **`context finalize`（kg-first）导出后重建 `docs/.doc-index.json`** —— 消除导出后索引过期；每个文档的导出字节 sha256 写回图作为后续漂移检测基线。既有 id 集合 diff 的 `overall_divergence_count` / `ok` 语义不变。

### Deprecated

- **`docs load` / `docs index` / `docs validate`** —— 转为废弃别名：stdout 与 exit code 不变，stderr 追加一行指向 `cataforge context <verb>` 的提示；doctor 的 deprecated-reference 扫描会标记 prose 中对旧动词的引用。`docs migrate-nav` / `docs migrate-reviews` 不受影响。

### Fixed

- **章节顺序在更新时丢失** —— `add_section` 更新既有 Section 时会整体替换 quads、把 `cf:position` 重置为 0，导致下次 `context finalize` 章节顺序错乱；现沿用图中既有 position / level，新建章节按同文档 `max(position)+1` 追加。

<a id='changelog-0.10.0'></a>
## [0.10.0] — 2026-06-13

### Added

- **整篇文档导出** —— kg-first 非空图下 `context finalize` 经 `compile_documents()` 从图谱按文档序重建整篇 markdown（frontmatter / 前导 / 章节原文切片），`finalize → ingest → finalize` 字节级幂等；不被任何 Document 覆盖的孤儿实体兜底导出 per-entity 卡片。
- **ingest 结构保真度** —— Section 记录 `cf:position`（文档序）与 `cf:section_level`；Document 记录 `cf:frontmatter_raw` / `cf:preamble_body` / `cf:source_path`，章节顺序不再依赖 anchor 字典序。

- **authoring API 完备化** —— `context write` 新增 `--parent`（part_of 层级 + parent-scoped IRI）、`--relation PREDICATE=OBJECT_ID`（repeatable）、`--narrative` / `--narrative-stdin`（多行叙事）；新命令 `context transact` 经 stdin / `--file` JSON 在单事务内提交多实体/关系/叙事操作，校验失败整批补偿、图状态零残留。

### Changed

- **Windows shell 统一走 Git Bash** —— `.claude/settings.json` 以 `env.CLAUDE_CODE_USE_POWERSHELL_TOOL=0` + `defaultShell: bash` 关闭 Claude Code 的 PowerShell 工具；`setup.py --apply-permissions` 在 Windows 上为下游项目写入同样配置（Bootstrap 与 framework-update 自动调用）。Shell 约束从 CLAUDE.md / PROJECT-STATE 模板文字下沉到配置层，模型不再看到 PowerShell 工具。

- **`cataforge kg export`** 默认整篇导出，`--per-entity` flag 保留实体卡片形态。

- **实体内容哈希统一** —— `context write` 与 `kg add` 默认哈希共用 `entity_content_hash(title, slots)`，跨路径写入幂等一致（`kg add --content-hash` 显式值行为不变）。

### Fixed

- **Windows 会话误用 PowerShell** —— harness 在 Git Bash 已安装时仍渐进暴露 PowerShell 工具并设为默认 shell，与项目 Git Bash 约定冲突；现由配置层物理消除该工具，而非依赖 prompt 文字约束。

<a id='changelog-0.9.2'></a>
## [0.9.2] — 2026-06-12

### Added

- **实体正文进图** —— `narrative_body` 槽上移到 `SoftwareArtifact` 基类，ingest 为每个业务实体写入自身正文（heading 实体 = 节正文去 heading 行；正文行 subordinate = 自身切片，与 content_hash 同口径）。
- **存量 store 迁移指引** —— 0.9.x 已导入的 KG 因 hash 幂等跳过无法经普通 ingest 自愈，需重建：`cataforge kg init --force && cataforge context ingest && cataforge kg reconcile && cataforge doctor`（markdown 为事实源，重建无损；曾用 `context write` 直写过图的项目先 `cataforge kg snapshot`）。

- **Shell 约定（Windows）** —— 项目指令模板 §全局约定 新增：Windows 环境优先使用 Git Bash 执行 shell 命令（POSIX 语法与引号/转义行为跨平台一致），PowerShell 仅用于 Windows 专属操作；下游项目 deploy 时随指令文件模板继承。

- **实体定义 doc_type 权威表** —— 实体类的定义仅在其权威 doc_type 中成立（Feature/AC→prd、Task→dev-plan、TestCase→test-report 等，单一事实源为 `ENTITY_CLASS_TO_DOC_TYPE`）；非权威 doc_type 中的 heading-subject 与 subordinate 命中降级为引用，不产出定义——test-report 按任务分节复述 T-xxx 不再触发 collision 中止导入。subordinate（AC）的权威跟随其 parent 实体类。项目可经 `framework.json#context.kg_definition_authority`（`{class_name: [doc_type, ...]}`）合并扩展缺省权威（只增不减）。

### Changed

- **`cataforge context` 写入/生命周期命令按 `context.strategy` 路由** —— `finalize` / `ingest` 在 doc-only 项目下路由到文档索引重建（等价 `cataforge docs index`，输出 `indexed N doc(s)`）；`reconcile` 路由到索引完整性校验（orphan / stale / xref / alias / invalid-id），有问题时与 kg-first 漂移同语义 exit 3，索引缺失时 exit 2 并提示 `cataforge docs index`。`write` / `write-narrative` 在 doc-only 下抛出 `ContextStrategyError` 配置错误（说明需要 `context.strategy = "kg-first"`），不再误导性提示 `cataforge kg init`。路由在 application 层（`cataforge.application.context.write`）实现，编程调用方同样生效；kg-first 路径返回契约不变。

- **collision 迁移引导** —— `KGEntityCollisionError` 消息与 doctor `kg_ingestion_completeness` FAIL 输出逐条列出 `source_doc :: source_section`，并给出动作建议：统一到权威定义，其余出现改 xref（`doc_id#§N.ENTITY-ID`）或行内 code。
- **dangling WARN 降噪** —— doctor 悬挂引用按前缀聚合：全库无任何定义的前缀输出单行汇总（`N TC- id(s) referenced, none defined in active sources (e.g. …)`），有定义的前缀仍逐 id 列出（上限 5 + 省略号）。

### Fixed

- **context 定稿指引指向真实命令面** —— `generate.md` 定稿步骤按 `context.strategy` 显式分支（`kg-first`: `cataforge context finalize` / Edit 直写后 `cataforge context ingest`；`doc-only`: `cataforge docs index`）；COMMON-RULES §Agent 文档 I/O 契约同步为"定稿与回灌"；ORCHESTRATOR-PROTOCOLS 在 Phase Transition / Revision / Change Request 收口处补全 `ingest → reconcile` 漂移闭环锚点。

- **Bootstrap setup 调用形式** —— ORCHESTRATOR-PROTOCOLS §Project Bootstrap Step 8、framework-update SKILL、PROJECT-STATE 模板与 CLAUDE.md §执行环境占位符统一指向 `python .cataforge/scripts/framework/setup.py --emit-env-block` / `--apply-permissions`；包 CLI `cataforge setup` 不提供这两个选项，原指引按包 CLI 形式调用会直接报错。
- **emit-env 迁移守护复活** —— 新增 `mc-0.9.2-setup-emit-env`（file_must_contain，守护 setup.py 的 `--emit-env-block` / `build_env_block`），接替因 `deprecate_after: 0.2.0` 永久 SKIP 的 `mc-0.1.5-setup-emit-env`；setup.py docstring 中的迁移检查引用同步指向新 id。

- **`kg repair` 闭环 Section 级漂移** —— repair 现消费 reconcile 报出的 `ghost_sections` / `missing_sections`：ghost Section 节点连同入向 `cf:has_section` 边按 `source_doc` 域内删除（其他文档中同名 anchor 的 Section 不受影响）；missing Section 触发该 doc_type 的 `write_structure` 重灌（实体级 reingest 同步补灌结构节点）。`RepairStats` 与 `kg repair` 的 JSON / 文本输出新增 `ghost_sections_removed` / `missing_sections_ingested` 计数。
- **`kg delete` 按节点形态解析 id** —— `F-001`（扁平实体）、`F-001/AC-002`（父域从属）、`doc/{doc_id}`（Document）、`doc/{doc_id}/sec/{anchor}`（Section，`doc/` 前缀可省略）、完整 http(s) IRI 分流到对应 IRI 解析；完整 IRI 不再被二次 percent-encode 导致 `KGEntityNotFoundError`；not-found 报错列出解析出的形态与目标 IRI，CLI help 同步说明可接受的 id 形态。

- **KG 实体级 title 保真度** —— title 切分剥除前导分隔符；subordinate（AC 等）title 从自身正文行派生，不再复用父节标题。
- **per-entity content_hash** —— 正文行 subordinate 按自身切片计算 hash，父子不再共享整节 hash，实体级内容漂移对幂等跳过与 collision 检测可见。

- **kg-first 实体级读取不再产出空壳卡片** —— 实体 SPARQL 经 `source_doc` + `source_section` JOIN 源 Section 节点绑定 `narrative_body`，`cataforge docs load "prd#§N.F-XXX"` 渲染的实体卡现包含源章节正文；Feature 卡经 `cf:part_of` 入边列出其 AcceptanceCriteria 子实体（不再依赖显式 xref 的 `cf:satisfies`），AC 卡新增 Part Of 段列出父实体。KG 渲染产物既无正文也无子实体内容时，loader 自动回退文件后端抽取，保证调用方拿到的信息量不低于文件后端。
- **`cataforge kg trace` 沿 `cf:part_of` 聚合** —— downstream 收集 part_of 入边子实体（AC 进入 `acceptance_criteria` 桶），upstream 沿 part_of 出边回到父实体；`coverage_status` 仍仅由 impl / test 桶决定，AC 桶不参与。

- **MCP 并发 start 双 spawn 竞态** —— `load_state` 区分"文件不存在"与"撞上 `os.replace` 替换窗口的瞬时读错"（后者重试而非误报无状态），并发 `start()` 不再各拉起一个进程；`start()` 对 `unhealthy` 但进程存活的服务附着重探而非重复 spawn。

<a id='changelog-0.9.1'></a>

## [0.9.1] — 2026-06-11

### Added

- **workflow 路由骨架 SSOT** —— `framework.json#/workflow` 声明 phase→role→`execution_host`，orchestrator 路由表与 framework-review B5 均以此为准。

- **Inline Role Execution Protocol** —— `execution_host: inline` 的发散性 phase 由 orchestrator 主线程承载角色执行，AskUserQuestion / research 多轮澄清原生可用。

- **B5-ζ 交互宿主守卫** —— framework-review 校验 `interactive: true` 的 phase 须 `inline`，除非平台 `features.subagent_interactive=true`；否则 FAIL（带 `interactive_subagent_ack` 降为 INFO）。

- **`subagent_interactive` 平台能力位** —— 各 platform profile 声明派发子代理能否触达用户，使 inline/subagent 决策成为平台能力的函数。

### Changed

- **Phase 1/2/3 改为 inline 执行** —— requirements / architecture / ui_design 在主线程承载角色而非派发非交互子代理，修复 user-interview / 头脑风暴 / 澄清在子代理中失效的缺陷；审查门禁仍派子代理。

<a id='changelog-0.9.0'></a>

## [0.9.0] — 2026-06-11

### Added

- **approved 状态溯源校验** — 可审查的主卷文档 `status: approved` 时要求存在 `docs/reviews/doc/REVIEW-{doc_id}-r*.md` 审查报告，新建产物无法预标 approved 绕过 doc-review 门禁；审查报告类 doc_type 与分卷豁免。

- **upgrade 残留清理** — scaffold force refresh 按 manifest 修剪包内已不存在且用户未改动的文件（清空目录一并移除；用户改过的保留并告警），升级不再留下触发 framework-review FAIL 的废弃 skill 目录。
- **Bootstrap 存量项目归档引导** — 历史文档可移入根级 `archive/` 或经 `docs/.docignore` 豁免，避免 brownfield 项目初始化即 orphan FAIL。

### Changed

- **sprint-review 任务状态检查** — dev-plan 未声明状态降为 advisory；新增 `project_features.task_status_external` 显式跳过该检查；dev-plan 模板状态列标注为该检查的事实源。
- **deliverables 二选一默认启用** — `A | B` 交付物条目端到端生效（解析器保留管道条目、检查默认 alternation 语义），`deliverables_accept_alternation: false` 可退出。
- **gold-plating 默认豁免** — 新增测试辅助类默认 glob 白名单（tests/、fixtures/、`*.test.*`、`*.spec.*`、`*.stories.*` 等），项目 `unplanned_glob_patterns` 在其上追加，`--no-default-ignores` 一并关闭。

- **session_start 去抖** — SessionStart hook 在 60 秒窗口内的重复事件不再落盘，消除 IDE 多窗口/重连的 EVENT-LOG 噪声。
- **kg import 关系可观测性** — 实体数 >0 而关系数 =0 时输出提取语法提示（追溯边仅来自严格 `doc_id#§N.ITEM` 交叉引用）。
- **dispatch-prompt 约束细化** — 审查报告类 new_creation 豁免用户确认轮（verdict 经 orchestrator 流转）；new_creation 产物必须以 `status: draft` 起始。
- **test-writer 接线类 AC Anti-Pattern** — 禁止以读源码字符串锚定验证接线，必须经真实运行时对象断言回调/状态产出。

### Fixed

- **EVENT-LOG UTF-8 钉死与 doctor 容错** — `append_event` 显式按 UTF-8 写盘（未走 `ensure_utf8` 的宿主不再按 locale 写出 GBK 字节）；doctor 的 EVENT-LOG schema 检查逐行解码，非 UTF-8 行降级为该检查 FAIL 并报行号，不再以 UnicodeDecodeError 中断 doctor；feedback collectors / phase / framework-review 等读取方补 `errors="replace"` 容错。

- **kg import verify 范围化** — 实体/关系计数限定在本次 import 覆盖的 source-doc 集合内，`kg add` 合法添加的 synthetic 实体不再使后续所有 `kg import` 永久 verify FAIL（exit 3）。
- **doctor kg_ingestion 缺失分流** — 引用了无任何 active doc_type 定义来源的实体（如 ADR-XXXX）降为 WARN 并给出 `context.kg_active_doc_types` / inline-code 指引，不再统一指向对该场景无效的 `kg repair`；真实摄入缺口维持 FAIL。
- **generator 模板 namespace 对齐** — workflow-framework-generator 的 `framework.json.tmpl` 与 `docs/reference/configuration.md` 改用规范 `ontology/` / `instance/` 命名空间，新生成框架不再出现 `rdfs:subClassOf*` 遍历为空。

- **doc-review 多卷 PRD 兼容** — 主卷的 F/用户故事配比与 AC 计数聚合 `split_from` 指向它的分卷，委托式主卷不再因 AC 全在功能分卷而 FAIL。

- **feedback --gh 仓库定向** — `gh issue create` 统一注入 `-R {framework.json#upgrade.source.repo}`，无 git remote 或 remote 指向业务仓库的下游项目可直接上报上游。
- **doc-id slug ASCII 化** — `derive_doc_id` 折叠非 ASCII 字符并按连字符词边界封顶，中文摘要不再产出混合文字、任意截断的 frontmatter id。

<a id='changelog-0.8.0'></a>

## [0.8.0] — 2026-06-06

### Added

- **agent 语言细则注入** —— architect / implementer / test-writer / reviewer / devops / debugger 六个核心 agent 声明 `lang_aware: true`，部署时按 `active_languages()` 在落地副本追加 `## 语言细则` 段，链接 `.cataforge/agents/<id>/rules/lang-<lang>.md`；内置 python / js-ts / go / rust / csharp / java 共 36 个片段，含面向 LLM 编码的协作要点（不臆造 API / 包、先复现再改、补异常路径等）。
- **内置 wiring / e2e 规则扩展至 go / rust / csharp / java** —— code-review 与 testing 的 Layer 1 现覆盖这四种语言的占位实现、测试后门与真实输入模式（基于 chromedp / thirtyfour / Playwright / Selenium 等真实框架 API）。
- **覆盖层骨架** —— `.cataforge/overrides/` 随框架附带 README + `project/` / `user/` 占位目录，作为 `cataforge override eject` 的起步说明。

- **部署漂移检测** —— `cataforge deploy` 现在把 `.cataforge/` 源指纹（`source_digest`）+ 运行包版本（`package_version`）写入 `.deploy-manifest.json` 作为基线。`cataforge doctor` 新增非 gating 的「Deploy drift」段，新增 `deploy_drift` SessionStart hook（observe，stderr 提示）；当 `.cataforge/` 源或已安装的 `cataforge` 版本自上次部署后变更时，提示运行 `cataforge deploy`，避免改了源却忘记 redeploy 导致 IDE 产物静默过期。

- **`cataforge agent list --skills`** —— 在 agent 列表后附带每个 agent 在 AGENT.md frontmatter 声明的 skills（`skills: []` 显示 `(none)`）。`AgentManager.skills_for()` 以结构化 frontmatter 解析替代 agent-dispatch 里脆弱的 `grep -h 'skills:' -A 20` 行窗启发式（字段顺序/长度变化会截断或串入无关内容）。

- **`{AGENTS_SRC_DIR}` 运行时占位符** —— 恒解析为 `.cataforge/agents` 源目录（跨平台一致、结构完整、部署后仍可读），供 agent 跨引用 sibling `*PROTOCOLS*.md` 或其他 agent 的 `AGENT.md` 时使用，与 lang-fragment 链接的"指源"策略统一。

- **`docs/.docignore`** —— 声明免于 doc-index orphan 检查的发布型文档子树，避免人工散文文档被误报为孤儿。

`find_orphan_docs` 原先只排除 `.archive/`，把所有缺 `id` front matter 的 `docs/**.md` 一律判为 orphan —— 对 SDLC 管线产物正确，对框架自身的 architecture/guide/reference 等人工文档是误报。新增 `docs/.docignore`（gitignore 风格：目录尾 `/` 或相对 docs/ 的 fnmatch 行，`#` 注释）声明非 SDLC artefact 子树；`cataforge docs validate` / `cataforge doctor` 读取它，匹配的无 front matter 文档不计为 orphan，改打印 `N doc(s) excluded by docs/.docignore` 以防静默放行。

- **自然语言 → SPARQL 只读查询面** —— `cataforge.domain.kg.nl_query` 新增 `translate()` / `query()` / `answer()`：用调用方注入的、仅需暴露 `.invoke(prompt)` 的 LLM（不引入任何 LLM 框架依赖）把自然语言问题翻译成 SPARQL，经 SELECT/ASK 白名单门控（`read_query.assert_read_only`）后走现有只读路径执行，杜绝幻觉写操作落库；`answer()` 复用 `query()` 取数后再一次 `.invoke()` 把结果行转述为自然语言，同样受只读门控保护。
- **LinkML 生成的 Pydantic 模型可作运行时类型视图** —— `cataforge.domain.kg.models.to_model()` 把 `QueryAPI` 的标量 dict 提升为生成的 Pydantic 模型（`model_construct` 标量视图），生成产物缺失时优雅返回 `None`。生成的 `*_pydantic.py` + `subclass_axioms.ttl` 现纳入版本控制并随 wheel 分发，新增 `check_codegen_fresh` 守卫保证它们与 `schemas/*.yaml` 始终同步。

### Changed

- **`iter_scaffold_files` 排除 `overrides/`** —— 覆盖层不再进入 scaffold manifest，兑现 `overrides_dir` 的升级免疫承诺：`upgrade apply` 永不触碰用户定制层。

- **最低 Python 版本提升至 3.11** —— `requires-python` 从 `>=3.10` 改为 `>=3.11`，CI matrix 与 classifiers 同步去除 3.10。放弃 3.10 用户以启用 `tomllib` / `typing.Self` 等现代特性。
- **平台 profile / hooks 加载期强校验** —— `profile.yaml` 与 `hooks.yaml` 现由 pydantic 模型（`PlatformProfile` / `HooksSpec`）在加载期校验：字段类型错误、结构漂移、拼写错误会在加载期即报出可定位的字段级错误，而非延迟到运行时。缺失的可选节仍回退默认值，不会"加载即崩"。

- **`context finalize` 对空图自动从 markdown 收敛** —— kg-first 下 markdown-first 授权的内容会被 seed 入图（md→KG，不做有损的反向 re-export），reconcile 不再把整棵文档树报为漂移，「持久化由框架路由」契约成立。
- **`cataforge bootstrap` 为 kg-first 项目初始化 KG store** —— 幂等创建（`--dry-run` 显示为 `kg-init` 步骤），首个 `context write`/`reconcile` 不再撞上缺失的 store。
- **`DOC_REVIEW_L2_SKIP_DOC_TYPES` 改用真实基名 `[brief, changelog]`** —— 移除永不命中的 `-lite` 死项；lite 变体的 Layer 2 短路改由 frontmatter `mode ∈ {agile-lite, agile-prototype}` 驱动。

- **元资产边界与触发性打磨** —— implementer 断言强度自检改引 test-writer `行为断言强制` 单一事实来源（去重）；testing/arc-design/deploy-config 等补全 description 触发句与"不做"承接 skill 标注；多个 agent/skill 的 Anti-Patterns 补"做 A 而非 B + 具体反例"。

- **全仓 enforce ruff-format** —— pre-commit 与 CI 新增 `ruff format --check src tests scripts`，源码树一次性规范化为 canonical 格式。

此前 CI 只 enforce `ruff check`（lint）不 enforce format，而 `lint_format` PostToolUse hook 对 `.py` 编辑跑整文件 `ruff format`，导致编辑触碰的非 canonical 行被重排、在 diff 里产生无关 churn。现按与 lint 相同的范围（`src tests scripts`）enforce ruff-format，消除该漂移。

- **修正 `lint_format` hook 的 `.cataforge/` 跳过** —— 原先只对 `.md` 生效，现对所有文件类型生效，与 docstring 及 ruff 作用域（`src tests scripts`，不含 `.cataforge/`）一致；框架资产不再被自动格式化。

- **`/self-update` skill 与 `/bootstrap` command 合并为 `framework-update` skill** —— 单一 `/framework-update [check|apply|verify]` 覆盖整条框架生命周期。

两个旧入口都是 `cataforge bootstrap` 脊柱的薄包装，对同一调用协议各写一遍。合并后脊柱只描述一处：`apply` 串起条件包升级（pip/uv）→ `cataforge bootstrap` 幂等刷新/部署/验证 → upgrade.state 与框架版本簿记 → 按项目指令文件存在与否分流项目初始化或恢复。在已部署项目上重跑 `apply` 等价于一次升级检查 + 刷新，再分流 from-scratch 初始化或环境补齐 + `/start-orchestrator continue` 恢复。`/bootstrap` command 作为纯重复包装移除；`framework-update` 既 user-invocable 又 model-invocable，直接 `/framework-update` 调用。CLI `cataforge bootstrap` / `cataforge upgrade` 不变。

- **`cataforge kg query` 的 SPARQL 只读策略下沉到 `domain/kg/read_query`** —— 写操作白名单与 `LIMIT` 注入提取为共享原语，CLI 与新的 NL 查询面共用同一套 SELECT/ASK 策略，不再各自实现。
- **SHACL 桥接改用序列化往返** —— `validate` 的 pyoxigraph→rdflib 桥接改为 `store.dump` + `rdflib.parse`，由两个 spec 实现负责 term 边界，移除手写的逐类型 term 映射。

- **mypy 全局 strict 门禁** —— `[tool.mypy]` 改为全局 `strict = true`，覆盖整个 `cataforge.*`；新包默认就在 strict 下、无需 opt-in 登记，全树类型基线收敛到 0 error。CI `test.yml` 的 mypy step 从「全仓 informational + 单包 gate」改为单一阻塞的 `mypy src/cataforge`，任何新类型错误都会让 PR 失败。仅两处豁免：`_generated` codegen（`ignore_errors`，手改注解会被重新生成覆盖）与 3 个无 stub 第三方库 `pyshacl` / `linkml_runtime` / `docker`（`ignore_missing_imports`）。动态边界（pyoxigraph 查询结果、jinja render、entry-point 加载）统一经一个 `_sparql_utils.select_rows()` helper 或局部 `cast` 收窄。

- **实体定义判定收紧为标题锚定** —— 非从属实体仅当 entity-id 是其所属 section 标题的主语（标题首个 entity-id token）才算定义；他处裸提及不再铸节点，仅 xref 提及经 `relation_extract` 成边。消除"提及即定义"导致的虚假跨文档碰撞。

- **KG 读侧 facade 解析从属实体 IRI** —— `query.entity/exists/depends_on` 与 `trace.coverage/from_requirement` 在扁平 IRI 不存在时回退到按 `cf:entity_id` 字面量解析实际节点，使按裸 id 访问 `AC-NNN` 仍可命中父限定节点。

### Fixed

- **`cataforge kg import` 不再静默坍缩跨文档同名实体** —— 扁平 `cfprj:<entity_id>` IRI 让 entity_id 项目级全局唯一，同一 id 在多个 doc_type 中被定义且内容不同时会坍缩成单节点、last-writer-wins 丢数据，而 verify / `doctor` 仍假绿。现 import 在写库前检测"≥2 个不同 source_doc 且 ≥2 个不同 content_hash"的碰撞并以 `KGVerificationError`（exit 3）中止，信息提示跨文档语义漂移并要求先统一 markdown 再迁移；`doctor` 的 `kg_ingestion_completeness` 复用同一检测，从 markdown 侧暴露存量已导入 store 的坍缩。内容一致的跨文档复述仍正常去重，不受影响。

- **`cataforge phase status` recognises the agile merged phases** —— `planning`（融合 requirements+architecture，同时校验 prd 与 arch）与 `brief` 现为已知阶段；此前被驱动的 agile-lite/agile-prototype 项目会在阶段门禁结构性失败。
- **`phase status` 的 doc-present 检查遵循 `docs/{doc_type}/` 子目录约定** —— 扫描子目录（按 frontmatter `doc_type` 过滤，排除误放的他类文档）并保留扁平路径回退；按约定产出的文档不再被误判缺失。
- **`cataforge event log` / `context *` 继承全局 `--project-dir`** —— 这些子命令此前只读自身 `--project-root`，在 `--project-dir` 隔离场景下会静默写入宿主项目。
- **审查类 skill 的自动事件归属到真实生命周期阶段** —— `CATAFORGE_EVENT_PHASE` 未设时，skill runner 回退读取项目指令文件的「当前阶段」，而非硬编码 `development`。
- **`cataforge context reconcile/finalize/ingest` 在 KG store 缺失时干净退出** —— CLI 边界捕获 `KGStoreNotInitializedError`，渲染为带 `kg init` 提示的 `Error:`，不再泄漏 traceback。

- **生成器模板使下游 AGENT.md 通过 framework-review B1-α** —— `workflow-framework-generator` 的 `agent.md.tmpl` 原先输出合并段 `## Input/Output Contract`，匹配不到 B1-α 要求的独立 `Input Contract` / `Output Contract` 两条正则，导致每个生成框架"出生即不合规"；现拆为两个独立二级标题，并在生成器结构完整性检查中加入该自校验项。
- **penpot-review 设计审查报告补全 front matter** —— 报告模板原以 `# 标题` + HTML 注释起始、无 YAML front matter 且无修订号，会被 `cataforge docs index` 跳过、被 `doctor` 计为 orphan 并 FAIL；现补 `id`/`doc_type: design-review`/`author`/`status`/`deps` front matter（元数据迁出注释）+ 路径加 `-r{N}` 编号，并在 COMMON-RULES 报告 front-matter 表登记 `design-review` 类别。
- **`RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT` 纳入常量 SSOT** —— 该上游反馈触发阈值此前仅存在于代码与 docs/reference，未登记进 `framework.json#/constants` 与 COMMON-RULES 常量表，违反"表镜像 constants"的单一事实来源契约；现两处补登记（值 3），framework-feedback 同步删去内联裸值。
- **`deploy_drift` hook 在四平台显式声明 `native`** —— 各 `profile.yaml` 的 `degradation` 段原缺该条目、靠隐式 `.get(..., "native")` 兜底，触发 framework-review B6-δ 覆盖告警；补显式声明后告警清零，行为不变。

- **flat-layout 平台上 agent 协议跨引用悬空** —— Claude Code / OpenCode / Codex 按 `<name>.md` 扁平部署，不复刻源 `<name>/AGENT.md` 子目录及 sibling 协议文件。orchestrator 等用 `{AGENTS_DIR}/<name>/<file>` 写的跨引用会渲染成部署树里并不存在的子路径（如 `.claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`），运行时定位失败。全部此类跨引用改用 `{AGENTS_SRC_DIR}` 后落到真实源文件，所有平台一致。`_resolve_agents_dir` 的 docstring 同步修正（原先平台分类写反、且声称 flat 平台 sibling 引用"指向源覆盖层"与实现不符）。

- **部署的 CLAUDE.md / AGENTS.md `框架版本` 字段现自动盖入已安装包版本** —— `cataforge deploy` 把指令文件模板里的 `{FRAMEWORK_VERSION}` 占位符渲染为 `cataforge.__version__`，并通过 section-merge `always_overwrite_fields` 在每次重新部署时刷新。

此前 `框架版本` 是静态描述文本、没有任何确定性写入路径（唯一写入者是升级 skill 的 AI Edit，纯 CLI 升级路径拿不到），导致升级后版本号停留在占位文本或首次部署的旧值，与 `framework.json.version` 漂移。现与 `运行时` 字段、`framework.json.version` 盖版本同等确定性：占位符 `{FRAMEWORK_VERSION}` 注册进渲染器，四平台 profile 的 `always_overwrite_fields.项目信息` 追加 `框架版本`。

- **`section-merge` 每次 deploy 删除 heading 后空行** —— `update_strategy: section-merge` 的 H2 解析正则 `\s*$`（`\s` 含换行）会连 heading 行尾换行一起吞掉,带走它与正文之间的空行;叠加 `_merge_fields` 丢弃空白 header、`_serialize` 不保证 section 之间有空行,使每次 `cataforge deploy` 都从 `CLAUDE.md` / `AGENTS.md` 删空行、产生 churn diff 并违反 MD022。正则收紧为 `[^\S\n]*$`、`_merge_fields` 保留 leading 空行、`_serialize` 在每个 `##` heading 前强制空行,deploy 对规范 markdown 自此幂等。

- **`cataforge kg import` 不再坍缩跨父 / 跨文档的同号从属实体** —— 从属实体按 `(parent_id, entity_id)` 去重并铸父限定 IRI，dev-plan 各任务卡的局部 `AC-001` 与 prd 各 Feature 的 `AC-001` 各自成节点；`kg reconcile` 按 scope key（普通实体 = `entity_id`，从属实体 = `parent/entity_id`）对账，跨父同号不再永久 divergence。父链经 `cf:part_of` 边记录，对账时排除该结构边。

### Removed

- **删除 `--no-deploy` 已废弃垫片** —— `cataforge setup` 不再接受 `--no-deploy`（自 0.2 起已是 no-op 默认行为）。
- **移除未接线的 `nl_query`（NL→SPARQL）模块** —— 该实验性表面无任何 CLI 入口，连同其 codegen 的 `governance_pydantic` 产物一并移除。

- **运行时依赖瘦身** —— `pytest` / `pytest-cov` 从 `[project.dependencies]` 移除（运行时零 import，仅测试用），保留在 `dev` extra；下游 `pip install cataforge` 不再拉入测试框架。

### BREAKING

- **从属实体改用父限定复合 IRI（KG 快照格式变更）** —— `AcceptanceCriteria`（`AC-NNN`）等从属实体的实例 IRI 由扁平 `instance/AC-001` 改为父限定 `instance/{parent_id}/AC-001`，使同号 AC 在不同 Feature/Task 下成为不同节点而非坍缩。既有 `.nq` 快照与新 IRI 不兼容，下游需重新导入。迁移：

  | 如果你曾依赖 | 改为 |
  |------------|------|
  | 扁平 `instance/AC-001` 实例 IRI | 父限定 `instance/{parent_id}/AC-001`（普通实体 IRI 不变） |
  | 旧 KG `.nq` 快照 | 删除后 `cataforge kg init && cataforge kg import` 重新导入 |
  | 按裸 `entity_id` 查从属实体 | 仍可用（facade 回退到 `cf:entity_id` 字面量解析），但同号多父时取首个匹配 |

## [0.7.0] — 2026-06-01

### Changed

- **Mid-Progress 落盘契约扩展到 reviewer / test-writer / debugger** —— 此前契约仅在 tdd-engine 对 implementer 注入；现为三个 agent 的 AGENT.md 各加一个适配自身产出物的落盘契约（reviewer：先落 REVIEW 报告骨架再逐维度追加；test-writer：先落测试骨架再逐 AC 填充并即时验证；debugger：增量最小修补 + 停滞时返回已排除假设与最佳线索），使长产出子代理被 task-notification truncation 打断时发出 mid-progress checkpoint 而非零产出静默返回。落点选 AGENT.md 因 `claude-code/profile.yaml` 仅 eager 注入 COMMON-RULES、AGENT.md 经 subagent_type 自动加载且不膨胀其他 agent。

- **deploy-spec 评审强制本地最小栈验证证据** —— deploy-spec 模板 `required_sections` 新增 `## 5. 本地最小栈验证证据`（启动命令 / 验证项 / bring-up 日志摘录 / 已核对部署面），doc-review Layer 1 `check_required_sections` 自动强制该段存在且非空；review Layer 2 加 deploy-spec 专属维度，核对证据为真实 bring-up 日志而非占位，否则 needs_revision。评审前被强制要求人工启动最小栈留证。

- **工作流状态唯一化到平台指令文件** —— `## 项目状态`（当前阶段 / 文档状态等）不再写入独立的 `.cataforge/PROJECT-STATE.md`，而是唯一承载在目标平台的指令文件（claude-code → `CLAUDE.md`，cursor / codex / opencode → `AGENTS.md`）的对应 section。`deploy` 从包内 PROJECT-STATE.md 模板生成指令文件（section-merge 保留运行时状态）；`cataforge phase` 经 `resolve_instruction_file` 跨平台解析并读取指令文件而非 PROJECT-STATE.md。

### Removed

- **下游不再部署 PROJECT-STATE.md** —— scaffold / `upgrade apply` 不再向项目发放 `.cataforge/PROJECT-STATE.md`（降级为包内模板源），消除它与项目根指令文件之间的状态双写冗余。已有项目的指令文件 `## 项目状态` 已由历次 deploy 镜像最新状态，迁移后直接沿用。`mc-0.1.7-cataforge-dir` migration check 不再要求 PROJECT-STATE.md。

## [0.6.1] — 2026-06-01

### Added

- **覆盖层（overrides）** —— `.cataforge/overrides/{user,project}/{agents,skills}/` 两层升级免疫的定制层，优先级 `user > project > 发货层 > 插件 > builtin`。支持整文件覆盖与 `<name>.patch.md` section 补丁（覆盖已有 `##` section + 追加新 section）。新增 `cataforge override {list,eject}`。
- **项目语言 SSOT** —— `framework.json` 新增 `project.languages`；`cataforge.core.languages` 注册表统一定义语言 canonical id / marker / 扩展名，`active_languages()` 声明优先、marker 探测兜底。`cataforge setup --language <id>`（可重复）声明语言。
- **插件 `provides_*` 消费** —— 插件的 `provides.{skills,agents,hooks,mcp_servers}` 被 SkillLoader / 资产 resolver / hook bridge / MCPRegistry 真正消费（插件资产位于发货层之下）。`cataforge plugin install/remove` 实装（本地目录拷入 `.cataforge/plugins/` 或 pip 包安装/卸载）。
- **可注册 rule_type** —— skill 规则加载器的 rule_type 改为 `register_rule_type()` 注册表，内置 `wiring` / `e2e` / `doc_terms`，项目 / 插件可扩展新规则族。
- **agent 语言细则注入** —— 声明 `lang_aware: true` 的 agent 在部署时按 `active_languages()` 追加 `## 语言细则` 段，链接 `.cataforge/agents/<id>/rules/lang-<lang>.md` 片段；agent 主体保持语言无关。

- **上下文能力端口 + 保真度路由(application 层)** —— 新增 `cataforge.application.context`:能力端口(`ContextReadPort` / `RelationPort` + `Fidelity` 三态 native/degraded/unsupported)、两个后端(`KgBackend` / `DocBackend`,各自按 operation 声明保真度)、`FidelityRouter`(按 `context.strategy` 装配启用后端,按 operation 取保真度最高且可用者,逐个回退),以及 routed 读门面 `read.py`(`extract` / `extract_batch` / `plan_load` / `resolve_deps` + `cataforge docs load` 编排)。`build_router(project_root)`:`kg-first` 启用 `[kg, doc]`,`doc-only` 仅 `[doc]`。

- **统一 `context` 父 skill + 分支 reference** —— 新增 `.cataforge/skills/context/SKILL.md` + `references/{navigate,generate,review,consistency,query}.md`,作为文档生命周期 I/O 的单一能力入口(读取/关系查询/生成写入/校验),指向 `cataforge context` / `cataforge docs` 门面;后端(图/文件)与保真度由框架按 `context.strategy` 路由,调用方只表达意图。`context` 计入 framework-review orphan 白名单(与 doc-nav/doc-gen 同类的基础设施 skill)。

- **`context.strategy` 配置契约** —— framework.json 新增 `context` 段,`strategy ∈ {kg-first, doc-only}`(默认 `kg-first`),声明上下文 I/O 的后端拓扑:`kg-first` 以知识图谱为事实源、Markdown 为导出审查视图;`doc-only` 以 Markdown 为源、无图后端。`cataforge.domain.kg._dispatch.context_strategy(project_root)` 解析(缓存,未声明 / 非法值回退默认)。

- **KG-first 授权写路径 + `cataforge context` 门面** —— 新增 `application.context.write`:`author_entity`(写时 schema 校验——entity_id↔class 前缀确定性闸门 + 提交后 `validate` 复核,违规即补偿删除并报错)、`write_narrative`(直接把 Section 散文写入图)、`finalize`(KG→md 导出供人审查)、`ingest`(人工修订 md→KG 回灌)、`reconcile_check`(漂移守门)。新增 `cataforge context` CLI 命令族(`read` / `write` / `write-narrative` / `finalize` / `ingest` / `reconcile`)作为统一后端路由门面,调用方不指名图或文件。

- **`cataforge phase status`** —— 只读校验当前 SDLC 阶段应有产物（阶段非占位符、期望文档存在且已 index、有 phase_start、文档状态非未开始），缺失即非零退出。
- **platform-audit 离线子集** —— `cataforge skill run platform-audit -- --offline` 静态跑 conformance + 一致性 + profile schema，FAIL 级阻断 PR、已接入 CI guards。
- **`cataforge setup --context-strategy`** —— 显式选 `kg-first` / `doc-only` 上下文后端，scaffold 缺失时交互提示。
- **profile 时效守卫** —— `check_profile_version_tested` 进 anti-rot 周扫，平台 profile 超 180 天未更新即告警。

- **`kg-ask` 知识图谱自然语言查询 skill** —— 把自然语言问题翻译为只读 SPARQL，对项目知识图谱（需求/模块/任务/测试的追溯关系）检索并用中文回答。新增 `cataforge kg schema-context` 子命令输出 schema card（实体类 / 追溯谓词 / 标量 slot / 示例查询，从 ontology 注册表派生，零 store 依赖）；翻译由宿主 agent 据 card 完成，执行与写守卫 / LIMIT 注入复用既有 `cataforge kg query`，无新增运行时依赖。

- **`cataforge kg diff SNAPSHOT_A SNAPSHOT_B`** —— 对两份 `kg snapshot` 产物做实体/关系级语义 diff（added / removed / content-modified 实体 + added / removed 追踪关系），`--json` 输出，差异时退出非零；bootstrap 子类公理不计入。

- **KG 文档/章节/卷本体** —— `core.yaml` 新增 `Document` / `Volume` / `Section` 三个结构性类(与 `Project` 同为 standalone,以 `id` 标识,不继承 `SoftwareArtifact` 的 entity_id/sort_key 约束)。`Section` 携带 `narrative_body`(散文)与 `contains_entity`(其下结构化实体),`SoftwareArtifact` 增 `located_in_section` 回指;配套 `has_volume` / `has_section` / `part_of_document` / `part_of_volume` / `doc_type` / `volume_type` / `section_anchor` slot。使整篇文档(结构化实体 + 散文)成为图的一等内容,为知识图谱成为完整后端、whole-section 走图奠定本体基础。codegen / subclass-axioms / schema-context card 均兼容,无运行时行为变更。

- **Page / Task 标量 slot ingest 抽取器** —— ingest 现从 section 内行内标签（`- Route:` / `- Layout:` / `- Status:`）抽取 `ui_route` / `layout_spec` / `task_status`，填入实体 `extra_slots`；`task_status` 归一化到 `TaskStatusEnum` 并丢弃非法值。此前这些标量从不被 ingest 产出，专用导出模板对应章节对真实 ingest 永远为空。

- **ingest 写入文档/章节结构节点** —— `cataforge kg import` 在写实体/关系之外,新增 Phase 3b:每个业务文档落一个 `Document` 节点,每个**实体所属章节**落一个 `Section` 节点(携带 `narrative_body` 散文、`content_hash`、`contains_entity` → 其下实体、`part_of_document`),`Document` 经 `has_section` 串联。结构节点以 `id` IRI(`/doc/...`、`/doc/.../sec/...`)标识、不带 `cf:entity_id`,与实体 IRI 隔离;按 `content_hash` 幂等(未变源零新增三元组)。`MigrationStats` 增 `documents_*` / `sections_*` 计数。

- **ui-spec / dev-plan 专用导出模板** —— `Page` / `UIComponent` / `Task` 现以专用模板导出，渲染 ingest 产出的 `satisfies` / `realizes` / `verifies` 追踪边为带链接的章节，并条件渲染 `ui_route` / `layout_spec` / `task_status` 标量；此前这些实体走 generic 模板、关系全部丢失。

- **whole-section 读路径走图** —— `cataforge docs load <doc>#§N`(无实体的整章引用)在 active doc_type 下从 KG `Section` 节点的 `narrative_body` 解析,不再被拖回文件切片。ingest 现为**每个 §-级标题**(level ≥ 2,含无实体的纯散文章节)落 Section 节点,使整篇文档结构皆为图内容;`loader._try_kg_extract` 按章节号匹配 `cf:section_anchor` 取 body,未命中再回退文件。`narrative_body` 尾部空行裁剪,与文件切片字节对齐。

### Changed

- **`upgrade apply` 保留用户改动** —— 强制刷新 scaffold 时，被手改过的（user-modified / drift）文件不再被覆盖，框架新版本写到同目录 `<文件名>.cataforge-new` 旁路文件供手动合并；`project.languages` 与 `context.kg_active_doc_types` 同列升级 preserve 字段。
- **skill 规则 / agent / skill 跨层解析** —— `discover_rules` 与 `SkillLoader` 按覆盖层 + 插件 + 发货层顺序解析；`deploy` 在存在覆盖 / 插件资产 / 激活语言时将 agents·skills 经临时 staging 解析落地（无以上情形时与旧流程逐字节一致）。

- **读路径分发上抬到 application 层** —— "先试 KG 再兜底文件"的策略分发从 domain 的 `loader` 上抬为 application 的 `FidelityRouter`(orchestration 是 application 职责,非 domain)。`domain.docs.loader` 回落为纯 doc 后端原语(`extract` / `plan_load` / `resolve_deps` 不再触图,不再反向依赖 router);`cataforge docs load` CLI 改由 `application.context.read.main` 编排。非对称由设计:文件后端对 deps/plan_load 仅 `degraded`(静态 `.doc-index.json`),图后端 `native`(`cf:depends_on` 闭包);`doc-only` 下 KG 后端不参与(拓扑选择,非故障兜底)。

- **全量重指引用与守卫至 context** —— 13 个 AGENT.md 的 `skills:`、17 个 SKILL.md 的 `depends:`、harness 散文、`doctor` migration_checks(模板/常量锚点)、doc_review 模板注册表路径(`template_registry.py`)、framework-review 常量(`ORPHAN_SKILL_WHITELIST` / `B1_REQUIRED_SECTIONS_EXEMPT_SKILLS`)、skill 计数文档(31 → 26)、agents-and-skills 目录与 agent→skill 映射,统一指向 `context`(或其 builtin)。framework-review `all` 由基线 3 WARN 收敛为 0 FAIL / 0 WARN。

- **删除散落 harness 的分发复述与实现细节泄露** —— 从 COMMON-RULES §Agent 文档 I/O 契约、doc-nav / doc-gen / doc-review / doc-consistency 的 SKILL 正文、change-guard、task-dep-analysis、ORCHESTRATOR-PROTOCOLS 中移除"KG-active vs legacy 分流"条件复述与 `kg_active_doc_types` / `framework.json.kg` / SPARQL / `cf:` 谓词 / `kg.query` / `render_entity` / `cataforge kg import|reconcile`-作分发条件等实现细节;改为"后端由框架透明路由,调用方不在 prompt 里判断走哪个后端"。skill 计数文档同步 30 → 31。

- **`kg_active_doc_types` 迁移到 `context` 段** —— 该键从 `kg` 段移到 `context.kg_active_doc_types`,成为上下文 I/O 路由是否走图的规范归属;`kg` 段只保留 store 级连接配置(store_backend / db_path / 命名空间)。`_dispatch.active_doc_types`、doctor `kg_ingestion`、scaffold upgrade 保留逻辑、`kg import` 默认范围、`workflow-framework-generator` 模板均改读 `context`。

- **写路径方向翻转为 KG-first** —— 生成走"授权写图(实体 + 叙述 slot,写时校验)→ 导出 markdown 供人审查",取代旧的"先写 md 再 import"投影:结构化实体与散文先入图(经校验),文件树由其派生。`reconcile` 由永久补丁降级为人工回灌后的轻量守门。

- **conformance 一致性检查升 WARN** —— web_fetch→shell 工具替换、computer_use×browser_preview 路由不可见、worktree_isolation 缺 isolation 字段、native 离群 hook、deploy_rules 路径偏离。
- **opencode 插件携带 matcher_agent_id 前置过滤** —— 非匹配 agent 不再 spawn Python 进程。
- **framework-review B9** —— migration_checks 三维结构审查（path 真实性 / allow_missing 类型 / deprecate_after 时序）。
- **doctor 反向孤儿检出** —— 部署 manifest 中 source 已删的 skill 发 WARN。

- **conditional_release 的归属与判定条件归位** —— `COMMON-RULES.md` §三态判定逻辑保持公共三态（reviewer 适用），仅加一句指针说明 qa-engineer 扩展第四态；conditional_release 的判定条件（"唯一未决项是因环境/CI 不可达的非缺陷阻塞时选用"）落到 `qa-engineer/AGENT.md`；§统一状态码 点明 conditional_release 是 verdict 而非 status 枚举。
- **多个 SKILL 补触发场景句** —— `req-analysis` / `start-orchestrator` / `tech-eval` / `agent-dispatch` / `task-decomp` / `testing` / `ui-design` 的 description 补"当…时使用"触发句，提升 LLM 自动调用准确率；`start-orchestrator` 能力边界由同义反复改为实际动作清单。
- **Anti-Patterns 格式统一为对比式** —— `framework-feedback` 与 `reviewer/AGENT.md` 的若干条由陈述句改为"禁止/避免 + 对比"格式。
- **debug skill 与语言解耦** —— Python/Windows 特定问题模式表下沉到新增的 `docs/reference/debug-patterns.md`，skill 主体改链接引用并改用语言无关表述。
- **`debugger` allowed_paths 收窄** —— 移除 `.cataforge/skills/`（prompt 文档，非可调试脚本），保留 dogfood 所需的 `.cataforge/scripts/` 与 `.cataforge/hooks/`。
- **元资产整洁度精简** —— `orchestrator/AGENT.md` 去除版本锚定表述；`workflow-framework-generator` 折叠领域模式预览表与扩展机制清单为指针/单行；`tdd-engine` 将重复的 dispatch 引导句提取为 §TDD 子代理共享约束 单一声明（行为中性）。

- **reconcile 纳入结构节点漂移** —— `cataforge kg reconcile` 在实体/关系对称差之外,新增按 `cf:source_doc` 归属的 `Section` 节点对称差(`missing_sections` / `ghost_sections`),计入 `divergence_count`。
- **验证/校验放行结构节点** —— hand-rolled `validate` 的 `entity_id-required` 形状、`verify_after_write` 的实体计数、export 实体枚举均把 Document/Volume/Section 视为 `id` 标识的结构节点排除,不再误报或误算。doctor `kg_ingestion_completeness` 仍为实体级门(结构漂移由 reconcile 守)。

- **Section 发射范围扩到全部 §-级标题** —— Phase 1b 仅落实体所属章节,现落每个 `§` 标题;`contains_entity` 仍只挂在实体的最内层归属章节,父章节承载散文。reconcile 的 Section 对称差随之覆盖全部章节。

### Fixed

- **语言规则运行期接线** —— code-review wiring / testing e2e 的项目覆盖规则此前在 import 期被冻结、运行期被忽略；现按 `cataforge skill run` 注入的项目根逐次解析，覆盖 YAML 改完即生效。

- **claude-code `reads_claude_md`** —— 订正为 `true`（原 `false` 与原生加载 CLAUDE.md 语义相反）。
- **section-merge 保留下游手写指令文件** —— 与模板零 schema/runtime 重叠时整体保留 + 仅追加框架导航，不再注入模板章节。
- **translator skills 字段降级提示** —— codex/opencode 不部署 skills 时丢弃 `skills:` 发 WARN，不再静默。

- **`detect_review_flag` 降级根因更正** —— `hooks.yaml` 与 `docs/reference/platform-capability-matrix.md` 原把 codex 降级归因为"依赖 schema v2 `matcher_agent_id`，v1-only 平台无法约束"，与运行时实现（`matcher_agent_id` 由 Python 在 hook 内强制，与平台 schema 版本无关）相悖；更正为真实根因"依赖 agent_dispatch 的 PostToolUse 匹配，无 agent matcher 的平台不触发"。
- **`penpot-sync` 默认 `bidirectional` 与 Anti-Pattern 自相矛盾** —— Step 4 澄清默认双向为"以 ui-spec 为唯一权威源的两次受控单向写出，不反向读回"，Anti-Pattern 改为针对"无权威源的双向自动回写覆盖循环"。
- **`arc-design` Anti-Pattern 引用不存在的章节** —— 由"§6 部署运行时"更正为真实存在的"§5.4 配置管理"。
- **`framework-review` 白名单重复项 / category 枚举缺漏** —— 去除 B2-α 白名单中重复的 `context`；§问题格式 category 枚举补上下文已使用的 `dead-code`。

### Removed

- **删除已被 context 取代的扁平 skill** —— 移除 `doc-nav` / `doc-gen` / `doc-review` / `doc-consistency` / `kg-ask` 五个 `.cataforge/skills/*/SKILL.md`(及目录),其能力已收敛进 `context` 父 skill 的 navigate/generate/review/consistency/query 分支。`doc-gen` 的 `templates/` 迁入 `.cataforge/skills/context/templates/`。`doc-review` / `doc-consistency` 的 runtime builtin 保留,`cataforge skill run doc-review|doc-consistency` 经 `_BUILTIN_ID_MAP`(新增 `doc_consistency` 映射)继续解析,作为 context review/consistency 分支的 Layer-1 引擎。

## [0.6.0] — 2026-05-29

### Added

- **KG section in `framework.json`** —— `framework.json` 现包含 `kg` 顶级配置块，脚手架生成的 `framework.json` 模板同步跟进。

- **COMMON-RULES §Agent 文档 I/O 契约（KG-active 通用约定）** —— 把"写后 finalize 自动 KG ingest / 读时 `cataforge docs load` 自动 KG dispatch / drift 检查由 orchestrator 负责"等约定集中到 `.cataforge/rules/COMMON-RULES.md`，13 个 Agent 的 Input/Output Contract 不再重复这条规则。
- **`mc-0.5.0-kg-config` migration_check** —— `cataforge doctor` 检查 `framework.json` 必须声明 `kg.kg_active_doc_types`；缺失会让 finalize / docs load / Phase Transition 静默走 legacy，掩盖 KG cutover 的覆盖率门。
- **doc-consistency KG dispatch** —— `check_prd_arch_ac_coverage` 与 `check_prd_devplan_ac_traceability` 在 active doc_type 下改用 SPARQL（`cf:source_doc` + 任意谓词指向 AC URI 的查询），消除 regex 在代码块 / HTML 注释 / 跨分卷 ID 出现上的假阳性 / 假阴性；其余检查（NFR 映射、优先级对齐、API 端点契约）仍走 regex，无 KG 等价。

- **Runtime placeholder renderer** —— `cataforge.core.template.render_runtime_content` resolves `{INSTRUCTION_FILE}` / `{AGENTS_DIR}` / `{RULES_DIR}` / `{SKILLS_DIR}` / `{COMMANDS_DIR}` to platform-native values driven by each platform's `profile.yaml`. Source files now carry a uniform token surface; the deployed artefact ships with platform-correct paths baked in (no more `CLAUDE.md` literal on Cursor / Codex / OpenCode projects).
- **Unified `deploy_overrides_rules` flow** —— `.cataforge/platforms/<id>/overrides/rules/*.md` is now scanned by a base method that routes through `_wrap_rule_for_platform`. Cursor wraps as MDC with `alwaysApply`; Codex / Claude Code copy verbatim to the declared rules dir; OpenCode registers in-place via `opencode.json#instructions`. Closes the silent-drop path that left `prompt_instruction` / `prompt_checklist` outputs unmaterialised on Codex.

- **`cataforge kg add` / `kg update` / `kg delete` CLI** —— surface the `TransactionContext` high-level CRUD (`add_entity` / `update_entity` / `delete_entity` / `add_relation`) as 3 click subcommands so ops & one-off scripts no longer need to drop into Python. `add` auto-detects the store's unique `cf:Project` node (or accepts `--project-id` + `--project-title` + `--project-process` to materialize one); idempotent on identical `--content-hash`; `--slot KEY=VALUE` and `--relation PRED=OID` are repeatable. `update` requires at least one of `--title` / `--source-section` / `--slot` / `--content-hash`, short-circuits when `--content-hash` matches. `delete` defaults to an interactive prompt (skip with `--yes`), refuses entities with incoming edges unless `--cascade`. All three honour `--json`. Closes backlog C3 / C4 / C5.

- **`cataforge.core.io.read_json` / `read_yaml`** —— 集中"读 UTF-8 文本 → 解析 → 失败时带路径抛 `ConfigError`"模式（此前在约 30 处手写）。空 YAML 文档归一为 `{}`。供"配置文件缺失/损坏应清晰报错"的读取点复用；刻意容忍缺失的尽力读取点保留各自的 try/except 默认值语义。

- **KG 渲染泛化 fallback** —— 新增 `export/sparql/_artifact.sparql`（core-slots 查询）+ `export/templates/_base/artifact.md.j2`（继承 artifact_base）。任意 `SoftwareArtifact` 子类无 bespoke 模板时经此渲染，`render_entity` / `compile_to_markdown` / `docs load` 不再对 ui-spec(Page/UIComponent) / dev-plan(Task) / deploy-spec(Deployment 等) 退回文件切片。bespoke 模板（feature/module/testcase/techstack）仍作为带 relations 的覆盖。

- **圈复杂度门禁** —— ruff 启用 `C901`（`max-complexity = 20`），最高复杂度的函数已拆分到阈值以下。
- **分层依赖方向守卫** —— `scripts/checks/check_layer_dependencies.py` 强制 `interface → application → {runtime, domain} → adapter → core → utils` 的模块级 import 方向（lazy / `TYPE_CHECKING` import 豁免，可用 `# allow-layer-dep:` 行内例外），纳入 pre-commit 与 `run_local.py`。

- **Penpot 构建工具链缺失的诊断模式** —— `penpot doctor` / 启动失败报告新增对 `ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL` 及 `Cannot find module …tsc|esbuild` 的识别，命中时提示 Node 版本超出兼容范围、改用 v22 LTS 重试。

### Changed

- **v0.5 参考文档对齐** —— `docs/reference/` 下 `agents-and-skills.md`、`cli.md`、`configuration.md`、`quick-reference.md` 与 v0.5 实现保持一致，涵盖 KG 查询 / 追踪 CLI 及相关配置。

- **doc-review SKILL.md** —— 文档化 `check_xref` / `check_bidirectional_coverage` 的 KG 分流（checker 实现自 v0.5.0 起已具备，SKILL.md 同步说明）。
- **task-dep-analysis SKILL.md** —— Step 1 加 KG 优先数据源：`cataforge kg query` 取 `cf:depends_on` 三元组，直接转 `--edges`；legacy 仅在非 active doc_type 或 KG 不可用时回退。
- **change-guard SKILL.md** —— Step 2 文档覆盖度扫描在 active doc_type 下改用 `cataforge kg trace --direction both` + `--coverage`；legacy doc-nav grep 仅作为回退。

- **`deploy_skills` / `deploy_rules` / `deploy_commands` default switched from symlink to copy + render** —— placeholders in `SKILL.md` / `COMMON-RULES.md` must be substituted before the IDE reads the file, which requires an independent copy. Trade-off: source edits no longer round-trip without a redeploy.
- **`deploy_agents` preserves and renders sibling `*.md`** —— `ORCHESTRATOR-PROTOCOLS.md` / `ORCHESTRATOR-META-PROTOCOLS.md` and any other sibling under `.cataforge/agents/<name>/` now land in the platform's agent subdir alongside `AGENT.md`, with stale siblings pruned only when the prior manifest claims ownership.
- **`deploy_instruction_files` applies the runtime renderer** —— the user's `CLAUDE.md` / `AGENTS.md` ships with `{INSTRUCTION_FILE}` / `{RULES_DIR}` / `{AGENTS_DIR}` already substituted in the `§文档导航` block (and anywhere else the template uses them).
- **67 `CLAUDE.md` references migrated to `{INSTRUCTION_FILE}`** —— orchestrator triplet, implementer / reviewer / ui-designer `AGENT.md`, `start-orchestrator` / `self-update` / `penpot-*` / `framework-review` / `ui-design` `SKILL.md`, `bootstrap.md`. Cross-file path references like `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` migrated to `{AGENTS_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md` in deployed files. `COMMON-RULES.md` uses the Chinese phrase "项目指令文件" instead, because Claude auto-injects it from source via preamble where the renderer does not run.
- **Dogfood whitelist** —— `.cataforge/commands/` and `.cataforge/PROJECT-STATE.md` added so framework template updates can ship through `prepare-pr.sh`. The stale "PROJECT-STATE.md gets written during dogfood" note is removed; the file is now treated as a template (parallel to `framework.json`), protected at runtime by `_preserve_if_exists` so existing downstream copies are never clobbered by `cataforge upgrade apply`.

- **`CompileResult.entity_count` → `discovered_count`** —— 该字段计的是 source 扫描发现的实体数（含 skip / error），不是渲染数；改名让两个计数（`discovered_count` vs `len(file_records)`）语义不再混。代码内调用方已全部更新，0.4.x 时期未暴露此 dataclass 给外部。
- **`validate._check_orphans` / `_check_xref_targets` 改为单次 SELECT + OPTIONAL** —— 之前每条 entity 跑 2-3 个独立 ASK（N+1 模式），整库大时明显拖慢。改 union + OPTIONAL 单次扫表，行为不变。
- **`trace.bidirectional_coverage` 笛卡尔积消除** —— 之前用并列双 OPTIONAL，一个 Feature 有 N 个 impl + M 个 TestCase 返回 N×M 行；改为 3-pass `FILTER EXISTS` 子查询，O(N+M)。
- **`shim.plan_load` per-item 分流** —— 之前整批用单一 boolean 决定走 KG 或 legacy，批次混了 active / inactive doc_type 时要么整批崩、要么整批降级；现在按 ref 单独判定再合并。
- **`KnowledgeGraph.open_store()` 公开 API** —— facade 不再让调用方直接 import `_open_pyoxigraph` 私有符号。
- **`update_entity()` 自动写 `cf:updated_at`** —— partial update 改 slot 后 `updated_at` 现在跟着刷新，下游 reconcile / verify 能感知 mutation 时间。
- **`kg_config_for()` 读完整 `framework.json.kg` 节** —— 之前只读 `kg_active_doc_types` + `db_path`，其它字段（`governance` / `coverage_mode` / `query_timeout` 等）走 dataclass 默认值；现在 framework.json 里写什么读什么。
- **`snapshot.restore_snapshot` 异常归一为 `KGError`** —— 之前抛裸 `FileNotFoundError` / `PermissionError` / `IsADirectoryError`，调用方需要 catch 多种 OS 异常；现在统一包成 `KGError(... from exc)`。

- **`ConfigManager.load` / `load_raw` 经 `read_json` 读取 framework.json** —— framework.json 损坏时抛出统一的 `ConfigError`（在 CLI 边界渲染为 `Error: Malformed JSON in ...`）而非裸 `json.JSONDecodeError`。`collect_environment` 相应改为捕获 `ConfigError` 以维持对损坏配置的诊断容忍。

- **framework-review 检查的 profile.yaml / hooks.yaml 读取改用 `core.io.read_yaml`** —— `b5` / `b6` / `b7` 的 `yaml.safe_load(path.read_text(...))` + `except (OSError, yaml.YAMLError)` 收敛为 `read_yaml(path)` + `except ConfigError`，移除各文件对 `yaml` 的直接依赖。行为等价（缺失文件由既有 `is_file()` 前置判断处理）。

- **全仓 JSON / YAML 文件读取收敛到 `core.io.read_json` / `read_yaml`** —— 把散落在 deploy / hook / adapter / doctor / mcp / docs / kg / scaffold 等约 30 处的 `json.loads(path.read_text(...))`、`json.load(open(...))` 手写读取统一为 `read_json(path)`，容忍点改捕 `ConfigError`（已同时覆盖 `OSError` + `JSONDecodeError`），抛错点获得带路径的统一报错。行为等价。

- **`kg_active_doc_types` 默认扩展为完整业务集** —— 由 `{prd, arch, test}` 改为 `BUSINESS_DOC_TYPES = (prd, arch, ui-spec, dev-plan, test-report, deploy-spec)`，0.5.0 全量支持这些 doc_type 的 KG 读路径。`test`→`test-report`：active 集现用 refs 实际使用的 doc_id，修复 dispatch 按 doc_id 匹配时 `test` 永不命中的接线缺口。
- **doc_type 集合单一事实来源** —— `cataforge.domain.kg._config.BUSINESS_DOC_TYPES` 统一驱动 `DEFAULT_KG_ACTIVE_DOC_TYPES`、ingest `DEFAULT_DOC_TYPES`、doctor `kg_ingestion` 默认集，消除三处硬编码三元组。
- **`kg import` 默认范围跟随 active 集** —— 不带 `--doc-type` 时从 framework.json `kg_active_doc_types` 推导（缺省回退到业务集），使 import 摄取范围与 doctor `kg_ingestion_completeness` 门禁范围一致，避免"激活了却没摄取→门禁红"。

- **分层包结构迁移** —— `src/cataforge/` 顶层包重组为分层结构：`cataforge.cli` → `cataforge.interface.cli`、`services` → `application.services`、`deploy`/`agent`/`skill`/`hook`/`mcp`/`plugin` → `runtime.*`、`platform`/`integrations` → `adapter.*`、`kg`/`docs` → `domain.*`、`schema` → `core.schema`（`core`/`utils` 保持顶层）。行为等价。直接 import 这些子模块、或通过 `python -m cataforge.skill.builtins.*` 与 hook 脚本模块路径调用的下游需同步路径；`cataforge` 控制台脚本与 entry-point 组名（`cataforge.plugins` / `cataforge.platforms`）不变。

- **`@penpot/mcp` 默认版本由 `latest` 固定到 `2.15.0`** —— `latest` 浮动会在上游 monorepo 引入新的 build-script 依赖时拉起 pnpm 10+ 的构建失败；`PENPOT_MCP_VERSION` 仍可覆盖以跟进更新版本。

- **`adapter/platform/_deploy_mixins.py` 拆分为同名包** —— 855 行的单文件按部署关注点拆为 `_deploy_mixins/{agents,instructions,skills,commands_rules,mcp}.py`，每个 mixin 与其单一消费者的模块级 helper / 常量同处一文件；`__init__.py` 重导出五个 mixin 类，保持 `from cataforge.adapter.platform._deploy_mixins import ...` 的导入面不变。顺带把 overrides/rules 路径改为经 `ProjectPaths.platform_overrides` 派生。纯结构性改动，行为等价。

- **`domain/docs/indexer.py` 抽出构建层到 `_index_build.py`** —— 把索引*构建*原语（`build_document_entry` / `build_xref` / `build_full_index` / `build_aliases` / `update_single_doc` / `write_index` / `_make_index` 及 dep-hash / section-meta 等 helper）移入叶子模块 `domain/docs/_index_build.py`；`indexer.py` 保留*校验*面（orphan / stale / xref / alias / invalid-id 检查）与 CLI 入口，并重导出构建器以保持导入面不变。校验器依赖构建器、构建器从不反向依赖，故拆分无环。纯结构性改动，行为等价。

- **`domain/docs/loader.py` 抽出 KG 桥接层到 `_loader_kg.py`** —— 把 `_try_kg_extract` / `_try_kg_plan_load` / `_try_kg_resolve_deps` / `_entity_id_to_ref` / `_all_active_parsed_refs`（KG-active 时的图分流，含惰性 kg 导入）移入 `domain/docs/_loader_kg.py`；公共 `extract` / `plan_load` / `resolve_deps` 仍在 `loader.py`。`parse_ref` 下沉到叶子模块 `index_ops.py`（与既有 ref 异常 / doc_type 映射同处），由 `loader` 重导出以保持 `loader.parse_ref` 与 `indexer` 的导入面，避免 loader↔_loader_kg 循环。纯结构性改动，行为等价。

- **路径解析统一收敛到 `ProjectPaths`（SSOT）** —— 将散落在 hook runtime、deploy manifest、docs index、framework-review 检查中的 `.cataforge/...` 字面量路径改为经 `cataforge.core.paths.ProjectPaths` 派生。新增 `HOOK_ERROR_LOG_REL` / `DEPLOY_MANIFEST_REL` 常量与 `hook_error_log` / `deploy_manifest` / `docs_dir` 属性，并新增 `find_project_root_or_none()`（无 cwd 回退、无告警）供"非项目内不得动作"的尽力日志/平台探测路径分支使用。删除 `runtime/hook/base.py` 中与 `find_project_root` 重复的 `_find_framework_json` 上行游走逻辑。对外行为等价。

- **测试套件并行化与 fast/slow 归类修正** —— `tests/e2e/test_docs_nav.py` 补 `pytest.mark.slow`，不再在 fast unit 矩阵触发 wheel+venv 构建；fast CI 步骤改用 `pytest -n auto --dist loadscope`（新增 `pytest-xdist` dev 依赖）。Linux leg 的 uv 冒烟由全量重跑收敛为 `tests/cli`+`tests/core` 子集，KG 注入回归命名门禁限 Linux。本地 fast 套件墙钟由约 375s 降至约 60s。

### Fixed

- **`agent-dispatch` SKILL.md dead reference** —— removed the reference to a non-existent `cataforge.runtime.template_renderer` module; orchestrator reads the main dispatch-prompt template + per-platform override in-context (no runtime merger module exists or is needed).
- **Cursor dispatch-prompt override** —— dropped the duplicate `startup_notes` block (the main template already carries it).

- **`pyoxigraph 0.5.x` 写操作原子性** —— pyoxigraph 0.5 没有原生事务，partial-write 失败会留下半截 entity。`ingest/writer._atomic_replace_entity`、`ingest/migrate._write_phase5`、`repair.repair` 三处现在采用 compensating snapshot + rollback；`TransactionContext` rollback 抛错也走 PEP 678 `add_note` 不再掩盖原始 traceback。新增 `test_ingest_writer_atomicity.py` 通过故障注入 store 验证。
- **`_ask.py` ASK 拒绝所有查询** —— `_SPARQL_KEYWORD_RE` 的 `\s*` 之前只挂在 `BASE` 分支末尾，PREFIX 之后的空白没被消费，`(\w+)` 落到空格上匹配失败，导致每条 ASK 都报 `"ask() only accepts ASK queries"`。改成共享 `(?:(?:PREFIX|BASE) … )\s*)*` 修复。
- **scaffold fixture 隔离泄漏** —— `core/scaffold.iter_scaffold_files` 在 editable-install fallback 下会 walk 框架自身的 `.cataforge/`，把本地 `.deploy-state` / `.deploy-manifest.json` / `.instruction-hashes.json` / `.scaffold-manifest.json` / `.backups/` 当 scaffold 内容拷给下游项目；下游 bootstrap 因此报 "deploy skip — already deployed"。加 top-level 黑名单过滤，6 个 bootstrap/upgrade/smoke 测试恢复。
- **`shim.resolve_deps` 静默丢依赖** —— KG path 实体不存在时返回空列表，调用方分不清"无依赖"还是"实体没 ingest"。改为先 `exists()` 检查，缺失时 fallback 到 legacy `.doc-index.json` 并 warning。`_kg_extract` 行 entity_id 缺失时回退到 regex 解析的 `match.group(1)`。
- **`_slice_section` 边界误命中** —— substring 匹配让 `"F-1"` 命中 `"## F-12 …"`，任意 `#` 开头的行都终结章节让 `### 2.1.1` 提前截断 `## 2.1`。改为 word boundary + heading level 感知，`_shim.py` 和 `query.py` 两处都修。

- **Windows 控制台脚本入口崩溃** —— `cataforge --version` / `--help` 经 console-script launcher（uv/pip trampoline，作为 zipapp 运行）启动时，`ensure_utf8()` 的 UTF-8 relaunch 逻辑把 `__main__.__spec__.name`（zipapp 下恒为字面量 `"__main__"`）当成 `-m` 目标重启，报 `ValueError: __main__.__spec__ is None`。重写为直接重放 `sys.orig_argv`（统一覆盖 console-script / `-m module` / `python script.py`，无需推断模块名），并把 relaunch 机制从 `os.exec*`（Windows 无真 exec，CRT 模拟在高输出量时 0xC0000005 崩溃）改为 spawn 子进程 + 转发退出码。新增 `tests/e2e/test_console_script_utf8.py`：以真实 console script + 剥离 `PYTHONUTF8`/`PYTEST_*` 的环境运行，是唯一能触发该 relaunch 分支的测试形态。

- **`cataforge penpot` 不再因 `claude mcp list` 超时误报失败** —— `register_claude_mcp` 此前用 10s 硬超时直跑 `claude mcp list`，并让 `subprocess.TimeoutExpired` 直接冒泡；当本机注册了多个远程 MCP server（`claude mcp list` 串行健康检查全部 server）时极易超时，导致一个**已成功启动**的 Penpot MCP 被整体判为退出 1。现把 `claude mcp list` / `claude mcp add` 收敛进 `_run_claude_mcp` best-effort 包装（超时放宽到 30s，超时/缺失 CLI 一律降级为非致命告警 + 手动注册提示），注册步骤不再阻断启动结果。

- **SessionStart hook 不再自动 deploy** —— `session_context` 此前每次会话启动都 shell out `cataforge deploy`，会把 CLAUDE.md 从模板重写、写 `.scaffold-manifest.json`，污染 tracked 文件并拖慢每次启动。改回其声明职责：仅向 gitignored 的 `docs/EVENT-LOG.jsonl` 追加一条 `session_start` 事件（best-effort，失败仅 stderr 警告，绝不改 tracked 文件）。部署改为显式 `cataforge deploy` / `bootstrap`。framework.json 的 `mc-0.1.5-session-context-simplified` 迁移检查新增 `deploy` 禁词以防回归。

- **`kg/test_codegen.py` codegen 重复执行** —— 只读断言共享 session 级 codegen 产物，linkml 生成由 5 次降为 2 次。
- **`mcp` 生命周期测试 teardown 超时** —— `test_start_cleans_stale_running_state` 的 `_pid_alive` patch 对真实 pid 委托真实实现，避免 stop() 空耗 SIGTERM+SIGKILL 超时（单测由约 10s 降至约 0.1s）。
- **测试输出 `RequestsDependencyWarning` 噪声** —— pytest `filterwarnings` 精准过滤 linkml 依赖栈（PyShExC→chardet 7.x 与 requests 的 chardet<6 兼容检查冲突）固有的版本不匹配告警。

### Removed

- **`cataforge.domain.kg._shim` 向后兼容层** —— 删除 0.4.x 业务文档调用点的 8 个 shim wrapper（`extract` / `extract_batch` / `extract_with_body` / `plan_load` / `build_full_index` / `resolve_deps` / `legacy_validate_report` / `source_section`）。该模块自始仅被测试引用，无任何生产调用点；调用方应直接使用 typed `KnowledgeGraph` API。同时移除已失效的 `check_deprecation_quota.py` 守卫（其正则匹配的模块路径 `cataforge.kg._shim` 与实际路径 `cataforge.domain.kg._shim` 不符，长期为 no-op）。

### Deprecated

- **`docs/.doc-index.json` 作为 active doc_type 的权威源** —— 0.5.x 起 KG 是 active doc_type 的唯一权威；`.doc-index.json` 在 active doc_type 上**降级为派生缓存**。0.6.0 计划：`cataforge docs index` 移出默认流程，由 `cataforge kg export-index` 取代（per task-7 rollout §Phase 2 Exit Condition）。下游外部工具若直接读 `.doc-index.json`，请准备迁移到 `cataforge kg query` 或等待 `kg export-index`。

### Security

- **SPARQL / IRI 注入加固** —— 引入 `cataforge.domain.kg._sparql_utils` 单一逃逸入口（`escape_sparql_literal` 走 SPARQL 1.1 ECHAR + C0 控制字符 `\uXXXX`；`escape_iri_component` 走 RFC 3987 percent-encoding；`assert_safe_iri` 守 `<...>` 边界）。writer / transaction / shim / reconcile / verify / compare_read / validate / export / repair 中所有 ASK / SELECT 走过的用户值都路由到这些工具；新增 44 项 escape 单元测试 + 16 项端到端注入回归。CI 加 "KG injection regression (P0–P3 named gate)" 命名步骤 + `kg-injection-regression` pre-commit hook，保证回归命中时归因清楚。

### Documentation

- **active doc_type 扩张路径** —— `src/cataforge/domain/kg/_config.py` 注释展开 0.5.x → 0.6.0 候选清单（dev-plan / ui-spec）。ingest 已支持 T/C/P 实体提取；扩张需要 fixture 覆盖 + golden-file 回归，不在 0.5.x 默认集中。项目可在 `framework.json.kg.kg_active_doc_types` 提前 opt-in。

<a id='changelog-0.5.0'></a>

## [0.5.0] — 2026-05-27

完整迁移指南见 [docs/migration/kg-cutover-0.5.0.md](docs/migration/kg-cutover-0.5.0.md)。

### 替代范围

0.5.0 替换了 0.4.x 业务文档（PRD / Arch / Test）的索引与跨文档关系层。下表列清哪些旧路径被取代、新路径长什么样、对终端用户的可见差异。

| 旧路径（0.4.x） | 新路径（0.5.0） | 范围 |
|----------------|----------------|------|
| `docs/.doc-index.json` 作为权威索引 | RocksDB-backed Oxigraph store at `.cataforge/kg/store/`，`.doc-index.json` 降级为派生缓存 | `kg_active_doc_types ⊇ {prd, arch, test}` 内 |
| `loader.extract()` 文件切片读 PRD/Arch/Test 段 | `cataforge.domain.kg.export.render_entity` 经 SPARQL hydrate 出 canonical Markdown | 同上 |
| `check_xref` 用 file-glob 解析 entity_id（URL-fragment / cross-volume 误报） | SPARQL 实体解析 | 同上 |
| `check_bidirectional_coverage` 正则 grep 双向覆盖（task-1 §1.4 case A 假阳） | `cf:implements + cf:verifies+` SPARQL property path | 同上 |
| arch §1.4 tech-stack narrative 走 `source_section()` 转义 hatch | `cf:TechStack` 类 + `cataforge kg import` codemod 抽取为实体 | arch doc_type |
| ui-spec `C-NNN` 与 arch `C-NNN` 同 prefix 冲突 | ui-spec 重映射为 `UC-NNN`（`UIComponent`），arch `C-NNN` 保持为 `Component` | ui-spec doc_type（codemod 自动重写） |
| `loader.extract()` 直读 `governance` 元资产 | 仍走 file-system；`KGConfig.governance=False` 默认关闭 | `.cataforge/` 自身资产（不在替代范围内） |

不在 `kg_active_doc_types` 集合内的 doc_type 全部走旧 `loader.extract()` 路径，0.5.0 内不变。

### BREAKING

KG-first 模型不再提供运行时 markdown-loader fallback。三条主要破坏点 + 缓解迁移路径如下。

| 影响项 | 0.4.x 行为 | 0.5.0 行为 | 如果你曾依赖 X，改为 Y |
|--------|-----------|-----------|----------------------|
| Optional `[kg]` extra 必装 | 无 KG 概念，`pip install cataforge` 即够用 | 启用 KG 模式的项目必须 `pip install cataforge[kg]`；不装则 `cataforge kg *` 子命令退出码 1 提示安装 | 升级时执行 `pip install --upgrade "cataforge[kg]"`（uv: `uv tool install --upgrade "cataforge[kg]"`） |
| `cataforge kg init` 是先决条件 | N/A | `.cataforge/kg/store/` 不存在时 `kg_active_doc_types` 配了也按 SKIP 处理，doctor 不阻断；但黄金路径不再连通 | 升级后跑一次 `cataforge kg init` |
| `kg_ingestion_completeness` ERROR-gate | N/A | `cataforge doctor` 在某 active doc_type 的 Markdown 实体缺失于 KG 时 ERROR 阻断，无 WARN 过渡期 | 翻 flag 前先 `cataforge kg import` + `cataforge kg reconcile`，确认零 missing |
| `docs/.doc-index.json` 派生化 | 权威索引，第三方可直接 import 读字段 | 派生缓存，可能落后于 KG | 第三方读者改用 `cataforge kg query` 或 `cataforge docs load`（后者自动按 doc_type 路由到 KG 或 legacy） |
| Component C-NNN 与 ui-spec C-NNN 命名空间分裂 | 共享 `C-NNN` prefix，混淆来源 | ui-spec C-NNN 在 `cataforge kg import` 中 codemod 为 UC-NNN（`UIComponent`） | inbound xref 由 codemod 自动追踪；下游 grep 工具切到 `UC-` |
| `cataforge.domain.kg._shim` 公开接口 | N/A | shim 层 5 + 3 个函数（`extract` / `extract_batch` / `plan_load` / `build_full_index` / `resolve_deps` + `extract_with_body` / `legacy_validate_report` / `source_section`）发 `DeprecationWarning` | 调用方迁到 `QueryAPI` / `TraceAPI` 直接接口；0.6.0 移除 shim 层 |
| `governance.yaml` schema 提供但默认关闭 | N/A | `KGConfig.governance=False` 默认；仅 framework-review 等内部 skill 开关切 True | 业务项目无操作；自定 governance 整合的项目自管 `governance=True` 切换 |

回滚粒度 = 单 doc_type：从 `kg_active_doc_types` 移除该 doc_type 即让该 doc_type 读路径退回 legacy loader，其它 doc_type 不受影响。Systemic snapshot 回滚走 `cataforge kg snapshot --output <path>` → `cataforge kg rollback <path>`。完整流程见 [迁移指南](docs/migration/kg-cutover-0.5.0.md) §回滚。

### Added

- **`cataforge mcp health <id>`** —— 主动探测注册的 MCP 服务健康。按 `spec.health_check.type` 分派：`http` → `GET` 目标 URL（2xx 即健康）；`tcp` → `socket.connect("host:port")`；`command` → shell 执行（exit 0 即健康）；缺省 → pid alive 兜底。结果写回 `last_health_check`；unhealthy 时 exit 1。
- **`start()` 完成后跑 readiness 探测** —— spawn 后立即调一次 `health()`，返回的 state 反映「真正可用」而非「OS 已 fork」。
- **Codex / OpenCode `deploy_agents` orphan prune** —— 与 Claude Code / base 对齐。删除/重命名 agent 后，下次 `cataforge deploy` 自动清掉旧的 `.codex/agents/<name>.toml` / `.opencode/agents/<name>.md`。只动带自动生成签名（`# Auto-generated from <stem>/AGENT.md` / `name: <stem>` frontmatter）的文件，用户自创的同名文件不动。
- **CI `mypy` informational + 严格包阻塞** —— `mypy src/cataforge` 整库 info-only 印错误数；opt-in strict 包列表（首批：`cataforge.application.services.*`）任何 strict 错误阻塞 PR。convergence 流程文档化在 [docs/contributing.md § 类型检查](docs/contributing.md)。
- **CI `uv run --extra dev pytest` smoke + 默认 extras collect smoke** —— 前者覆盖 uv 路径不漂移；后者干净 venv 跑 pytest collect 守住 P0-1 的 jinja2 修复（防止 runtime dep 再次被 [dev] 间接拉入掩盖）。
- **CI 平台 dry-run 矩阵** —— `cataforge deploy --platform cursor/codex/opencode --dry-run` 每个 PR 都跑一次，弥补 [README.md:90](README.md) 承认的「Cursor/CodeX/OpenCode 未等同 E2E 验证」缺口。

- **`.cataforge/framework.json#/constants/SKILL_RUNNER_TIMEOUT_DEFAULT_SECS = 300`** —— skill runner 读此值作为默认 subprocess timeout；[docs/reference/configuration.md](docs/reference/configuration.md) 同步条目。
- **测试基线大幅扩充** —— 多个新测试文件覆盖此前盲区（penpot 集成 / migrate_nav + migrate_review_frontmatter 单测 / deployer 错误路径 / mcp 并发启动）+ 针对本 PR 修复的回归屏障（hook 三平台转义 10 / orphan prune helper 10 / cli entrypoint 2 含负向 guard / event log 大小 4 / md_parse 并发 2 / docker_util 懒加载 5 / config int 解析 3 等）。

- **`[kg]` optional-dependencies group** —— `pip install cataforge[kg]` 拉 `linkml-runtime>=1.11.1` 和 `pyoxigraph>=0.5.8`，是 0.5.0 KG 迁移 sub-PR 1（schema + codegen）的运行时依赖前置。`[dev]` 同时加入 `linkml>=1.11.1` 提供 `gen-pydantic` / `gen-shacl` / `gen-owl` codegen 工具链。`[all]` 已同步包含 KG 两包。

- **`src/cataforge/domain/kg/schemas/` 作为 KG schema 唯一权威源** —— `core.yaml` / `governance.yaml` 从 `docs/proposals/kg-migration-0.5.0/schemas/` 复制到包内可寻址路径，runtime 通过 `importlib.resources.files("cataforge.domain.kg.schemas")` 解析。`docs/proposals/` 副本冻结为设计时刻快照，不再随实现演进更新（README 顶部已加 SoT 指针）。

- **`scripts/codegen_kg_schema.py` LinkML → Pydantic / SHACL / rdfs:subClassOf 一次性编译** —— 调用 LinkML Python API（`PydanticGenerator` / `ShaclGenerator`）把 `core.yaml` + `governance.yaml` 编译到 `src/cataforge/domain/kg/_generated/`（`.gitignore` 已收）：
  - `core_pydantic.py` / `governance_pydantic.py` —— Pydantic v2 模型，供 ingest / write 层数据校验
  - `core_shapes.ttl` / `governance_shapes.ttl` —— SHACL shapes，供可选 `pyshacl` 后置校验
  - `subclass_axioms.ttl` —— 把 LinkML `is_a` 链显式物化成 `rdfs:subClassOf` triples，给 sub-PR 2 的 `cataforge kg init` 在 store bootstrap 时灌入。pyoxigraph 0.5.x 不做 OWL/RDFS 推理，property-path 查询 `a/rdfs:subClassOf*` 必须依赖显式三元组才能走通子类闭包（spike-2 §2.1，[CataForge#142](https://github.com/lync-cyber/CataForge/issues/142)）。
  脚本在 `os.environ` 里强制设 `PYTHONIOENCODING=utf-8`，避开 spike-1 §1.4 记录的 Windows GBK 控制台 UnicodeEncodeError；自身走 `Path.write_text(..., encoding="utf-8")` 绕过 stdout 编码。`subclass_axioms.ttl` 按字典序排三元组、剔除时间戳，二次运行字节级一致。

- **`tests/kg/test_codegen.py` codegen 烟测 4 例** —— 产物存在、`subclass_axioms.ttl` 重跑字节级一致、已知 `is_a` 链（Feature→Requirement→SoftwareArtifact、Page→Screen→SoftwareArtifact、Sprint→WorkUnit→SoftwareArtifact）落到产物里、生成的 Pydantic 模块能 import 出 Feature / Component / TestCase / Project / SoftwareArtifact 五个核心类。`linkml` 未安装时整组测试自动 skip（属 `dev` extra，不进运行时依赖）。

- **`cataforge kg init` —— 0.5.0 KG store lifecycle 起手** —— Alpha sub-PR 2 (`store + init`，task-7 §7.1)。新建 `src/cataforge/domain/kg/` 运行时包：

  - `KGConfig` dataclass（task-5 §5.2）—— `store_backend` / `db_path` / `governance` / `coverage_mode` / `kg_active_doc_types` 等十个字段；其中 `kg_active_doc_types: set[str]` 默认空 set，per-doc_type cutover 旗标的存放点。round-2 决策落地。
  - `KnowledgeGraphStore` —— 包住 `pyoxigraph.Store` 的薄壳，sync `connect()` context manager + `.ask()` 走 `_ask.ask()` 单点。完整 `KnowledgeGraph` facade（query/trace/transaction）留给后续 sub-PR。
  - `bootstrap_subclass_axioms(store)` —— 把 LinkML `is_a` 链直接写成 `rdfs:subClassOf` triples 灌进 store（spike-2 §2.1）。pyoxigraph 0.5.x 无 OWL/RDFS 推理，`a/rdfs:subClassOf*` 必须依赖显式三元组才能走子类闭包。集成测试断言 `?s a/rdfs:subClassOf* cf:Screen` 在插入一个 `cf:Page` 实例后返回它。
  - `cataforge kg init [--db-path] [--backend memory|oxigraph] [--governance] [--force]` —— 创建 RocksDB store 目录 + bootstrap；存在则 `KGStoreAlreadyExistsError` 退出 1 除非给 `--force`。

- **`cataforge.domain.kg._ask.ask(store, sparql) -> bool` —— `QueryBoolean` 单点 chokepoint**（spike-2 §2.2 / 风险册 R-09 / [#142](https://github.com/lync-cyber/CataForge/issues/142)）—— pyoxigraph `Store.query()` 对 ASK 返回 `QueryBoolean`，`== True` 永远等于 False 即使答案为 True。所有 ASK 消费走这一个 wrapper；测试 pin 住"return is real Python bool"契约，并加一条"如果 pyoxigraph 改成返回真 bool 就提醒移除 wrapper"的回归 pin。

- **`scripts/checks/check_no_query_boolean_eq_true.py` 防回归 grep gate** —— 拒绝 `src/cataforge/domain/kg/**.py` 里出现 `.query(...) == True` / `is True` / `== False` / `is False` 模式（docstring 反引号 / 字符串字面量自动排除）。挂上 pre-commit + per-PR test.yml。

- **`src/cataforge/domain/kg/_schema_axioms.py` 共享 is_a → subClassOf 萃取器** —— `iter_subclass_axioms()` / `prefix_map()` / `expand_curie()`。`scripts/codegen_kg_schema.py`（sub-PR 1 codegen）和 `cataforge.domain.kg.store.bootstrap_subclass_axioms()`（runtime）共用同一份遍历逻辑，runtime 不依赖 `_generated/` 工件存在。

- **`cataforge kg import` —— 0.5.0 KG 迁移 codemod**（Alpha sub-PR 3，task-7 §7.2）。新增 `src/cataforge/domain/kg/ingest/` 子包，按设计文档的六阶段管道实现：

  - **scan + parse**（`scan.py` / `frontmatter.py`）—— 枚举 prd / arch / test-report 下 `*.md`、提取 YAML frontmatter、用 `markdown-it-py` 解析 heading 边界。
  - **entity-extract**（`entity_extract.py`）—— `ENTITY_PREFIX_RE` 在 section 文本里 finditer，归属到最深 enclosing heading，SHA-256 hash section body。`prd#§2.F-001` 形式的 xref 不再被误抽成 arch 的 Feature（曾导致跨文档 entity_id 重复）。
  - **relation-extract**（`relation_extract.py`）—— `XREF_RE` 抽 `doc_id#§N.ITEM`，按 `(source_class, target_prefix)` 查表推断 predicate；表项对齐 `core.yaml` 真实 slot 名（`cf:implements` / `cf:verifies` / `cf:realizes` / `cf:satisfies`），不再用设计文档草案里的 `cf:implementsFeature` 旧名。
  - **writer**（`writer.py`）—— 用 [#142](https://github.com/lync-cyber/CataForge/issues/142) §2.2 的 `cataforge.domain.kg._ask.ask()` chokepoint 做 content-hash dedup ASK。再跑同一份 source zero new triples（idempotency）。先写 Project node（从 `framework.json` `kg` 块读 process_model / project_id / title）再写 entities + relations。
  - **verify**（`verify.py`）—— 六阶段最后做实体/关系计数对账、content-hash compare、missing-entity 扫描；任意不通过则非零退出。
  - **migrate orchestrator**（`migrate.py`）—— 串六阶段，跨文档 entity dedup（first occurrence wins —— prd 顶部 doc_types 顺序保证 Feature/AC 的"主定义"来自 prd），支持 `--dry-run` 跳 phase 5。

- **`cataforge kg validate`** —— 基础 orphan + xref-target 完整性检查；`--shacl` 旗标接受但当前 pyoxigraph → rdflib 桥未实现时安静 skip。

- **`scripts/migrate_docs_to_kg.py`** —— task-7 §7.2 指名的入口脚本，作为 `cataforge kg import` 的 thin shell wrapper。

- **`tests/fixtures/kg-vertical-slice/{waterfall,agile}/`** —— hand-crafted fixture project，覆盖 prd 2 Feature × 2 AC + arch 2 Module（`cf:implements` F-NNN）+ test-report 2 TestCase（`cf:verifies` AC-NNN）；两套结构相同，`framework.json` `kg.process_model` 字段分别为 `waterfall` / `agile`，迁移后 Project node 的 `cf:process_model` 字面量随之不同（round-2 双 process_model 覆盖）。

- **15 个新增 sub-PR 3 测试** —— end-to-end @parametrize(variant) × {ingest, idempotency, dry-run, process_model, validate-clean} + xref-pollution 回归 pin + CLI smoke {memory, dry-run, oxigraph round-trip}。

- **`cataforge kg export` —— 0.5.0 KG 导出管道**（Alpha sub-PR 4，task-4 §4.1）。新增 `src/cataforge/domain/kg/export/` 子包，按设计文档的 query → hydrate → render → write 四层落地：

  - **registry**（`registry.py`）—— `SparqlRegistry` 扫描 `sparql/*.sparql`，stem 即 LinkML 类名（小写）。sub-PR 4 ships built-ins for the four-entity fixture slice（Feature / AcceptanceCriteria / Module / TestCase）；其它实体类型在被引用的 sub-PR 里随之落地。
  - **hydrator**（`hydrator.py`）—— SPARQL `QuerySolution` 多行结果折叠成 render context dict：标量字段 first-non-null wins；多值关系组按 `(sort_key, entity_id)` 复合键 stable-sort。`_row_lookup()` 容忍 pyoxigraph `QuerySolution.__getitem__` 的 KeyError，把"变量不在 projection"和"OPTIONAL 未绑定"都归一成 None。
  - **pipeline**（`pipeline.py`）—— `compile_to_markdown(store, output_dir)` 主入口。enumerate business entities 排除 `cf:Project`（无 `cf:sort_key`，且文档结构上是 root container），按 `sort_key` ORDER BY 决定迭代顺序；每实体 query → hydrate → render → SHA-256 计哈希落盘。
  - **templates**（`templates/{doc_type}/{entity_type}.md.j2`）—— Jinja2 `StrictUndefined` 是幂等性安全网（task-4 §4.4.3）：模板里写 `{{ generated_at }}` 之类的幻影变量会立刻抛错而不是静默渲染成空串。`_base/artifact_base.md.j2` 提供共享 frontmatter + heading + description 骨架，各实体模板用 `{% block body %}` / `{% block relations %}` 扩展。

- **`cataforge kg export` CLI 子命令** —— `--db-path` / `--output-dir` / `--json`；导出失败 exit 3。

- **6 个新增 sub-PR 4 测试** —— end-to-end @parametrize(variant) × {render-every-entity, byte-identical-across-runs, in-place-overwrite-idempotent, every-relation-as-link, strict-undefined-blocks-generated-at} + base-import-without-pyoxigraph 回归 pin + CLI smoke `kg export` oxigraph 全链路。

- **Alpha sub-PR 5 —— KG cutover + doctor gate ERROR**（task-7 §7.1 收官）。本 PR 同时落 Alpha 退出条件所需的 5 项构件：

  - **KnowledgeGraph facade + QueryAPI / TraceAPI / TransactionContext**（`src/cataforge/domain/kg/{facade,query,trace,transaction}.py`）—— 同步读 + 同步事务最小可行面。`QueryAPI` 覆盖 `feature/module/component/page/api/task/test_case/requirement/entity/exists/all_entities/entity_ids/source_section/plan_load`，errata C1 (`api()`/`page()` typed accessor) 落地。`TraceAPI` 提供 `bidirectional_coverage` / `coverage` / `from_requirement` / `stale_dependencies`。返回 flat dict（Pydantic 完整往返留待后续 sub-PR，配合 SHACL post-validation）。
  - **`cataforge.domain.kg.export.render_entity`** —— 单实体渲染公共符号（errata C2）。复用 sub-PR 4 的 SparqlRegistry / hydrator / Jinja2 stack，shim 层的 `extract_with_body` 依赖它。
  - **Shim 层 `src/cataforge/domain/kg/_shim.py`** —— Task 5 §5.5 五函数 (`extract` / `extract_batch` / `plan_load` / `build_full_index` / `resolve_deps`) + Task 6 §6.5 三延伸 (`extract_with_body` / `legacy_validate_report` / `source_section`)。每函数按 `doc_type in KGConfig.kg_active_doc_types` per-doc_type dispatch，KG 分支走 QueryAPI / TraceAPI，legacy 分支委托 `cataforge.domain.docs.loader` / `indexer`。可选 `kg: KnowledgeGraph` 参数让测试 / 批量调用复用连接而非反复 reopen。所有公共函数发 `DeprecationWarning`，0.6.0 移除。
  - **Doctor gate `kg_ingestion_completeness`** —— `src/cataforge/interface/cli/doctor/kg_ingestion.py` 直接以 ERROR 级别接入，不走 WARN 过渡（README §User decisions Round 2 明确）。missing 实体贡献 `failed_count`，stale 仅 WARN 打印不阻断；`.cataforge/kg/store/` 不存在或 active 集为空时优雅 SKIP，避免阻塞未启用 KG 的下游项目。doctor_cmd 在 "Docs validation" 之后调度。

- **`cataforge kg reconcile` —— per-doc_type drift detector**（Alpha sub-PR 6，task-7 §7.5 收口）。`src/cataforge/domain/kg/reconcile.py` 实现六步管线：scan → extract entities → extract relations → KG SPARQL pull → symmetric diff → JSON report。默认报告路径 `docs/.kg-reconcile-report.json`；有 `missing` / `ghost` entry 即非零退出。这是 Alpha exit condition 2（doctor `kg_ingestion_completeness` 在 ERROR 严重度下跑完一个完整 reconcile cycle）从此可验证的前提 —— 没有这条命令，"reconcile cycle" 无法实操地度量。

  - SPARQL 侧以 `cf:source_doc` 把每条 entity / relation 归属到 doc_type；relations 继承 subject 的 source_doc。
  - 与 `cataforge kg import` 复用同一组 `scan_business_docs` / `extract_entities` / `extract_relations`，确保 FS 侧的"看见过什么"与 ingest 完全等价。
  - CURIE-normalize 谓词（`cf:slot` form），过滤掉 `cf:belongs_to_project` 这种 housekeeping 边，diff 集合仅覆盖 traceability slots。

- **`cataforge kg compare-read` —— post-cutover 内容漂移采样**（task-7 §7.5）。`src/cataforge/domain/kg/compare_read.py` 改用 **content_hash 对比** 而非提案原文的 "Jaccard on rendered Markdown"：sub-PR 4 的 export 模板是 traceability card（不含 source body），与 `loader.extract()` 切片在结构上不对等，按原意算 Jaccard 永远低于阈值。content_hash 既精确又复用 sub-PR 3 已经持久化的同一个哈希，是同义务的更可靠实现。

  - 三种 alarm reason：`content-hash-mismatch`（KG 旧、FS 新）/ `kg-missing-entity`（FS 新加但未 re-ingest）/ `kg-content-hash-absent`（KG store 损坏）。
  - 任何 alarm 都不改变 exit code —— 与 §7.5 "diagnostic, not gating" 一致；alarm 持续才触发"该 doc_type 移出 `kg_active_doc_types`" 的运维动作。
  - `--seed` 让采样可复现。

- **`docs/reference/kg-verified-behaviors.md`** —— 把 README §Open follow-ups 里 7 条 `[待验证]` 收口：4 条在 Alpha 已通过现有测试验证（property-path `a/rdfs:subClassOf*` / `belongs_to_work_unit` 继承式多态 / TC-NNN 模式 / 编程态 codegen），2 条以 documented escape hatch 推到 GA（SHACL 运行期校验 / 自然语言查询），并把 errata C1 / C2 标记为"sub-PR 5 已落地"。README §Open follow-ups 同步精简到一屏。

- **`cataforge.utils.atomic_write.atomic_write_text(path, data)`** —— 统一的"写 tmp + `os.replace`"原子写入封装。多个 CLI 命令此前用裸 `Path.write_text` 改写 `framework.json` / `CORRECTIONS-LOG.md` / 部署状态缓存，进程中断会留半截文件下次解析直接失败。后续把这些站点逐步切到该 helper（本 PR 仅提供基建，迁移在后续阶段）。

- **`KGStoreError` / `KGVerificationError` 类型化 KG 错误**（`src/cataforge/interface/cli/errors.py`） —— `cataforge kg` 子命令此前在 10 个位置重复 `err = CataforgeError(...); err.exit_code = N; raise err`，运行时赋值脆弱且无类型保证。两个子类把退出码声明到类属性：`KGStoreError`（store 未初始化 / 已存在，exit 1）、`KGVerificationError`（import 校验 / validate 违例 / export 渲染 / reconcile 漂移，exit 3）。

- **`cataforge.utils.run_subprocess.run`** —— 统一的 subprocess 封装：固定 `check=False`（调用方显式查 `returncode`）、默认 `timeout=60.0s`、默认 `capture_output=True`、强制 `text=True` + `encoding="utf-8"`（避开 Windows cp1252 fallback）。`TimeoutExpired` 与 `FileNotFoundError` 仍透传，便于调用方区分"诊断后继续"vs"抛 CataforgeError 中止命令"。仓库现有 46 处裸 `subprocess.run` 是分多次 PR 渐进迁移的目标，本 PR 仅引入封装本身与迁移模式（见函数 docstring 的 before/after 范例）。

- **`scripts/checks/check_no_raw_subprocess.py`** —— 裸 subprocess 调用清单守卫（advisory 模式）。今日 exit 0 不强制，但在每次 commit 都打印剩余清单数（当前 46），让迁移积压保持可见。脚本顶部 `ADVISORY_MODE = True` 一旦切 `False` 即进入强制模式；同行 `# allow-raw-subprocess: <reason>` 注释豁免单点。已接入 `scripts/checks/run_local.py` 与 `.pre-commit-config.yaml`。

- **`scripts/checks/check_echo_err_for_errors.py`** —— `cli/` 错误输出走 stderr 的守卫。扫描 `src/cataforge/interface/cli/`（排除 `cli/doctor/` —— 那里整棵子树按设计就是结构化 stdout 报告）下 `click.echo(...)` / `click.secho(...)` 第一个参数以 `Error:` / `ERROR:` / `Cannot` / `Could not` / `Refused` / `Invalid` / `Failed` / `FAIL:` 开头的调用，要求同一调用带 `err=True`。同行 `# allow-stdout-echo: <reason>` 豁免。守卫初次扫描当前 cli/ 0 违规（错误均走 `CataforgeError`），直接 enforced 防未来回归。守卫自带 13 个自测覆盖 enforcement / 豁免 / 多行调用 / 各前缀 / 中性消息。已接入 `run_local.py` 与 `.pre-commit-config.yaml`。

### Changed

- **reviewer agent 现在可调用 AskUserQuestion** —— `tools:` 加 `user_question`，让 §Execution Rules §强制批量提问规则可执行（此前 tool 缺失导致规则形同虚设）。
- **qa-engineer / refactorer / reflector 的 `allowed_paths` 与 Anti-Patterns 行为约束对齐** —— qa-engineer 删 `src/` 写权限（Anti-Patterns 禁止修改源代码）；reflector 删 `docs/reviews/CORRECTIONS-LOG.md` 与 `docs/EVENT-LOG.jsonl` 写权限（Identity 明确不修改被分析文档）；refactorer Anti-Patterns 收紧为"禁止新增/删除测试 + 改 assertion"，明确允许 import 路径同步等机械改动。
- **penpot-review 输出路径改为 `docs/reviews/design/`** —— 此前 §输出规范声明写 `docs/reviews/code/` 与 §Anti-Patterns §3 "禁止写此路径" 自相矛盾；新增独立 design 子目录解决冲突。reviewer.allowed_paths 同步增 `docs/reviews/design/`。

- **framework-issue-resolve.SKILL.md** §Step 5 bash 示例的字面 issue / PR / 版本号改为占位符（`<issue-id>` / `<pr-number>` / `<release-tag>`）—— 消除 CLAUDE.md §硬约束 1 禁止的"版本里程碑 + 溯源引用"残留；教学示例语义不变。
- **penpot-implement.SKILL.md** §Step 3 移除 `React / Vue / HTML` 框架字面量枚举 —— 改为按 arch#§1.4 声明的技术栈生成；消除 §硬约束 2 与编程语言解耦违规。
- **test-writer.AGENT.md** §3 跨平台 syscall 测试模式 重写 —— 删除 vitest hoisted-mock TypeScript 代码块与 fs.symlink/child.kill/chmod 具体场景表，保留抽象决策树（mock > 跨平台断言 > skip），无论宿主测试框架皆适用。
- **ORCHESTRATOR-PROTOCOLS.md** —— 代码块内 HTML 注释加 `<!-- allow-design-residue: downstream-claude-template -->` 同行豁免；代码块外单独的 HTML 注释行改为 blockquote prose。

- **6 个 SKILL 补 `## Anti-Patterns` 段** —— `agent-dispatch` / `doc-gen` / `doc-nav` / `research` / `tdd-engine` / `workflow-framework-generator` 此前缺该段（B8-α WARN），各补 3-5 条覆盖该 skill 典型误用模式（如 doc-nav 禁全文 Read >200 行 / tdd-engine 禁 prototype 模式跑 standard TDD）。
- **start-orchestrator.SKILL.md 补输入/输出规范段 + 新增第 3 条 Anti-Pattern** —— I/O 契约此前缺失（B1-α 不满足），Anti-Patterns 仅 2 条不达 B8-β `ANTI_PATTERN_MIN_COUNT_SKILL=3` 门槛。
- **workflow-framework-generator.SKILL.md 补输入/输出规范段 + Anti-Patterns 段** —— 此前 I/O 字段埋在 Phase 内不清晰；新增 4 条 Anti-Patterns 覆盖生成框架的典型坑（生成硬约束违规 / Anti-Pattern 数量不足 / allowed_paths-vs-行为矛盾 / 跳过 Phase 4 验证）。
- **5 处双向边界对称** —— ui-design 不做加 "从 Penpot 生成代码骨架（by penpot-implement）"；research 不做加 "技术选型最终判定（by tech-eval）"；task-decomp 不做加 "最终 Sprint 分组（by task-dep-analysis）"；arc-design §5.4 加 prose 说明 "配置形态决策属本节；CI/CD 配置文件生成由 deploy-config 负责"；platform-audit 不做加 "审查 `.cataforge/` 框架内部资产（by framework-review）"。

- **hooks.yaml `lint_format` description 注明 in-place rewrite 语义** —— 框架 type 枚举仅 `{block, observe}`（无 `inject`），但 `lint_format` 走 `--fix` / `--write` 实际修改磁盘；description 增补"observe 类但允许 in-place rewrite"消除命名歧义。
- **hooks.yaml `detect_review_flag` degradation reason 补 v2 schema 风险说明** —— 此 hook 依赖 schema v2 `matcher_agent_id` 过滤目标 agent，v1-only 平台无法约束触发范围，文字注明统一 skip 的合理性。
- **orchestrator.AGENT.md frontmatter 显式声明 `model_tier: inherit`** —— 其他 12 个 agent 均已显式声明；orchestrator 在主线程运行不走 model_routing，显式 > 隐式利于可读性。

- **`core/feedback` 分层倒置修复** —— `collect_doctor_summary` 实现迁移到新模块 `cataforge.application.services.doctor_summary`；`core/feedback.py` 不再在模块顶层 `from cataforge.interface.cli.main import cli`，只通过 lazy delegation 调用 service。新增 `cataforge/services/` 包作为允许依赖 `cli/` 的编排层；新增机器可检守卫测试防回归。

- **`mypy strict = true` 退役 → opt-in strict per-package** —— 此前 ~200 个 baseline error 让 strict 永远做不成真正的门禁。现在 `[tool.mypy]` 全局非 strict，`[[tool.mypy.overrides]]` 按包 opt-in。首批 opt-in：`cataforge.application.services.*`（0 errors）。新增包加入 strict 的流程见 contributing.md。

- **`requires-python` 加上界 `<3.15` + `.python-version` 钉到 3.13** —— 之前 `>=3.10` 无上界，`uv venv` 会乐于挑当前最新 CPython（包括尚未在 CI 矩阵内验证的 3.14 / 3.15-prerelease）。现在 `pyproject.toml` 收口到 `>=3.10,<3.15`（覆盖 3.10/3.11/3.12/3.13/3.14 但拒绝 3.15+），仓库根 `.python-version` 钉 `3.13`，让 `uv sync` 默认选最新 LTS-class CPython（与发布物 classifiers + CI 矩阵 ["3.10","3.13"] 对齐）。
- **`AGENT_MODEL_DEFAULTS` 显式补 `orchestrator: inherit`** —— 之前 12 个条目 vs 13 个 agent 像是漏项；实际上 orchestrator 是主线程，AGENT.md 已声明 `model_tier: inherit`。补登记后表项完整，B7 已接受 `inherit`，行为零变化。

- **Platform adapter 孤儿剪枝抽公共 helper** —— `claude_code.py` / `opencode.py` / `codex.py` 三处的 flat-file 剪枝（枚举 + 排除已知名 + 读 head 签名校验 + unlink）合并到 [`platform/helpers._prune_orphan_flat_files`](src/cataforge/adapter/platform/helpers.py)，参数化 `head_signature` 占位符（`name: {stem}` / `# Auto-generated from {stem}/AGENT.md`） + `head_read_size`（codex 256-byte 窗口）。`base.py` 的 subdir/glob 形态结构不同，保留原样。
- **`HealthCheckSpec.target`: `str` → `str | list[str]`** —— http/tcp probe 接受 URL 字符串，command probe 强制 list。
- **设计阶段残留清扫** —— 删除 src/ 与 tests/ docstring 中所有版本里程碑（`Pre-v0.1.13` / `since vX.Y.Z`）、回溯叙事（`Before the fix...` / `Historically...`）、issue 编号引用（`Regression for issue #115`）等违反 [CLAUDE.md 硬约束 1](CLAUDE.md) 的内容。`check_no_design_residue.py` 全仓 clean。
- **`platform/helpers._replace_toml_mcp_section` assert → raise** —— 生产路径 `assert end is not None` 在 `python -O` 下被剥除会用 None 切片静默损坏 TOML；改 `RuntimeError` 含 start 行号。

- **0.5.0 KG 迁移设计提案 Alpha 入场前置 patch 一次性补齐** —— `docs/proposals/kg-migration-0.5.0/` 三处修正吃进 spike 验证回来的硬障碍：

  - **`schemas/governance.yaml`** —— `generates` / `consumed_by` 两个 slot 的 `range` 从 `cf:SoftwareArtifact`（CURIE）改成 `SoftwareArtifact`（裸名）。LinkML 的 `gen-pydantic` 不能解析 `range:` 里的 CURIE 前缀，即使类是通过 `imports:` 拉进来的；改裸名后 codegen 通过。
  - **`task-3-domain-ontology.md` §3.8.3**  —— `add()` 辅助函数自动给非 Project 的 SoftwareArtifact 子类塞 `belongs_to_project`，并在示例顶部加一个 `proj-demo` Project 实例，让 Feature / Module / Task / TestCase 四个实例都通过 SHACL 的「`belongs_to_project required`」检查；每个实例补上 `title`。原例只有 3 个必填字段，实际 SHACL 要 5 个。
  - **`task-3-domain-ontology.md` §3.2.4** —— 显式记录 closed-shape 策略：`core.yaml` 故意不写 per-class `closed: true` / `tree_root:`；统一靠 LinkML 默认 `ConfiguredBaseModel(extra='forbid')` 兜底。避免未来 maintainer 误以为缺 flag 而往 `core.yaml` 加，那是 no-op 改动会被 review 拒。

- **`docs/proposals/kg-migration-0.5.0/README.md` Round 2 决策回灌** —— 把 Alpha 范围澄清产出的 6 项用户决策（PRD+Arch+Test 三层垂直切片、full cutover 去 Beta dual-track、waterfall+agile 双覆盖、`KGConfig.kg_active_doc_types` per-doc_type 旗标、doctor 门 ERROR 严重度、严格线性 sub-PR）合入提案主文档；路线图从 3 阶段简化为 2 阶段；`task-7-rollout-strategy.md` §7.1 同步重写为 5 个严格线性 sub-PR。

- **`scripts/codegen_kg_schema.py` 折射到共享 helper** —— `gen_subclass_axioms()` 改成调 `cataforge.domain.kg._schema_axioms`，移除内联的 `SchemaView` 遍历副本。sub-PR 1 的 4 个 codegen 烟测继续全绿。

- **Group A read-side call sites 接入 per-doc_type 调度** —— 新增 `src/cataforge/domain/kg/_dispatch.py` (`is_active_for` / `kg_config_for`)，按 `.cataforge/framework.json` `kg.kg_active_doc_types` + 文件系统 store 存在性两层 gate。已接入：

  - `cataforge.domain.docs.loader.extract()` —— ref 携带 entity_id 且 doc_type active 时通过 `render_entity` 返回 canonical Markdown；其余 fallback 到原 file-slice 路径
  - `cataforge.runtime.skill.builtins.doc_review.checker.check_xref()` —— active 时 SPARQL 解析 entity_id，淘汰 file-glob 的 URL-fragment / cross-volume 误报（Task 6 §6.4 A12）
  - `cataforge.runtime.skill.builtins.doc_review.checker.check_bidirectional_coverage()` —— active 时走 `cf:implements` + `cf:verifies+` SPARQL，斩首 Task 1 §1.4 case A 假阳性（Task 6 §6.4 A13）

  KG 分支任何错误透明降级回 legacy file 路径；硬 gate 由 doctor `kg_ingestion_completeness` 在部署期强制完整性，运行期 read 不阻断。

- **`KGConfig.kg_active_doc_types` 默认值翻转为 `{prd, arch, test}`** —— Alpha cutover 范围。安全网：`_dispatch.is_active_for()` 同时要求 `.cataforge/kg/store/` 存在，未 `cataforge kg init` 的下游项目自动保持 legacy 读路径，默认翻转不破坏现有行为。新增模块级 `DEFAULT_KG_ACTIVE_DOC_TYPES` frozenset 作为规范常量。

- **`cataforge.domain.docs.loader._DEFAULT_DOC_TYPE_MAP` 补 `test → test-report` 别名** —— 这是 `KGConfig.kg_active_doc_types` 默认值（`{prd, arch, test}`）和 doctor `_doc_type_to_subdir` 一直在用的规范别名；之前 loader 自己的默认 map 里缺这条，导致用 `"test"` 作 doc_type 调 `_load_doc_type_map` 的代码路径（reconcile / scan_business_docs）解析到不存在的 `docs/test/` 目录。两份分叉的别名表合并为一份，doctor / loader / reconcile 现在共用同一份规范。

- **`docs/reference/cli.md` §退出码补全 `3`** —— `cataforge kg` 已用退出码 `3` 表达"内容门失败"（数据真有问题）vs `1`（环境没准备好），但文档此前缺失这条；现统一记录由 `KGVerificationError` 抛出，便于 CI 脚本基于此分流。

- **`cataforge.adapter.platform.helpers.symlink_or_copy` 重构 symlink → junction → copy 回退链** —— 抽出 `_try_symlink` / `_try_junction` / `_do_copy` 三个尝试函数，共享一个 `removed` 状态格控制 `_remove_target` 在整条回退链里**至多调用一次**。旧实现在每个策略之前都独立删一次 target，前一次删除留下的半完成状态（或与外部进程的竞态）有概率让后续删除递归进真目录；新的状态格让回退链幂等于一次删除。

- **`cataforge.core.config.ConfigManager._write_raw` 切到原子写** —— `set_runtime_platform` 之类的写入路径不再用裸 `Path.write_text`；改走 `atomic_write_text`（tmp + `os.replace`）。崩溃时 `framework.json` 保持上一次完整状态，不会半改写后让下次 CLI 调用整体起不来。

- **`cataforge.interface.cli.bootstrap_cmd` 区分 `.deploy-state` 缺失 vs 损坏** —— 旧实现 `(OSError, JSONDecodeError)` 一并吞掉成 `state = {}`，于是 JSON 文件被截断后用户只会看到"never deployed"再静默重跑 deploy，永远不知道状态文件已坏。改为分支处理：`FileNotFoundError` 走 first-deploy 分支；其他 `OSError`/`JSONDecodeError` 都升级为 `ConfigError`，错误信息含具体路径并提示 `cataforge deploy --rebuild`。

- **`cataforge.runtime.deploy.deployer.Deployer._rebuild_purge` 增加 platform_id 校验** —— 旧实现 `--rebuild` 会按上一次 manifest 删除所有路径，不管那些路径属不属于本次目标 platform。`cursor` deploy 后切换到 `claude-code --rebuild` 会清掉 `.cursor/` 下的所有 manifest 路径（包括用户手编辑过的内容），是静默数据丢失。改为在 `_rebuild_purge` 入口比对 `prior_platform vs platform_id`，不匹配直接打 WARN 跳过 purge —— 切换平台需要用户先手动清旧 platform 的目录树。新增 `load_prior_manifest_platform(project_root)` 辅助返回历史 platform_id。

- **`cataforge.core.feedback.collect_framework_review` 分段异常处理** —— 旧实现把 `import SkillRunner` 与 `runner.run(...)` 两阶段用同一个 `except Exception` 兜底，所有失败都归到含糊的 `runner-failed:` 一行。改为：import 阶段单独捕 `ImportError` → `status=skipped`, `reason=runner-unavailable:`；运行时阶段保留 `Exception` 兜底但加 `status=error`, `reason=runner-failed: {type}: {msg}`, `traceback=...` 三字段，让上游 bug 报告能区分"skill 子系统不可用" vs "runner 自身崩溃"并直接贴 traceback。

- **`cataforge.runtime.agent.manager._parse_tools_from_frontmatter` 收敛到 `utils.frontmatter.split_yaml_frontmatter`** —— 删掉本地正则 `_FRONTMATTER_RE` 与对 `yaml.safe_load` 的直接调用，与 skill loader / docs indexer 公用同一份 frontmatter 解析。两者规则一旦漂变（如新的 `---` 分隔符变体）将自动同步，避免后续因双实现而出现"agent 校验通过但 docs 索引失败"的不一致。

- **`cataforge.adapter.platform.PlatformAdapter._deploy_flat_agents` 新增基类 helper** —— 抽出 Claude Code / Codex / OpenCode 三个 adapter 都在做的"扫源 → translate → 写 `<name>{suffix}` → 用头部签名 prune 孤儿 → 聚合 dropped capability WARN"流水线。差异通过 `suffix` / `head_signature` / `formatter`（`(agent_name, translated) → final_text`）/ `head_read_size` 参数化注入。`ClaudeCodeAdapter` 复用 helper 后将额外的"旧 `<name>/AGENT.md` 子目录清理"拆为独立私有方法 `_prune_legacy_agent_subdirs`，逻辑零行为变化。OpenCode 与 Codex 之间的样板代码完全消失。

- **`cataforge.adapter.platform.helpers.remove_dir_with_manifest_check` 新增 helper** —— `platform.base.deploy_agents` 与 `claude_code._prune_legacy_agent_subdirs` 中重复的"`prior_manifest` 检查 → `dry_run` 分支 → `shutil.rmtree` → action 一行"五行样板抽成单一入口。`display_rel`（用于显示）与 `manifest_key`（用于查 manifest）分参数因为前者是目录路径、后者是文件路径，不能合一。`kind` 是 action 消息里的名词（`orphan` / `legacy`），动词时态由 helper 拥有，调用方不会因笔误让 dry-run 与 real 输出走形。

- **`cataforge.interface.cli.helpers.classify_tallies` 新增 helper** —— `bootstrap_cmd` 与 `upgrade_cmd` 里那段 `tallies: dict[str, int] = {}; for _, status in classified: tallies[status] = tallies.get(status, 0) + 1` 收敛到 `collections.Counter` 的单表达式。两个调用点都替换。

- **`cataforge.adapter.integrations.penpot.HANDLERS` 注册表替代 `getattr` 调度** —— 旧调用面 `cli/penpot_cmd._run_penpot("cmd_init", "init")` 同时传"内部函数名"和"用户子命令名"，两个字符串在两个文件里维护同一份映射，一旦 `cmd_*` 函数重命名只在运行时 AttributeError 才会发现。新模块级 `HANDLERS: dict[str, Callable]` 在 `penpot.py` 顶层声明、由 `cli/penpot_cmd._run_penpot(command)` 与 `penpot.main()` 共用查表，未注册的子命令前置抛 `CataforgeError` 含已注册列表。`_run_penpot` 参数从两个收成一个，9 个 click 子命令的调用点同步精简。

- **`cataforge.interface.cli.doctor._helpers.check_import` 返回 `int`** —— 之前函数返回 `None`，与同模块的 `check_file` / `check_dir`（都返回 0/1）接口不一致；`doctor_cmd` 想根据缺失依赖把 doctor 标 FAIL 时无法做到。新增 `required=True` 关键字参数（默认 False 保留旧行为）让 doctor 像对待 `required` 文件那样把 PyYAML / click 缺失计入 `failed_count`；调用点同步加 `+=` 累加。

- **`scripts/checks/run_local.py` 新增 2 条守卫接入** —— `raw-subprocess inventory (advisory)` + `no error output to stdout`，与现有 8 条守卫一起跑。本地 pre-commit 通过同 `.pre-commit-config.yaml` 入口共用，确保 CI / 本地 / `pre-commit run --all-files` 三处口径一致。

- **`cataforge.adapter.integrations.penpot._is_mcp_running` 2 秒 `urlopen` 超时增加注释** —— `urlopen(req, timeout=2)` 是故意的快失败：探针在 `penpot status` / `penpot ensure` / Penpot 系列 skill 的 warm-up 路径上每次调用都会跑，更长的超时会让 MCP 没装的场景里这些命令看着像卡死。注释明确警告未来不要随手调大、并指向 `cmd_ensure` / `cmd_status` 的 UX 依赖。

- **`cataforge.runtime.hook.scripts.lint_format` / `notify_util` / `session_context` 走 `run_subprocess.run`** —— 三个 hook 脚本里 5 处裸 `subprocess.run` 迁到统一封装；`session_context._auto_deploy` 顺手脱掉 `check=True`，改用 `returncode != 0` + 显式 stderr 警告（封装从不抛 `CalledProcessError`）。`check_no_raw_subprocess.py` 计数 46 → 41。配套测试 `tests/hook/test_notify_util_escape.py` / `test_session_context_warns.py` patch 目标改为模块内 `run_proc` 重绑定，原 `shell=` 防御断言去掉（封装结构上没有 `shell=` 入口）。

- **`cataforge.utils.common` / `docker_util` 走 `run_subprocess.run`** —— `common.run_cmd` 改为 `run_proc` 的薄壳（去掉了无人使用的 `**kwargs` 漏接口）；`common.get_command_version` 与 `docker_util` 里 10 处裸 `subprocess.run`（docker info / pull / tag / compose version 等）迁到统一封装。`docker_util.py:69` 的 `Popen([Docker Desktop.exe], creationflags=...)` 是 fire-and-forget GUI 启动、wrapper 不覆盖 Popen 语义，加 `# allow-raw-subprocess:` 同行豁免并落到多行让 ruff E501 通过。计数 41 → 30。

- **`cataforge.utils.run_subprocess.run` 增加 `errors=` 参数** —— 默认 `"strict"`（保持 subprocess 行为），允许 skill runner 这类对子进程输出宽容（非 UTF-8 字节回退到 replace）的调用方显式传 `errors="replace"`。

- **`cataforge.runtime.skill.runner` / `skill.builtins.code_review.code_lint` / `skill.builtins.sprint_review.ignore` 走 `run_subprocess.run`** —— 7 处裸 `subprocess.run`（skill 脚本调度入口 + lint/scan 探针 + git ls-files / rev-parse 探针）迁到统一封装。skill runner 保留 `errors="replace"` —— skill 输出可能含 emoji、中文、warning 行，cp1252 fallback 会让 runner 自身崩在 decode 上。计数 30 → 23。

- **`cataforge.adapter.integrations.penpot` 走 `run_subprocess.run`** —— 7 处裸 `subprocess.run`（`docker ps` / `tasklist` / `taskkill` 探针 + 3 处 `docker compose up -d` / `down`）迁到统一封装。`docker compose up -d` / `down` 这类用户应能看到拉镜像 / 启动日志的命令显式传 `capture_output=False` 让 stdout 直通到终端 —— 不然 `cataforge penpot start` 看着像卡死。两处 MCP server `subprocess.Popen` 加 `# allow-raw-subprocess: long-running MCP server` 同行豁免（wrapper 只覆盖 one-shot `run`，进程控制 Popen 留作显式例外）。计数 23 → 14。

- **`cataforge.interface.cli` 命令模块走 `run_subprocess.run`** —— `agent_cmd` / `feedback_cmd` / `issue_cmd` / `sync_cmd` 共 10 处裸 `subprocess.run` 迁到统一封装：
  - `agent_cmd._try_copy_to_clipboard` 3 处剪贴板探针（clip / pbcopy / xclip / xsel）。
  - `feedback_cmd._to_clipboard` / `_to_gh` / `ensure_labels` 4 处 `gh issue create` / `gh label list` / `gh label create`：把 `check=True` + `except subprocess.CalledProcessError` 模式重构为显式 `returncode != 0` 判断 + 直接抛 `ExternalToolError`，错误信息从 `e.stderr or e.stdout` 改为 `result.stderr or result.stdout`，行为不变。
  - `issue_cmd.close_command` 与 `triage_command` 同样重构（`gh issue close` / `gh issue list`）。
  - `sync_cmd._git` 改为薄壳：内部走 `run_proc`，但当 `check=True` 时手动构造 `CalledProcessError` 抛出，保留所有 14 处 `_git(..., check=True)` 调用者的 `try/except` 语义。

- **`cataforge.interface.cli.hook_cmd` test 子命令豁免** —— `hook test` 必须支持 `unsafe_shell: true` 的 hook 入口（`shell=True` 走 shell 解释），封装故意不暴露 `shell=` 也不支持 `args=` kwarg 透传，加同行 `# allow-raw-subprocess: shell=True for unsafe_shell hooks` 豁免。

- 配套测试 `tests/cli/test_feedback_cmd.py` / `test_feedback_label_fallback.py` / `test_issue_cmd.py` 6 个 mock 点位 patch 目标从 `<mod>.subprocess.run` 迁到 `<mod>.run_proc`，并把 `raise subprocess.CalledProcessError(...)` 改为 `return subprocess.CompletedProcess(returncode=1, stderr=...)`。

计数 14 → 3（剩 mcp/lifecycle Popen + platform/helpers 的最后清理，下一批处理）。

- **`cataforge.runtime.mcp.lifecycle` 健康探针 + `cataforge.adapter.platform.helpers` mklink 走 `run_subprocess.run`** —— 最后 3 处裸 `subprocess` 调用清零：
  - `lifecycle._probe_command` 的 `subprocess.run(target, shell=False, ...)` 改为 `run_proc(target, timeout=...)`，`shell=False` 在 wrapper 是结构性保证（封装没有 `shell=` 入口）。
  - `lifecycle._start_one` 启动 MCP server 的 `subprocess.Popen` 加 `# allow-raw-subprocess: long-running MCP server` 同行豁免。
  - `platform.helpers._try_junction` 的 `mklink /J` 调用从 `check=True` + `except CalledProcessError` 改为 `returncode != 0` 判定。

- **`scripts/checks/check_no_raw_subprocess.py` 切 enforced 模式** —— `ADVISORY_MODE = False`，从今天起任何新增 `subprocess.run` / `Popen` / `call` 调用必须走 `cataforge.utils.run_subprocess.run` 或同行加 `# allow-raw-subprocess: <reason>` 豁免，pre-commit + CI 直接拒掉。脚本顶部 docstring 改为说明"enforced + 合法例外清单"（Popen 长寿命进程、`shell=True` + `**proc_kwargs` 透传）。守卫 id 从 `raw-subprocess-inventory` 重命名为 `no-raw-subprocess`，[`scripts/checks/run_local.py`](scripts/checks/run_local.py) 与 [`.pre-commit-config.yaml`](.pre-commit-config.yaml) 同步。

- **`tests/mcp/test_probe_shell_off.py` + `tests/platform/test_link_strategies.py` 配套修订** —— 把 patch 目标从 `cataforge.runtime.mcp.lifecycle.subprocess.run` / 全局 `subprocess.run` 改到 `cataforge.runtime.mcp.lifecycle.run_proc` / `cataforge.utils.run_subprocess.run`，并把 `raise CalledProcessError(...)` 改为 `return subprocess.CompletedProcess(returncode=1, ...)`。`shell=False` 断言删除（封装结构上不暴露 `shell=`，断言再也没有意义）。

经过 6 批迁移，46 → 0 unmarked，共 4 处合法 Popen / shell-passthrough 豁免，guard 进入 enforced 模式。

- **`cataforge.utils.common.ensure_utf8_stdio` 重命名为 `ensure_utf8` + 新增 Windows UTF-8 Mode re-exec** —— 老的 `ensure_utf8_stdio` 只重配 stdout / stderr，subprocess 子进程仍按 ANSI codepage（zh-CN 默认 cp936 / GBK）解码 stdin / stdout / 写文件，碰到 UTF-8 字节就 `UnicodeDecodeError`。新函数走两阶段：

  1. Windows 上 `PYTHONUTF8` 未设 + 非 pytest 上下文时，`os.execvpe(sys.executable, ["-X", "utf8", "-m", <inferred>, ...])` 把整个进程换到 UTF-8 Mode —— 一次解决 subprocess / `open()` / locale 三处编码，再不用每个调用点显式塞 `encoding="utf-8"`。re-exec target 通过 `sys.modules['__main__'].__spec__` 推断，所以 `python -m cataforge.domain.docs.loader` 这种 subscript 会正确 relaunch 自己而不是顶层 CLI；console-script (`cataforge.exe`) 走 argv\[0\] basename 匹配 fall back 到 `-m cataforge`；standalone 脚本（`python scripts/checks/check_foo.py`）re-exec target 推不出来时静默跳过，只保留 phase 2 stdio reconfigure。
  2. Phase 2 是原来的 stdout / stderr UTF-8 重配（兜底非 Windows / 已在 UTF-8 Mode / pytest）。

- **pytest 检测必须用 `sys.modules` 而不只是 `PYTEST_CURRENT_TEST`** —— pytest collection 在执行任何测试前先 import 所有测试模块，那些 import 链最终拉到 `cataforge.interface.cli.main`，后者 module-load 时就调 `ensure_utf8()`。此时 `PYTEST_CURRENT_TEST` 尚未设置，但 `pytest` 已经在 `sys.modules` 里。少了这条检查 Windows pytest 会在 collection 阶段把自己 re-exec 到 `python -X utf8 -m cataforge`，整个进程崩成 access violation。

- **`ensure_utf8_stdio` → `ensure_utf8` 在 28 个调用点同步替换** —— `cataforge.interface.cli.main`、`integrations/penpot`、`docs/`、所有 `skill/builtins/*` 子脚本、所有 `scripts/checks/*` 守卫脚本、`tests/conftest.py` / `tests/cli/test_cli_smoke.py`。`tests/test_scripts_stdio_guard.py` 的 `CALL_PATTERNS` 正则同步换为 `\bensure_utf8\s*\(`。

- **CLI `KGError` 重命名为 `KGCLIError`** —— 消除与 domain 层 `KGError(Exception)` 的命名冲突。
- **KG SPARQL 工具函数统一到 `_sparql_utils.py`** —— `_term_value`/`_row_lookup`/`_strv` 从 4 个文件提取为共享模块。
- **KG `render_entity()` 接受可选预构建 `registry`/`jinja_env`** —— 循环调用时避免重复磁盘读取。
- **KG trace docstring 修正** —— `cf:reviewed_by` 正确标注为上游遍历而非下游。
- **`framework.json` 的 `kg` 段纳入 Pydantic schema 校验** —— 新增 `FrameworkKG` model，字段拼写错误将被捕获。

### Fixed

- **MCP `register` 落盘到 `.cataforge/mcp/<id>.yaml`** —— 之前 `cataforge mcp register <spec>` 只写当前进程的内存 registry，下一次 CLI 调用就丢失；现在正规化复制到约定路径，新进程通过 `_scan_declarative` 自动发现。冲突时报错，加 `--force` 覆盖。
- **MCP `start` 跨进程幂等 + 死 pid 清理** —— 之前 `start` 只查内存 state，跨 CLI 会重复 spawn；现在 `start` 先读持久化 state + 跨平台 pid 存活校验（Windows 走 `OpenProcess`，POSIX 走 `os.kill(pid, 0)`），活的复用、死的清理重启。
- **MCP `stop` SIGTERM → wait → SIGKILL 兜底** —— 之前 SIGTERM 后立刻标记 stopped，不验证进程死亡；现在等到 pid 真消失才写状态，超时升级 SIGKILL，最终仍存活写 error。
- **`cli/plugin install/remove` help 文案显式标注未实现** —— 命令行 help 现在以 `[未实现 · 规划中]` 开头，并在 group docstring 列出 `Available now: list` + issue tracker 链接，避免用户误以为已可用（命令本身仍正常 exit 70 抛 NotImplementedFeature）。

- **`core/corrections` 日期改 UTC** —— `_append_markdown` 之前用 `datetime.now()`（机器本地时区），与 EVENT-LOG 一律 UTC 不一致：CST 凌晨产生的修正会在 markdown 标 *昨天*、EVENT-LOG 标 *今天*。现在统一 `datetime.now(timezone.utc)`。
- **`tests/platform/test_unwraps_legacy_whole_dir_link` 不再因 Windows 无 Developer Mode 跳过** —— 测试原本用 `Path.symlink_to()` 模拟「legacy deploy 留下的整目录链接」前置条件，但 Windows 默认权限造不出符号链接。改成跨平台 helper：POSIX 用 symlink、Windows 用 `mklink /J` junction（无需提权），断言改为接受 symlink ∪ junction。production `symlink_or_copy` 在 Windows 上本来就 fallback 到 junction，所以新的 setup 比之前更贴近真实场景。
- **MCP `_pid_alive` 在 POSIX 上识别自家僵尸进程** —— Linux/macOS CI 上 `test_start_stop_persists_state` / `test_stop_waits_for_pid_to_die` 报 `status='error'`：SIGTERM 杀掉子进程后变 zombie，旧版 `kill(pid, 0)` 对自家未 `wait()` 的僵尸仍返回成功，`_wait_for_pid_dead` 永远等不到 dead，最后误判为「SIGTERM + SIGKILL 都打不死」。新版先用 `os.waitpid(pid, os.WNOHANG)` 回收僵尸再做 kill 探测：自家僵尸立刻 reap 后报 False，非自家进程（`ChildProcessError`）走原来的 kill 路径。同时把 MCP 测试 fixture 从 `sys.stdin.read()` 换成 `time.sleep(60)` —— 不依赖父进程 stdin 状态，SIGTERM 仍能干净中断，CI 上不再因 stdin EOF 让子进程在测开始前就退掉。

**安全边界**

- **CLI `hook run` 命令注入** —— 之前 hooks.yaml 中非 `python` 前缀的 `command` 字段走 `subprocess.run(shell=True)`，可被 shell 元字符注入。现在默认 `shlex.split` + `shell=False`，元字符 (`;|&\`$<>(){}\\\n`) 拒绝；显式 `unsafe_shell: true` 字段作为 escape hatch（受信任的维护者 opt-in）；`hook_name` 加 `^[a-zA-Z0-9_]+$` 正则校验防路径/模块名注入。
- **MCP probe `shell=True` + entry-point spec 信任边界** —— `_probe_command` 改 `shell=False`，要求 `health_check.target` 为 list（http/tcp 仍接受 URL 字符串，command probe 强制 list）。第三方 entry-point 注册的 `MCPServerSpec.command[0]` 加白名单 `{python, python3, node, uv, uvx}` + 含路径分隔符的相对路径，其它命令 warning 跳过注册。
- **notify_util macOS title 转义** —— `_notify_macos` 的 `title` 之前未转义拼入 osascript 双引号字符串。Win32 路径已有 `html.escape` 保护；Linux 已用 argv 列表；本次只补 macOS title 的 `.replace('"', '\\"')`，加 10 个跨平台回归测试。
- **Platform `deploy_instruction_files` target_rel 路径遍历** —— `profile.yaml` 中 `target_rel` 解析后用 `is_relative_to(project_root)` 强校验，越界抛 `CataforgeError`。
- **JSON merge 静默清空合法配置** —— `merge_json_key` / `merge_opencode_project_mcp` / `merge_codex_mcp_server` 读已存配置失败（JSONDecodeError / OSError）时之前静默 `data = {}` 然后写盘清空，现在抛 `CataforgeError` 保留原文件。

**运行时正确性**

- **`yaml.safe_load(None)` 让 deploy 崩** —— `platform/registry.py` 的 `dict(yaml.safe_load(f))` 在空 profile.yaml 下 None → TypeError；改 `dict(... or {})`。
- **OpenCode 生成的 TS plugin 同步 lambda 丢 async Promise** —— `event.on(evt, (ctx) => dispatch(...))` 改为 `async (ctx) => { await dispatch(...) }`，hook `throw Error` 阻断逻辑现在能传播给 OpenCode；OpenCode `deploy_agents` 补传 `dropped_collector` 与其他三平台对齐；Cursor MDC `alwaysApply: true` 时省略空 `globs:` 字段；platform adapter cache 加 `threading.Lock`。
- **Hook scripts import-time I/O + auto-deploy 静默** —— `validate_agent_result.py` 模块顶层 `ProjectPaths().schemas_dir` 改 lazy（原本在项目根外 import 即抛）；`session_context.py` `_auto_deploy` 失败不再 `suppress(Exception)`，改 stderr `warn` 行（仍 hook_main 保护下，退出码 0）。
- **CLI 错误一致性 5 项** —— `correction record` 改 `resolve_root()` 让 `--project-dir` 全局标志生效；`claude-md check` 失败改抛 `CataforgeError`（之前裸 `SystemExit(1)` 绕过 [errors.py](src/cataforge/interface/cli/errors.py) 统一渲染）；`feedback` 三处 assemble 包装异常改 `from e` 保留 `__cause__`；`mcp_cmd` / `cli/helpers.py` 过宽 `except Exception` 收窄到具体异常元组。
- **`EventBus.emit` 写盘失败让所有上游崩** —— 包 `try/except OSError` 降级 `logger.warning`。
- **`utils/docker_util.PLATFORM` 模块导入时立即求值** —— 改 PEP 562 `__getattr__` 懒加载，测试 mock `sys.platform` 现在生效；保留 `from cataforge.utils.docker_util import PLATFORM` 兼容性。
- **`doctor_summary` 短路三元改显式 if/else** —— `findall and [...] or []` 语义模糊且重复计算，改 `if _DOCTOR_FAIL_RE.search(text):` 显式分支。
- **Skill runner subprocess 无 timeout** —— 加默认 `timeout=300`（常量来自 [`.cataforge/framework.json`](.cataforge/framework.json) `SKILL_RUNNER_TIMEOUT_DEFAULT_SECS`），超时抛 `SkillTimeoutError` 并写 EVENT-LOG `skill_timeout` 事件；`timeout=0` 作为 escape hatch 显式禁用。
- **Agent partial parse 误识别裸 XML 标签** —— `_try_partial_parse` / `_try_xml_parse` 要求 `<status>` / `<outputs>` / `<summary>` / `<questions>` 必须位于 `<agent-result>` 容器内；LLM 回复正文中的 markdown 代码块 / 解释性 XML 片段不再被误抽。`questions` JSON 解析失败改 `logger.debug` 而非完全静默。

**hook / 入口结构（测试加固反向暴露）**

- **`python -m cataforge.interface.cli.main` 结构上不可作为入口** —— 即使加 `__main__` block 也是虚假修复：subcommand 模块 `from cataforge.interface.cli.main import cli` 在 `__main__` 加载路径下触发重复导入产生第二份 `cli`，subcommands 注册到第二份但 `__main__.cli()` 运行第一份。cli/main.py 留 7 行警告注释 + 测试 2 个回归屏障（含一条负向 guard 防止后人误加）。pre-commit 与 hook 调用统一改用 `python -m cataforge`。

**Core/utils + KG parser + hook/mcp/agent 一致性**

- **EVENT-LOG / feedback 读取无大小上限** —— 长期运行项目可能 OOM。新增模块常量 `MAX_EVENTLOG_BYTES = 100 MB`，超出降级追加 + warning。
- **`load_dotenv` 路径无边界校验** —— 加 `is_relative_to(cwd)` 防外部 dotenv 注入。
- **`config.claude_md_limits` 非数字字符串无诊断** —— `int(v)` 包 `try/except` 抛 `ValueError(f"claude_md_limits.{k}: ...")` 含字段名。
- **`_preserve_if_exists` TOCTOU** —— `target.read_bytes()` 包 OSError，失败降级用 `new_bytes` 不崩。
- **`frontmatter` 第二个 `---` 不限制行首** —— 改 `^---\s*$` MULTILINE 正则匹配，水平分割线 `---text---` 不再被误识别为 frontmatter 结尾。
- **`migrate_nav` project_root 未 resolve** —— 相对路径 `--project-root ../foo` 后续 `relative_to` 会 ValueError；加 `.resolve()`。
- **Hook scripts `.cataforge/` 路径检测漏相对路径** —— `lint_format.py` 之前 `"/.cataforge/"` + `"\\.cataforge\\"` 字符串搜索漏掉 `.cataforge/skills/foo.md` 形态（反斜杠分支实际是死代码，路径在 line 55 已 forward-slash 化），改 `".cataforge" in Path(file_path).parts` 跨平台。
- **MCP `Popen` 永久丢弃 stderr** —— 调试困难；`CATAFORGE_MCP_DEBUG=1` 下保留 stderr inherit。
- **`agent/manager.tools_match` 无法解析 flow-style YAML** —— `tools: [a, b]` 之前被正则错切为 `["[a", "b]"]`；改 `yaml.safe_load` 统一处理 flow-style / block-style list / comma string。
- **`hook/base._spec_entry_for_script` 高频读盘** —— 加 `@functools.cache` 避免每次 PostToolUse 重复读 hooks.yaml 解析。

- **`cataforge deploy` 偏好相对 symlink，落地 `.claude/skills/` 跨环境可移植** —— `platform/helpers.py:symlink_or_copy` 之前在 Windows 直奔 `mklink /J`，junction 在 NTFS reparse point 里只能存绝对路径，仓库目录改名 / 移动后所有 `.claude/skills/*` 静默失效；多人开发者 / devcontainer 场景一并踩雷。现在 Unix 与 Windows-DevMode 都走 `os.symlink(rel, …)` 写相对路径，权限不足时回落 junction，最后兜底 copy。首次回落 junction 时 deploy log emit 一次 WARN，引导用户启用 Developer Mode。
- **`cataforge doctor` 升级为部署完整性的硬门禁** —— 之前 `.cataforge/{agents,skills,rules,hooks,platforms}` / `.claude/skills/` 缺失或链接悬空时，doctor 只打印 `MISSING` / `[absent]` 仍 exit 0，部署回归无人值守。新增 [`cli/doctor/deploy_integrity.py`](src/cataforge/interface/cli/doctor/deploy_integrity.py)：读 `.deploy-state` 后逐项校验 owned dir 存在 + per-skill 子链接可解析，悬空 junction / symlink 单独标 dangling 并指出修复命令。`check_file` / `check_dir` 引入 `required=True` 把源资产纳入退出码。doctor 末尾追加 `Summary: N passed / M failed` 一行，失败时附 `cataforge deploy` / `cataforge upgrade apply` 建议。

- **`cataforge deploy` 端到端幂等：删了文件能自愈、不再误删用户文件** —— 之前 `cataforge deploy` 对资产包内单文件型产物（agents `.md` / commands `.md` / `CLAUDE.md` 等）是幂等的，但对目录型产物（`.claude/skills/`、`.claude/rules/`）和源 `.cataforge/` 完全不是：在 Windows 非 Dev-Mode 走 NTFS junction 的链接里删一个 `SKILL.md` 会穿透删源；用户自己写的 `.claude/commands/<name>.md` 或 `.claude/skills/<name>/` 会被无归属判断的 prune 直接清掉（dogfood 的 `.claude/commands/framework-issue-resolve.md` 每次 deploy 都被点名）。本次重构按 P0+P1+P2+P3 一次性把幂等性补上：

  - **P0 归属型 prune**：新增 [`src/cataforge/runtime/deploy/manifest.py`](src/cataforge/runtime/deploy/manifest.py) 记录每次 deploy 写过 / 链过的相对路径到 `.cataforge/.deploy-manifest.json`；`deploy_commands` / `deploy_skills` / `deploy_agents` / `_prune_orphan_flat_files` 的 prune 一律改成「孤儿 ∩ 上次 manifest」，没在上次 manifest 里的文件一律视为用户自写，永远不删。
  - **P1 scaffold 自愈**：`Deployer.deploy()` 入口先跑 `copy_scaffold_to(force=False, backup=False)`，把 `.cataforge/` 里被穿透删 / 误删的源文件从 wheel 包补齐；`force=False` 决定它绝不覆盖用户编辑过的源。
  - **P2 junction 风险告警 + `--copy`**：`symlink_or_copy` 在第一次落 junction 时的 WARN 现在显式提示「**穿过 junction 删文件等同删源**」并指路 Developer Mode 或 `--copy`；新加 `cataforge deploy --copy` flag 直接落 `shutil.copytree`，IDE 侧的 `.claude/skills/<name>/` 是独立副本，删它不会再波及源。
  - **P3 `--rebuild`**：新加 `cataforge deploy --rebuild`，先按上次 manifest 清掉所有 owned path 再正常 deploy，用来从损坏 / 不一致状态做硬重置；首次部署上无 manifest 时退化为 no-op，绝不误伤用户文件。

  覆盖测试新增 16 个 e2e 用例在 [`tests/deploy/test_idempotency.py`](tests/deploy/test_idempotency.py)，把以上每个反例 pin 死：两次 deploy 状态一致、用户自写文件存活、source 被删能恢复、`--copy` 隔离副本、`--rebuild` 不误伤、manifest 不冒认用户文件等。

- **Windows CI 单元测试 4 个 pre-existing 失败一次性扫平** —— 都是 Py 3.10 / Windows 上的潜伏问题，PR #138 的 CI 触发后浮出。在 `.venv-py310` 本地复现到根因后逐个修：

  - **`test_windows_falls_back_to_junction_then_copy`** —— `symlink_or_copy` 的 WARN 文本里含「symlinks」字样，assertion `"symlink" in a` 误命中。改 WARN 文案为「relative-path soft links」绕开 substring；同时给 [`tests/platform/test_symlink_or_copy_portable.py`](tests/platform/test_symlink_or_copy_portable.py) 加 autouse fixture 在每测前后 `reset_junction_warning_state()`，把进程级 once-flag 重置干净，避免顺序依赖（先跑的测试烧掉 flag 后这个测试看不到 WARN）。
  - **`test_unwraps_legacy_whole_dir_link`** —— Py 3.10 没有 `Path.is_junction`，`Path.is_symlink()` 对 NTFS junction 也返回 False，导致 `deploy_skills` 的「whole-dir 链接 unwrap」分支在 3.10 上变成 no-op，stale junction 永远拆不掉。新增 [`helpers._is_dir_link`](src/cataforge/adapter/platform/helpers.py:18) 三段式检测：symlink → `is_junction()` → `ctypes.windll.kernel32.GetFileAttributesW` 检 `FILE_ATTRIBUTE_REPARSE_POINT` 位，覆盖 3.10 / 3.11 / 3.12+。test_helper 同步替换为这个 production helper。
  - **`test_concurrent_start_produces_single_pid`** —— 两线程争 spawn-lock 时 10s 必超时。本地复现锁定根因：`os.open(O_CREAT | O_EXCL)` 在 Py 3.10 Windows + 线程争用下，holder 释放锁（`os.unlink` 返回 OK、`os.path.exists` 返回 False）后，peer 线程的 `os.open(O_EXCL)` 仍持续报 `FileExistsError`，长达 10s。属内核句柄 / dirent 缓存的边角行为。修复加一层进程内 `threading.Lock`（per lock_path）做同进程串行化，文件锁仍保留给跨进程场景；额外把临界区收窄到「spawn-or-attach 决策 + 写 state」，readiness probe 移到锁外，并支持 `CATAFORGE_MCP_SPAWN_LOCK_TIMEOUT` env 让慢机器可调。
  - **`test_doc_gen_version_in_frontmatter_resolves_via_xref`** —— 在本地 Py 3.10 venv 上无法复现（运行 1290 测全绿），疑似与上面 3 个失败的连带受害测试。等本 PR CI 跑完再观察是否退稳定。

- **MCP `_save_state` 改为 atomic rename** —— PR #138 合并到 main 后，Ubuntu Py 3.13 `uv run --extra dev pytest` smoke 步骤仍稳定挂 `test_concurrent_start_produces_single_pid: multiple distinct PIDs {N, N+1}`。同 job 的主步 pytest 是绿的，同一份代码同一台机，只是 timing 略不同 —— 典型部分写竞争。

  根因：[`MCPLifecycleManager._save_state`](src/cataforge/runtime/mcp/lifecycle.py) 用 `path.write_text(...)` 单步写状态文件。它 open + write + close 之间存在窄窗：thread A 在 open / 写一半 / close 的任意中间点暂停，thread B 刚释放 spawn-lock 进入 `_load_state` 调 `json.loads`，读到半成品 → `JSONDecodeError` → 返回 None → thread B 误判「服务未起」→ 自己再 spawn 一遍。这就是为何两个 PID 总是连续号 ({N, N+1})：thread A 抢到锁创建第一个进程，状态还没写干净 thread B 已经读完空状态在 race 它。

  修复：dump 到同级 `.tmp.<pid>.<tid>` 临时文件，然后 `os.replace` 原子重命名替换正式状态文件。POSIX rename / NTFS replace 都是原子的，reader 看到的永远是「上一份完整状态」或「这次写完的完整状态」，不会再看见半成品 JSON。tmpfile 名带 pid+tid 保证同进程多线程写不互相覆盖临时文件。

- **`#142` §2.2 chokepoint 闭环** —— `cataforge.domain.kg._ask.ask()` 在 sub-PR 2 引入但仅在测试里使用；sub-PR 3 的 writer.py 在 phase 5 dedup ASK 上真正消费它。pre-commit grep gate 仍守住 `query(...) == True` 反模式不再出现于 `src/cataforge/domain/kg/`。

- **`.claude/scheduled_tasks.lock`** —— 加入 `.gitignore`（harness 本地锁文件不应入库）。

- **Windows 上 `symlink_or_copy` 写入的 symlink target 反斜杠破裂跨平台访问**（`src/cataforge/adapter/platform/helpers.py`） —— `os.path.relpath()` 在 Windows 返回 `..\\..\\src`，直接交给 `os.symlink()` 会把反斜杠原样写进 NTFS reparse 点。链接随后在 WSL / 网络挂载 / sibling POSIX CI runner 上访问即失效。修复：交给 `os.symlink` 前 `.replace("\\", "/")` 一次。回归测试在所有平台（即使无 symlink 权限）通过 `os.path.relpath` mock 拦截，验证传给内核的 target 串无反斜杠。

- **`cataforge sync-main` 解析 `git rev-list --left-right --count` 输出时未验证 token 数量** —— git 输出契约漂变（或者 locale 让 warning 串进 stdout）时只能见到含糊的 `ValueError: not enough values to unpack`，看不到 git 真实输出。改为先校验 token 数、再用专门的 `unexpected git rev-list ... output: <raw>` 错误信息；非整数也分开抛 `non-integer ahead/behind counts`。空输出仍按 `0/0` 处理保持容错。

- **`cataforge event accept-legacy` 写 `framework.json` 改为原子写** —— 同 `ConfigManager._write_raw` 的修复路径：旧实现 `cfg.paths.framework_json.write_text(...)` 在 truncate 与 write 之间崩溃会把 `framework.json` 留成零字节或半截 JSON，下次 `cataforge --version` 起就解析失败。改走 `atomic_write_text`，前后状态二选一。

- **`cataforge.core.corrections._append_markdown` 合并双写入分支并原子化** —— 旧实现首次调用 `with open("w")` 顺序 `write(_HEADER)` + `write(entry)`；进程在两次 write 之间挂掉就留下"只有 header 无 entry"且 `is_file()` 为真的状态，后续调用永远走 append 分支不再补 entry。改为读 (若不存在用 `_HEADER` 模板) → 拼接 → `atomic_write_text` 一次落盘；CORRECTIONS-LOG 增长频率低（每个项目寿命内一只手数得过来），多一次读 I/O 远小于"文件状态从此一致"的收益。

- **`cataforge.runtime.hook.base.hook_main` 不再吞掉 `KeyboardInterrupt`** —— 旧实现的 `except Exception` 把 `Ctrl+C` 转成 `exit 0`，部署或调度中 hook 出现长时间运行时用户按 Ctrl+C 想取消但外层流程继续跑下去，同时取消信号也对 wrapping CLI 不可见。新增显式 `except KeyboardInterrupt: raise` 早于通用分支，hook-errors.jsonl 也不再记录用户取消。

- **`cataforge.runtime.deploy.deployer._deploy_hooks` / `_apply_degradation` 保留 traceback** —— 旧实现 `except Exception as e: return [...]` 配 `logger.warning` 把 plugin import 错、属性缺失等真实问题压成 "hooks: generation failed — X" 一行，CI 排错只能看到这条没有 traceback。改为：先匹配 `(ImportError, AttributeError)` 给出 plugin 兼容性提示；其余 `Exception` 保留兜底；两条分支都用 `logger.exception(...)` 把完整 traceback 留到日志，action 行加上异常类型。

- **`cataforge.core.config.ConfigManager.version` 收窄 `except Exception` 为 `ImportError`** —— 老的兜底分支会把 `cataforge/__init__.py` 中的循环导入 / 语法错误悄悄当成 "用占位符版本"，让真 bug 永远没机会浮出水面。改为只兜底 `ImportError`。

- **`cataforge.core.events._safe_call` 添加 stderr 兜底** —— 典型 CLI 进程把 `cataforge` logger 默认在 WARNING 以上、无 stderr handler 绑定；事件处理器出错时 `logger.exception(...)` 实际写入了 *nothing*，handler bug 静默到完全看不见。改为：`logger.exception(...)` 之后若 `logger.getEffectiveLevel() > ERROR` 则向 `sys.stderr` 写一行 `[events] handler ... failed for ...: TypeName: msg`。`core` 模块不引入 click 依赖，使用裸 `sys.stderr.write`。

- **`cataforge.adapter.integrations.penpot.stop_mcp` 前置校验 `taskkill`** —— Windows Nano Server / 裁剪过的 CI 镜像里没有 `taskkill`；旧实现 `FileNotFoundError` 被外层裸 `except OSError: pass` 吞掉，函数照样报"已停止"但进程其实还活着。改为：调 `subprocess.run` 前 `shutil.which("taskkill")` 检查，缺失就抛 `CataforgeError` 含可操作的修复提示。

- **`cataforge.adapter.integrations.penpot._read_mcp_pid` / `_write_mcp_pid` 补 `encoding="utf-8"`** —— PID 是 ASCII 数字，行为上无差，但消除"裸 `open()` 跟随系统 locale"的隐患，与仓库内其他 I/O 一致。

- **`cataforge.interface.cli.ui.UI._write` 拆分 `BrokenPipeError` 与 `ValueError`** —— 老实现 `except (BrokenPipeError, ValueError): pass` 把两种含义完全不同的异常一起吞掉：前者是下游管道关了（合理静默），后者通常是 pytest CliRunner 在 invocation 之间换了 stream（也合理）但如果将来真有未预期的 `ValueError` 从 stream write 跑出来就会无声蒸发。改为：`BrokenPipeError` 单独静默；`ValueError` 走 `logger.debug(...)` 在 verbose 跟踪时可见、正常模式不污染输出。

- **`cataforge.utils.run_subprocess.run` 默认 `errors="replace"`** —— 修 Windows CI 上 `tests/platform/test_deploy_skills_maintainer_only.py` / `test_idempotency.py` / `test_symlink_or_copy.py` 共 8 个用例（target 路径不存在）。`platform.helpers._try_junction` 跑 `cmd /c mklink /J ...` 时 cmd 的 stdout 是 OEM codepage（CI 上的 US English Windows runner 用 cp437），出现 ≥0x80 字节就会在 wrapper 强制的 `text=True, encoding="utf-8", errors="strict"` 解码路径上抛 `UnicodeDecodeError`。本机表现为 daemon reader 线程异常告警但 junction 已建（test 过），CI 上则把异常上抛炸掉整条 `symlink_or_copy` 调用链，目标根本没建出来。

  默认改 replace 是真正想要的 child-process I/O 行为 —— strict 模式只在调用方明确需要"看到 decode 失败"时才有意义；批 3 加 `errors=` 参数时把默认设成 strict 是过度防守。`cataforge.runtime.skill.runner` 同步删掉显式 `errors="replace"`（现在已是默认）。

- **Windows admin / Dev-Mode 环境下 `symlink_or_copy` 生成不可解析 symlink** —— [#153](https://github.com/lync-cyber/CataForge/pull/153) 在 `_try_symlink` 加了 `os.path.relpath(...).replace("\\", "/")`，把相对目标里的反斜杠强制换成正斜杠（`..\..\src` → `../../src`）。无 `SeCreateSymbolicLinkPrivilege` 的 Windows 客户机上 `os.symlink` 抛 `WinError 1314`，fallback 到 junction 路径，问题被掩盖；但 GitHub Actions `windows-latest` 跑 `runneradmin` 时 `CreateSymbolicLinkW` 接受 `../../src` 创建 reparse 点成功，Windows 内核随后 lookup 阶段拒绝跟随正斜杠的相对 reparse target —— `target.exists()` / `is_file()` 返回 `False`，整条 fallback chain 因为没有异常信号也不会兜底，调用方拿到的"成功"返回值是假的。具体表现：`tests/platform/test_symlink_or_copy.py::test_creates_target_when_parent_missing` + 7 个 `deploy_skills` 相关 test 在 `windows-latest` 上 fail，本地无 admin / Dev-Mode 的 Windows 与所有 POSIX runner 全通过。

  修复：移除 `_try_symlink` 中的 `.replace("\\", "/")`，让 `os.symlink` 拿到 `os.path.relpath` 的原生输出（Windows 反斜杠 / POSIX 正斜杠）。NTFS reparse 点是 Windows 专有结构，POSIX 内核不会按 raw filesystem 语义跟随 —— WSL2 / DrvFs 与 SMB `mfsymlinks` 等跨平台访问层有自己的 Win32-path 翻译，对原生反斜杠的兼容性反而比正斜杠更好。同步删除 `tests/platform/test_symlink_relpath.py` —— 该回归测试断言"传给 `os.symlink` 的字符串不含反斜杠"，方向反了；正向 fail-on-Windows 不变量已经被 `test_creates_target_when_parent_missing` 通过 `target.exists()` 覆盖（这正是该 regression 在 CI 上能被抓到的根本原因）。

- **KG `kg query --timeout` 参数生效** —— 此前 `--timeout` 被静默忽略，现通过线程化执行 + 结果物化实现超时保护，超时抛出 `KGQueryTimeoutError`（exit code 6）。
- **KG doctor 提示消息引用正确的 CLI 命令** —— FAIL/WARN 消息中不存在的 `--on-conflict` 和 `--fix-orphans` 选项替换为 `cataforge kg repair`。
- **KG `ask()` SPARQL 验证器** —— 修复带注释前缀的合法 ASK 查询被误拒、含 `?ask` 变量名的 SELECT 查询误通过两个缺陷。
- **KG `verify_after_write` 不再双重计数缺失实体** —— 先检查实体存在性，缺失时跳过 hash 检查。
- **KG `_kg_validate_report` 的 `stale` 键正确填充** —— 从 reconcile ghost_entities 填充，下游消费方可检测 KG-only 实体。
- **KG `commit()` 双重提交检测** —— 重复调用 `commit()` 抛出 `RuntimeError` 而非静默忽略。
- **KG `_sparql_lit()` 转义完整** —— 增加 `\n`/`\r`/`\t` 转义，防止含换行的输入导致 SPARQL 语法错误。
- **KG frontmatter `---` 分隔符容忍尾随空格** —— `.strip()` 替代 `.rstrip("\n").rstrip("\r")`。
- **KG export SPARQL 模板注入防护** —— entity_id 中的 `\` 和 `"` 在模板替换前转义。

### Removed

- **`KGTransactionConflictError`** —— 导出但从未被抛出的死异常类。
- **`CompareReadReport.skipped` 字段** —— 从未写入的死字段。
- **`--threshold` CLI 选项** —— 文档标注"当前忽略"的未实现选项。
- **`_fetch_subclass` 透明别名** —— `requirement()` 直接调用 `_fetch_typed`。
- **KG 源码设计残留** —— 24 个文件中的 `sub-PR`/`task-N`/`spike-N`/`issue #` 等内部跟踪引用。

### Idempotency

幂等性靠三重保险（task-4 §4.4）：

1. 每条 SPARQL 模板 `ORDER BY ?sort_key` 让 SPARQL 引擎本身先排好序；
2. `hydrator.hydrate_rows()` 对每个 relation 组按 `(sort_key, entity_id)` 复合键 Python 侧再排一遍 —— SPARQL 引擎不保证 join 顺序稳定，Python 侧重排是托底；
3. Jinja2 `StrictUndefined` 阻断任何对 `generated_at` / `exported_at` 之类时间戳变量的隐式引用 —— 模板作者一不小心加这种字段会立刻 raise 而不是静默渲染。

`tests/kg/test_export.py::test_export_is_byte_identical_across_runs` 和 `::test_export_in_place_overwrite_is_idempotent` 都对两次连续导出的每个文件 SHA-256 做完整对账。

### Notes

- Sub-PR 6 完成 Alpha → GA 闸口 2 条退出条件中的最后一条工具缺口。剩余闸口仍需在真实项目上跑通："doctor `kg_ingestion_completeness` ERROR-enforced 一个完整 reconcile cycle" + "Group A 15 个 call point 黄金文件回归" + "waterfall + agile 端到端绿"。
- Sub-PR 7 起的快照/回滚机制（`cataforge kg snapshot` / `repair` / `rollback` / `diff`）是下一道工序，task-7 §7.3 的回滚路径目前仍是空缺。

### Documentation

- **`hook test` 自定义命令 `shell=True` 的边界说明** —— `docs/reference/cli.md` 补一段 *Custom hook commands run via shell=True* 注记，明确威胁模型（hook 字符串由仓库维护者拥有，不接收远程输入；pipe / redirect 是设计目的），让审计读到代码注释时不必反推意图。
- **`docs/migration/kg-cutover-0.5.0.md`** —— KG-first 切换的 operator 视角迁移指南：cutover 模型（per-doc_type rolling，无 dual-track）、推进/撤回 doc_type 的判定、单 doc_type 回滚与 systemic snapshot 回滚的两级路径、已知边界。从 [task-7 §7.5](docs/proposals/kg-migration-0.5.0/task-7-rollout-strategy.md) 提取后按 operator 视角重写。

### Known Limits

KG-first 模型下，operator 应知悉以下边界。它们不阻塞 0.5.0 落地，但决定推进节奏与故障兜底面。

| 项 | 状态 | 处置 |
|---|------|------|
| `kg_active_doc_types` Alpha 范围 = `{prd, arch, test}` | 设计选择 | 其它 doc_type 在 0.6.0+ 评估扩展；当前对它们读路径不变 |
| SHACL `sh:closed true` 运行期校验 | `--shacl` flag 已留，pyoxigraph↔rdflib 桥未实现 | LinkML schema-level write-time 检查兜底；GA 重审 |
| 自然语言查询 LLM 接口 | 0.6.0+ 候选 | 现有 `QueryAPI` / `TraceAPI` 提供编程接口 |
| `cataforge kg compare-read` 退出码 = 0 | 设计选择（diagnostic, not gate） | alarm 持续才触发"移出 `kg_active_doc_types`" 运维动作 |
| `docs/.doc-index.json` 派生化 | 0.5.0 已生效 | 第三方读者改 `cataforge kg query` 或 `cataforge docs load`（按 doc_type 自动路由） |
| `cataforge.domain.kg._shim` 5 + 3 个函数发 `DeprecationWarning` | 0.6.0 移除 | 调用方迁到 `QueryAPI` / `TraceAPI` 直接接口 |
| pyoxigraph 0.5.x 无 OWL/RDFS 推理 | 受 pyoxigraph 上游限制 | `cataforge kg init` 在 bootstrap 时显式物化 `rdfs:subClassOf` triples 兜底子类闭包查询 |
| Systemic snapshot 回滚依赖人工预先 `cataforge kg snapshot` | 0.5.0 已发货命令 | 升级前打 git tag (`git tag pre-kg-cutover-0.5.0`) + 跑 `cataforge kg snapshot`，建议合并到 upgrade 流程 |

<a id='changelog-0.4.1'></a>

## [0.4.1] — 2026-05-24

### Added

- **code-review `integration-wiring` 维度** —— Layer 2 新增 `integration-wiring (consistency)` 检查，识别 prop 链路 / 事件 handler / store action 是否真实落地（非 `() => {}` / `return null` 占位）；Layer 1 配套新增 wiring 空 handler 正则扫描（`code_lint.wiring_empty_handler`）。短路豁免：`user_facing_critical_path: true` / `consumer_components` 非空时即使 light/chore 模式也强制跑 Layer 2。
- **testing e2e 后门扫描** —— 新增 `e2e_backdoor_scan` + `e2e_real_input_presence` Layer 1 检查，命中 `window.__*__=` / `?e2e=1` / `setStore(JSON.parse(...))` 等模式即 WARN；e2e 套件至少含一处 `keyboard.type` / `page.fill` / `send_keys` 真实交互调用，否则 WARN。
- **agent-result schema v0.2.0 wiring 字段** —— 新增 `wiring_complete: true|false|"n/a"` + `wiring_evidence: array<{consumer_file, consumer_line?, deliverable_symbol}>`；implementer 必须填写，tdd-engine Step 3 解析后将 `wiring_complete=false` + `user_facing_critical_path=true` 升级为 HIGH continuation。
- **orchestrator Phase Transition hygiene gate** —— Phase Transition Protocol 新增 Step 6：派发下一阶段 Agent 前强制运行 `cataforge claude-md check`，FAIL 时阻塞推进并提供 inline `cataforge claude-md compact` 恢复选项。
- **framework-review B5_hook_installed 检查** —— 新增 FAIL 级检查：`hooks.yaml` PostToolUse 段必须含 `script: validate_agent_result` + `matcher_capability: agent_dispatch` 条目，否则 `agent_return` 事件永远不会写入 EVENT-LOG，B5-γ 漂移检测会在 0 数据下静默放行。
- **framework-review B8 Anti-Patterns 系列** —— 新增 B8-α/β/γ：每个非豁免 skill / agent 应有 `## Anti-Patterns` 段（缺失 WARN）；skill bullet 数 ≥ `ANTI_PATTERN_MIN_COUNT_SKILL`（默认 3）/ agent ≥ `ANTI_PATTERN_MIN_COUNT_AGENT`（默认 4），不足 FAIL；每条 bullet 正文 ≥ 12 字符（过滤 placeholder），不足 WARN。
- **plugin-style 跨语言规则架构** —— 新增 `cataforge.runtime.skill.rules.loader` 模块（`validate_yaml_text` / `discover_rules` / `RuleSpec`），按 `(rule_type, language)` 索引；wiring + e2e 正则迁移到 YAML（`cataforge.runtime.skill.builtins.{code_review,testing}.rules.*.yaml`），项目可在 `.cataforge/skills/<skill>/rules/` 放同名文件覆盖默认值，加新语言只需放 YAML 不改 Python；framework-review 新增 B3-β `rules_schema_compliance` 自动校验项目 YAML。
- **doc-review `ac-observability` 检查** —— dev-plan AC 用主观语义动词（"很好地处理…"/"友好地…"）会被 needs_revision；AC 必须可观察可测试。
- **sprint-review `wiring-completeness` 维度** —— Layer 2 新增维度，并细化 `ac-coverage` 要求 non-mock 测试。
- **COMMON-RULES §verdict_blocking_semantics** —— 明确 `approved` / `approved_with_notes` / `conditional_release` / `needs_revision` 在 Phase Transition / Sprint Review 流转上的阻塞语义，禁止用 `[ENV-LIMITATION]` 让缺陷豁免 needs_revision。

- **SKILL.md `maintainer-only: true` frontmatter 标志** —— SkillMeta 新增 `maintainer_only: bool` 字段；`cataforge deploy` 默认跳过 maintainer-only skill，避免无用 prompt 上下文下发给下游业务项目。`cataforge deploy --include-maintainer-only` 让上游 CataForge 仓库 dogfood 时一并部署。framework-issue-resolve 是当前唯一 maintainer-only skill；标记后下游不再拿到。
- **`.claude/commands/framework-issue-resolve.md` slash command wrapper** —— 上游 CataForge 仓库 maintainer clone 后无需 deploy 即可在 Claude Code 用 `/framework-issue-resolve` 触发五步闭环。wrapper 通过 `.gitignore` 例外（`!.claude/commands/framework-issue-resolve.md`）单文件 git-tracked，其他 `.claude/commands/` 内容仍 ignore。
- **deploy_skills per-skill 链接** —— 原先整个 `.cataforge/skills/` 目录被作为单一 junction/symlink 暴露到 `.claude/skills/`；改为枚举每个 skill 子目录单独链接，并在 deploy 时检测 maintainer-only frontmatter 决定是否暴露。旧的整目录 link 在升级 deploy 时被自动 unwrap。
- **`docs/reference/wiring-checks.md`** —— 新建 reference 文档，承载具体语言的 wiring 识别模式（JS/TS / Python / Go / Rust / Java 分节）。code-review §integration-wiring 与 tech-lead §production-path AC 主体退回语言无关、以 markdown 链接引用本 reference。
- **anti-rot 守卫 `scripts/checks/check_no_language_coupling.py`** —— 扫 `.cataforge/skills/**/SKILL.md` / `.cataforge/agents/**/AGENT.md` 主体中的特定语言业务关键字（`FastAPI` / `Spring @Autowired` / `Redux` / `useEffect` / `SQLAlchemy` / `goroutine` / `tokio::spawn` 等），命中 FAIL 并打印应迁入的 reference 路径；豁免：fenced code block / `[…](docs/reference/…)` markdown link / 同行 `<!-- allow-language-coupling: <reason> -->` escape hatch。接入 pre-commit + per-PR test.yml + weekly anti-rot.yml。
- **`derive_doc_id(title, kind)`** —— `cataforge.core.feedback` 新增 slug 派生工具，CLI / API 不传 `doc_id` 时自动从 title 派生符合 `DOC_ID_RE`（`^[\w-]+$`）的 id，前缀 `feedback-{kind}-`，title 已含 `feedback-` 或 `{kind}-` 前缀时自动去重。

- **implementer/AGENT.md §Assertion Strength Guard** —— GREEN/Light 完成前对让测试 PASS 的断言做强度自检：仅校验 mock/spy 调用计数 / 对象存在性 / 常量真值的"弱断言"返回 blocked；mock 中诡异条件让弱断言 PASS（永远返回常量 / 永远 raise / 强行短路）视为 implementation bug 假阳性而非测试问题。code-review §Layer 2 test-quality 新增 "断言强度" 子项作为审查侧兜底。
- **implementer/AGENT.md §Post-GREEN Validation 四档表** —— GREEN/Light 完成后按 tdd-engine 四档执行不同强度收尾：standard / light-dispatch 强制修改文件 lint + 全量回归 + `git diff --name-only` 报告；light-inline 豁免全量回归保 lint；prototype-inline 全豁免（lint hook 兜底）。lint 失败 3 次未通过返回 blocked。
- **tech-lead/AGENT.md §Execution Rules AC literal-reference 规则** —— AC 引用架构接口字段名 / 返回值结构 / 枚举值时必须逐字复用 arch 文档定义并附 `[ARCH#§M.API-NNN]` 锚点；不得用同义词 / 翻译 / 简写替代，附 3 反例（`内容数` → `content_count` 等）。
- **`docs/reference/corrections.md`** —— 新建 reference 文档承载 5 deviation 类型语义（preference / self-caused / external / framework-bug / upstream-gap）+ 各 1-3 个具体示例 + "不在枚举内的常见误标"重映射表（`protocol-gap` → self-caused/upstream-gap；`technical-constraint` → external；`framework-debt` → framework-bug/upstream-gap）。下游 RETRO 用错枚举导致 `cataforge feedback correction-export` 永远空 bundle 的问题从源头杜绝。

- **SKILL.md `<!-- requires: cataforge>=X.Y.Z -->` 注解 + B3 release-lag INFO 降级** —— B3 anchor 漂移 (`check_id` 引用了 manifest 未声明的 id) 在 release 发布到 PyPI 与下游 `cataforge upgrade` 之间窗口内可能误判：上游 SKILL.md 已声明新 check_id，下游 cataforge 包仍是旧版未注册。SKILL.md 顶部可加 `<!-- requires: cataforge>=0.4.1 -->` 注解，runtime 版本低于声明时把 orphan anchor 从 FAIL 降为 INFO；runtime 满足时维持严格 FAIL 守护。
- **B1-β PROTOCOL companion 扫描** —— `framework-review` B1-β size threshold 之前仅扫 AGENT.md / SKILL.md 主体，遗漏 `agents/<id>/*PROTOCOL*.md`（如 ORCHESTRATOR-PROTOCOLS.md）等 companion 文档；这些 companion 与主体一样每次 LLM 调度都被加载，必须共同受 META_DOC_SPLIT_THRESHOLD_LINES (500) 约束。新增 5 个测试覆盖发现 / 单数 PROTOCOL / 复数 PROTOCOLS / 超阈值 FAIL / scope=skills 不扫 agent。
- **12 个 skill `## Anti-Patterns` 段** —— arc-design / change-guard / debug / deploy-config / penpot-{implement,review,sync} / platform-audit / req-analysis / task-decomp / tech-eval / ui-design 在 B8-α/β/γ 守门下补齐 Anti-Patterns 段（每段 ≥3 条具体反例 + 后果描述）。devops / tech-lead placeholder-thin 条目重写为含具体后果陈述。
- **`docs/reference/builtin-skill-layout.md`** —— builtin skill Python 包命名约定（`cataforge.runtime.skill.builtins.<skill_name>`，下划线分词），同时列出存量不符约定的 skill 待后续 narrow-PR 迁移。
- **`cataforge.adapter.platform.instruction_cache`** —— `platform/base.py` 的 instruction-hash 持久化逻辑抽取为独立模块；platform deploy 现复用统一缓存接口。

- **doc `content_hash` + `dep_hashes` 快照** —— `.doc-index.json` 每个文档新增 `content_hash`（frontmatter 剔除后 body 的 sha256 前 8 位），含 `deps:` 字段的文档同时写入 `dep_hashes: {upstream_id → upstream_content_hash}` 快照其依赖时的上游版本。
- **`cataforge docs validate` 检 `stale_deps`** —— 比对 downstream 文档的 `dep_hashes` snapshot 与上游 doc 当前 `content_hash`，不一致即列为 stale dependency WARN（不阻断 validate，仅提示 downstream 可能需要跟随更新）。`validate_docs()` 返回值新增 `stale_deps` key。
- **doc-review §双向覆盖检查 (`check_bidirectional_coverage`)** —— `arch` / `dev-plan` / `ui-spec` 主卷 review 时反向扫描上游文档（prd / arch）的所有 `^### F-NNN` / `^### M-NNN` 锚点，downstream 主卷必须引用全部上游 item，未覆盖项 FAIL 并列出（>5 项时截断显示）。从源头堵住"PRD 加了新 feature 但 ARCH/PLAN 没跟进"的悄然漂移。
- **`docs/research/feedback-analysis-doc-drift-and-iteration.md` + `revision-plan-drift-prevention-and-iteration.md`** —— CataForge v0.4.0 结构性缺陷三维分析（PRD/ARCH/PLAN 漂移 / 跨引用腐化 / 用户 checkpoint 稀疏），含 14 条按优先级排序的改进提案与实现草图。后续 issue/PR 会按提案分批落地。

- **test-writer/AGENT.md §Behavioral Assertion Mandate** —— 禁止存在性断言（hasattr/isDefined/isNotNone/callable/len>0）6 种模式表 + 假实现检测 + 期望值溯源到 AC Then 子句；测试质量自检从三维度扩展为四维度（+行为验证充分性）。
- **tdd-engine/SKILL.md dispatch prompt 注入 PRD 上下文** —— Step 1 新增 user_story + business_rules 加载；RED/Light Dispatch/Light Inline 三处 prompt 均注入 `## user_story` 段。
- **task-decomp/SKILL.md AC Given-When-Then 格式约束** —— 每条 AC 必须包含 Given（前置条件）、When（触发动作）、Then（可观测结果），禁止"实现 X"等无行为描述的模糊 AC。
- **code-review/SKILL.md §增量审查模式** —— `task_type=revision` 时审查范围收窄到 `git diff` 涉及的文件和函数。
- **typed_checks.py GWT 格式检测** —— doc-review Layer 1 新增 Given/When/Then 关键词检测，AC 缺 GWT 结构发出 WARN。
- **`scripts/checks/check_doc_structure.py`** —— pre-commit + CI 守卫，扫描 `.cataforge/` 下 markdown 文件的非标准步骤编号（3a./4b.）、编号跳跃、编号重复。
- **CLAUDE.md §硬约束 3 · 文档结构规范** —— 编号列表必须使用连续整数，禁止非标准子步骤编号/编号跳跃/编号重复。

### Changed

- **B5-γ phase-routed agent 0 returns 升级为 FAIL** —— `B5_eventlog_agent_return_drift` 在 `total_returns ≥ EVENT_LOG_DRIFT_MIN_EVENTS` 且某 phase-routed agent 0 returns 时，从 WARN 升级为 FAIL（强 dead-routing 信号；阈值已过滤稀疏数据）。
- **self-update Step 6 增加 hygiene 同步** —— 升级后强制同步 CLAUDE.md `框架版本` 字段并跑 `cataforge claude-md check`，FAIL 仅作为提示（让 Phase Transition 在下次推进时强制处理）。
- **ORPHAN_SKILL_WHITELIST 扩充** —— `framework-issue-resolve` / `framework-feedback` 加入白名单（用户直接调用，不在任何 AGENT.md `skills:` 中声明）。
- **framework.json 新增常量** —— `PRE_DEPLOY_DEMO_REQUIRED` / `PRE_DEPLOY_DEMO_MIN_ACS` / `ANTI_PATTERN_MIN_COUNT_SKILL` / `ANTI_PATTERN_MIN_COUNT_AGENT`。

- **`cataforge feedback bug|suggest|correction-export` 输出 prepend YAML front matter** —— `_render_header` 之前注入 `id` / `doc_type: framework-feedback` / `status: approved` / `deps: []`，让 `--out PATH` 落盘的 bundle 直接通过 `cataforge docs validate`，不再 orphan FAIL。
- **`cataforge issue triage` 多 label 改 OR 语义** —— `gh issue list --label X --label Y` 是 AND 语义，会漏只挂一种 label 的 suggest / bug issue；改为按每个 label 各调用一次 `gh`、按 issue number 合并去重，让 `framework.json#feedback.gh.labels` 配置的 label 并集真正生效。
- **`cataforge issue triage` reported_version 解析覆盖 issue 模板格式** —— 新增 `_VERSION_TEMPLATE_RE` / `_VERSION_BOLD_RE` 识别 `### CataForge version\n\n0.4.0`（H3 模板）与 `**CataForge package**: \`0.4.0\``（markdown bold env 块），不再让`cataforge feedback ... --gh` 生成的 GitHub issue 落入 `unrelated`。
- **code-review §integration-wiring 与 tech-lead §production-path AC 语言解耦** —— 主体退回 generic 接线判据（接线对象在生产路径有真实调用点、仅 tests/ 内调用不算落地），具体语言模式抽到 [`docs/reference/wiring-checks.md`](../docs/reference/wiring-checks.md)。
- **`scripts/checks/check_no_design_residue.py` 守卫范围扩展** —— 在原 HTML 注释残留（`<!-- 变更原因 -->` / `<!-- diagnostic #N -->`）之外，新增 inline 叙事残留识别：`issue #N` / `PR #N` / `closes|fixes|closeout #N` / `landed in` / `vX.Y.Z 起` / `pre-vX.Y.Z`；fenced code block 内自动豁免（规则文件 regex 字面量合法）；保留同行 `<!-- allow-design-residue -->` escape hatch。
- **`CLAUDE.md` 新增 §Agent / Skill 撰写约定** —— 明确两条硬约束：(1) 最小可行修改（删到不能再删；禁止溯源引用 / 版本里程碑 / 过程标签 / 对比叙事 / HTML 注释残留）；(2) 与编程语言解耦（主题是职责不是语言，具体语言关键字进 `docs/reference/`）。两条都列示守卫脚本、合法例外、escape hatch 机制。

- **refactorer/AGENT.md §Anti-Patterns 硬禁所有 git 操作** —— refactorer 仅产出文件路径，git 由 orchestrator 独占；add / commit / push / branch / reset / restore / checkout / stash 全部明文禁止。配套 tdd-engine §Step 4 协议层防御。
- **tdd-engine/SKILL.md §Step 4 REFACTOR 完成后验证** —— orchestrator 在 refactorer 返回 completed 后跑 `git status --short` 比对调度前 baseline；staged/unstaged 变化中含 deliverables 外文件、HEAD 位移（分支切换 / 新增 commit）、working tree 出现 stash 或 cherry-pick 中间态 → BLOCKED 并请求人工介入。

- **`framework_check.py` 1613 → 203 LOC** —— B1..B8 检查拆分到 `cataforge.runtime.skill.builtins.framework_review.checks.b{1..8}`，配合 `_types/_discover/_constants/_framework_data/_hook_resolution` 内部模块；公开 API 通过 `__all__` re-export 保持稳定，下游调用方零修改。
- **`doctor_cmd.py` 1218 → 142 LOC** —— `cataforge.interface.cli.doctor` 拆分为 `_helpers/migration/protocol_refs/hook_health/skill_health/event_log/hygiene/provenance` 子模块；`cataforge doctor` 命令行接口不变。
- **B5-γ phase-routed agent 0 returns 升级条件** —— `total_returns ≥ EVENT_LOG_DRIFT_MIN_EVENTS` 且某 phase-routed agent 0 returns 时 FAIL（强 dead-routing 信号；阈值过滤稀疏数据），低于阈值时仍为 INFO。
- **`test-writer` / `refactorer` `skills: []` 标注** —— 两个 AGENT 留空 skills 不是疏漏而是 tdd-engine inline-dispatch 设计：tdd-engine 直接组装 prompt 调度二者，不经 skill 路由。在 frontmatter 注释明确，避免 framework-review B5 误报 orphan。

- **`doc-gen/templates/standard/dev-plan.md`** —— task 模板 frontmatter / AC 段约束跟进 #125 GWT 格式与 task-decomp #123 literal-reference 规则，模板示例统一改为 `Given X / When Y / Then Z [ARCH#§M.API-NNN]` 形态。
- **`task-decomp/SKILL.md` AC literal-reference 强化** —— 在 #123 写入的 "AC 引用 arch 字段必须逐字复用" 基础上，明示当 PRD F-NNN 被 dev-plan 间接覆盖时仍需把 PRD 锚点写进任务 context_load，避免 LLM 在 AC 推断时遗忘业务规则源头。
- **`sprint-review/SKILL.md`** —— Layer 1 §coverage-check 段补一条：每 Sprint 结束前跑 `cataforge docs validate`，`stale_deps` 非空时在 sprint review 报告里列出，maintainer 决定下 Sprint 是否安排同步任务（不强制阻断）。

- **tdd-engine/SKILL.md 流程轻量化** —— per-task code-review 改为分级触发：仅 `security_sensitive` / `user_facing_critical_path` / `consumer_components` 非空的高风险任务走即时审查，其余延迟到 sprint-review 批量覆盖；agile-standard 模式的 light 任务放宽为可走 light-inline（审计粒度通过 EVENT-LOG 保持）。
- **ORCHESTRATOR-PROTOCOLS.md Revision Protocol 增量审查** —— revision re-review 仅审查 `git diff` 变更部分，上轮无 CRITICAL/HIGH 的维度标注 `[previously-approved]` 不重复审查；needs_revision 循环上限从 N≥3 收紧到 N≥2。
- **ORCHESTRATOR-PROTOCOLS.md Sprint Review Protocol** —— 新增 Batch Code-Review 机制，对未经 per-task code-review 的延迟任务在 sprint-review 报告中逐任务覆盖 L2 维度。
- **doc-gen 模板 tdd_acceptance 格式** —— standard/lite/sprint-volume/brief 四套模板的 AC 占位符从 `{测试描述} → 预期: {结果}` 改为 Given-When-Then 格式。
- **sprint_review `code_review_present` 严重等级** —— 从 FAIL 降为 WARN，适配延迟批量审查模式。

### Fixed

- **tech-lead/AGENT.md 残留 `dep-analysis` 引用** —— 重命名为 `task-dep-analysis`（v0.1.15 后的正确名称），消除 `cataforge doctor` B2-α orphan WARN 的真实源头；task-decomp/SKILL.md 同步更新两处引用。
- **6 个 skill / 1 个 agent Anti-Patterns 缺失或不足** —— code-review / sprint-review / doc-review / self-update / task-dep-analysis 补写 `## Anti-Patterns` 段（每段 ≥3 条）；refactorer/AGENT.md Anti-Patterns 从 2 条扩到 5 条达到 agent ≥4 floor；qa-engineer/AGENT.md Anti-Patterns 扩到 6 条覆盖 verdict 三态语义。

- **8 个 skill / agent / rules 文档 12 处存量设计残留清理** —— `COMMON-RULES.md` / `code-review/SKILL.md` ×2 / `orchestrator/ORCHESTRATOR-PROTOCOLS.md` ×2 / `sprint-review/SKILL.md` / `self-update/SKILL.md` ×4 / `testing/SKILL.md` / `task-dep-analysis/SKILL.md` 中 `issue #113 反馈现象` / `v0.1.10 起` / `v0.1.15 起由原 ... 重命名为 ...` / `pre-v0.4.0 项目` 等溯源叙事与版本里程碑全部移除。
- **`COMMON-RULES.md §禁止设计阶段与变更说明残留` 自检 regex 扩展** —— 原 regex 仅覆盖 `之前 / previously / used to / 修复了 / 替代了 / MVP / 改为` 等关键词；新增 `issue\s*#?\d+` / `PR\s*#?\d+` / `closes|fixes\s*#\d+` / `closeout` / `landed in` / `本次新增` / `本轮加入` / `现已支持` / `v[0-9]+\.[0-9]+\.[0-9]+\s*起` 等溯源关键词。

- **`sprint_check.py` exit=2 stderr 诊断** —— 顶层 try/except 兜底，未捕异常时打印 `[FAIL] sprint_check runtime error: <type>: <msg>` + 5 行 traceback 摘要（text/json mode-aware），exit 2 区分 runtime error 与 normal FAIL（exit 1）。先前 sprint-review Layer 1 在某些 runtime error 路径只给状态码不输出诊断，orchestrator / maintainer 无法定位失败 check。

- **ORCHESTRATOR-PROTOCOLS.md 非标准步骤编号** —— Bootstrap `3a.` 重编号为连续整数（步骤 3~10）；Revision Protocol `4a.` 合并到步骤 4 行内；Sprint Review `2a.` 合并到步骤 2 行内；Change Request Protocol 重复 `4.` 收拢为散文段落。

<a id='changelog-0.4.0'></a>

## [0.4.0] — 2026-05-06

### Added

- **Project Bootstrap 写入跨平台 `.gitattributes`** —— ORCHESTRATOR-PROTOCOLS §Project Bootstrap 新增 Step 3a：项目根目录无 `.gitattributes` 时写入最小集（`* text=auto eol=lf` + 常见文本/二进制扩展名），治理 Windows `core.autocrlf=true` 与 fixture/snapshot 字节哈希漂移导致的多平台测试 fail（reporter 在 wechat-typeset-X 0.1.1 实测 22 vitest snapshot fail 落地后清零）。已存在 `.gitattributes` 时只读判断（含 `eol=` 即视为已归一化），不动用户既有内容。闭环 [#103](https://github.com/lync-cyber/CataForge/issues/103) EXP-010。

- **Approved-with-Notes Protocol 选项 (4) 全量 inline-fix** —— ORCHESTRATOR-PROTOCOLS §Approved-with-Notes 新增第 4 个用户决策路径：MEDIUM/LOW 问题数 ≥ 8 且全部为表述漂移 / 格式 / 引用对齐 / 完整性补充（非设计缺陷）时，orchestrator/reviewer 主线程逐条 inline-fix（同会话），完成后 verdict 保持 approved_with_notes 但实质等价 approved，文档 status: draft → approved；REVIEW 报告末尾追加 §Inline-Fix 闭环记录 表。不适用 PRD / ARCH 等需求冻结类文档（防止文档冻结后被静默改动）。闭环 [#106](https://github.com/lync-cyber/CataForge/issues/106) EXP-009。

- **`cataforge sync-main`** —— 单命令把本地默认分支从 `origin` 快进到最新；`--prune-merged` 删除已合并的 feature 分支。拒绝在工作区脏 / 分叉 / detached HEAD 时执行任何写动作。`prepare-pr.sh` 的 cheat sheet 也一并指向这条命令。
- **`cataforge claude-md`** —— `check` 子命令对照 `framework.json#claude_md_limits` 校验 CLAUDE.md 大小、§项目状态 行数、Learnings Registry 条目数；`compact` 子命令把超限的 Learnings Registry 旧条目归档到 `.cataforge/learnings/registry-archive.md`。同一组阈值由 `cataforge doctor` 复用。
- **`cataforge issue triage` / `cataforge issue close`** + 配套 **framework-issue-resolve skill** —— 上游 maintainer 侧 GitHub issue 全闭环。`triage` 拉 open issue，Layer 1 解析 `cataforge --version` / `framework-review FAIL` / `upstream-gap` 字段，分类 `confirmed` / `already-fixed` / `needs-repro` / `unrelated`，把 `confirmed` 写成 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md` 草稿（5 类 verdict 还含 maintainer 手编 `wontfix-by-design`）。`close <N> --verdict {fixed|wontfix|already-fixed} [--pr ...] [--reason ...]` 模板化包 `gh issue close --comment`，统一文案。闭环 framework-feedback → upstream issue → SKILL-IMPROVE → 修复 PR → close。
- **`cataforge feedback ensure-labels`** —— 一次性在上游仓库创建 `framework.json#feedback.gh.labels` 声明的所有 label（幂等，跳过已存在的）。
- **COMMON-RULES §禁止设计阶段与变更说明残留** —— 长期文档 / 源码默认不写版本里程碑、阶段标签、对比叙事；变更说明只属于 CHANGELOG / commit / PR 描述。

- **ORCHESTRATOR-PROTOCOLS §Sub-Agent Truncation Recovery Protocol** —— 与既有 §Agent Crash Recovery 协议区分：crash 是 process 死（无任何输出），truncation 是 token budget 耗尽（artifact 已部分落地，仅 `<agent-result>` JSON 缺失）。截断时主线程不再 blocked，而是按完成度路由：≥70% AC PASS（或 deliverables 齐全）→ 主线程接管收尾（inline-fix lint/typecheck + 补落盘 + 写 EVENT-LOG `state_change` 事件）；<70% → blocked 请求人工。每任务最多 1 次 truncation recovery，第 2 次同任务截断说明 prompt 设计问题，进 retrospective backlog。与 tdd-engine §Mid-Progress Drop Contract 协同：契约预防截断，本协议事后兜底。

- **sprint-review 三档模式 + `project_features` schema** —— sprint-review SKILL.md §审查档位 正式声明 standard / lite / **merged-review** 三档（merged-review 之前隐式存在，5 次实战稳定但框架文档未承认）。dev-plan 主卷 frontmatter 新增可选 `project_features` 块（`merged_review` / `deliverables_accept_alternation` / `unplanned_glob_patterns` 三键），由 `cataforge.runtime.skill.builtins.sprint_review.sprint_check.load_project_features()` 加载。

- **tdd-engine §Mid-Progress Drop Contract** —— LOC > 200 或 AC > 6 的任务在 implementer dispatch prompt（standard Step 3 + light-dispatch）强制注入 4 步落盘契约：先骨架 → 逐 AC 填充 → 每 AC 后跑测试 → 禁止末尾堆批 Edit。治理子代理在 finalize 阶段集中产出导致的 task-notification truncation（100+ tools / 100K+ tokens / 5min+ 后被打断）。light-inline / prototype-inline 不适用（主线程产出，不受子代理 token 额度限制）。失效时由 ORCHESTRATOR-PROTOCOLS §Sub-Agent Truncation Recovery 接管。

- **tech-lead 任务卡 `expected_tool_budget` 软门禁** —— dev-plan 任务卡可选标 `expected_tool_budget: ~N`（典型值 80-120，仅 standard 模式有意义）。tech-lead AGENT.md 新增决策矩阵（LOC × AC × Modules → light 内联 / light 拆分 / standard + mid-progress 三档），用于反向校验 `tdd_mode` 选择是否合理。orchestrator 在 dispatch 时按本字段做 sanity check（>150 警告，>200 阻断并建议拆分为 light 序列）。配合 tdd-engine §Mid-Progress Drop Contract（standard + LOC > 250 时强制注入 4 步落盘契约）。

- **test-writer §测试质量自检 checklist** —— 每个 `test()` / `it()` 块编写完成后强制三维度自检：(1) lint 白名单合规（4 类常见禁用规则替代 pattern：non-null assertion / `.not.toBeNull()` on `.find()` / `isNaN` / `delete obj.key`），(2) 测试名 ↔ 断言意图一致性（4 类反向 anti-pattern：反义 API 调用 / AC 语义 ↔ 断言 token 不符 / 测试数据 ↔ 名称反向 / Mock 缺失），(3) 跨平台 syscall 测试模式（决策树 + vi.hoisted + vi.mock(node:fs/promises) 模板代码 + fs.symlink/child.kill/chmod 三类典型场景）。配套 §Anti-Patterns 加一条"跨平台 syscall 优先 mock 而非 platform-skip"。

- **`event-log` schema 接收 `session_end` 事件** —— `event` enum 与 `cataforge.core.event_log.VALID_EVENTS` 同步追加 `session_end`，与既有 `session_start` 对称。下游 Stop hook / orchestrator 协议手写的 session 收尾事件不再被 `cataforge doctor` 标为 schema FAIL。

### Changed

- **`cataforge feedback --gh` label 来自配置** —— `framework.json#feedback.gh.labels` 三键 `bug` / `suggest` / `correction-export` 各自映射到一组 label；不再在 CLI 代码里硬编码 `feedback,bug` 等上游不存在的 label。`fallback_on_missing_label: true`（默认）让 `gh issue create` 在 label 不存在时自动重试不带 `--label`，并 stderr WARN 提示用户跑 `cataforge feedback ensure-labels`。
- **reflector 默认 inline 执行** —— Retrospective Protocol 由 orchestrator 在主对话直接执行，与 change-guard / Adaptive Review 一致；reflector AGENT.md frontmatter 增 `inline_dispatch: true` hint，`model_tier` 由 light 改为 inherit。手动入口 `cataforge agent run reflector` 仍保留作 fallback。
- **reflector Retrospective Protocol 扫描 `docs/EVENT-LOG.jsonl`** —— `correction` / `incident` / `revision_start` 事件作为补充 evidence 与 review 报告交叉验证；EVENT-LOG 单独不能撑起一条 EXP（仍需 review/CORRECTIONS-LOG 各一条）。
- **PROJECT-STATE.md `Learnings Registry` 字段** —— 模板默认值改为 bounded（容量来自 `framework.json#claude_md_limits.learnings_registry_max_entries`），首次 retrospective 后由 orchestrator append。

- **`sprint_check.py` Layer 1 三处升级** —— (A) `check_code_reviews` 在 `merged_review: true` 时短路 per-task CODE-REVIEW 检查（消除 9+8+1=18 次跨 sprint 误报）；(B) `check_deliverables` 支持 `accept_alternation` 模式，把 `A | B` 行视为或关系（任一存在即过），同时 `check_unplanned_files` 把两候选都标为 planned；(C) `check_unplanned_files` 新增 `glob_whitelist` 参数（来自 `unplanned_glob_patterns`），fnmatch 模式列表过滤 gold-plating WARN（典型用途：`**/*.test.ts` / `**/helpers/*` 等项目级命名约定）。所有键默认关闭，旧项目零迁移；新增 15 个 unit test 覆盖三处行为 + frontmatter 加载 + 主卷/分卷边界。闭环 [#106](https://github.com/lync-cyber/users/CataForge/issues/106) EXP-003 + EXP-005 + EXP-008。

- **reflector RETRO / SKILL-IMPROVE 输出强制带 YAML front matter** —— §Output Contract 把 "无 front matter，indexer 自动跳过" 的例外说明撤掉，改为最小 frontmatter 强制（id / doc_type / status / date / author，SKILL-IMPROVE 额外 target_id / target_kind / source_exp）。下游 `cataforge docs validate` / `doctor` 不再把 retro 文件标为 orphan FAIL。§Retrospective Protocol 第 1 条注释更新为"存量旧版无 frontmatter 文件仍可入回顾分析，新产出按契约带 frontmatter"，与 §Anti-Patterns 新增的"禁止产出无 frontmatter"一致。闭环 issue [#105](https://github.com/lync-cyber/CataForge/issues/105)。

### Fixed

- **`cataforge feedback bug --gh` 在干净 fork 上 422 失败** —— 上游若没创建 `feedback` / `triage` / `upstream-gap` 等自定义 label，老版本的硬编码 `--label feedback,bug` 会让 `gh issue create` 直接 422；新版默认与上游 `bug` / `enhancement` 对齐 + 自动 fallback 不再 fail。

<a id='changelog-0.3.1'></a>

## [0.3.1] — 2026-05-05

### Changed

- **GitHub Actions 升到 Node.js 24 兼容版本** —— `actions/checkout@v4 → v5` / `actions/setup-python@v5 → v6` / `actions/upload-artifact@v4 → v5` / `actions/download-artifact@v4 → v5`，覆盖 `publish.yml` / `test.yml` / `anti-rot.yml` / `no-dogfood-leak.yml`。GitHub 计划 2026-06-02 把 Node 24 设为默认、2026-09-16 移除 Node 20 runtime，提前升级避免到期被 hard-fail。

### Fixed

- **`cataforge bootstrap` / `deploy` 在 Windows + Python 3.11 / junction 已存在时炸成 `FileExistsError`** —— `symlink_or_copy` 的 cleanup 链漏掉了 Py3.11 上的 junction 形态：`Path.is_junction()` 是 3.12 才加的、`Path.is_symlink()` 对 junction 返回 `False`，落到 `shutil.rmtree(target)` 分支后又因为 `os.path.islink(junction)` 在 3.11 返回 `False` 可能递归进 source 树。提取 `_remove_target` helper：先 `os.path.lexists` 探测（含 dangling 链接），Windows + dir 形态时优先 `os.rmdir`（删 junction 不递归 source；对非空真目录 fail loudly 后回退 rmtree）；`copytree` fallback 前再 `lexists` 兜底，杜绝 `FileExistsError`。新增 9 个测试覆盖 dry-run / 缺父目录 / 真目录 / Unix 符号链接 / **Windows junction（v0.3.0 实际触发的 regression scenario）** / dangling 链接 / 空目标 / 重复部署幂等性。

<a id='changelog-0.3.0'></a>

## [0.3.0] — 2026-05-05

### Added

- **`cataforge feedback` CLI + `framework-feedback` builtin skill** —— 新增下游 → 上游反馈通道。三个子命令 `feedback bug` / `feedback suggest` / `feedback correction-export` 聚合 `cataforge doctor` + 最近 `EVENT-LOG` + `CORRECTIONS-LOG` 中的 `upstream-gap` 纠偏 + `framework-review` Layer 1 FAIL 摘要为 markdown body，通过 `--print` / `--out PATH` / `--clip`（pbcopy / wl-copy / xclip / clip）/ `--gh`（`gh issue create --body-file -`）四选一互斥 sink 发出。默认对 `<project>` / `~` 路径脱敏，`--include-paths` 显式关闭。配套 builtin skill `framework-feedback`（`record-to-event-log: true`，每次运行写一条 `state_change` 事件到 `EVENT-LOG`），方便 orchestrator / reflector 在累计 `upstream-gap` ≥ 阈值时自动调起。新增 `.github/ISSUE_TEMPLATE/feedback-from-cli.yml` issue 模板，字段与 CLI 输出 1:1 对齐；`bug_report.yml` 增加 tip 指引 `cataforge feedback bug --gh`。

### Changed

- **`correction record --deviation` 新增枚举值 `upstream-gap`** —— 与原 `framework-bug`（CataForge 框架缺陷）/ `self-caused`（下游自身偏离）正交，专表"上游 baseline 本身对此项目场景不对/不全"。`framework-feedback correction-export` 与 `cataforge feedback correction-export` 都按此 deviation 过滤聚合。`framework.json#features` 新增 `framework-feedback` 条目（`min_version: 0.3.0`，`auto_enable: true`，无 phase guard）。包版本由 0.2.1 → 0.3.0（minor bump：新公开 CLI 子命令组 + 新内置 skill + 新 deviation 枚举值，向后兼容）。

- **doc-gen 命名规则：`id` 与文件名禁含版本号** —— `id` 改为稳定 slug `{template_id}-{project}`（仅 `[a-z0-9-]`），版本号下沉到新增的 frontmatter `version:` 字段。同步更新 SKILL.md、20 份 template、所有 agent 输出契约（PRD / ARCH / UI-SPEC / DEV-PLAN / TEST-REPORT / DEPLOY-SPEC / RETRO 等）。这样跨版本升级时 cross-ref 不会断链；旧的 `prd-myapp-0.1.0.md` 类文件名在 `docs validate` 下会被标为 invalid id。

### Fixed

- **`cataforge docs load` 引用解析对带 `.` 的 doc_id 失败** —— `REF_RE` 的 `doc_id` 字符集是 `[\w-]+`，把 `prd-myapp-0.1.0#§1` 这类引用直接 reject 在 parse 阶段；现在 `cataforge docs validate` / `doctor` 会列出所有非 slug 形 id/alias 并 FAIL（exit 3），让根因在 index 阶段就暴露而不是在 load 时变成神秘的 parse error。

<a id='changelog-0.2.0'></a>

## [0.2.0] — 2026-04-28

### Highlight

收编三块长期靠"约定"维系的盲区到可执行规范：(1) `model_tier` 抽象把模型选择从"Claude Code 词汇"提升为平台无关四档（light/standard/heavy/inherit/none），Codex / OpenCode 部署不再被 `model: inherit` 错误透传污染；(2) framework-review 扩到 B7 含三项审计，dispatch_skills 显式声明替换 `endswith("-engine")` 命名硬编码，CHECKS_MANIFEST 锚点强制（删除 token 启发式 fallback）；(3) TDD 默认翻转 light + REFACTOR self-report + light-inline 主线程内联，典型小任务从 3 次子代理调度收敛到 0 次。

### BREAKING

迁移路径表（"如果你曾依赖 X，改为 Y"）：

| 你曾依赖 | 改为 | 自检 |
|---|---|---|
| AGENT.md `model: inherit\|sonnet\|opus\|haiku` | `model_tier: inherit\|light\|standard\|heavy\|none` | `framework-review --focus B7` (B7-β FAIL) |
| 自定义 SKILL.md "## Layer 1 检查项" 段 token 复述 | 加 `<!-- check_id: <id> -->` 锚点 或 `权威清单见 ...CHECKS_MANIFEST` 委托句 | `framework-review --focus B3` |
| `framework.json` 隐式 `endswith("-engine")` skill router 识别 | 顶层显式声明 `dispatcher_skills: [tdd-engine, ...]` | `cataforge doctor` (mc-0.2.0-dispatcher-skills) |
| `tdd_mode` 缺省 = `standard` | 缺省 = `light`（`TDD_LIGHT_LOC_THRESHOLD` 提升至 150） | `cataforge doctor` (mc-0.2.0-tdd-light-default) |
| `maxTurns: 100` (test-writer / implementer / refactorer) | test-writer=30 / implementer=80 / refactorer=30 | 部署后产物对账 |
| `.cataforge/.cache/tdd/T-{xxx}-context.md` bundle 文件 | prompt 内联（orchestrator Step 1 提取后主线程保留按阶段内联） | 子代理不再 Read bundle |
| `agent_config.supported_fields` 仅作 INFO | deploy 时强制过滤；`allowed_paths` 等 CataForge 内部字段自动剥离 | 看部署产物是否还含未声明字段 |

### Added

- **B5 子检查从 1 个扩到 4 个** —— `B5_workflow_coverage_matrix` 维持 phase→agent 单跳；新增 `B5_phase_skill_coverage` 三跳验证（每个 phase-routed agent 必须 ≥1 skill 且引用的 skill 必须存在），`B5_eventlog_agent_return_drift` 读 `docs/EVENT-LOG.jsonl` 比对（≥10 events 启用，0 returns 的 phase-routed agent 标 dead routing；returns 全缺 ref 字段标 output_path 追溯断链），`B5_feature_phase_alignment` 校验 framework.json `features[*].phase_guard` 命中 Phase Routing 已知 phase。新增 11 个测试。
- **HOOKS_MANIFEST 注册机制** —— 新模块 `cataforge.runtime.hook.manifest` 声明 builtin hook 脚本目录（含 events / default_capability / default_type / safety_critical 元数据），catch "把 helper 当 hook 挂" bug；framework-review 增 B6-ε 子检查双向校验：hooks.yaml 非 `custom:` 引用必须 ∈ HOOKS_MANIFEST（FAIL），HOOKS_MANIFEST 条目必须被 hooks.yaml 引用（WARN dead inventory）。新增 6 个测试覆盖正常 / 孤儿引用 / 未挂 / custom 跳过 / manifest 不可导入降级 / 真实 manifest 与 .py 文件 1:1 对账。
- **Pydantic V2 strict mode（保守应用）** —— `MCPServerState` 加 `strict=True`（输入仅来自 cataforge 自写状态文件，类型保真）；所有 schema 模型统一加 `validate_assignment=True`（catch "构造后赋错类型" bug）；`extra="allow"` / `extra="ignore"` 维持原状以容忍用户 YAML/JSON 类型宽松。文档化策略边界（user-input 模型暂不开 strict）。
- **CI gate `uv lock --check`** —— `.github/workflows/test.yml` Linux job 加 uv 安装 + 锁文件新鲜度检查，pyproject.toml 改依赖未刷 uv.lock 即 fail。`docs/contributing.md` 加锁文件刷新指引。

- **sprint-review CLI 增加 ignore / 输出形态控制参数** —— `--src-dir` 改为可重复 (monorepo 多包按需缩范围)；新增 `--ignore PATTERN` (可重复) / `--ignore-file PATH` (可重复) 追加 gitignore 风格规则；`--no-respect-gitignore` 关闭 git 集成、`--no-default-ignores` 关闭内建默认 ignore；`--warn-cap N` (默认 50) 折叠 unplanned WARN 到 top-level 目录摘要 (`node_modules/* (12340)`)，`--unplanned-log PATH` 把完整列表落盘以便审计；`--format json` 输出结构化 issue 列表 (`{summary: {fail, warn, total}, issues: [{severity, category, message, task?, path?}, ...]}`) 供 framework-review / CI 机读。
- **CHECKS_MANIFEST anchor 模式** —— `.cataforge/skills/sprint-review/SKILL.md` §Layer 1 检查项 升级到 `<!-- check_id: ... -->` anchor 模式 (B3 双向校验)，对每条 manifest 项强制 prose 锚点；`unplanned_files` 条目标题同步覆盖默认 ignore + .gitignore 集成语义。
- **`tests.conftest.run_utf8` 共享 subprocess 帮助函数** —— `subprocess.run(text=True)` 用 parent 的 cp1252 (Windows CI 默认) 解码 UTF-8 输出会让 reader 线程崩溃、`stdout` 静默变 `None`，下游 `json.loads` 报"not NoneType"难以诊断。提取 `run_utf8(cmd, *, cwd, check, timeout, extra_env, **kw)` 到根 `tests/conftest.py`，统一 `encoding="utf-8"` / `errors="replace"` / `PYTHONUTF8=1`；`tests/e2e/conftest.py` 的 `built_wheel` / `pip_install` / `run_cataforge` 与 sprint-review CLI 测试切换调用；新增 `tests/test_run_utf8.py` 5 个回归测试 (中文+em-dash 解码 / `PYTHONUTF8` 注入 / `extra_env` 合并 / `check=True` 抛错 / 默认放行非零码)，防止有人"简化"掉 `encoding`。
- **pre-commit 装机率 guard 三件套** —— 解决"`.pre-commit-config.yaml` 已配 ruff 但本地从未跑 `pre-commit install`，CI 60 秒后才翻红"的问题。(1) `tests/conftest.py` `pytest_sessionstart` 探测 `.git/hooks/pre-commit` 缺失时**自动**调用 `python -m pre_commit install` 安装钩子（`pre-commit` 已在 [dev] 依赖、且 `pre-commit install` 幂等无副作用），失败 fail-soft；power user 可设 `CATAFORGE_SKIP_HOOK_AUTOINSTALL=1` 关闭；(2) `.github/workflows/test.yml` Linux job 加 `pre-commit run --all-files --show-diff-on-failure` 作为 belt-and-braces step，杜绝 `.pre-commit-config.yaml` 与 CI 单点 ruff 命令偷偷漂移；(3) `docs/contributing.md` 把 `pre-commit install` 从"可选"提为开发环境 setup 必跑步骤，改写说明强调本地↔CI 检查 1:1 对账。

- **frontmatter `aliases:` 字段 + 三段式 doc_id 解析** —— 旧 cross-ref resolver 短引用（如 `arch-data#§4.E-002`）只在严格 doc_id 匹配 / `{doc_id}-*` prefix-fallback 两层尝试，命中不到 `arch-wechat-typeset-X-0.1.0-data` 这类后缀别名时直接 FAIL，下游 doc-review 在每份 theme 分卷上系统性触发"交叉引用目标未找到"。新增 `aliases:` frontmatter 字段：indexer 抽取后写入顶层 `aliases: {alias → doc_id}` 映射，`cataforge.domain.docs.loader._resolve_doc_entry` 改三段式（exact → aliases → prefix-fallback），prefix 多匹配从"取 dict 迭代第一个"升级为抛 `AmbiguousRefError` 并列出全部候选。重复声明 / 与真 doc_id 撞名的 alias 由 `build_aliases()` 第一占位胜出并记入 `alias_conflicts`，validate 时上报。
- **`cataforge docs validate` 跨引用 + alias 冲突校验** —— 旧实现仅查 orphan / stale，无法在 commit / CI 时拦下"DEPS 行写错 doc_id"或"两份文档抢同一 alias"；前者要等到下游 `cataforge docs load` 才暴露、后者完全静默。新增 `validate_docs(project_root)` 统一入口（`cataforge.domain.docs.indexer.validate_docs`），同时跑 orphans / stale / `find_xref_errors` / `find_alias_conflicts`；`cataforge doctor` 的 `_check_orphan_docs` 重命名为 `_check_docs_validate` 并切到同一 helper，命名段从 "Docs index completeness" 改为 "Docs validation"。
- **doc-review `required_sections` 模板未覆盖时回退读 frontmatter** —— `_registry.yaml` 未注册的 `(doc_type, volume_type)` 组合（如 `ui-spec/theme`）在 layer-1 checker 里只发一行 WARN 然后 `return`，等于该分卷整段 required_sections 校验被静默跳过。`DocChecker.check_required_sections` 现在在 `load_template_required_sections` miss 后回退读文档自声明 `required_sections:`（通过新公开的 `parse_required_sections_from_list`），仍发降级 WARN 提示模板缺失但不再短路。同时新注册 `ui-spec/theme` 模板 + `volumes/ui-spec-theme.md` 起手骨架，`-theme-NN-slug` 文件名加入 `_detect_volume_type` filename 探测。
- **COMMON-RULES §禁止估算任务用时** —— 适用所有 Agent 的 backlog / 改进建议 / PR 描述 / todo / 口头汇报；明确 LLM 任务用时与人类工时不可比，必须用"成本 / 复杂度"维度（"单点改动" / "涉及多文件" / "需新写测试"）替代"X 分钟 / 小时 / 天"等口语估算。

- **任务上下文 bundle 缓存** —— Step 1 新增写 `.cataforge/.cache/tdd/T-{xxx}-context.md`（meta / tdd_acceptance / interface_contract / directory_layout / naming_convention / deliverables / test_command 章节固定）。RED/GREEN/REFACTOR 子代理 prompt 仅传 bundle 路径，子代理首步 Read 即可获得全部上下文，节省每次调度 prompt 内联 arch 摘要的 token。
- **agile-prototype Inline 模式** —— prototype 项目 implementer 在主线程内联运行（不通过 agent_dispatch 启动子代理），节省每任务一次子代理 boot（AGENT.md + COMMON-RULES + dispatch-prompt 模板加载约 3-5K token）。tdd-engine SKILL.md 新增 §Prototype Inline 模式章节。
- **同模块 RED 批量化** —— 当 sprint_group 内 ≥2 个任务共享同一 `arch#§2.M-xxx` 时，可合并为一次 test-writer 调用（任务数 ≤4 时启用），summary 按 task_id 分块返回。test-writer AGENT.md Input Contract 新增"批量 RED 模式"小节。
- **task_kind 字段 + chore 跳过 TDD** —— dev-plan 任务卡新增 `task_kind ∈ {feature, fix, chore, config, docs}`。`chore`/`config`/`docs` 跳过 TDD 三阶段，仅由 implementer 单次产出 + lint hook 兜底。tech-lead Execution Rules 增加判定规则。
- **code-review Layer 2 短路条件** —— 类比 doc-review 短路。新增常量 `CODE_REVIEW_L2_SKIP_TASK_KINDS=[chore, config, docs]` + `CODE_REVIEW_L2_SKIP_LIGHT_MAX_AC=2`。light 模式 AC ≤2 / chore 类 / Adaptive Review 反向降级时跳过 Layer 2 直接 approved，由 sprint-review 兜底。`security_sensitive: true` 任务永不短路。
- **Adaptive Review 反向降级分支** —— 新增常量 `ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS=10`。连续 10 个任务零 self-caused 问题且 code-review approved 时，后续 code-review 调用仅跑 Layer 1（`--layer1-only`），sprint-review 兜底；任一后续任务出 MEDIUM+ 立即取消降级。ORCHESTRATOR-PROTOCOLS §Adaptive Review Protocol 新增"反向降级分支"小节。
- **migration_check `mc-0.2.0-tdd-light-default`** —— 守住 COMMON-RULES.md 含新常量的最新值（150 / light / 3）。

- **`model_tier` 抽象** —— AGENT.md 用平台无关的 `model_tier: light|standard|heavy|inherit|none` 取代具体模型字面量；platform `profile.yaml.model_routing.tier_map` 把 tier 翻译为各平台原生 model id。Codex (`per_agent_model: false`) 与 OpenCode (`user_resolved: true`) 的部署适配器自动省略 `model:` 字段，避免历史上 `model: inherit` / `model: sonnet` 被原样塞进 codex TOML 的 bug。README "特性亮点" 新增专门小节介绍。
- **0.2.0 迁移检查** —— `mc-0.2.0-model-tier-migration` + `mc-0.2.0-dispatcher-skills` 两条 migration_check 在 doctor 阶段守住升级路径：用户从 0.1.x 升级时，若 `framework.json` 缺 `AGENT_MODEL_DEFAULTS` / `dispatcher_skills` 会被立即标红。
- **B7 框架审计** —— `framework-review` 新增三项检查：B7-α (`model_tier` 合规 + 与 `AGENT_MODEL_DEFAULTS` 一致 + heavy 需进白名单)；B7-β (legacy `model:` 字段 FAIL，强制迁移)；B7-γ (platform `tier_map` 必须覆盖 light/standard/heavy)。
- **`dispatcher_skills` 顶层声明** —— `framework.json#/dispatcher_skills` 显式标记 skill-as-router (如 `tdd-engine`)，B5-α 不再依赖 `endswith("-engine")` 的命名硬编码，未来命名约定不同的派发型 skill 也能被正确识别。
- **可配置 EVENT-LOG 阈值** —— `constants.EVENT_LOG_DRIFT_MIN_EVENTS` 取代硬编码的 `≥ 10`；事件不足时输出一条 INFO 提示（而非沉默），新项目知道检查存在但数据未达阈值。
- **`framework-review --target <asset_id>`** —— Layer 2 仅审单个 agent / skill，节省 token；scope=all 时 Layer 2 自动按资产类型分批 (SKILL → AGENT → hooks)，避免一次性塞入稀释关注度。
- **Layer 2 按资产类型分层维度矩阵** —— framework-review SKILL/AGENT/hooks 各自独立维度（如 AGENT 维度含 model_tier 选择合理性、Identity↔Phase 一致、tools↔allowed_paths 自洽）。
- **implementer self-report `refactor_needed`** —— GREEN/Light 完成后自检 complexity / duplication / coupling 并在 `<agent-result>` 报告，orchestrator 据此触发 refactorer，免除每任务一次 code-review L1 的固定开销；sprint-review 阶段批量复核兜底。
- **TDD light-inline 模式** —— `tdd_mode=light` 且 LOC ≤ `TDD_LIGHT_LOC_THRESHOLD` 且非 security_sensitive 且执行模式 ∈ {agile-lite, agile-prototype} 时，orchestrator 在主线程内联实现，零 implementer dispatch；agile-standard 的 light 任务保持 dispatch 形态保留审计粒度。
- **TDD continuation 错误分级** —— 机械错（SyntaxError / 配置错 / 路径错）允许 ≤3 次 continuation；语义错 ≤1 次后 blocked。

### Changed

- **scaffold 镜像彻底消除** —— `src/cataforge/_assets/cataforge_scaffold/`（109 文件双写镜像）整树删除，`.cataforge/` 通过 `[tool.hatch.build.targets.wheel.force-include]` + `[tool.hatch.build.targets.editable.force-include]` 直接打进 wheel 为 `cataforge/_dot_cataforge/`；`scripts/sync_scaffold.py` / `scripts/hatch_build.py` / `.github/workflows/scaffold-sync.yml` / `.gitattributes`（仅为镜像而存在）/ `tests/test_scaffold_sync.py` 全部删除；`tests/hook/test_script_contract.py` / `tests/hook/test_script_filters.py` / `tests/core/test_event_log_schema_sync.py` 路径改指向 canonical `.cataforge/`。`.pre-commit-config.yaml` 删 scaffold-sync hook；`.github/workflows/no-dogfood-leak.yml` 删 PROJECT-STATE.md 双副本对账段。`src/cataforge/core/scaffold.py` `_scaffold_root()` 加 editable install 回退（`Path(__file__).parents[3] / ".cataforge"`），保证 `pip install -e .` 路径在 hatch force-include 不生效时仍能解析。

- **CHANGELOG 工作流改为 fragment-based（scriv）** —— 新建 `changelog.d/` 目录，每个 PR 加 `{PR#}.md` 含 `### Added` / `### Changed` / `### Fixed` 等小节的片段；发版时维护者跑 `scriv collect --version=X.Y.Z` 聚合到 `CHANGELOG.md` 顶部 scriv-insert-here 锚点（HTML comment 形式，文档里描述时避免直接写出，会被 scriv 误吞）并删除片段。`pyproject.toml` 加 `scriv[toml]>=1.5` dev dep + `[tool.scriv]` 配置；`docs/contributing.md` 加 fragment 工作流指引；CI gate `scripts/checks/check_changelog_fragments.py` 强制 user-visible PR 必须含片段或在 commit message 加 `[skip-changelog]` token。Windows 用户跑 `scriv collect` 需 `PYTHONUTF8=1`（scriv 默认按 cp1252 读 markdown）。历史 v0.1.x 条目原样保留不回填，从 PR #84 开始迁移到片段。

- **COMMON-RULES 整体重组压缩** —— 235 行 → 221 行；合并 §输出语言 入 §全局约定，删 §框架配置常量 与 §执行模式矩阵 的历史回溯文本（"自 2→5 以补偿…" 等设计阶段残留按 §禁止设计阶段残留 自检规则裁掉），保留所有外部引用的 anchor 名（§执行模式矩阵 / §统一状态码 / §归因分类 / §三态判定逻辑 / §对比式约束 / §报告 Front Matter 约定 等）。

- **TDD 默认翻转为 light + 阈值 50→150** —— `tdd_mode` 缺省值从 `standard` 改为 `light`（新增 `TDD_DEFAULT_MODE=light` 常量），`TDD_LIGHT_LOC_THRESHOLD` 从 50 提升至 150。tech-lead 仅在 LOC > 150 / `security_sensitive: true` / 跨 ≥2 个 arch 模块时才显式标 standard。覆盖 framework.json / COMMON-RULES §框架配置常量 + §执行模式矩阵 / dev-plan 模板（standard + lite + prototype）/ tech-lead AGENT.md / docs/guide/tdd-workflow.md / docs/faq.md / docs/reference/configuration.md / docs/reference/agents-and-skills.md / framework_check.py CONSTANT_LITERALS。原默认 50/standard 已废弃（`mc-0.2.0-tdd-light-default` 守门）。
- **REFACTOR 阶段改为条件触发** —— 新增 `TDD_REFACTOR_TRIGGER=[complexity, duplication, coupling]` 常量。GREEN 完成后 orchestrator 跑一次 `code-review --focus complexity,duplication,coupling`（Layer 1 only），命中任一 finding 才调度 refactorer；任务卡 `tdd_refactor: required` 强制触发，`skip` 强制跳过。多数小任务从"3 次子代理调度"收敛到"1 次 light + 0 次 refactor"。tdd-engine SKILL.md §Step 4 重写。
- **test-writer / implementer 降级到 Sonnet** —— `model: inherit` → `model: sonnet`；refactorer 保留 inherit（语义重构需 Opus）。配套 maxTurns 从 100 收紧到 test-writer=30 / implementer=80 / refactorer=30。RED/GREEN 是"AC→assert / test→最小代码"翻译类任务，Sonnet 完全够用，token 单价降至约 1/5。
- **同 sprint_group 任务并行调度** —— 新增 ORCHESTRATOR-PROTOCOLS §Parallel Task Dispatch Protocol。task-dep-analysis 输出的 `sprint_groups` 现被消费：同组无依赖任务在单条主线程消息内并发派发（上限 3）；REFACTOR 仍强制串行避免源码冲突；deliverables 路径冲突立即降级串行。墙钟时间在 5+ 任务的 Sprint 上从串行 N×T 收敛到约 ⌈N/3⌉×T。
- **SPRINT_REVIEW_MICRO_TASK_COUNT 2 → 3** —— 配合 light 默认化后小任务密度上升，sprint-review 短路阈值同步上调，多数小项目整 sprint 直接走快路径。
- **删除 orchestrator-side 失败分类二次核验** —— tdd-engine §Step 2 原本 SKILL.md 自己注释"orchestrator 仅二次确认，不重复分析"，现彻底删除。失败原因验证完全交给 test-writer 内部 Execution Rules，避免主线程上下文重复消费 test-writer 的详细输出。

- **TDD 子代理上下文从 bundle 文件改为 prompt 内联** —— orchestrator 在 Step 1 提取任务上下文（meta / tdd_acceptance / interface_contract / directory_layout / naming_convention / test_command）后**主线程保留**，按阶段内联进 test-writer / implementer / refactorer 的 dispatch prompt；子代理 Input Contract 从 "首步 Read bundle" 改为 "读取 prompt 内联章节"。同模块 RED 批量化的 prompt 按 task_id 分块内联各 §tdd_acceptance + 共享接口契约。覆盖 tdd-engine SKILL.md / 三个 TDD AGENT.md / ORCHESTRATOR-PROTOCOLS §Parallel Task Dispatch 示例。原 PR #89 引入的 bundle 缓存机制因此回滚。
- **penpot-implement 能力边界收窄到 generation** —— "能做" 移除 "比对设计与代码一致性"；"不做" 显式点名 "由 penpot-review 负责"；输出规范删除 "一致性检查报告"；执行流程删除 Step 4 一致性验证。一致性验证由 penpot-review 单独负责，避免与 implement 职责重叠导致 LLM 选错 skill。
- **用户/LLM 直触发 skill description 加触发短语 + 负向边界** —— code-review / doc-review / sprint-review / debug / research / penpot 三件套的 frontmatter description 新增 "当 X 时使用此 skill" + "由 Y 负责，本 skill 不处理" 子句，互划范围（src/ vs docs/ vs .cataforge/ vs Sprint 级；implement vs review vs sync）。pipeline 类 skill（arc-design / req-analysis / task-decomp / ui-design 等阶段路由触发）保持原短描述不动。
- **testing 新增 §与 debug 的关系 段** —— 显式描述 testing 缺陷清单 → orchestrator 调度 debug → testing 重跑验证的 handoff，对齐既有 §与 tdd-engine 的关系 写法。

- **`agent_config.supported_fields` 现在在 deploy 时强制过滤** —— 此前是纯 INFO 信息；现在 translator 会按 `supported_fields ∩ 内部黑名单` 决定哪些 frontmatter 字段写入目标平台。Codex 部署改走与其他平台一致的 `translate_agent_md` 管线，再做 TOML 序列化，不再绕过翻译层。
- **B3-α 严格化** —— 移除 token 启发式 fallback；每个 builtin SKILL.md 的 "## Layer 1 检查项" 段必须用 `<!-- check_id: ... -->` 锚点或 `权威清单见 ...CHECKS_MANIFEST` 委托句，二者必居其一，否则 FAIL。
- **REFACTOR 触发去掉每任务 code-review L1 调用** —— 改由 implementer self-report 触发；sprint-review 阶段做批量 `--focus complexity,duplication,coupling` 的 L1 兜底。
- **架构选型 tier 调整** —— architect / debugger 升 heavy（架构与跨栈调试需要深推理）；test-writer / implementer 落 standard（避免 light 漏判细节 bug）。其余按 `AGENT_MODEL_DEFAULTS` 默认值。

### Fixed

- **sprint-review unplanned-file 检测在 monorepo 下噪声爆炸** —— 旧实现 `os.walk(--src-dir)` 无 ignore 列表，packages 根目录里的 `node_modules/zod/...`、`dist/`、`*.tsbuildinfo` 等会被全部当成 gold-plating，单次运行 13k+ WARN 把 6 条真实 FAIL (缺 CODE-REVIEW 报告) 完全淹没。重写 `cataforge.runtime.skill.builtins.sprint_review.sprint_check.check_unplanned_files`：候选集合默认通过 `git ls-files -co --exclude-standard` 取得（同时尊重 `.gitignore` / 子模块 / global excludes），不在 git 仓内时回落到 `os.walk` 并预剪 `node_modules` / `__pycache__` / `.git`；新增 `cataforge.runtime.skill.builtins.sprint_review.ignore` 模块，`DEFAULT_IGNORE_PATTERNS` 兜底覆盖 Node / TS / Python / coverage / lock 文件常见产物。

- **`check_required_sections` 在 frontmatter 内自命中** —— 旧实现 `re.search(re.escape(heading), self.content, re.MULTILINE)` 直接在全文跑，`required_sections:` YAML 数组里写的字面量（`- "## 4. 主题方案"`）会先于真正的 `## 4. 主题方案` 标题被匹中并截走 group(1) 直到下一个 `^##`，导致缺章节场景永远不 FAIL。改为先 `split_yaml_frontmatter` 剥离 frontmatter 再做 regex；新增的 `test_check_required_sections_fallback_flags_missing_section` 守住该回归。

- **codex deploy `model: inherit` / `model: sonnet` 错误透传** —— 此前 `translate_agent_md` 仅翻译 tools/disallowedTools，`model:` 原样塞进 `.codex/agents/*.toml`；codex `available_models = [gpt-5.4, gpt-5.3-codex-spark]` 不识别 `inherit`/`sonnet`，会静默回落默认。现已通过 `model_tier` 抽象彻底修复。
- **codex deploy 完全绕过 translator** —— `_md_to_toml` 此前只白名单 `(model, model_reasoning_effort, sandbox_mode, nickname_candidates)`，导致 `tools` / `disallowedTools` 不经任何处理即被丢弃且无审计；现在与其他平台共享 `translate_agent_md` 管线，能力丢失通过 `dropped_collector` 统一报告。
- **`allowed_paths` 等内部字段污染部署产物** —— `allowed_paths` 是 CataForge agent-dispatch 内部字段，从未在任何平台 supported_fields 里声明，但仍被原样写入 `.claude/agents/*.md` 等；现在被明确划入 `_INTERNAL_FIELDS` 黑名单，所有平台一律剥离。

### Removed

- **`maxTurns: 100`（test-writer / implementer / refactorer）** —— 实测远超实际所需。test-writer 30 / implementer 80 / refactorer 30 即足够，超出兜底为 blocked → 人工介入。

- **`.cataforge/.cache/tdd/T-{xxx}-context.md` bundle 文件机制** —— PR #89 引入的磁盘 bundle 缓存（含固定 7 章节）整体废弃。子代理不再 Read bundle 文件，prompt 自包含；消除磁盘往返与子代理首步 Read 开销。

- **B3-α token 启发式 fallback** —— 与 "向后兼容期" 整体一并删除；新 SKILL 强制 anchor 或 delegation。
- **AGENT.md `model:` 字段** —— 13 个内置 agent 全部迁移到 `model_tier:`；orchestrator 直接省略（主线程不需要）。translator 在部署时主动剥离 legacy `model:` 行（无过渡期）。
- **B5 `endswith("-engine")` 硬编码** —— 由 `framework.json#/dispatcher_skills` 显式声明替代。

<!-- 变更原因：按新 Changelog 写作约定重写 v0.1.15 章节作为后续版本范式；拆分长 bullet 为短句、单独列出 BREAKING 段并附迁移表；Previously Unreleased 散条归入对应子节 -->
## [0.1.15] — 2026-04-27

### Highlight

把"项目代码腐化扫描"与"框架元资产质量审计"两个长期靠人工维护的盲区，收编为可在 CI 强制执行的 skill。同时把 `dep-analysis` 重命名为 `task-dep-analysis`，与未来代码 coupling 分析消歧。

### Added

- `code-review scan` 操作 — 项目级健康度扫描，叠加 jscpd / vulture / ts-prune / radon / gocyclo 探针。工具缺失自动 WARN 跳过。报告 `docs/reviews/code/CODE-SCAN-{YYYYMMDD}-r{N}.md`。
- `framework-review` 内置 skill — 框架元资产质量审计，scope ∈ {agents, skills, hooks, rules, workflow, all}，6 个子检查覆盖必填段 / 行数 / 交叉引用 / manifest 漂移 / 裸数值 / phase×agent×skill 矩阵。
- 4 个 review-class builtin 暴露 `CHECKS_MANIFEST` — 作为 framework-review B3 漂移检测的权威数据源。
- `cataforge agent run` 子命令 — 渲染 AGENT.md + task framing，自动复制到剪贴板（Windows clip / macOS pbcopy / Linux xclip 或 xsel）。
- COMMON-RULES §统一问题分类体系新增 4 个代码 category — `duplication` / `dead-code` / `complexity` / `coupling`。
- COMMON-RULES §报告 Front Matter 约定增 `framework-review` / `code-scan` 两类报告。
- `META_DOC_SPLIT_THRESHOLD_LINES = 500` 常量 — SKILL.md / AGENT.md / 协议文档拆分提示阈值（相对 DOC_SPLIT_THRESHOLD_LINES = 300 放宽）。
- `tests/conftest.py` — 启动前探测 `build` / `pytest` / `yaml` 三个 dev 依赖，缺失即提示 `pip install -e '.[dev]'` 后退出。
- `tests/test_scripts_stdio_guard.py` — 强制 `scripts/*.py` 入口 reconfigure stdio 为 UTF-8。
- `framework-review -- all` step 接入 CI required gate（Linux job）。
- `cataforge docs migrate-reviews` 子命令 — legacy review 报告补齐 YAML front matter。
- `docs/reviews/CORRECTIONS-LOG.md` 自动 front matter。

### Changed

- 三个 review skill 删除四态返回表复述，改为单行引用 §Layer 1 调用协议。
- `doc-review` / `code-review` SKILL.md Layer 2 加 `--focus <category[,...]>` 让维度可收敛。
- `doc-review/SKILL.md` §Layer 1 检查项补齐 `check_split_header` / `check_split_consistency` / `check_line_count`。
- 4 处裸数值替换为常量名引用（`MAX_QUESTIONS_PER_BATCH` / `DOC_SPLIT_THRESHOLD_LINES`）。
- `.pre-commit-config.yaml` scaffold-sync hook 由 `--check` 改为实际写入。
- `scripts/sync_scaffold.py` 顶部 reconfigure stdio 为 UTF-8（修 `→` 字符在 Windows cp1252 崩溃）。
- `reflector/AGENT.md` 文档化 on-demand 用法。
- `cataforge.domain.docs.indexer.main` orphan WARN 文案改进。
- `doc-review` / `code-review` SKILL.md Step 4 强制 front matter。
- `reflector/AGENT.md` Retrospective Protocol 改为 glob-based 说明。

### Deprecated

- `dep-analysis` skill 名 — 改名为 `task-dep-analysis`。详见下方 BREAKING。

### Fixed

- `SkillRunner.run` Windows cp1252 解码崩溃 — `subprocess.run` 显式 `encoding="utf-8", errors="replace"`。

### BREAKING

| 影响 | 旧 | 新 | 迁移路径 |
|------|---|---|---------|
| Skill ID 重命名 | `dep-analysis` | `task-dep-analysis` | 1) `cataforge upgrade apply` 自动同步 scaffold；2) 项目自定义引用过 `dep-analysis` 的 SKILL.md / AGENT.md `skills:` 段需手改；3) `cataforge skill list` 验证迁移完成 |

无其它破坏性变更。

## [0.1.14] — 2026-04-27

doc-index 审计**完整闭环**（PR-1 #74 + PR-2 #75 = 2 个 PR 一线串过 audit 表**全部 12 项**：A1-A7 + B1-B2 + 新-1 + 新-3 + 新-4）。一句话：本轮把 v0.1.13 引入的 doc-index 子系统从"manual-only 工具"升级为"CI/upgrade/bootstrap/pre-commit 全链路自我治理"，并把"5 AGENT.md 重复指令"和"schemas/ 与 Python 镜像漂移"这两个跨切面腐化点同步收敛。

### Added

- **`.github/workflows/test.yml` 加 `cataforge doctor` step**（Linux job）—— v0.1.13 落地的 6 个 anti-rot 守卫之外，把 doctor 自身从"diagnostic"升级为"required gate"，捕获 `_DEPRECATED_REFS` / `runtime_api_version` 漂移 / protocol-script orphan / EVENT-LOG schema / 新加的 docs-index 反向 orphan。Audit A1。
- **`cataforge docs validate` 子命令** —— 只读 CI gate，覆盖 `docs index --strict` 不写盘的语义。失败时 stderr 列出 orphan + stale entry：exit 0 = clean，exit 2 = `docs/.doc-index.json` 不存在（distinct error class — 调用者应先 `docs index`），exit 3 = 校验不通过。pre-commit、CI workflow、agent 自检三种场景都可调用。Audit A6。
- **`cataforge.domain.docs.indexer.find_stale_index_entries()` + doctor + `docs index --strict` 接入反向 orphan 检测** —— `.doc-index.json` 登记的 `file_path` 在磁盘已不存在时：doctor 报 FAIL（counts toward `failed_count` exit gate）+ `docs index --strict` 增量分支 exit 3。这是 audit A5 提到的"反向孤儿"，与正向 orphan（磁盘有 md 文件但缺 front matter）形成对称：indexer 维护双向一致性。
- **`bootstrap` 末尾自动跑 `cataforge docs index`**（仅当 `docs/` 含 `.md` 文件）—— 闭合"首次 bootstrap 永远拿不到 `.doc-index.json` → doctor 的 orphan 检查永远静默跳过 → 用户从未感知到 docs-index 子系统"的链式失败模式。失败时 WARN 不阻塞 bootstrap 流程。Audit A4 + A3。
- **`upgrade apply` 末尾自动 rebuild `.doc-index.json`**（仅当文件已存在）—— 让 upgrade 的副作用包括索引刷新，避免用户手动跑 `docs index`。orphan 失败时 WARN，不回滚 upgrade。Audit A3。
- **`.pre-commit-config.yaml`** —— 三个本地钩子：(1) `scripts/sync_scaffold.py --check`（防 dogfood ↔ mirror drift）；(2) `ruff check`（防误提带 lint 错的 commit）；(3) `.github/workflows/*.yml` PyYAML safe_load 解析（防 step name 未引号冒号这类静默 workflow rejection）。`docs/contributing.md` 加 `pre-commit install` 指引段。Audit B1 + 本轮 PR-1 暴露的 workflow YAML 失败模式的防再发。
- **`src/cataforge/_assets/cataforge_scaffold/GENERATED.md`** —— 在生成镜像目录根放 banner，明确"DO NOT EDIT" + 指向 `scripts/sync_scaffold.py`。`scripts/sync_scaffold.py` 的 `TARGET_ONLY_FILES = frozenset({"GENERATED.md"})` 集合保护该文件不被双向同步覆盖；`tests/test_scaffold_sync.py::EXPECTED_ONLY_IN_SHIPPED` 同步 carve-out。Audit B2。
- **`COMMON-RULES.md` 新增 §文档加载纪律**（在 §文档引用格式 与 §通用 Anti-Patterns 之间）—— 把 5 个 AGENT.md 中重复出现的"禁止 Read 全文 + 必走 `cataforge docs load`"通用规则单点收敛。COMMON-RULES 由 platform adapter 在 deploy 时通过 `@.cataforge/rules/COMMON-RULES.md` at-mention 自动 prepend 到 CLAUDE.md，所有 sub-agent 加载即得，AGENT.md 不需要回引。Audit A7。
- **`scripts/checks/check_schema_python_parity.py` + `tests/schema/test_schema_python_parity.py`** —— 新 anti-rot 守卫（CI + pre-commit + unit），锁定 `.cataforge/schemas/{event-log,agent-result}.schema.json` 与各自 Python 镜像的 enum / required / allowed-fields 一致性。两个 schema 文件历来是文档-only（无 jsonschema-validate 调用），运行时校验由 `cataforge.core.event_log.validate_record` 和 `cataforge.runtime.hook.scripts.validate_agent_result` 中的硬编码常量承担——任一边漂移会让 validation 静默分叉。本守卫闭合该漂移面。Audit 新-3（采用 parity-guard 路线，避免引入 jsonschema 新依赖）。
- **`tests/cli/test_docs_indexer.py` + `tests/cli/test_docs_validate.py` + `tests/schema/test_schema_python_parity.py`** —— 17 个新测试覆盖：`--strict` 全量 / 增量 / 干净树矩阵、reverse-orphan 检测、`docs validate` 三种 exit 码、doctor 新 WARN/FAIL 路径、schema-Python parity 双面。

### Changed

- **`cataforge doctor` 的 docs-index 完整性检查不再静默跳过** —— `docs/.doc-index.json` 缺失但 `docs/` 含 markdown 时，emit 黄色 WARN 提示 `cataforge docs index`（非阻塞，不计入 `failed_count`）；`docs/` 真正不存在或不含 markdown 时仍静默跳过（genuinely not-applicable）。Audit A2。
- **`.cataforge/skills/doc-nav/SKILL.md`** 加"指令 4: 校验索引完整性 (validate)"段，引用 `cataforge docs validate`，与 doctor 的新 WARN 行为对齐——doctor 和 doc-nav 现在都给同一条修复指引（运行 `cataforge docs index` 重建），解决了 audit 新-4 提到的两条不一致降级路径。
- **5 个 AGENT.md（architect / tech-lead / qa-engineer / devops / ui-designer）瘦身** —— 每个文件删除 Input Contract 与 Anti-Patterns 段中"禁止一次性 Read … 全文" / "Bash 仅用于 cataforge docs load" 的通用表述（这些已迁移到 COMMON-RULES §文档加载纪律）；保留各自的**doc_id 白名单**（如 architect 的 `prd#§2.F-xxx`、devops 的 `arch#§3.API-xxx`）——这部分是真正的角色特定信息。Audit A7。
- **`tests/cli/test_doctor_anti_rot.py::test_doctor_orphan_check_skips_when_no_doc_index` 重命名为 `test_doctor_warns_when_docs_present_but_no_index`** —— 旧测试断言"silent skip"，与本轮 audit A2 的新行为冲突。新测试断言 WARN 路径 + 新增 `test_doctor_silent_when_docs_dir_has_no_markdown` 守住"genuinely empty docs/"应静默的契约。

### Fixed

- **`cataforge.domain.docs.indexer.main` `--strict` 增量分支 no-op (audit 新-1)** —— `--doc-file` 增量更新时整段跳过 `find_orphan_docs` 全树扫描，意味着 `--strict` 在 PostToolUse 钩子 / agent 单文件回写等增量场景下永远不会失败，前条目缺失 front matter 也能溜过 gate。现在每次调用都跑全树 orphan + 反向 stale-entry 扫描；增量场景的 `--strict` 与全量行为对称。
- **`.github/workflows/test.yml` 因 step `name` 含未引号冒号导致 YAML 解析失败** —— `Anti-rot guards (6: skill count, ...)` 这一行的 `6:` 让 GitHub Actions 报 "workflow file issue" 直接拒跑（"This run likely failed because of a workflow file issue"，无任何 job log），main 已连红 3 个 PR 都是这个原因（不是 ruff、不是 pytest，是 workflow 根本没启动）。给该 name 加引号，本轮新加的 doctor step name 同时引号化；pre-commit hook 加 workflow YAML 解析检查防再发。
- **3 处 pre-existing ruff 错误**（`UP012` × 2 in `tests/cli/test_event_cmd.py` / `tests/core/test_io.py`，`I001` in `src/cataforge/core/template.py`）—— 与 workflow YAML 一起 unblock CI。这 3 处源自 #72，但因 workflow 根本未启动而被 CI 漏掉。

## [0.1.13] — 2026-04-25

二轮腐化审计闭环（PR-1 → PR-8 一线串过 26+8 = **34 条腐化**修复 + 6 个 anti-rot CI 守卫 + 1 个 weekly sweep workflow + migration_check 生命周期机制）。

### Added

- **`cataforge core/template.py`** — `render_project_state()` 抽象，把"运行时: {platform}" 的字面量模板替换从 `PlatformAdapter` 抽象基类剥离。
- **`SkillRunner.run(..., agent=)`** + `cataforge skill run --agent <name>`：EVENT-LOG `state_change` 事件按真实调用方归因，环境变量 `CATAFORGE_INVOKING_AGENT` 兜底（旧"硬编码 reviewer"行为作为最终 fallback 保留）。
- **`framework.json` 占位 `version: "0.0.0-template"`** + `Config.version` 在读时解析为运行包版本 + `bootstrap_cmd._semver_newer` 对 `0.0.0-` 前缀短路；源仓库 commit 不再随每次发版漂移版本号。
- **`migration_checks[].deprecate_after`** 字段 + doctor 在 `__version__ ≥ deprecate_after` 时 SKIP；12 条历史 check（mc-0.1.0-*/ mc-0.1.5-* / mc-0.1.7-*）已标 `deprecate_after: "0.2.0"`，2 条结构性 check（mc-0.1.9-* / mc-0.1.10-event-logger-shim）保持永久启用。
- **`migration_checks[].allow_missing`**（仅 `file_must_not_contain` 类型）：路径不存在时默认 FAIL（防止 vacuous PASS），allow_missing 提供"路径在某些安装下合法缺失"的逃生口。
- **`runtime_api_version` 契约校验**：`SUPPORTED_RUNTIME_API_VERSION = "1.0"` 常量 + doctor `runtime_api_version contract` 段，从源头让该字段不再是装饰性。
- **6 个 anti-rot 守卫脚本**（`scripts/checks/`）：`check_skill_count` / `check_no_dev_branch_refs` / `check_changelog_link_table` / `check_doc_versions` / `check_profile_yaml_keys` / `check_hooks_yaml_schema`。前 4 个守覆盖一轮审计落地的事实型腐化；后 2 个守 schema 漂移（二轮审计发现的 §profile.yaml / §hooks.yaml 整段错位类）。
- **`.github/workflows/anti-rot.yml`** weekly cron：每周一 04:00 UTC 在 `main` 跑 6 守卫，失败时自动开 `rot` label issue。
- **CHANGELOG `## [0.1.4]` / `## [0.1.9]` 章节回填**：tag 已存在但章节缺失的两条历史 release 补回。

### Changed

- **`bootstrap_cmd._execute_plan` 真正变 thin**：fresh-install 的 setup 步骤改用 `ctx.invoke(setup_command, ...)` 而非内联 `copy_scaffold_to + cfg.set_runtime_platform`，setup 后续新增的副作用（如 `--emit-env-block`）会自动覆盖 bootstrap 路径。
- **`migration_checks` 命名统一**：`mc-0.6.0-*` / `mc-0.7.0-*` / `mc-0.10.0-*` 三类预改名前的混杂前缀全部统一为 `mc-0.1.x-*`，与 0.1.x 主线版本号对齐。
- **`features.correction-hook.min_version`**：`"0.7.0"` → `"0.1.0"`（之前是预改名前遗留）。
- **`docs/reference/configuration.md` §framework.json / §profile.yaml / §hooks.yaml** 三段全部按真实代码 schema 重写（旧文档描述的字段在代码中根本不存在；`runtime.mode`、`runtime.checkpoints`、扁平 `features`、`migration_checks[].severity`、字符串 `upgrade.source`、`hooks.yaml: version: 1` 扁平列表、`profile.yaml: paths: / capabilities: / degradation:` 等）。
- **CHANGELOG 链接表**：`[Unreleased]` 比较基线从 v0.1.9 → v0.1.13；`[0.1.10/11/12/13]` reference link 全部补全。
- **dogfood "长期 dev 分支" 模型退役**：`scaffold-sync.yml` / dogfood README / PR 模板 / `no-dogfood-leak.yml` / `product-paths.txt` 五处仍按 dev-branch 写的指令统一改为 feature-branch + prepare-pr.sh 模型。
- **`docs/contributing.md`**：补 `build` / `ci` / `release` conventional-commits type；发布流程从手动 `twine upload` 改为 OIDC trusted publishing 流程描述；新增 §改代码 = 改文档 强约定表（PR 模板 Doc impact 段引用此表）。
- **README / docs/README / agents-and-skills.md**：Skill 计数 24 → 25（v0.1.7 引入的 self-update 之前一直未计入文档）。

### Fixed

- **`docs/reference/cli.md` / `status-codes.md`** 假历史："v0.1.x 用退出码 2 表示 stub，v0.2 起改 70" — 实际 `errors.py` 自 v0.1.0 起就是 70；删除编造的"版本演进"叙事。
- **`docs/reference/cli.md`**：`hook test` 的 `(v0.2+)` 标注（功能已发版）；`plugin install/remove` 的硬编码 v0.3 计划改为 GitHub issue 链接。
- **`docs/reference/configuration.md` schema 漂移整组**：`runtime.mode` / `runtime.checkpoints` / 扁平 `features` 等大量"文档里有、代码里没"的字段已删除；正确的 preserve / overwrite 字段表对应 `_merge_framework_json`。
- **`workflow-framework-generator/SKILL.md:135`** 字段名拼写错：`suggested_tools:` → `suggested-tools:`（SkillLoader 仅识别短横线形式；旧拼写会让生成的 skill 静默丢失 suggested-tools 字段）。
- **`mc-0.1.5-session-context-simplified` 路径**：原 `.cataforge/hooks/session_context.py` 实物不存在 → vacuous PASS（`file_must_not_contain` 在文件缺失时默认按通过处理）；现改为 `src/cataforge/runtime/hook/scripts/session_context.py` + `allow_missing: true` + `deprecate_after: "0.2.0"`。
- **doctor `file_must_not_contain` 默认严格**：路径缺失时 FAIL 并提示三种解决方案（修路径 / 加 `allow_missing` / 加 `deprecate_after`），堵住同类 vacuous-PASS 失败模式。
- **CHANGELOG `[0.1.0]` Roadmap 段**：补 STATUS UPDATE 注脚说明 `upgrade {check,apply,verify}` 与 `hook test` 自 v0.1.5 起已发版，仅 `plugin install/remove` 仍为 stub。
- **`framework.json.description`**：之前写"upgrade.source 升级时保留用户配置"与代码（每次 overwrite）矛盾；改为以代码为准。
- **`COMMON-RULES.md:139`** TODO/TBD/FIXME 规则改为引用 doc-review 实现，单一来源。
- **`platform-audit/SKILL.md:365`** 占位符更显眼。
- **codex `profile.yaml` `command_definition` 长期 TODO** 转架构文档跟踪点。
- **根 `CONTRIBUTING.md`** 补"完整指南见 docs/contributing.md"redirect 说明。

### Retired

- **dev 分支语义（剩余 5 处）**：v0.1.9 时 `chore(docs): retire dev branch` PR (#56) 漏掉的 5 个文件本次补齐；自此 origin 上 dev 分支不存在 + 全套文档/CI 一致按 feature 分支 + prepare-pr.sh 描述。

## [0.1.12] — 2026-04-25

### Fixed

- **`dep-analysis` 与三个 Penpot Skill 的脚本路径同形 bug** — `dep-analysis/SKILL.md` 与 `tech-lead/AGENT.md` 仍指令 `python .cataforge/skills/dep-analysis/scripts/dep_analysis.py`，磁盘上无该路径（实现已移到 `cataforge.runtime.skill.builtins.dep_analysis`）；`penpot-sync` / `penpot-implement` / `penpot-review` 三个 Skill 指令 `python .cataforge/integrations/penpot/setup_penpot.py ensure`，磁盘上同样无该路径，且 `cataforge penpot` CLI 缺失 `ensure` 子命令（`cmd_ensure` 函数实现完整但未注册）。这是 v0.1.11 修复 review skill 时遗漏的同类缺陷。现 dep-analysis 改走 `cataforge skill run dep-analysis -- ...`、Penpot 改走新加的 `cataforge penpot ensure`，scaffold 镜像同步更新。

### Changed

- **`cataforge doctor` 协议脚本扫描扩展到整个 `.cataforge/` 子树** — 原正则只匹配 `python .cataforge/scripts/...`，错过 `python .cataforge/skills/<id>/scripts/*.py` 与 `python .cataforge/integrations/...` 两类路径（dep-analysis 和 Penpot bug 正好落在这两个盲区）。现匹配 `.cataforge/` 下任意 `.py` 路径；同时显式过滤含 `*` / `...` 的占位符路径与 `.cataforge/hooks/custom/` 用户扩展目录的教学示例，避免误报。
- **`cataforge doctor` Layer 1 reachability 检查改名为 Built-in skill reachability，覆盖所有内置 Skill** — 之前硬编码 `(code-review, sprint-review, doc-review)`，新增 builtin（如 dep-analysis）会自动绕过检查；现从 `SkillLoader._scan_builtins()` 动态枚举，新增内置 Skill 的可达性自动纳入门禁。
- **`SkillRunner` 事件日志开关改由 SKILL.md frontmatter 驱动** — 新增 `record-to-event-log: true` 字段，`SkillMeta.record_to_event_log` 解析并经 `_merge_builtin_fallback` 在项目覆写时自动从 builtin 继承；移除 runner 端的硬编码 `_EVENT_LOGGED_SKILLS` 常量。新增审查类 Skill 只需翻一处标志，不再需要同时改 runner 与 doctor 两份名单。
- **`SkillLoader` 用 AST 判 `if __name__ == "__main__"`** — 旧实现是 `"__main__" in text and "__name__" in text` 文本匹配，会把 docstring 偶然提及这两个 token 的 helper 模块误判为 CLI 入口、混入 `meta.scripts`；现改用 `ast.parse` + `Compare` 节点结构匹配，false-positive 收敛为零。
- **`cataforge penpot` 新增 `ensure` 子命令** — `cmd_ensure(config)` 已存在于 `cataforge.adapter.integrations.penpot` 但未挂到 click group；本次显式注册，三个 Penpot Skill 才能按文档调用。

### Added

- **migration check `mc-0.1.10-event-logger-shim`** — 守住 `event_logger.py` 必须保持 forwarder 形态（`from cataforge.interface.cli.main import cli`）。orchestrator/tdd-engine/doc-gen 等十几处 `[EVENT]` 行依赖该 shim 的路径稳定性，以前没有任何机制阻止它被"重构掉"。
- **scaffold-sync 守卫测试** — `tests/test_scaffold_sync.py` 用 `filecmp.dircmp` 递归对比 `.cataforge/` 与 `src/cataforge/_assets/cataforge_scaffold/`，要求两边除显式白名单（`scripts/dogfood`）外字节级一致。dep-analysis 与 Penpot bug 在两份副本里同时存在，是双写无校验放大错误的直接证据；测试关掉这条退路。
- **doctor 静态扫描的回归用例** — `tests/cli/test_doctor_exit_code.py` 新增 `test_doctor_flags_missing_skill_subdir_script` / `test_doctor_flags_missing_integrations_script`，分别覆盖 `python .cataforge/skills/<id>/scripts/...` 与 `python .cataforge/integrations/...` 两个新扫描盲区的死亡情形。

### Changed

- **TDD 三阶段 subagent 的 `maxTurns` 由 50 放宽到 100** — `test-writer`（RED）/ `implementer`（GREEN）/ `refactorer`（REFACTOR）三个 AGENT.md 同步更新（含 scaffold 镜像）。50 次工具调用对略复杂的 AC 集合或多文件改动经常不够，subagent 在写完一半就被 host 截停后只能让 orchestrator 重新派发，不只是体验差，还会让 EVENT-LOG 出现"未完成的 phase"记录污染重试统计。100 次给出更充裕的预算，仍然有上限可以兜住失控的 agent。

## [0.1.11] — 2026-04-24

### Fixed

- **Layer 1 审查脚本从未真正运行** — 三个审查 Skill（`code-review` / `sprint-review` / `doc-review`）的 `SKILL.md` 向 AI 指令 `python .cataforge/skills/<id>/scripts/<script>.py`，但该路径在默认 scaffold 中不存在（脚本实为 `cataforge.runtime.skill.builtins.*` Python 模块，需通过 `-m` 调用）。AI 按字面执行必然 `FileNotFoundError`，命中 SKILL.md 定义的"脚本异常→降级 Layer 2"分支，Layer 1 质量闸从未真正运行；叠加 `SkillLoader.get_skill` 的 overshadow bug（项目级空壳 SKILL.md 屏蔽 builtin），`cataforge skill run` 也无退路（实测 `Error: Skill code-review has no executable scripts`）。现象是 `docs/reviews/` 目录长期为空、用户反馈"缺少 Layer 1 脚本工具、没有生成 code review 报告"。

### Changed

- **Layer 1 调用协议统一为 `cataforge skill run <skill-id> -- <args>`** — 三个审查 Skill 的 SKILL.md 全部改写；`SkillRunner` 解析 SKILL.md 元数据后派发到内置或项目覆写脚本。`docs/architecture/quality-and-learning.md` 新增 §2.1 *Layer 1 调用协议（single entry）* 作为权威条款，`.cataforge/rules/COMMON-RULES.md` 同步加指针段。调用路径 `python .cataforge/skills/.../scripts/*.py` 在所有文档中明令禁止。
- **Layer 1 降级规则收紧为四态** — 之前把 `FileNotFoundError` 与 Python 运行异常并列为"降级进入 Layer 2"，让路径错配长期隐身。现在 SKILL.md 拆出独立分支：`exit 2` / `exit 127` / `CataforgeError("no executable scripts")` 判定为**脚本不可达 → FAIL 不降级**，先跑 `cataforge doctor` 修复；仅真正的 Python 运行异常 / 超时仍按降级处理。
- **`SkillLoader` 在项目级 SKILL.md 无 scripts 时合并 builtin** — `_merge_builtin_fallback` 新增：当 `.cataforge/skills/<id>/SKILL.md` 存在但没有 `scripts/` 子目录，且 builtin 中有同名 Skill 时，借用 builtin 的 scripts 和 `builtin=True` 标记。这样项目仅覆写 SKILL.md 文案（prose override）而不打算重写脚本的场景 —— 正是三个审查 Skill 的日常用法 —— `cataforge skill run` 仍可用。
- **`cataforge doctor` 新增 `Review skill Layer 1 reachability` 段** — 三个审查 Skill 的脚本可达性一次性校验，shadow bug 再次潜伏时立刻 FAIL，并指向 `docs/architecture/quality-and-learning.md §2.1` 的修复路径。
- **`SkillRunner` 对三个审查 Skill 的运行记事件日志** — 每次 `cataforge skill run {code,sprint,doc}-review` 完成后向 `docs/EVENT-LOG.jsonl` 追加一条 `state_change` 记录（`agent=reviewer`，`status` 映射 `completed` / `needs_revision` / `blocked`，`ref=skill:<id>/<script>`），retrospective 可据此统计"质量闸到岗率"。非审查 Skill 不写入，保持 event log 窄通道语义。事件追加为 best-effort，日志不可写时不阻断脚本返回。

## [0.1.10] — 2026-04-24

### Added

- **`cataforge bootstrap` 子命令** — 一键串起 `setup → upgrade → deploy → doctor` 全流程，每一步根据 on-disk 产物状态（`.cataforge/framework.json` / `.scaffold-manifest.json` / `.deploy-state`）决定 skip 或 run，不引入"是否跑过 bootstrap"的缓存状态（这样用户手动 `rm -rf .claude/` 或回滚 scaffold 后下次运行能正确补上）。支持 `--dry-run` 打印每步 skip/run 决策与原因、`--yes` 跳过确认、`--skip-doctor` 跳过验证门、`--platform` 显式指定（与现有 `runtime.platform` 冲突时报错不改写）。版本判定用 semver 严格大于，editable dev install 的 metadata 反向滞后（如 0.1.8 < 0.1.9）不误触发 upgrade。根 `--help` 的 GETTING STARTED 段改以 bootstrap 为 0→1 推荐入口，原 `setup → deploy` 两步仍保留在 EVERYDAY COMMANDS 供底层使用。
- **`cataforge event accept-legacy` 子命令** — 设置 `upgrade.state.event_log_validate_since` ISO-8601 水位线，`cataforge doctor` 遇 `ts < 水位线` 的 EVENT-LOG 记录跳过 schema 校验。用于处理 v0.1.7 之前旁路写入遗留的坏记录（如 `revision_completed` 枚举外事件、`review_round`/`verdict` 未知字段），这些记录会永久让 doctor 返回非零。支持 `--before <ISO>` 显式指定截止时间，默认取当前 UTC now；写入时保持 framework.json 其他字段不变（复用 `load_raw → patch → write_text` 模式，与 `set_runtime_platform` 一致）。

### Changed

- **`cataforge upgrade apply` 完成后提示 `cataforge deploy`** — 当 `.cataforge/.deploy-state` 存在时，apply 结尾输出 `Tip: scaffold refreshed — run \`cataforge deploy\` to propagate changes to platform deliverables (e.g. .claude/settings.json).`。之前`upgrade apply` 只刷 `.cataforge/` scaffold，不触碰 `.claude/` 等 deploy 产物，导致用户 `pip install -U` + `upgrade apply` 之后 `.claude/settings.json` 里的 hook 注册永远落后一拍（实测场景：migration check `mc-0.1.9-detect-review-flag-registered` 在 apply 后依然 FAIL）。新提示明确引导下一步，但不隐式自动 deploy —— 显式优于隐式。
- **`cataforge doctor` EVENT-LOG schema 检查感知水位线** — `_check_event_log_schema` 读 `upgrade.state.event_log_validate_since`，pre-cutoff 记录单独统计为 `pre-cutoff skipped` 不计入失败数；水位线未设且出现 FAIL 时，输出 hint 指向 `cataforge event accept-legacy`，让历史脏数据的处置路径对用户可发现。坏 cutoff（无法解析的 ISO-8601 字符串）降级为 warning，不让 doctor 本身崩溃。

### Added

- **`cataforge upgrade rollback` 子命令** — `apply` 时自动把当前 `.cataforge/`（`.backups/` 自身除外）快照到 `.cataforge/.backups/<YYYYMMDD-HHMMSS>/`。新子命令 `rollback [--list | --from <ts-or-path>] [--yes]` 从最新快照（或指定快照）恢复，恢复前将当前状态再次快照到 `.backups/pre-rollback-<ts>/`，使回滚本身可逆。填补了之前 "scaffold 回滚必须走 git" 的限制。
- **`cataforge upgrade check` CHANGELOG BREAKING 检测** — 在检测到包版本与 scaffold 版本不一致时，扫描项目根 `CHANGELOG.md` 的 `## [x.y.z]` 段落，对落在 `scaffold_version < v <= installed_version` 范围且含 `### BREAKING` 子标题的条目，以黄色警告输出版本号与第一条要点摘要，并提示用户在 `upgrade apply` 前先阅读 CHANGELOG。
- **`cataforge upgrade check` 指向 `/self-update` skill 的提示** — 检测到过期时输出 `Tip: inside Claude Code / Cursor, the /self-update skill automates the whole flow (check → confirm → apply → verify).`，让 AI IDE 用户知道存在一条编排自动化的并行路径。同步在 `docs/guide/upgrade.md` 顶部以表格形式对比 CLI 与 `/self-update` 两条路径。
- **根目录治理文件**（GitHub 约定） — 新增 `CONTRIBUTING.md`（一行指针指向 `docs/contributing.md`）、`CODE_OF_CONDUCT.md`（Contributor Covenant v2.1 中文版）、`.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`（GitHub Issue Forms schema，含版本 / 平台 / doctor 输出字段）。
- **`docs/reference/quick-reference.md` 一页速查卡** — 平台能力矩阵 + 14 个 CLI 子命令一行定位 + 四平台产物落盘路径 + 退出码表。紧急查阅时无需读 190 行 `cli.md`。
- **`docs/getting-started/troubleshooting.md` 按症状索引的故障排查** — 从 696 行的 `manual-verification.md §5` 抽离出来独立成页，覆盖安装/环境、CLI 乱码、命令入口、Agent/Skill 为空、IDE 看不到产物、MCP、Hook、升级、登录态 9 个场景。
- **`agents-and-skills.md §工具权限语法`** — 正式文档化 `allow:` / `deny:` 在 `AGENT.md` frontmatter 中的优先级规则（allow 空=允许全部；deny 优先级高于 allow）。
- **`docs/guide/upgrade.md` 覆盖语义警告 + FAQ** — 在"字段保留规则"表格上方显式告知 "除表中文件外，`.cataforge/` 下所有文件在 `apply` 时会被整体覆盖"，并新增"我改过的 AGENT.md 升级后不见了怎么办"等 3 个 FAQ 条目，同步推荐 `.cataforge/plugins/` 作为自定义内容归宿。
- **`.gitignore`** 新增 `.cataforge/.backups/` 条目，让快照目录默认不入库。

### Changed

- **`cataforge --help` 顶层子命令目录** — 原本只罗列 `setup` / `deploy` / `doctor` 3 个"Getting started"示例，用户无法从 `--help` 知道 15 个子命令的存在。现按 `GETTING STARTED` / `EVERYDAY COMMANDS` / `FRAMEWORK OBJECTS` / `LOGS & INTEGRATIONS` 四段枚举全部子命令并附一行作用说明。
- **`cataforge deploy --help` / `setup --help` 文档** — 原一句式 docstring 改为带 `EXAMPLES` 段的多段说明；`setup --help` 顶部用 ascii 箭头显式呈现 `setup → deploy` 两步管线，并警示 `--force-scaffold` 对 `.cataforge/` 非保留文件的覆盖行为，引导用户改用 `upgrade apply --dry-run` 做预览。
- **`cataforge setup --check` 更名为 `--check-prereqs`** — setup 的 `--check` 原语义为"仅前置检查不安装"，deploy 的 `--check` 为 "`--dry-run` 别名"，两子命令同名异义。`--check` 与 `--check-only` 保留为 hidden alias（计划 v0.3 移除）；主名改为自解释的 `--check-prereqs`。
- **文档结构重构** — 按 "入门 → 指南 → 架构 → 参考" 四层职责拆分重叠内容，12 对重复段落收敛到唯一权威源并加锚点链接：`tdd-workflow.md §状态码` + `§Sprint Review` 引去 `status-codes.md §1` + `quality-and-learning.md §4`；`runtime-workflow.md §7 事件日志` 引去 `status-codes.md §5`；`quality-and-learning.md §3 问题分类` 引去 `status-codes.md §2+§3`；`platform-adaptation.md §2a context_injection` 字段表引去 `configuration.md`；`platform-adaptation.md §6 幂等清理` 引去 `overview.md §4`；`platforms.md §跨平台目录隔离` 引去 `platform-adaptation.md §4`；`overview.md §关键配置文件` 引去 `configuration.md §文件总览`；`contributing.md §文档分层原则` 引去 `docs/README.md`。
- **`manual-verification.md` 瘦身** — 从 696 行拆分：`§5 故障排查` 抽出到 `docs/getting-started/troubleshooting.md`；`§1.2/§1.2a` 安装复述删除，链到 `installation.md` 唯一源；`§3.6` 孤儿清理修正为覆盖 Claude Code 扁平布局（`.claude/agents/*.md`，v0.1.2 起）与 Cursor/OpenCode 嵌套布局（`<name>/AGENT.md`）两种。
- **`docs/guide/upgrade.md` 全文被动语态改主动** — "被覆盖" → "覆盖"、"会被保留" → "apply 保留"；补 `--from` 两种取值样例（时间戳名 vs 绝对路径）；新增 `快照生命周期` 小节明确不自动 GC、典型 5-15 MB / 快照。
- **`cli.md` 补齐 `upgrade rollback` + `event log` 子命令** — 之前 `rollback` 在 `upgrade.md` 有完整文档、`cli.md` 却完全缺失；`event log` 在协议文档里引用但 CLI 参考未收录。每个子命令补"何时用它"一行定位（`doctor` / `setup` / `deploy`）。
- **`agents-and-skills.md` 术语对齐 YAML 键** — "可用工具" → "允许工具（allow）"；"禁用工具" 明注为 YAML 键 `deny:` 的中文说明；文首新增 §工具权限语法 小节。
- **`runtime-workflow.md`** 增加 `## 目录` 与 `## 关键术语` 小节（Fork context / Dispatch prompt / start-orchestrator），消除未解释术语；`configuration.md` 增加 TOC（236 行）；`platform-adaptation.md` 补 `烘焙` 首现解释。
- **`README.md` 重写** — 删除 §为什么选择叙事段 / §适用场景 / §架构大表；Quick Start 从 4 个单独 bash 块合成一段可直接复制的 5 步命令块（`--dry-run` 而非已弃用的 `--check`）；文档导航改为按用户意图组织的"我想……"表格；新增 CI badge 与 CODE_OF_CONDUCT 链接。
- **`docs/getting-started/quick-start.md` 可视化与下一步分叉** — 在 "3 条命令"之前新增 Mermaid flowchart 概览 doctor → setup → deploy → IDE 产物 的管线；"下一步"由三个并列链接改为按用户意图（platforms / manual-verification / upgrade / agents-and-skills / architecture）的分叉表格。
- **`CLAUDE.md` PR 标题反例升级为解释表** — 原一行反例列表扩写为"标题 / 为什么错"对照表，补 `fix(scaffold)` / `test(e2e,ci)` 等正例，并显式告知 main 上残留的历史不合规 squash commit 不要模仿。

### Fixed

- **`configuration.md` 示例 `framework.json` 版本号过时** — 示例写 `"version": "0.1.1"`，与当前 `__version__` 差 7 个版本；改为 `"0.1.9"`。
- **`platform-adaptation.md` 虚构模型名** — CodeX 多模型路由列出 `gpt-5.4 / spark`（`gpt-5.4` 不是任何真实模型名），改为 `OpenAI 系（gpt / o 系列）`。
- **`platform-adaptation.md` + `platforms.md` 把已弃用的 `deploy --check` 说成当前功能** — `--check` 自 v0.1.7 起已 `hidden=True` 并打印 `[deprecated]` 黄色警告（计划 v0.3 移除），但这两份文档仍把它描述为可用干运行标志。统一改为 `--dry-run`。
- **`manual-verification.md` 同文件内自相矛盾的 `pytest -q` 基线数字** — `§3.4` 说 `154 passed`、`§4 case 8` 说 `116 passed`。删除两处具体数字，改为 "全部用例通过，以 `main` 最新 CI 为准"。
- **`status-codes.md §6` 退出码表缺 `70`** — 只列了 `2` 为 stub 占位；而 `cli.md` L218 已明确 v0.2 起 `70` 替代 `2`。补齐 `70`（BSD `EX_SOFTWARE`），并保留历史注记。
- **`manual-verification.md` Claude Code agent 路径过时** — 示例写 `.claude/agents/*/AGENT.md`（v0.1.2 前的嵌套布局），当前实际是 `.claude/agents/*.md`（扁平）。同步修正 §3.6 的孤儿清理规则。
- **`faq.md` 3 个失效锚点** — `README.md §项目定位`（不存在）→ `§功能亮点`；`upgrade.md §字段保留规则` → `§文件保留规则`；`§MCP 看不到 server` 里的 "不是 `--check`" → `不是 --dry-run`。
- **`docs/assets/verification-flow.svg`** — stage 3 标签 `deploy --check` 改为 `deploy --dry-run`。
- **`runtime-workflow.md` TOC 漏掉新加的 `关键术语`** — 修正。

## [0.1.9] — 2026-04-24

历史回填（首次发版时仅打 tag 未补章节，本条由后续审计补齐；改动通过链接的 commit 范围核对）。

### Added

- **`cataforge upgrade rollback` 子命令** — `upgrade apply` 自动写入 `.cataforge/.upgrade-backups/` 快照，`rollback` 一键回滚到上一个快照；保留 `runtime.platform`、`upgrade.state`、`PROJECT-STATE.md` 等用户态。
- **Upgrade BREAKING hints** — `upgrade check` / `upgrade apply` 解析 CHANGELOG 的 `### BREAKING` 条目，在升级前显式列出可能影响的行为，避免静默回归。
- **PR 标题强制 conventional-commits** — `.github/workflows/pr-title.yml` 拒绝 `Dev` / `Pr/dev-…` / 大写开头等 noise 标题，从源头保证 squash merge 后的 main 历史整洁。
- **e2e 安装 / 升级测试** — 真实 wheel + venv 矩阵跑 install / upgrade，作为 CI gate。

### Changed

- **文档大重构** — 拆 `getting-started/` `guide/` `architecture/` `reference/` 四层；删除重复内容，新增 `quick-reference.md` 速查卡。
- **`cataforge setup --check` 更名为 `--check-prereqs`** — 与 `deploy --check`（dry-run 别名）解耦，旧名计划 v0.3 移除。
- **CLI help / quick-start 图** — 扩充每个子命令的 `--help` 文案，`docs/getting-started/` 新增引导图。

### Fixed

- **`correction-log` 韧性** — 半写入下不再损坏 markdown / jsonl，schema 校验后再 append。

### Retired

- **dev 分支语义（部分）** — `CLAUDE.md` / `pr-title.yml` / `prepare-pr.sh` 头注释删除"长期 dev 分支"假设。后续 v0.1.13 在 #PR-3 完成 `scaffold-sync.yml` / dogfood README / PR 模板 / `no-dogfood-leak.yml` / `product-paths.txt` 五处补丁，使整套退役一致。

## [0.1.8] — 2026-04-24

### Added

- **`cataforge correction record` CLI** — interrupt-override 通路的官方写入入口。orchestrator 在 Interrupt-Resume 协议中识别用户推翻 `[ASSUMPTION]` 后调用此命令，自动双写 `docs/reviews/CORRECTIONS-LOG.md` 与 `docs/EVENT-LOG.jsonl (event=correction)`，替代之前易漏写的"手动编辑两个文件"流程。
- **`detect_review_flag` hook（review-flag 通路自动化）** — 新增 PostToolUse / Agent 钩子（matcher_agent_id=`reviewer`），当 reviewer 报告中出现包含 `[ASSUMPTION]` 的 CRITICAL/HIGH 级问题时，自动 append 到 CORRECTIONS-LOG + EVENT-LOG，无需 reviewer 自我约束写入。
- **`cataforge.core.corrections.record_correction` 共享写入器** — On-Correction Learning Protocol 三条通路（option-override / interrupt-override / review-flag）共享单一写入函数，schema 与双日志同步由此点统一保证；旧 `detect_correction.py` 仅写 markdown 不写 EVENT-LOG 的偏移随之消失。
- **`cataforge doctor` Hook script importability 检查** — 对 `hooks.yaml` 中声明的每个内置脚本执行 `importlib.util.find_spec("cataforge.runtime.hook.scripts.<name>")`，模块缺失（如 site-packages 残留旧 stub 遮蔽 editable install）即 FAIL 并提示 `pip install -e .` 修复。这是导致 `detect_correction` 静默失效数周的失败模式的直接守卫。
- **`cataforge doctor` Runtime degradation 段** — 在导入性检查后报告当前平台的每脚本降级状态（native / skip / degraded），让"已安装但运行时被跳过"这种隐式行为损失不再隐藏在 deploy 输出里。
- **`self-update` 用户技能** — 新增 `/self-update [check|apply|verify]` 用户可调用技能，在 AI IDE 会话内标准化 CataForge 升级流程：`check` 对比已安装包版本与项目 scaffold 版本；`apply` 自动识别 pip/uv、升级包、刷新 `.cataforge/` scaffold 并写入 `upgrade.state`；`verify` 通过 `cataforge doctor` 执行迁移检查。无参调用时依次执行 check → confirm → apply → verify 完整流程。
- **`.cataforge/.scaffold-manifest.json` 脚手架清单** — `cataforge setup` / `cataforge upgrade apply` 写入 scaffold 时，同时记录每个文件的 `sha256` 与写入它的包版本。升级时 `upgrade apply --dry-run` 可对比清单，逐文件标注 `[new]` / `[unchanged]` / `[update]` / `[user-modified]` / `[preserved]`，首次把"哪些文件将被覆盖"从黑箱变为透明清单。

### Fixed

- **hatch build hook GBK 解码崩溃（Windows 中文系统）** — `hatch_build.py` 使用 `text=True` 调用子进程，Windows 中文系统默认编码 GBK 无法解码输出中含有的弯引号字节（`0x92`），导致读取线程 `UnicodeDecodeError`、`result.stdout` 变 `None`、`write()` 随后抛 `TypeError`，使 `uv sync` / `uv build` 在中文 Windows 上完全不可用。改为 `encoding="utf-8", errors="replace"` 并为 `stdout/stderr` 增加 `None` 守卫。
- **CHANGELOG 重复 `## [0.1.8]` 段** — 0.1.8 发版时两条独立工作线的 changelog 条目被分别写入同一版本号下两个段，使 `grep "^## \[0.1.8\]" CHANGELOG.md` 返回两次命中。本次合并为单段，避免 CHANGELOG 成为发版可信度的反例。
- **CHANGELOG 孤儿 link `[0.1.4]`** — `v0.1.4` 既无 `## [0.1.4]` 段、也无 git tag，但底部 `[0.1.4]:` reference link 挂向不存在的 `releases/tag/v0.1.4`（404）。删除该孤儿 link；`v0.1.3` / `v0.1.5` tag 待另行补打，现 link 暂保留。
- **Quick Start 沿用已弃用的 `deploy --check`** — 官方 `docs/getting-started/quick-start.md` 与 `README.md` 的"4 步部署"示例仍使用 `deploy --check`，而该 flag 自 0.1.7 起已 `hidden=True` 并打印 `[deprecated]` 黄色告警（计划 v0.3 移除）。新用户跟随官方 Quick Start 敲命令即看到 deprecation noise。改为 `deploy --dry-run`。
- **`publish.yml` 缺版本一致性预检** — `push: tags: v*` 直接触发 PyPI 发布，无任何 tag-vs-`__version__`-vs-CHANGELOG 段的一致性校验。新增 pre-check step：tag 与 `src/cataforge/__init__.py` `__version__` 必须相等，且 `CHANGELOG.md` 必须含对应 `## [x.y.z]` 段，否则 workflow 红灯。

### Changed

- **`cataforge upgrade apply --dry-run` 输出** — 从 `Would refresh N scaffold file(s).` 一句总览，扩展为逐文件列表，每行附状态标签：`[new]` 磁盘缺失、`[unchanged]` 无字节变化、`[update]` 干净更新、`[user-modified, will overwrite]` 用户手改过即将被覆盖、`[preserved]` 走 `_MERGE_HANDLERS` 保留用户字段。用户首次能在升级前看清"到底会改什么"。

## [0.1.7] — 2026-04-23

### Added

- **`cataforge event log` 子命令** — 将协议里长期引用、但实际从未存在的 `event_logger.py` 从文档契约升级为真实实现。新增 `cataforge.core.event_log`（JSONL 写入 + schema 校验 + 批量原子写入）、`cataforge event log` CLI（支持 `--event/--phase/--agent/--status/--task-type/--ref/--detail/--data` 单条写入，以及 `--batch` 从 stdin 读取 JSONL 原子批量写入）。`.cataforge/scripts/framework/event_logger.py` 作为转发 shim 保留，兼容旧协议中的调用字面量。
- **`cataforge doctor` 协议脚本引用扫描** — 扫描 `.cataforge/` 下所有 `.md/.yaml/.yml` 中形如 `python .cataforge/scripts/<path>.py` 的调用，任一引用文件不存在即 FAIL 并列出调用点。防止 `event_logger.py` 这类"协议里引用但磁盘上不存在"的引用再次长期潜伏。

### Fixed

- **`cataforge hook test` 子进程找不到 cataforge 包** — 非 site-packages 安装（editable / `pip install <path>`）下，`hook test` 通过 `subprocess.run` 调用 `python -m cataforge.runtime.hook.scripts.X` 时子进程继承不到 pytest 的 `pythonpath=["src"]`。新增 `_child_env_with_cataforge_importable` 基于 `cataforge.__file__` 反推包根并注入子进程 `PYTHONPATH`。
- **`log_agent_dispatch` 降级模板容错** — 审计日志属 `observe` 类最佳努力行为，但降级模板之前没有说明失败不应阻断流程。现模板追加 `|| true` 并注明"任何非 0 退出仅作 stderr 警告"，避免 shim 偶发失败中断 LLM 主流程。
- **orchestrator 协议脚本清单漂移** — `ORCHESTRATOR-PROTOCOLS.md` 的脚本清单段落仍在列举已被 CLI 子命令取代的 `.py` 路径。改写为反映当前真实布局，并重写"本地路径升级步骤"小节以使用 `pip install <path> && cataforge upgrade apply` 模型。

### Changed

- **文档去陈（scaffold + 实时双写）** — 18 个 agent/skill/protocol 文档共 46 处将 `python .cataforge/scripts/...` 直接调用替换为等价的 `cataforge` 子命令：`docs/load_section.py` → `cataforge docs load`；`docs/build_doc_index.py` → `cataforge docs index`；`framework/upgrade.py {check,upgrade,verify}` → `cataforge upgrade {check,apply,verify}`。下游协议从此不再依赖已退役的脚本字面量。

## [0.1.6] — 2026-04-23

### Fixed

- **agile-lite / agile-prototype 行数限制** — lite 模板（prd-lite / arch-lite / dev-plan-lite）的行数目标从 ≤50 行放宽至目标 ≤100 行，超 150 行才触发模式升级提示；brief 模板从 ≤150 行放宽至目标 ≤200 行，超 300 行才触发。任务数升级触发从 >15 调整为 >25。旧限制在扣除模板结构开销后实际可用行数不足，导致 5 功能的 agile-lite 项目即会触发不必要的模式升级。
- **orchestrator 误作 subagent 启动** — `start-orchestrator` SKILL.md 缺少明确的角色假设声明，导致 LLM 默认通过 `agent-dispatch` 激活 orchestrator 子代理而非让主线程直接担任该角色。新增 `§角色假设` 和 `Anti-Patterns` 段修正此行为；同时移除 `orchestrator/AGENT.md` 中对主线程无意义的 `maxTurns: 200` 字段。

## [0.1.5] — 2026-04-23

### Fixed

- **sdist 构建** — `.cataforge/` scaffold 目录及注册的构建产物现已正确包含在源码分发包中。

## [0.1.4] — 2026-04-23

历史回填（首次发版时仅打 tag 未补章节，本条由后续审计补齐；改动通过 git log 范围核对）。

### Fixed

- **`fix(build): include .cataforge in sdist + force-register scaffold artifacts`** (#40) — sdist 现在带上 `.cataforge/` 目录，避免下游从 sdist 安装时缺 scaffold 模板；hatch 构建 hook 强制注册 scaffold artifact。

### Docs

- **`docs(installation): add upgrade section`** (#39) — 安装文档补 upgrade 段。

## [0.1.3] — 2026-04-23

### Changed

- **README** — Overhauled project homepage: removed emoji, introduced
  `hero-banner.svg` and `key-features.svg` SVG assets for richer visual
  presentation, rewrote narrative with benefit-first structure and lower
  onboarding friction, added `uvx` zero-install quick-start path, converted
  all relative links to absolute GitHub URLs for correct rendering on PyPI.

## [0.1.2] — 2026-04-17

Housekeeping release: scaffold-sync automation, platform-adapter
deduplication, and correction of the OpenCode hook-degradation matrix so
it reflects the TS-plugin bridge already emitted by the adapter.

### Changed

- **OpenCode hooks** — `platforms/opencode/profile.yaml` now marks
  `guard_dangerous`, `log_agent_dispatch`, `validate_agent_result`,
  `lint_format`, `detect_correction`, `notify_done`, and `session_context`
  as `native` (they flow through the generated
  `.opencode/plugins/cataforge-hooks.ts` bridge).  Only
  `notify_permission` remains `degraded` because OpenCode has no
  `Notification` event.  Previously the whole table read `degraded`,
  which triggered unnecessary warnings and degradation artefacts on every
  deploy.
- **Claude Code agent layout** — `deploy_agents` now emits only the flat
  `.claude/agents/<name>.md` form (the layout Claude Code's native
  `/agents` discovery actually scans).  The legacy
  `<name>/AGENT.md` subdir mirror is no longer written; on first deploy
  after upgrade, any pre-existing legacy subdir is pruned automatically
  so users land in a clean state without manual cleanup.
- **Platform adapters** — `get_tool_map` and the standard
  `inject_mcp_config` now have base-class defaults driven by the
  platform profile; Claude Code / Cursor only override a single
  `_mcp_json_path` template method.  Codex / OpenCode keep their
  custom `inject_mcp_config` for non-JSON layouts.
- **ConfigManager** — removed the dead `_write()` backward-compat
  shim; all write paths already use `_write_raw` + explicit cache
  invalidation.

### Added

- **Scaffold mirror automation** — `scripts/sync_scaffold.py` is now the
  source of truth for keeping `src/cataforge/_assets/cataforge_scaffold/`
  in lockstep with the repo-root `.cataforge/`.  A Hatch build hook
  (`scripts/hatch_build.py`) refreshes the mirror before every
  sdist/wheel build; a CI workflow (`.github/workflows/scaffold-sync.yml`)
  rejects drift on PR/push; `.gitattributes` marks the mirror
  `linguist-generated=true` so GitHub folds the diff in reviews.
- **Migration guard** — a new regression test ensures legacy Claude Code
  `<name>/AGENT.md` subdirs are pruned on upgrade.

## [0.1.1] — 2026-04-15

Documentation-only release. Corrects counts and removes stale environment-variable
gymnastics in examples so the published PyPI page reflects the actual CLI UX.

### Changed

- **README** — update module/subpackage count (88 / 13), test count (105),
  skill count (24); drop obsolete `PYTHONUTF8=1 PYTHONPATH=src` prefix from
  usage and testing examples (CLI auto-configures UTF-8 via
  `ensure_utf8_stdio()`, and installed console script doesn't need
  `PYTHONPATH=src`).
- **docs/manual-verification-guide.md** — remove redundant "set UTF-8 env"
  step; rewrite Unicode-troubleshooting section to point at terminal code
  page rather than `PYTHONUTF8=1`; update test baseline to `105 passed`.
- **docs/README.md** — update skill count to 24.

## [0.1.0] — 2026-04-15

First public release on PyPI. The `cataforge` CLI can bootstrap a project
scaffold and deploy it to four AI IDE platforms from a single
`.cataforge/` spec.

### Added

- **Unified CLI** (`cataforge`) with subcommands: `setup`, `deploy`,
  `doctor`, `hook`, `agent`, `skill`, `mcp`, `plugin`, `docs`, `penpot`,
  `upgrade`.
- **Multi-platform deploy** — bundled adapters for Claude Code, Cursor,
  Codex, and OpenCode, discovered via the `cataforge.platforms`
  entry-point group.
- **Bundled scaffold** — `cataforge setup` copies a full `.cataforge/`
  skeleton (agents, skills, rules, hooks, platform profiles, schemas)
  into a fresh project; no `git clone` required.
- **Skill runtime** — declarative SKILL.md discovery plus a
  `SkillRunner` that invokes built-in and project-level scripts with a
  consistent `CATAFORGE_PROJECT_ROOT` environment.
- **MCP registry & lifecycle** — declarative `.cataforge/mcp/*.yaml`
  specs, `cataforge.runtime.mcp` entry-points, and process start/stop with
  on-disk state under `.cataforge/.mcp-state/`.
- **Plugin loader** — `cataforge.plugins` entry-points and project-local
  `.cataforge/plugins/*/cataforge-plugin.yaml` manifests.
- **Hook bridge** — JSON-stdin dispatch to framework-level hook scripts
  with configurable skip rules.
- **Platform conformance tests** — every adapter is exercised against a
  shared capability checklist.
- **UTF-8 stdio guard** — CLI reconfigures stdout/stderr on Windows
  `cp936` terminals so status glyphs render without `PYTHONUTF8=1`.
- **MIT license**, PyPI classifiers, `py.typed` marker for downstream
  type-checkers.

### Roadmap (stub in 0.1.0)

The following subcommands exit with code 2 and print an actionable
hint; full implementation is tracked for later milestones:

- `cataforge upgrade {check,apply,verify}` — planned v0.2.
- `cataforge hook test <name>` — planned v0.2.
- `cataforge plugin {install,remove}` — planned v0.3.

> **STATUS UPDATE (since v0.1.5):** `upgrade {check,apply,verify,rollback}` 已实现（见 0.1.5 / 0.1.7 / 0.1.9 entries），`hook test <name>` 已实现（见 `cataforge.interface.cli.hook_cmd`）。仅 `plugin {install,remove}` 仍为 stub。

[Unreleased]: https://github.com/lync-cyber/CataForge/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.11.0
[0.10.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.10.0
[0.9.2]: https://github.com/lync-cyber/CataForge/releases/tag/v0.9.2
[0.9.1]: https://github.com/lync-cyber/CataForge/releases/tag/v0.9.1
[0.9.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.9.0
[0.8.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.8.0
[0.7.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.7.0
[0.6.1]: https://github.com/lync-cyber/CataForge/releases/tag/v0.6.1
[0.6.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.6.0
[0.5.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.5.0
[0.4.1]: https://github.com/lync-cyber/CataForge/releases/tag/v0.4.1
[0.4.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.4.0
[0.3.1]: https://github.com/lync-cyber/CataForge/releases/tag/v0.3.1
[0.3.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.3.0
[0.2.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.2.0
[0.1.15]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.15
[0.1.14]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.14
[0.1.13]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.13
[0.1.12]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.12
[0.1.11]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.11
[0.1.10]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.10
[0.1.9]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.9
[0.1.8]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.8
[0.1.7]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.7
[0.1.6]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.6
[0.1.5]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.5
[0.1.4]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.4
[0.1.3]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.3
[0.1.2]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.2
[0.1.1]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.1
[0.1.0]: https://github.com/lync-cyber/CataForge/releases/tag/v0.1.0
