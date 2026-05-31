# CataForge 跨平台部署评估报告

## 一、四端成熟度矩阵

| 平台 | 能力覆盖 | 降级到位度 | 验证档位 | version_tested 时效 | 总体成熟度 |
|------|---------|-----------|---------|--------------------|-----------|
| **claude-code** | high（核心 10/10 native，扩展 3/4，hooks 9/9 native，features 15/17） | high（作为降级基线，唯一全 native hook 端；存疑项仅 notify_permission） | **E2E**（`test_deploy_links_and_doctor.py` 真实 wheel install → deploy → doctor → skill link 可达性 + rename 存活；但无真实进程行为级 E2E） | `"2.1"`，已过期、无 CI 追踪 | **high** |
| **cursor** | medium（核心 8/10，web_fetch + user_question 缺失；扩展仅 browser_preview→computer；features 缺 plan_mode/multi_root/agent_memory/context_management） | medium（detect_correction/notify_permission 降级正确；但多个 native 声明未经验证，file_edit/file_write 合并产生冲突隐患） | **dry-run only**（无 `--platform cursor` E2E；仅 dry-run CI 无结构断言 + 局部 `.claude/` 隔离测试） | `"3.1"`，明显滞后；`available_models` 字面量无校验门禁 | **medium** |
| **codex** | medium（核心 10/10 但 file_read/glob/grep/web_fetch 均 shell 模拟；user_question 缺失；扩展 2/4 含独有 code_review→/review；features 含独有 realtime_voice/multi_root） | medium（5 个 degraded 判定全部正确；web_fetch→shell 是工具替换非语义等价；computer_use feature 与 browser_preview cap 路由层不可见） | **dry-run only**（`tests/e2e/` 无 codex 测试；仅 deploy --dry-run + tmp_path mock profile 单测） | `"2026.04"`，日期格式与其他端不统一；无同步校验机制 | **medium** |
| **opencode** | medium（核心 10/10 native，含 user_question→question；扩展仅 image_input；features 最少——parallel_agents/background_agents/computer_use 全 false） | **medium-low**（hook 全走 TS plugin 桥接；guard_dangerous block 语义依赖 Python spawn 成功，spawn 失败 `on('error')`→`resolve(0)` 静默放行；session.created 事件名未验证） | **dry-run only**（无 TS plugin 语法检查 / 无 agent 加载集成 / 无 hook 触发验证；CHANGELOG 自承此缺口） | `"1.3"`，无更新机制 | **medium-low** |

**矩阵总览**：claude-code 是事实上的「黄金路径」与降级基线——全 native、唯一有 E2E 闭环。其余三端在能力声明上各有特色（codex 的 code_review/realtime_voice、opencode 的 ci_cd_integration/plan_mode），但验证档位统一停留在 dry-run，与 claude-code 形成一道明显的「验证断崖」。opencode 因 hook 安全关键路径的静默放行风险，降级到位度单独低半档。

---

## 二、适配与降级缺口清单

### HIGH

**H-1 · opencode guard_dangerous 在 Python 不可达时静默放行**（security / dead-code）
证据：`_render_opencode_plugin` 生成的 TS 代码中，block hook 以 `throw new Error(...)` 拦截，`runPython` 用 `spawn` 异步执行；`child.on('error')` handler 直接 `resolve(0)`。
影响：未安装 `cataforge` 包或 spawn 失败时，**安全关键的 guard_dangerous 静默通过**，无 fallback 降级规则。`native` 标记不产出降级文件，用户在缺 Python 环境的场景下零警示——比 `degraded` 更危险。

**H-2 · cursor file_edit 与 file_write 共用 Write 工具，无冲突检测**（structure / consistency）
证据：cursor profile `file_edit: Write`、`file_write: Write` 映射同一工具名；`resolve_tools_list` 只做 null 过滤，不做冲突检测。
影响：agent 若 `disallowedTools: [file_edit]` 同时 `tools` 含 `file_write`，部署后 allowed 与 denied 同时出现 `Write`，形成静默能力丢失或意外授权。另：file_edit 的局部替换语义退化为整文件重写。

**H-3 · codex web_fetch→shell 是工具替换而非语义等价**（feasibility / error-handling）
证据：codex profile `web_fetch: shell`（OPTIONAL 白名单，conformance 仅 INFO）。
影响：依赖 web_fetch 的 agent 得到 shell，尝试 curl/wget；在 `read_only` permission mode 下可能被沙箱阻断，且不触发 native fetch 的成功/失败语义。同类降级在 cursor 是直接缺失（`web_fetch: null`），research skill 的 web-search 模式深度调研能力受损，且无 prompt_checklist 补偿。

