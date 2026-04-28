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
- **HOOKS_MANIFEST 注册机制** —— 新模块 `cataforge.hook.manifest` 声明 builtin hook 脚本目录（含 events / default_capability / default_type / safety_critical 元数据），catch "把 helper 当 hook 挂" bug；framework-review 增 B6-ε 子检查双向校验：hooks.yaml 非 `custom:` 引用必须 ∈ HOOKS_MANIFEST（FAIL），HOOKS_MANIFEST 条目必须被 hooks.yaml 引用（WARN dead inventory）。新增 6 个测试覆盖正常 / 孤儿引用 / 未挂 / custom 跳过 / manifest 不可导入降级 / 真实 manifest 与 .py 文件 1:1 对账。
- **Pydantic V2 strict mode（保守应用）** —— `MCPServerState` 加 `strict=True`（输入仅来自 cataforge 自写状态文件，类型保真）；所有 schema 模型统一加 `validate_assignment=True`（catch "构造后赋错类型" bug）；`extra="allow"` / `extra="ignore"` 维持原状以容忍用户 YAML/JSON 类型宽松。文档化策略边界（user-input 模型暂不开 strict）。
- **CI gate `uv lock --check`** —— `.github/workflows/test.yml` Linux job 加 uv 安装 + 锁文件新鲜度检查，pyproject.toml 改依赖未刷 uv.lock 即 fail。`docs/contributing.md` 加锁文件刷新指引。

- **sprint-review CLI 增加 ignore / 输出形态控制参数** —— `--src-dir` 改为可重复 (monorepo 多包按需缩范围)；新增 `--ignore PATTERN` (可重复) / `--ignore-file PATH` (可重复) 追加 gitignore 风格规则；`--no-respect-gitignore` 关闭 git 集成、`--no-default-ignores` 关闭内建默认 ignore；`--warn-cap N` (默认 50) 折叠 unplanned WARN 到 top-level 目录摘要 (`node_modules/* (12340)`)，`--unplanned-log PATH` 把完整列表落盘以便审计；`--format json` 输出结构化 issue 列表 (`{summary: {fail, warn, total}, issues: [{severity, category, message, task?, path?}, ...]}`) 供 framework-review / CI 机读。
- **CHECKS_MANIFEST anchor 模式** —— `.cataforge/skills/sprint-review/SKILL.md` §Layer 1 检查项 升级到 `<!-- check_id: ... -->` anchor 模式 (B3 双向校验)，对每条 manifest 项强制 prose 锚点；`unplanned_files` 条目标题同步覆盖默认 ignore + .gitignore 集成语义。
- **`tests.conftest.run_utf8` 共享 subprocess 帮助函数** —— `subprocess.run(text=True)` 用 parent 的 cp1252 (Windows CI 默认) 解码 UTF-8 输出会让 reader 线程崩溃、`stdout` 静默变 `None`，下游 `json.loads` 报"not NoneType"难以诊断。提取 `run_utf8(cmd, *, cwd, check, timeout, extra_env, **kw)` 到根 `tests/conftest.py`，统一 `encoding="utf-8"` / `errors="replace"` / `PYTHONUTF8=1`；`tests/e2e/conftest.py` 的 `built_wheel` / `pip_install` / `run_cataforge` 与 sprint-review CLI 测试切换调用；新增 `tests/test_run_utf8.py` 5 个回归测试 (中文+em-dash 解码 / `PYTHONUTF8` 注入 / `extra_env` 合并 / `check=True` 抛错 / 默认放行非零码)，防止有人"简化"掉 `encoding`。
- **pre-commit 装机率 guard 三件套** —— 解决"`.pre-commit-config.yaml` 已配 ruff 但本地从未跑 `pre-commit install`，CI 60 秒后才翻红"的问题。(1) `tests/conftest.py` `pytest_sessionstart` 探测 `.git/hooks/pre-commit` 缺失时**自动**调用 `python -m pre_commit install` 安装钩子（`pre-commit` 已在 [dev] 依赖、且 `pre-commit install` 幂等无副作用），失败 fail-soft；power user 可设 `CATAFORGE_SKIP_HOOK_AUTOINSTALL=1` 关闭；(2) `.github/workflows/test.yml` Linux job 加 `pre-commit run --all-files --show-diff-on-failure` 作为 belt-and-braces step，杜绝 `.pre-commit-config.yaml` 与 CI 单点 ruff 命令偷偷漂移；(3) `docs/contributing.md` 把 `pre-commit install` 从"可选"提为开发环境 setup 必跑步骤，改写说明强调本地↔CI 检查 1:1 对账。

