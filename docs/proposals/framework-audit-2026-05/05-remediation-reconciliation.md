# 纯净基点修复对账（迭代任务 1）

本文件是对 [`01-implementation-review.md`](01-implementation-review.md) / [`02-platform-deployment-eval.md`](02-platform-deployment-eval.md) / [`03-walkthrough-first-run.md`](03-walkthrough-first-run.md) 三份审查报告逐条 finding 的**核实 + 处置对账**。方法学：对当前 HEAD 派独立怀疑者并行复核每条 finding 的证据是否仍成立（confirmed / already-fixed / rejected / severity-shift / 需维护者决策），再对 confirmed 项做「最小正确修复 + 回归测试 + 全套门禁」纵切。报告里的「建议」是输入假设，多处经复核被修正（见 §决策记录）。

裁定枚举：**fixed**（已核实并修复，附回归测试）/ **already-fixed**（核实时已不成立，空操作）/ **rejected**（附驳回证据）/ **deferred**（移交任务 2，附理由）。

## 门禁结果（DoD）

| 门禁 | 结果 |
|------|------|
| `python scripts/checks/run_local.py` | ✅ 10 checks passed |
| `pytest`（全量） | ✅ 1679 passed, 12 skipped |
| `cataforge doctor` | ✅ all checks passed |
| `cataforge skill run framework-review -- all` | ✅ 0 FAIL / 0 WARN / 1 INFO |
| dogfood `cataforge deploy` 部署面 | ✅ `context` + `framework-walkthrough` 部署，无陈旧 `doc-*`，与源一致 |

---

## 报告 01 · 实现审查（R-001~R-029）