**H-4 · 三端（cursor/codex/opencode）无行为级 E2E**（test-quality）
证据：`tests/e2e/` 全部 `--platform claude-code` bootstrap；CI `guards`/`platform dry-run` job 对三端仅跑 `deploy --dry-run`，无结构断言（通过仅意味不崩溃）。`test.yml` 注释确认 E2E 为 Linux-only。
影响：三端的 hooks 配置正确性、agent frontmatter 过滤、section-merge 在 AGENTS.md 上的行为、TS plugin 语法有效性、真实 IDE 加载——均无写盘后读回验证。CHANGELOG（#199）自承此缺口，dry-run 是缓解非消除。

**H-5 · cursor/claude-code version_tested 明显滞后且无校验门禁**（consistency）
证据：claude-code `"2.1"`、cursor `"3.1"`、codex `"2026.04"`（日期格式不统一）、opencode `"1.3"`；`check_profile_yaml_keys.py` 仅校验键结构，不校验值时效性；无任何 CI job 追踪。
影响：`available_models`（cursor 的 gpt-5.4/gemini-3-pro 等）字面量腐化后，per-agent model 路由会静默写入无效模型名到 `.cursor/agents/*.md`，Cursor 静默忽略或报错。`session_resume: false`（claude-code）相对 codex 的 `true` 存疑，可能为能力低报，导致 orchestrator 错误跳过依赖分支。

### MEDIUM

**M-1 · agent_dispatch 同步 vs 异步语义断裂（codex）**（structure）
证据：codex `dispatch.is_async: true`，两步式 spawn_agent + wait_agent；`fork_context=false` 子代理不继承父上下文。其他三端同步。
影响：orchestrator 串行 Phase Transition Protocol 假设同步阻塞；codex 上若不特判会在子代理完成前继续推进。COMMON-RULES.md / Phase 状态须在 dispatch prompt 显式重传（override 已注明，但 orchestrator 省略即失上下文）。

**M-2 · user_question 缺失使 needs_input 状态无法表达（cursor + codex）**（completeness）
证据：cursor/codex 均 `user_question: null`；codex dispatch-prompt override 注明「如需输入返回 blocked」。
影响：`pre_dev`/`post_sprint`/`pre_deploy` 三个 MANUAL_REVIEW_CHECKPOINTS 退化为「阻断等待重启」而非「会话内交互确认」。cursor 的 override 未说明此降级，存在文档不对称。

**M-3 · TS plugin 层缺 matcher_agent_id 前置过滤（opencode/cursor）**（performance）
证据：hooks.yaml v2 为 detect_review_flag 声明 `matcher_agent_id: [reviewer]`；bridge.py / `_render_opencode_plugin` 均不携带该过滤到平台配置层，依赖 Python `matches_script_filters()` 运行时二次过滤。
影响：每次 agent_dispatch PostToolUse 都 spawn detect_review_flag.py（非仅 reviewer），功能不丢但性能冗余；`native` 标签掩盖「平台配置层无过滤」事实。

**M-4 · session_context native 声明缺乏验证保障（codex + opencode）**（consistency）
证据：codex SessionStart→SessionStart、opencode SessionStart→`session.created`（opencode 官方事件命名约定接近 `tool.execute.before/after`，session 生命周期事件文档覆盖不完整，`session.created` 合法性未确认）；叠加已确认 finding——`mc-0.1.5-session-context-simplified` 指向腐化路径 `src/cataforge/hook/scripts/session_context.py`（真实文件在 `runtime/hook/scripts/`）且 `allow_missing: true` 永远静默通过。
影响：若 opencode 事件名不存在，handler 永不触发，session_context 静默空转，`native` 不产降级告警；空转守卫无法兜底检测。

**M-5 · computer_use feature 与 browser_preview cap 路由层不可见（codex）**（consistency）
证据：codex `features.computer_use: true` 但 `extended_capabilities.browser_preview: null`。`resolve_tool_name("browser_preview")` 静默返回 None。
影响：若 codex computer_use 可承接浏览器预览，框架路由层看不到该能力，无报错无降级提示。