- **frontmatter `aliases:` 字段 + 三段式 doc_id 解析** —— 旧 cross-ref resolver 短引用（如 `arch-data#§4.E-002`）只在严格 doc_id 匹配 / `{doc_id}-*` prefix-fallback 两层尝试，命中不到 `arch-wechat-typeset-X-0.1.0-data` 这类后缀别名时直接 FAIL，下游 doc-review 在每份 theme 分卷上系统性触发"交叉引用目标未找到"。新增 `aliases:` frontmatter 字段：indexer 抽取后写入顶层 `aliases: {alias → doc_id}` 映射，`cataforge.docs.loader._resolve_doc_entry` 改三段式（exact → aliases → prefix-fallback），prefix 多匹配从"取 dict 迭代第一个"升级为抛 `AmbiguousRefError` 并列出全部候选。重复声明 / 与真 doc_id 撞名的 alias 由 `build_aliases()` 第一占位胜出并记入 `alias_conflicts`，validate 时上报。
- **`cataforge docs validate` 跨引用 + alias 冲突校验** —— 旧实现仅查 orphan / stale，无法在 commit / CI 时拦下"DEPS 行写错 doc_id"或"两份文档抢同一 alias"；前者要等到下游 `cataforge docs load` 才暴露、后者完全静默。新增 `validate_docs(project_root)` 统一入口（`cataforge.docs.indexer.validate_docs`），同时跑 orphans / stale / `find_xref_errors` / `find_alias_conflicts`；`cataforge doctor` 的 `_check_orphan_docs` 重命名为 `_check_docs_validate` 并切到同一 helper，命名段从 "Docs index completeness" 改为 "Docs validation"。
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

- **sprint-review unplanned-file 检测在 monorepo 下噪声爆炸** —— 旧实现 `os.walk(--src-dir)` 无 ignore 列表，packages 根目录里的 `node_modules/zod/...`、`dist/`、`*.tsbuildinfo` 等会被全部当成 gold-plating，单次运行 13k+ WARN 把 6 条真实 FAIL (缺 CODE-REVIEW 报告) 完全淹没。重写 `cataforge.skill.builtins.sprint_review.sprint_check.check_unplanned_files`：候选集合默认通过 `git ls-files -co --exclude-standard` 取得（同时尊重 `.gitignore` / 子模块 / global excludes），不在 git 仓内时回落到 `os.walk` 并预剪 `node_modules` / `__pycache__` / `.git`；新增 `cataforge.skill.builtins.sprint_review.ignore` 模块，`DEFAULT_IGNORE_PATTERNS` 兜底覆盖 Node / TS / Python / coverage / lock 文件常见产物。