| ID | severity | 裁定 | 处置摘要 |
|----|----------|------|---------|
| R-001 | MEDIUM | fixed | `context_cmd` finalize/reconcile 改走 `CataforgeError`+`exit_code`（finalize 2→1，reconcile 3），统一 banner，不再绕过 `CataforgeGroup`。 |
| R-002 | MEDIUM | fixed | 新增 `kg/_options.py` 的 `db_path_option`/`db_path_ro_option` 工厂；只读 kg 子命令（query/trace/validate）`exists=` 归一。 |
| R-003 | MEDIUM | fixed | 抽出 `indexer.format_stale_deps_warning`，`docs validate` 与 `doctor` 共用；stale_deps 现两处都显示。 |
| R-004 | LOW | fixed | 移除 `setup --check` 别名与 `deploy --check` hidden 别名（逾期废弃跟进）。 |
| R-005 | LOW | fixed（随 R-003） | `check_docs_validate` 的 gating 计数确认不含 stale_deps（WARN 不计 FAIL）；返回结构整形（task 2）留待。 |
| R-006 | HIGH→**降为低影响** | fixed | `SparqlRegistry.has()` 恒真且与 `get()` 的 generic 回落语义重叠——属冗余死代码而非「未知类型逃逸」（`get()` 设计上对任意类回落 generic）。删除 `has()` 与 `render.py` 的早退守卫。**严重度纠偏见 §决策记录**。 |
| R-007 | MEDIUM | fixed | `_restore_ghosts` 不再 `contextlib.suppress` 静默吞错，改为返回失败清单并并入 `stats.errors`，混合态对调用方可见。 |
| R-008 | MEDIUM | fixed | 删除零调用方的 `KGConfig.query_timeout` / `max_transaction_retries`（含 `_dispatch` 读入与 `test_config` 断言）。 |
| R-009 | MEDIUM | fixed | 为 `ChangeRequest/Phase/SprintReviewIssue/ReviewReport` 4 个 ingest 类补显式 export doc_type（不再静默落 misc/），并加 ingest⊆export 的 parity 守卫测试。 |
| R-010 | LOW | fixed | `_triple_exists` 三个 IRI 入口补 `assert_safe_iri`，与 `_content_hash_matches` 一致。 |
| R-011 | LOW | fixed | `TransactionContext.commit()` 在 adds 阶段异常时回补已删 quad（幂等 re-add），不再静默丢数据。 |
| R-012 | HIGH | fixed（与 R-020 收敛为删除） | 见 R-020。 |
| R-013 | HIGH | fixed | COMMON-RULES §框架配置常量表补齐 6 个可发现性断裂常量（EVENT_LOG_DRIFT_MIN_EVENTS / ANTI_PATTERN_MIN_COUNT_SKILL/AGENT / AGENT_MODEL_DEFAULTS / AGENT_MODEL_TIER_HEAVY_WHITELIST / SKILL_RUNNER_TIMEOUT_DEFAULT_SECS）；另 2 个（PRE_DEPLOY_DEMO_*）按 R-014 删除而非补录。加 framework.json↔COMMON-RULES 全等 parity 测试。 |
| R-014 | MEDIUM | fixed | 删除零实现零调用方的 `PRE_DEPLOY_DEMO_REQUIRED` / `PRE_DEPLOY_DEMO_MIN_ACS`。 |
| R-015 | MEDIUM | fixed | `SkillRunner` 在 `timeout=None` 时从 framework.json `SKILL_RUNNER_TIMEOUT_DEFAULT_SECS` 读取（缺省回落 300），docstring 与实现对齐。 |
| R-016 | MEDIUM | fixed | framework.json 两条永久活跃 migration_check 描述的 `doc-gen` 改 `context`。 |
| R-017 | LOW | fixed | 5 条 migration_check 描述重写为「当前强制条件」表述，去除「已废弃/取代/已删除/放宽至/无过渡期」变更叙事（framework.json 不在 design-residue 守卫扫描面，属规约精神收口）。 |
| R-018 | HIGH | fixed（操作型） | fresh clone 无部署产物（`.claude/skills/` 空、manifest gitignored）。`cataforge deploy` 后部署面与源一致：`context`/`framework-walkthrough` 已部署、无陈旧 `doc-*`。无源码改动；产物 gitignored 不入版本控制。 |
| R-019 | MEDIUM | fixed | 删除零导入的死 `PermissionMode` enum；platform-audit 文档中对该符号的引用改指 profile `permissions.modes` 概念（保持语言中立、无残留）。 |
| R-020 | MEDIUM | fixed | 删除 `mc-0.1.5-session-context-simplified`——`deprecate_after:0.2.0` 已逾期、`path` 指向重构后已不存在的 `src/cataforge/hook/scripts/session_context.py`、`allow_missing:true` 使其结构性空转。与 R-012「改 path」**收敛为删除**（见 §决策记录）。 |
| R-021 | MEDIUM | **partial-fix + defer** | 该 finding 指向的活跃漂移（mc-0.1.5 错误路径）已由 R-020 删除消除；并加 `test_framework_constants_ssot` 的「migration_check 的 `src/` 路径必须真实存在」测试级守卫（dogfood/CI 内生效，不触碰下游运行时）。完整的 B9 三维度结构审查（path/allow_missing/deprecate_after 全量遍历）**deferred**——见 §决策记录（运行时强制会误伤下游 site-packages 安装）。 |
| R-022 | HIGH | fixed | `testing` 补入 B3 `builtin_map`，其 SKILL.md delegation 声明「不一致即 FAIL」现真正参与对账。 |
| R-023 | MEDIUM | deferred | doctor `deploy_integrity` 不读 `.deploy-manifest.json`，反向「source-removed 孤儿」检出是新增能力（报告自身归为「新增能力」），且 fresh clone 不可复现。移交任务 2。 |
| R-024 | HIGH | fixed（报告前提已纠偏） | 报告设想「doc-review SKILL.md 已迁入 Python 包、用 importlib 读包内 SKILL.md」——**核实为假**：90be4fd 把 doc-review SKILL.md 并入 context skill 后包内并无 SKILL.md。改为：B3 `builtin_map` 移除 doc-review（其 prose 现由 context review 引用 delegation 到 manifest）+ 修正 `doc_review/__init__` 仍指向已删 `.cataforge/skills/doc-review/SKILL.md` 的陈旧 docstring；加「builtin_map 每项必须有真实 SKILL.md」测试守住根因。 |
| R-025 | MEDIUM | fixed | B4 `CONSTANT_LITERALS` 由静态硬编码副本改为 `build_constant_literals(root)` 从 framework.json 动态生成正则（复用 `_framework_data`）；改 framework.json 常量值即重定向 B4。 |
| R-026 | LOW | fixed | `MCPRegistry._is_trusted_command` 对含 `..` 段的相对路径 reject（PurePosix+PureWindows parts）。 |
| R-027 | LOW | fixed | `manifest.save_manifest` 改用既有 `cataforge.utils.atomic_write.atomic_write_text`（tmp→os.replace）。 |
| R-028 | LOW | **rejected** | `.scaffold-manifest.json` gitignored 且 fresh clone 不存在，bundled scaffold 源已是最新（29 个 context 条目、0 个 doc-gen）。非 tracked-repo 缺陷，`upgrade --force` 即重生成。 |
| R-029 | LOW | fixed（折叠入 R-022） | testing 进 B3 builtin_map 后其 CHECKS_MANIFEST 已被覆盖；独立的 doctor CHECKS_MANIFEST 检查属冗余守卫，按 anti-rot 取向不新增。 |