**M-6 · codex 特有字段双重声明源（codex）**（duplication / consistency）
证据：`codex.py` 的 `_md_to_toml` 硬编码透传列表 `("model", "model_reasoning_effort", "sandbox_mode", "nickname_candidates")`，与 profile `agent_config.supported_fields` 独立两处来源；且这三个字段不在 `AGENT_FRONTMATTER_FIELDS`（types.py 17 字段规范枚举）中。
影响：profile supported_fields 更新后 `_md_to_toml` 硬编码不同步，造成声明与实现分离。

**M-7 · permissionMode 字段跨端丢弃无降级策略**（security）
证据：cursor/codex/opencode 的 profile 均不含 permissionMode 字段，translator 静默丢弃；无 prompt_checklist / rules_injection 告知 agent。
影响：`auto`/`bypassPermissions` 等高权限声明在三端以平台默认权限执行，安全面扩大且行为不可预测，无任何检测。

**M-8 · claude-code notify_permission native 与降级模板语义矛盾**（consistency）
证据：claude-code 标 `notify_permission: native`，但 hooks.yaml `degradation_templates.notify_permission` 策略为 `skip` 并注「通知为非关键」；其余三端均标 degraded。
影响：四端唯一标 native，但脚本成功只确保 Python 层发出通知，无法验证 Notification 事件在所有 OS/版本可靠触发；声明与降级模板自相矛盾。

**M-9 · skills 字段跨端降级路径不一致**（completeness）
证据：cursor 有 `target_dir: .claude/skills` 但注入依赖目录存在；codex/opencode `needs_deploy: false` 使 skill 完全不部署，AGENT.md 的 `skills:` 字段仍被 translator 处理后丢弃。
影响：skill 引用无声消失，子代理 skill 上下文断裂，无 fallback 提示。

**M-10 · browser_preview 依赖 MCP 但无可达性门禁（claude-code）**（feasibility）
证据：claude-code `browser_preview → preview_start`（Claude Preview MCP）；conformance/deploy 均不验证 MCP 是否连接，extended_conformance 仅 INFO 不 WARN。
影响：用户未启用该 MCP 时 browser_preview 实际不可用，部署不阻塞，无运行时「MCP 可达性→能力有效性」门禁。

**M-11 · deploy_rules 目标路径隐式推导**（structure / coupling）
证据：`deploy_rules()` 从 `Path(scan_dirs[0]).parent / "rules"` 推导目标目录，依赖约定非显式声明，无校验守卫。
影响：四端当前满足约定，但非标准 `scan_dirs[0]`（如 `.cursor/agents/custom`）会把规则静默写到错位置。

**M-12 · 孤儿 patch 文件静默通过（override #199）**（error-handling）
证据：`resolver._materialize` 中 `<name>.patch.md` 无对应 base 时，`files.get(base_rel, b"")` 返回空，`apply_section_patch("")` 走 `if not base.strip(): return patch` 分支直接写出 patch 内容；无守卫检测 patch 是否有 base。
影响：拼错的 patch 名（`orchestrater.patch.md`）静默创建意外 agent 文件并部署到 IDE。

**M-13 · platform-audit 从未被自动触发**（test-quality / dead-code）
证据：全量 grep 确认 `.github/workflows/` 五个 workflow、`hooks.yaml`、16 条 migration_checks 均无 platform-audit 引用；SKILL.md「建议每月一次」仅为 prose。对比 framework-review 在 CI `guards` job 有 `cataforge skill run framework-review -- all` 强制执行。
影响：profile.yaml 时效性零自动保障；同为维护类健康审查，platform-audit 与 framework-review 调度优先级不对称。

**M-14 · agent_dispatch 等 native hook 三端未经验证（cursor）**（test-quality）
证据：log_agent_dispatch/validate_agent_result/lint_format 在 codex 为 degraded 但 cursor 标 native；架构上 PostToolUse→postToolUse + Task 映射逻辑成立，但无 E2E。
影响：未经验证的 native 声明，行为正确性仅靠 dry-run snapshot（无断言）。

### LOW

**L-1 · claude-code reads_claude_md: false 与真实行为语义相反**（consistency）— profile 字段在当前实现被 targets 列表覆盖，不触发功能错误，但后续维护者看到 false 会误判。

**L-2 · opencode matcher_map: {} 致 TS 层无工具名前置过滤**（performance）— 每次工具调用都 spawn Python，与 claude-code 原生事件前过滤存在语义差异，有意降低性能的设计。

**L-3 · image_input native 无测试覆盖（opencode/codex/claude-code）**（test-quality）— 各端 image_input 声明 native，但单测均不测 extended_capabilities，conformance 仅 INFO。