- **`check_required_sections` 在 frontmatter 内自命中** —— 旧实现 `re.search(re.escape(heading), self.content, re.MULTILINE)` 直接在全文跑，`required_sections:` YAML 数组里写的字面量（`- "## 4. 主题方案"`）会先于真正的 `## 4. 主题方案` 标题被匹中并截走 group(1) 直到下一个 `^## `，导致缺章节场景永远不 FAIL。改为先 `split_yaml_frontmatter` 剥离 frontmatter 再做 regex；新增的 `test_check_required_sections_fallback_flags_missing_section` 守住该回归。

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
- `cataforge.docs.indexer.main` orphan WARN 文案改进。
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
- **`cataforge.docs.indexer.find_stale_index_entries()` + doctor + `docs index --strict` 接入反向 orphan 检测** —— `.doc-index.json` 登记的 `file_path` 在磁盘已不存在时：doctor 报 FAIL（counts toward `failed_count` exit gate）+ `docs index --strict` 增量分支 exit 3。这是 audit A5 提到的"反向孤儿"，与正向 orphan（磁盘有 md 文件但缺 front matter）形成对称：indexer 维护双向一致性。
- **`bootstrap` 末尾自动跑 `cataforge docs index`**（仅当 `docs/` 含 `.md` 文件）—— 闭合"首次 bootstrap 永远拿不到 `.doc-index.json` → doctor 的 orphan 检查永远静默跳过 → 用户从未感知到 docs-index 子系统"的链式失败模式。失败时 WARN 不阻塞 bootstrap 流程。Audit A4 + A3。
- **`upgrade apply` 末尾自动 rebuild `.doc-index.json`**（仅当文件已存在）—— 让 upgrade 的副作用包括索引刷新，避免用户手动跑 `docs index`。orphan 失败时 WARN，不回滚 upgrade。Audit A3。
- **`.pre-commit-config.yaml`** —— 三个本地钩子：(1) `scripts/sync_scaffold.py --check`（防 dogfood ↔ mirror drift）；(2) `ruff check`（防误提带 lint 错的 commit）；(3) `.github/workflows/*.yml` PyYAML safe_load 解析（防 step name 未引号冒号这类静默 workflow rejection）。`docs/contributing.md` 加 `pre-commit install` 指引段。Audit B1 + 本轮 PR-1 暴露的 workflow YAML 失败模式的防再发。
- **`src/cataforge/_assets/cataforge_scaffold/GENERATED.md`** —— 在生成镜像目录根放 banner，明确"DO NOT EDIT" + 指向 `scripts/sync_scaffold.py`。`scripts/sync_scaffold.py` 的 `TARGET_ONLY_FILES = frozenset({"GENERATED.md"})` 集合保护该文件不被双向同步覆盖；`tests/test_scaffold_sync.py::EXPECTED_ONLY_IN_SHIPPED` 同步 carve-out。Audit B2。
- **`COMMON-RULES.md` 新增 §文档加载纪律**（在 §文档引用格式 与 §通用 Anti-Patterns 之间）—— 把 5 个 AGENT.md 中重复出现的"禁止 Read 全文 + 必走 `cataforge docs load`"通用规则单点收敛。COMMON-RULES 由 platform adapter 在 deploy 时通过 `@.cataforge/rules/COMMON-RULES.md` at-mention 自动 prepend 到 CLAUDE.md，所有 sub-agent 加载即得，AGENT.md 不需要回引。Audit A7。
- **`scripts/checks/check_schema_python_parity.py` + `tests/schema/test_schema_python_parity.py`** —— 新 anti-rot 守卫（CI + pre-commit + unit），锁定 `.cataforge/schemas/{event-log,agent-result}.schema.json` 与各自 Python 镜像的 enum / required / allowed-fields 一致性。两个 schema 文件历来是文档-only（无 jsonschema-validate 调用），运行时校验由 `cataforge.core.event_log.validate_record` 和 `cataforge.hook.scripts.validate_agent_result` 中的硬编码常量承担——任一边漂移会让 validation 静默分叉。本守卫闭合该漂移面。Audit 新-3（采用 parity-guard 路线，避免引入 jsonschema 新依赖）。
- **`tests/cli/test_docs_indexer.py` + `tests/cli/test_docs_validate.py` + `tests/schema/test_schema_python_parity.py`** —— 17 个新测试覆盖：`--strict` 全量 / 增量 / 干净树矩阵、reverse-orphan 检测、`docs validate` 三种 exit 码、doctor 新 WARN/FAIL 路径、schema-Python parity 双面。

### Changed

