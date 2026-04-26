# Changelog

All notable changes to CataForge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/lync-cyber/CataForge/compare/v0.1.14...HEAD
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