**L-4 · cursor worktree feature 与 frontmatter 不一致**（consistency）— `features.worktree_isolation: true` 但 `supported_fields` 不含 `isolation`，`isolation: worktree` 部署时被丢弃，无法通过 frontmatter 激活，无降级说明。

**L-5 · agent_teams: true 仅实验性（claude-code）**（consistency）— 附注 `experimental — CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`，`supports_feature("agent_teams")` 返回 true 但无环境变量时不可用，依赖该布尔的 orchestrator 分支在标准安装走错路径。

**L-6 · 平台矩阵文档 native 来源表述不准确**（convention）— `docs/reference/platform-capability-matrix.md` 称 notify_done/session_context 四端 native，实为「不在 degradation 表即隐式 native」的默认值，文档措辞误导维护者以为已明确测试。

---

## 三、改进路径

整份评估暴露的**根本不对称**是：claude-code 有 E2E 闭环，其余三端停在 dry-run。降级声明系统化（每个 profile 都有 degradation 字段 + OPTIONAL 白名单区分 INFO/WARN），但「声明正确」与「行为正确」之间隔着一道无人验证的鸿沟——多个 `native` 标签实为「架构逻辑成立但从未在真实 IDE 触发过」。下面优先论证如何把三端验证拉到 claude-code 同档，再附两条结构性补强。

### 核心议题：把 cursor/codex/opencode 验证拉到 claude-code 同档

**前置共识**：「同档」不必等于「在真实 IDE 进程里端到端跑通」。claude-code 现有 E2E 本身也未启动真实进程（H-2 类缺口同样存在）。真正可达的「同档」是**artifact 行为级验证**——deploy 写盘后读回、断言生成产物的结构与语义正确性、且对生成的可执行/可解析产物（TS plugin、TOML、hooks.json）做语法级校验。

**选项 A：Artifact 读回断言矩阵（在现有 dry-run job 升级为真实 deploy + 结构断言）**
- 做法：把 CI `guards` job 的三端 `deploy --dry-run` 替换/补充为真实写盘 deploy 到临时目录，复用 claude-code 侧 `test_deploy_links_and_doctor.py` 的模式，对每端断言：(1) agent frontmatter 字段过滤正确（cursor 9 / codex 6 / opencode 4 字段）；(2) hooks 产物结构合规（codex `.codex/hooks.json` 的 entry_type、opencode `.opencode/plugins/*.ts` 能被 `node --check`/`tsc --noEmit` 解析、cursor `.cursor/hooks.json`）；(3) section-merge 在 AGENTS.md 上的实际合并结果；(4) override + section patch 写盘内容（已有 `test_override_deploy.py` 单测，提升到 deploy 全流程）。
- 成本/复杂度：**中等，单点扩展为主**——大部分断言逻辑可从 claude-code E2E 与现有 `tests/deploy/` 单测迁移；需新写三端各自的产物断言（涉多文件，但无新依赖）；opencode 的 TS 语法校验需 CI 装 node（已有前端工具链时近乎零成本）。
- 直接消解：H-4（行为级 E2E 缺失）、H-2（cursor Write 冲突可在断言中捕获）、M-12（孤儿 patch 在写盘断言中暴露）、M-14（cursor native hook 产物正确性）、部分 L-3。
- 不消解：真实 IDE 加载行为、hook 事件真实触发（这部分 claude-code 自己也没有，不是「拉到同档」的范畴）。

**选项 B：Conformance 守卫前移 + profile 时效门禁（用静态强校验替代部分行为验证）**
- 做法：(1) 把 platform-audit 从 prose 建议升级为 CI 强制步骤，对齐 framework-review 的 `cataforge skill run` 模式（消解 M-13 的调度不对称）；(2) 新增 `check_profile_version_tested.py` 纳入 anti-rot weekly sweep——`version_tested` 距当前日期超过 N 天即 WARN（消解 H-5）；(3) 扩展 conformance checker：把当前仅 INFO 的几类升级为 WARN/FAIL——工具替换型映射（web_fetch→shell，H-3）发 WARN、feature 与 cap 路由不一致（computer_use vs browser_preview，M-5）发 WARN、`_md_to_toml` 硬编码列表与 supported_fields 一致性校验（M-6）。
- 成本/复杂度：**低-中，纯新增守卫脚本**——不触碰适配器源码，符合「数据驱动 + 守卫」的既有架构风格；每条守卫单点改动；不需要 node/真实 deploy。
- 直接消解：H-5、M-5、M-6、M-13，以及 H-1/H-3/M-7/M-8 的「声明矛盾可被静态检测」部分。
- 局限：静态守卫验证「声明自洽」，不验证「运行时行为」——guard_dangerous 静默放行（H-1）这类需要执行路径才能暴露的缺陷，守卫只能检测到「声明为 native 但策略矛盾」，无法证明 spawn 失败路径被正确处理。