---

## 报告 02 · 跨平台部署（缺陷/一致性可点修部分）

| ID | severity | 裁定 | 处置摘要 |
|----|----------|------|---------|
| H-1 | HIGH（release-blocker） | fixed | opencode 生成的 TS plugin：block hook 失败路径（spawn error / null / 非 0 退出）由 `resolve(0)` 改为**fail-closed**（block 哨兵 2 + dispatch 对非 0 一律 throw），缺 python/cataforge 不再静默放行 guard_dangerous。 |
| H-2 | HIGH | fixed | cursor `file_edit`/`file_write` 同映射 `Write`；translator 翻译 allow/deny 后检测同名碰撞并发 WARN，不再同名静默两挂。 |
| M-6 | MEDIUM | fixed | codex `_md_to_toml` 透传字段由硬编码元组改为从 profile `agent_config.supported_fields` 派生（单一事实来源）。 |
| M-7 | MEDIUM | fixed | translator 丢弃 `permissionMode` 等安全敏感字段时进 warnings collector 并由 deploy 输出 WARN，不再静默丢权限声明。 |
| M-12 | MEDIUM | fixed | resolver `_materialize` 对无 base 的孤儿 `*.patch.md` 发 WARN 并跳过，拼错的 patch 名不再静默落为真 agent 文件。 |
| H-3 / H-4 / H-5 | HIGH | deferred | web_fetch→shell 语义降级、三端行为级 E2E、version_tested 时效门——均属验证档位升档/新增守卫，task 2。 |
| M-1/M-3/M-4/M-5/M-8/M-9/M-10/M-11/M-13/M-14 | MEDIUM | deferred | 异步 dispatch 语义、TS 前置过滤、事件名真测、feature↔cap 路由一致性检查、native↔降级模板一致性检查、skill 字段降级提示、MCP 可达性门、deploy_rules 路径守卫、platform-audit CI 触发、cursor native hook E2E——均为新增守卫/校验或验证升档（task 2）。 |
| L-1~L-6 | LOW | deferred | profile 语义反转/实验位/文档措辞/性能权衡等，属验证升档或文档增强（task 2）。 |

---

## 报告 03 · agile-lite 端到端走查

| ID | severity | 裁定 | 处置摘要 |
|----|----------|------|---------|
| W-001 / W-002 / W-003 | HIGH×3 | **escalated（待维护者决策）** | agile-lite × KG-active 下 lite 文档系统性 FAIL doc-review，涉「lite 文档如何通过 doc-review/KG 覆盖门」的产品方向（报告 03 已标 W-003「牵动演进策略」）。按任务 §四模糊地带处置上抛维护者做选择题，未擅自实施。详见 §决策记录。 |
| W-004 | MEDIUM | deferred | `cataforge phase status` 是新 CLI 子命令（task 2）。 |
| W-005 | LOW | fixed | code-review 入口对 `-h`/`--help` 打印 usage 并 exit 0，与 doc-review 对齐。 |
| W-006 | LOW | fixed | `arch-lite.md` 技术栈示例 `{如 FastAPI}` 改语言中立 `{如 Web 框架}`。 |
| R-S1 | HIGH | fixed | doctor `_scan_fs_entity_ids` 删除「有 frontmatter `id` 即只取文档级 id」短路，改为恒扫 item 级 id；文档级 frontmatter id（importer 从不发 `cf:entity_id`）不再被当作必需实体。happy-path KG-active 项目不再恒 FAIL。`_extract_frontmatter_id` 随之删除。 |
| R-S2 | MEDIUM | already-fixed | 全局 `--project-dir` 透传已于本审查分支落地（见审查 README）。 |
| R-S3 | LOW | fixed | `setup` 在空 cwd 不再静默向上附着父项目；以 `--project-dir` 显式选择父根，否则就地初始化。 |
| R-S4 | LOW | fixed | skill-run hook 对入参错误 `exit 2` 用区分性 detail（"Layer 1 bad arguments"）/状态，不再误记为 "unreachable"。 |
| P-001~P-004 / P-S1 | — | deferred | 走查 skill 自身的流程/rubric 改进（含 run-id 唯一性）属 framework-walkthrough 能力增强（task 2）。 |

---

## 决策记录（非平凡选择）

**互斥收敛 · R-012 vs R-020（改 path / 删除）→ 删除。** 该 migration_check `deprecate_after:0.2.0` 已逾期（当前 0.6.0）、doctor 对其恒 SKIP，重新指向正确 path 等于复活一个使命窗口已关闭的 check；且真实文件 `runtime/hook/scripts/session_context.py` 经核实已干净（无禁用模式）。删除是单点无副作用，重评条件：若要重新约束 session_context 行为，应另建 path 正确且 `allow_missing:false` 的新 check。