- **`cataforge doctor` 的 docs-index 完整性检查不再静默跳过** —— `docs/.doc-index.json` 缺失但 `docs/` 含 markdown 时，emit 黄色 WARN 提示 `cataforge docs index`（非阻塞，不计入 `failed_count`）；`docs/` 真正不存在或不含 markdown 时仍静默跳过（genuinely not-applicable）。Audit A2。
- **`.cataforge/skills/doc-nav/SKILL.md`** 加"指令 4: 校验索引完整性 (validate)"段，引用 `cataforge docs validate`，与 doctor 的新 WARN 行为对齐——doctor 和 doc-nav 现在都给同一条修复指引（运行 `cataforge docs index` 重建），解决了 audit 新-4 提到的两条不一致降级路径。
- **5 个 AGENT.md（architect / tech-lead / qa-engineer / devops / ui-designer）瘦身** —— 每个文件删除 Input Contract 与 Anti-Patterns 段中"禁止一次性 Read … 全文" / "Bash 仅用于 cataforge docs load" 的通用表述（这些已迁移到 COMMON-RULES §文档加载纪律）；保留各自的**doc_id 白名单**（如 architect 的 `prd#§2.F-xxx`、devops 的 `arch#§3.API-xxx`）——这部分是真正的角色特定信息。Audit A7。
- **`tests/cli/test_doctor_anti_rot.py::test_doctor_orphan_check_skips_when_no_doc_index` 重命名为 `test_doctor_warns_when_docs_present_but_no_index`** —— 旧测试断言"silent skip"，与本轮 audit A2 的新行为冲突。新测试断言 WARN 路径 + 新增 `test_doctor_silent_when_docs_dir_has_no_markdown` 守住"genuinely empty docs/"应静默的契约。

### Fixed

- **`cataforge.docs.indexer.main` `--strict` 增量分支 no-op (audit 新-1)** —— `--doc-file` 增量更新时整段跳过 `find_orphan_docs` 全树扫描，意味着 `--strict` 在 PostToolUse 钩子 / agent 单文件回写等增量场景下永远不会失败，前条目缺失 front matter 也能溜过 gate。现在每次调用都跑全树 orphan + 反向 stale-entry 扫描；增量场景的 `--strict` 与全量行为对称。
- **`.github/workflows/test.yml` 因 step `name` 含未引号冒号导致 YAML 解析失败** —— `Anti-rot guards (6: skill count, ...)` 这一行的 `6:` 让 GitHub Actions 报 "workflow file issue" 直接拒跑（"This run likely failed because of a workflow file issue"，无任何 job log），main 已连红 3 个 PR 都是这个原因（不是 ruff、不是 pytest，是 workflow 根本没启动）。给该 name 加引号，本轮新加的 doctor step name 同时引号化；pre-commit hook 加 workflow YAML 解析检查防再发。
- **3 处 pre-existing ruff 错误**（`UP012` × 2 in `tests/cli/test_event_cmd.py` / `tests/core/test_io.py`，`I001` in `src/cataforge/core/template.py`）—— 与 workflow YAML 一起 unblock CI。这 3 处源自 #72，但因 workflow 根本未启动而被 CI 漏掉。

## [0.1.13] — 2026-04-25

二轮腐化审计闭环（PR-1 → PR-8 一线串过 26+8 = **34 条腐化**修复 + 6 个 anti-rot CI 守卫 + 1 个 weekly sweep workflow + migration_check 生命周期机制）。

### Added

- **`cataforge core/template.py`** — `render_project_state()` 抽象，把"运行时: {platform}" 的字面量模板替换从 `PlatformAdapter` 抽象基类剥离。
- **`SkillRunner.run(..., agent=)`** + `cataforge skill run --agent <name>`：EVENT-LOG `state_change` 事件按真实调用方归因，环境变量 `CATAFORGE_INVOKING_AGENT` 兜底（旧"硬编码 reviewer"行为作为最终 fallback 保留）。
- **`framework.json` 占位 `version: "0.0.0-template"`** + `Config.version` 在读时解析为运行包版本 + `bootstrap_cmd._semver_newer` 对 `0.0.0-` 前缀短路；源仓库 commit 不再随每次发版漂移版本号。
- **`migration_checks[].deprecate_after`** 字段 + doctor 在 `__version__ ≥ deprecate_after` 时 SKIP；12 条历史 check（mc-0.1.0-* / mc-0.1.5-* / mc-0.1.7-*）已标 `deprecate_after: "0.2.0"`，2 条结构性 check（mc-0.1.9-* / mc-0.1.10-event-logger-shim）保持永久启用。
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
- **`mc-0.1.5-session-context-simplified` 路径**：原 `.cataforge/hooks/session_context.py` 实物不存在 → vacuous PASS（`file_must_not_contain` 在文件缺失时默认按通过处理）；现改为 `src/cataforge/hook/scripts/session_context.py` + `allow_missing: true` + `deprecate_after: "0.2.0"`。
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