**选项 C（最小增量兜底）：仅修高危静默放行 + 降级补偿文本**
- 做法：(1) 修 H-1——opencode TS plugin 的 `on('error')` 改为对 block hook `reject`/`throw`（spawn 失败时拒绝放行）而非 `resolve(0)`，并产出降级规则文件；(2) 给 cursor/codex 补 web_fetch 缺失的 prompt_checklist 降级提示（H-3 的 cursor 侧、M-2 的 cursor 文档不对称）；(3) permissionMode 跨端丢弃补 rules_injection 告知（M-7）。
- 成本/复杂度：**低，单点改动**——但只堵高危漏洞，不改变「三端无验证」的结构性现状。

**推荐倾向：B 作为底座先行，A 作为目标态分阶段补齐，C 中的 H-1 修复无条件优先。**

理由：
1. **H-1 必须立即修**，与选哪条路径无关——安全关键 hook 静默放行是 release blocker 级别，且修复是单点改动（一行 `resolve(0)` → 拒绝语义 + 降级文件）。
2. **B 性价比最高、风险最低**：纯守卫脚本，完全贴合 CataForge「profile 数据驱动 + check 脚本守卫 + anti-rot sweep」的既有范式（framework-review 已是先例），不引入真实 IDE/node 依赖，能立刻消解一批 consistency/声明类缺口（H-5、M-5、M-6、M-13），且把 platform-audit 与 framework-review 的调度优先级对齐——这是用最小结构改动换取「profile 不再静默腐化」的保障。
3. **A 是真正把验证档位从 dry-run 提到「artifact 行为级」的唯一路径**，但成本更高（三端各写产物断言 + opencode 引入 node 语法校验 + CI 时长增加），适合在 B 落地后分平台增量推进——优先级排序建议 opencode（H-1 同源、TS 语法校验收益最大）> codex（TOML/hooks.json 结构 + 异步 dispatch 语义）> cursor（Write 冲突 + section-merge）。
4. **不推荐 C 单独使用**：它只是止血，不改变结构性验证缺口；但其 H-1 子项应剥离出来无条件先做。

落地后，四端成熟度矩阵的「验证档位」列可从「cursor/codex/opencode = dry-run only」推进到「artifact 行为级」，与 claude-code 拉平（claude-code 自身的真实进程 E2E 缺口是另一议题，对四端一视同仁，不影响「同档」判定）。

---

**报告涉及的关键证据文件（绝对路径）**：
- `C:\Users\huanc\Work\GitRepo\CataForge\.cataforge\platforms\<id>\profile.yaml`（四端能力/降级/version_tested 声明）
- `C:\Users\huanc\Work\GitRepo\CataForge\.cataforge\hooks\hooks.yaml`（hook degradation_templates / v2 matcher_agent_id）
- `C:\Users\huanc\Work\GitRepo\CataForge\.cataforge\framework.json`（mc-0.1.5 腐化迁移检查 / migration_checks）
- `C:\Users\huanc\Work\GitRepo\CataForge\src\cataforge\core\types.py`（CAPABILITY_IDS / EXTENDED / AGENT_FRONTMATTER_FIELDS / PLATFORM_FEATURES）
- `C:\Users\huanc\Work\GitRepo\CataForge\src\cataforge\runtime\deploy\`（deployer / resolver / section_merge / section_patch）
- `C:\Users\huanc\Work\GitRepo\CataForge\src\cataforge\adapter\platform\opencode.py`（`_render_opencode_plugin` 的 spawn `on('error')` 静默放行）
- `C:\Users\huanc\Work\GitRepo\CataForge\src\cataforge\adapter\platform\codex.py`（`_md_to_toml` 硬编码透传列表）
- `C:\Users\huanc\Work\GitRepo\CataForge\tests\e2e\`（仅 claude-code bootstrap；三端无 E2E）
- `C:\Users\huanc\Work\GitRepo\CataForge\.github\workflows\test.yml` / `anti-rot.yml`（dry-run 矩阵 / 缺 platform-audit 触发）
- `C:\Users\huanc\Work\GitRepo\CataForge\docs\reference\platform-capability-matrix.md`（native 来源表述）