**互斥收敛 · R-013 vs R-014（补录 / 删除 PRE_DEPLOY_DEMO_*）→ 删除。** 二者经 grep 核实零实现零调用方（仅 framework.json 定义 + CHANGELOG），属死配置；删除优先于补录进 SSOT 表。其余 6 个有真实调用方的常量补录 COMMON-RULES。

**严重度纠偏 · R-006（HIGH→低影响）。** 报告称「未知 entity_type 不再被早退拦截」，但 `SparqlRegistry.get()` 对任意类回落 generic 模板（`compile_to_markdown` 据此「每类都能渲染」），故「拦截未知类型」与 get() 的 generic 回落语义自相矛盾——`has()` 恒真实为与设计一致的冗余，而非安全/正确性漏洞。报告建议的一行改法（`entity_type.lower() in _templates or GENERIC in _templates`）因 generic 恒在仍恒真，属空操作。正确修复是删除该冗余守卫对（dead-code 收口）。

**报告前提纠偏 · R-024。** 报告建议「B3 用 `importlib.resources` 读 builtin 包内 SKILL.md」，前提是 doc-review 的 SKILL.md 已迁入 `builtins/doc_review/`。核实为假：90be4fd 将 doc-review 的 146 行 SKILL.md 并入 context skill（`references/review.md`，delegation 到 CHECKS_MANIFEST），包内并无 SKILL.md。故采最小正确修复：从 B3 builtin_map 移除 doc-review（无独立 prose 面可对账）+ 修正陈旧 docstring + 加 builtin_map 完整性测试守住根因（任何 map 项缺真实 SKILL.md 即测试 FAIL）。此修复尊重既定架构（doc-review prose 已并入 context），不逆转合并。

**R-021 拆分（task1 守卫 / task2 能力）。** 报告与怀疑者均指出：mc-0.1.5 的活跃漂移是死守卫（task1），已由 R-020 删除消除，并加测试级路径存在性守卫。但「allow_missing + 文件缺失即 FAIL」的**运行时**守卫会误伤下游 site-packages 安装（彼处 `src/cataforge/...` 本就不在项目根，allow_missing 正是为此设计）；正确的结构审查需区分 editable/downstream，属新增能力（B9），deferred 至 task 2。

**R-009 映射选择。** 4 个 meta 实体（ChangeRequest/Phase/SprintReviewIssue/ReviewReport）无对应 SDLC doc_type，按最近承载阶段就近映射（prd/arch/dev-plan/test-report），核心保护是 ingest⊆export 的 parity 守卫——杜绝未来任何 ingest 类静默落 misc/。若这些 meta 实体将来获得专属 doc_type，可重评映射目标。

**W-001/002/003 上抛维护者。** 三条同指一个产品决策：agile-lite 的 lite 文档在 KG-active 下如何通过 doc-review。候选方向风险/语义差异实质牵动演进（lite 模板补字段会「让 lite 不再 lite」；doc-review 放宽/`-lite` 类型注册/KG 覆盖降 WARN 各有取舍），按任务纪律不擅自猜测，已以选择题形式上抛。

---

## 遗留项（移交任务 2）

- **自审工具新增能力**：R-021 完整 B9（migration_checks 三维结构审查，需 editable/downstream 区分）、R-023（doctor 读 manifest 做 source-removed 孤儿反向检出）。
- **平台验证升档**：H-3/H-4/H-5 与 M-1/M-3/M-4/M-5/M-8~M-14、L-1~L-6——三端 artifact 行为级 E2E、conformance 守卫前移、version_tested 时效门、platform-audit CI 触发等（报告 02 §三 选项 A/B）。
- **走查能力增强**：W-004（`cataforge phase status` 新 CLI）、P-001~P-004 / P-S1（framework-walkthrough 沙盒隔离 + run-id 唯一性 + rubric 硬门）。
- **agile-lite × KG-active 契约**：W-001/002/003 待维护者方向决策后实施。

## 附 · 修复期间的增量观察（非报告 finding，未处置）

- `cataforge deploy` / `setup` 渲染 claude-code 指令文件时会以 scaffold 模板**整体覆盖** dogfood 仓自身精简版 `CLAUDE.md`（并改写 tracked `.claude/settings.json`）。本轮验证部署面后已还原这两个 tracked 文件、未纳入提交。该「部署覆盖 curated 指令文件」行为属既有机制，建议任务 2 评估（部署对已存在 curated 指令文件应 preserve / section-merge 而非整体覆盖）。