- **`dep-analysis` 与三个 Penpot Skill 的脚本路径同形 bug** — `dep-analysis/SKILL.md` 与 `tech-lead/AGENT.md` 仍指令 `python .cataforge/skills/dep-analysis/scripts/dep_analysis.py`，磁盘上无该路径（实现已移到 `cataforge.skill.builtins.dep_analysis`）；`penpot-sync` / `penpot-implement` / `penpot-review` 三个 Skill 指令 `python .cataforge/integrations/penpot/setup_penpot.py ensure`，磁盘上同样无该路径，且 `cataforge penpot` CLI 缺失 `ensure` 子命令（`cmd_ensure` 函数实现完整但未注册）。这是 v0.1.11 修复 review skill 时遗漏的同类缺陷。现 dep-analysis 改走 `cataforge skill run dep-analysis -- ...`、Penpot 改走新加的 `cataforge penpot ensure`，scaffold 镜像同步更新。

### Changed

- **`cataforge doctor` 协议脚本扫描扩展到整个 `.cataforge/` 子树** — 原正则只匹配 `python .cataforge/scripts/...`，错过 `python .cataforge/skills/<id>/scripts/*.py` 与 `python .cataforge/integrations/...` 两类路径（dep-analysis 和 Penpot bug 正好落在这两个盲区）。现匹配 `.cataforge/` 下任意 `.py` 路径；同时显式过滤含 `*` / `...` 的占位符路径与 `.cataforge/hooks/custom/` 用户扩展目录的教学示例，避免误报。
- **`cataforge doctor` Layer 1 reachability 检查改名为 Built-in skill reachability，覆盖所有内置 Skill** — 之前硬编码 `(code-review, sprint-review, doc-review)`，新增 builtin（如 dep-analysis）会自动绕过检查；现从 `SkillLoader._scan_builtins()` 动态枚举，新增内置 Skill 的可达性自动纳入门禁。
- **`SkillRunner` 事件日志开关改由 SKILL.md frontmatter 驱动** — 新增 `record-to-event-log: true` 字段，`SkillMeta.record_to_event_log` 解析并经 `_merge_builtin_fallback` 在项目覆写时自动从 builtin 继承；移除 runner 端的硬编码 `_EVENT_LOGGED_SKILLS` 常量。新增审查类 Skill 只需翻一处标志，不再需要同时改 runner 与 doctor 两份名单。
- **`SkillLoader` 用 AST 判 `if __name__ == "__main__"`** — 旧实现是 `"__main__" in text and "__name__" in text` 文本匹配，会把 docstring 偶然提及这两个 token 的 helper 模块误判为 CLI 入口、混入 `meta.scripts`；现改用 `ast.parse` + `Compare` 节点结构匹配，false-positive 收敛为零。
- **`cataforge penpot` 新增 `ensure` 子命令** — `cmd_ensure(config)` 已存在于 `cataforge.integrations.penpot` 但未挂到 click group；本次显式注册，三个 Penpot Skill 才能按文档调用。

### Added

- **migration check `mc-0.1.10-event-logger-shim`** — 守住 `event_logger.py` 必须保持 forwarder 形态（`from cataforge.cli.main import cli`）。orchestrator/tdd-engine/doc-gen 等十几处 `[EVENT]` 行依赖该 shim 的路径稳定性，以前没有任何机制阻止它被"重构掉"。
- **scaffold-sync 守卫测试** — `tests/test_scaffold_sync.py` 用 `filecmp.dircmp` 递归对比 `.cataforge/` 与 `src/cataforge/_assets/cataforge_scaffold/`，要求两边除显式白名单（`scripts/dogfood`）外字节级一致。dep-analysis 与 Penpot bug 在两份副本里同时存在，是双写无校验放大错误的直接证据；测试关掉这条退路。
- **doctor 静态扫描的回归用例** — `tests/cli/test_doctor_exit_code.py` 新增 `test_doctor_flags_missing_skill_subdir_script` / `test_doctor_flags_missing_integrations_script`，分别覆盖 `python .cataforge/skills/<id>/scripts/...` 与 `python .cataforge/integrations/...` 两个新扫描盲区的死亡情形。

### Changed

- **TDD 三阶段 subagent 的 `maxTurns` 由 50 放宽到 100** — `test-writer`（RED）/ `implementer`（GREEN）/ `refactorer`（REFACTOR）三个 AGENT.md 同步更新（含 scaffold 镜像）。50 次工具调用对略复杂的 AC 集合或多文件改动经常不够，subagent 在写完一半就被 host 截停后只能让 orchestrator 重新派发，不只是体验差，还会让 EVENT-LOG 出现"未完成的 phase"记录污染重试统计。100 次给出更充裕的预算，仍然有上限可以兜住失控的 agent。

## [0.1.11] — 2026-04-24

### Fixed

- **Layer 1 审查脚本从未真正运行** — 三个审查 Skill（`code-review` / `sprint-review` / `doc-review`）的 `SKILL.md` 向 AI 指令 `python .cataforge/skills/<id>/scripts/<script>.py`，但该路径在默认 scaffold 中不存在（脚本实为 `cataforge.skill.builtins.*` Python 模块，需通过 `-m` 调用）。AI 按字面执行必然 `FileNotFoundError`，命中 SKILL.md 定义的"脚本异常→降级 Layer 2"分支，Layer 1 质量闸从未真正运行；叠加 `SkillLoader.get_skill` 的 overshadow bug（项目级空壳 SKILL.md 屏蔽 builtin），`cataforge skill run` 也无退路（实测 `Error: Skill code-review has no executable scripts`）。现象是 `docs/reviews/` 目录长期为空、用户反馈"缺少 Layer 1 脚本工具、没有生成 code review 报告"。

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

- **`cataforge upgrade apply` 完成后提示 `cataforge deploy`** — 当 `.cataforge/.deploy-state` 存在时，apply 结尾输出 `Tip: scaffold refreshed — run \`cataforge deploy\` to propagate changes to platform deliverables (e.g. .claude/settings.json).`。之前 `upgrade apply` 只刷 `.cataforge/` scaffold，不触碰 `.claude/` 等 deploy 产物，导致用户 `pip install -U` + `upgrade apply` 之后 `.claude/settings.json` 里的 hook 注册永远落后一拍（实测场景：migration check `mc-0.1.9-detect-review-flag-registered` 在 apply 后依然 FAIL）。新提示明确引导下一步，但不隐式自动 deploy —— 显式优于隐式。
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
- **`cataforge doctor` Hook script importability 检查** — 对 `hooks.yaml` 中声明的每个内置脚本执行 `importlib.util.find_spec("cataforge.hook.scripts.<name>")`，模块缺失（如 site-packages 残留旧 stub 遮蔽 editable install）即 FAIL 并提示 `pip install -e .` 修复。这是导致 `detect_correction` 静默失效数周的失败模式的直接守卫。
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

- **`cataforge hook test` 子进程找不到 cataforge 包** — 非 site-packages 安装（editable / `pip install <path>`）下，`hook test` 通过 `subprocess.run` 调用 `python -m cataforge.hook.scripts.X` 时子进程继承不到 pytest 的 `pythonpath=["src"]`。新增 `_child_env_with_cataforge_importable` 基于 `cataforge.__file__` 反推包根并注入子进程 `PYTHONPATH`。
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
  specs, `cataforge.mcp` entry-points, and process start/stop with
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

> **STATUS UPDATE (since v0.1.5):** `upgrade {check,apply,verify,rollback}` 已实现（见 0.1.5 / 0.1.7 / 0.1.9 entries），`hook test <name>` 已实现（见 `cataforge.cli.hook_cmd`）。仅 `plugin {install,remove}` 仍为 stub。

[Unreleased]: https://github.com/lync-cyber/CataForge/compare/v0.2.0...HEAD
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
