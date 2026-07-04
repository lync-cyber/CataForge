# 实施计划：框架元资产审计修复（6 批 FRAMEWORK-REVIEW 整合）

> 状态：已实施。P1–P7 全部落地（按依赖序多 PR），P0 决策门（§0）与 8 项目标值均达成。以各 PR git 历史为准，本文余下为历史设计记录。
> 范围：`.cataforge/{rules,agents,skills}/**`、`src/cataforge/{core,runtime/skill/builtins}/**`、`scripts/checks/**`、`docs/reference/**`、`.claude/**` 镜像、`.cataforge/framework.json` 常量注册。
> 证据源：`docs/reviews/framework/FRAMEWORK-REVIEW-{foundation,phase-agents,core-skills,meta-skills,support-code,references}-20260627-r1.md`（6 批，每条 finding 锚定 file:line）+ `AUDIT-LEDGER.md`。
> 交付边界：本文给出架构决策、去重问题清单、P0 决策结论、文件级修复步骤、依赖序与验收标准；实现以各 PR 的 git 历史为准。阶段=依赖层，非时间档，无工时估算。

---

## 0. P0 决策门（已闭）

8 项开放决策已关闭：5 项由代码证据锁定，3 项经用户拍板。后续步骤的目标值据此固定。

| # | 关联 | 决议 | 依据 |
|---|------|------|------|
| Q1 | A4 拆分阈值 | **保留分层 + 改因果**：250 拆分 / 200 mid-progress 各司其职（200-250 由 mid-progress 增量落盘处理，>250 才拆分以保任务粒度单一）；两值注册为常量；删除「拆分为避免 mid-progress」的错误因果 | 用户拍板；两机制职责不重叠，行为零变更 |
| Q2 | A2 cascade 阈值 | **统一为 ≥2**：cascade 引用 §needs_revision 计数规范单一定义 | `ORCHESTRATOR-PROTOCOLS.md:444-447`/`:130` 通用 ≥2，唯 cascade `:406` ≥3，是"收紧自 N≥3"未传导的漏改 |
| Q3 | B1 死 task_type | **从 agent-dispatch 枚举删 retrospective/skill-improvement/apply-learnings**；CLI `--task-type` 面保留 | `META-PROTOCOLS:161` retrospective inline、`:175` 仅 CLI fallback；skill-improvement/apply-learnings 经用户审批+commit，无 dispatch 路径 |
| Q4 | B2 sprint-review lite | **删 lite 档行** | Sprint Review Protocol `:365-391` 仅"跳过 / 完整审查"两路径，无 lite 入口 |
| Q5 | B3 triage 路径 | **注册进 §报告 Front Matter 约定表 + `status: triage-draft`→`draft` + 写明真实消费方** | `META-PROTOCOLS:122/:168` reflector 消费 CORRECTIONS-LOG/EVENT-LOG，不扫 triage/ |
| Q6 | H1 reflector tier | **升 `standard`(→sonnet)** | 综合/归因/生成属推理密集；本仓全局策略禁 Haiku，light→haiku 双重不当 |
| Q7 | A7 consumers 字段 | **改规则**：COMMON-RULES 最小字段集补 `consumers`（含例外 research/changelog） | `checker.py:138` 已豁免 research/changelog，全部真实报告已满足 |
| Q8 | K2 守卫扫描范围 | **docs/reference/ 纳入三守卫 SCAN_GLOBS**；守卫 rationale 扩写为"含长期 repo 文档"；存量残留清理 | 用户拍板；`kg-verified-behaviors.md` 等已实际腐化 |

**残留 SUSPECTED（不据此改动）**：`B6-R-005.3` —— `docs/reference/continuation-portability.md:14` 信源链接 `code.claude.com/docs/...md` 格式可疑，只读不可核。实施 S2.8 时人工打开验证。

---

## 1. 终态概览（7 架构决策）

整套修复收敛到 7 条架构决策（AD）。它们不是 7 个补丁，而是一套自洽的资产纪律 —— 执行后框架看起来"从一开始就按这套规则长出来"。

| 决策 | 终态 | 消解的问题簇 |
|------|------|------------|
| **AD-1 可部署边界 = 引用位置边界** | 可部署 prompt 资产（`.cataforge/**` 下 SKILL/AGENT）链接的内容必须自身可部署（在 `.cataforge/**` 内）。承重语言/反例 reference 从 `docs/reference/` 迁入 `.cataforge/skills/<skill>/references/`；`docs/reference/` 重定性为维护者文档，不被任何可部署资产链接 | D1, D2, E1, E2 |
| **AD-2 单一定义，引用而非复述** | 每个枚举/阈值/常量/路由只有一个权威定义（core `Literal` / `framework.json` / COMMON-RULES 常量表 / `profile.yaml`+`_schema.yaml`）；其余处按名引用，绝不复述裸值 | A1–A11 |
| **AD-3 退出码契约单一权威** | COMMON-RULES §Layer 1 调用协议是退出码唯一事实源。`_shared.CheckReport.exit_code`：advisory-only→`0`，`2` 仅留给 bad-args/不可执行；`runner` 与三态对齐 | C1 |
| **AD-4 守卫 = 规则的可执行表达，覆盖均匀** | 抽 `scripts/checks/_common.py`；三条 anti-rot 守卫扫同一套资产全集（`.cataforge/**` 含 references/+templates/+rules/，及 docs/reference/）；编号识别覆盖 heading/表格；新增对账探针覆盖当前静默漂移的 SSOT 关系 | K1–K6 |
| **AD-5 镜像是纯生成物** | `.claude/**` 由 deploy 从 canonical 生成，绝不手维护；freshness 守卫对漂移 FAIL；消除同一权威文件双份注入上下文 | J1 |
| **AD-6 模型 tier 匹配任务复杂度，工具边界匹配角色** | reflector→`standard`；product-manager 的 Bash 收紧到只读 context，与同类文档创作角色对齐 | H1, H2 |
| **AD-7 无死路径** | 死枚举、死档位、死分支、死代码一律删除（不注释、不留 deprecated 标记），让能力声明与实际可达路径一致 | B1–B5 |

**为何整体自洽**：六批报告收敛出三条系统主线 —— ①守卫覆盖/正确性盲区 ②doc/reference↔SSOT 漂移 ③部署边界与卸载模式矛盾。AD-1 解③并给①②提供锚点（引用位置确定后，扫描范围与对账关系才能定义）；AD-2/AD-3 解②（漂移皆"复述后失同步"）；AD-4/AD-5 解①；AD-6/AD-7 清离群与死路径。唯二 HIGH（C1 退出码、D1 部署边界）都在支撑层/边界，prompt 资产主体质量稳健 —— 计划重心是"跨资产一致性 + 守卫闭环"。

---

## 2. 问题清单（去重后）

去重：`B4-R-001`(doc)+`B5-R-002`(code)=同一 PLATFORM_FEATURES；`B1-R-004`+`B6-R-003`(checkpoint)=同一 SSOT 两站点；`B1-R-006/007`+`B3-R-006`+`B4-R-005`+`B5-R-010`+`B6-R-002`=同一守卫覆盖主线。归并-LOW 微项折入所属线程行并在对应步骤逐条落地。

| ID | 来源 | 严重度/优先级 | 依赖 | 描述 |
|----|------|--------------|------|------|
| **C1** | B5-R-001 | HIGH / P0 | — | Layer 1 退出码 `2` 被 `_shared`(advisory)/`runner`(bad-args)/COMMON-RULES(FAIL) 三方互斥定义，advisory 路径可达 |
| **D1** | B6-R-001 | HIGH / P0 | — | 7 可部署资产链接 `docs/reference/{3 文件}`，deploy 只落地 `.cataforge/**` → 下游链接全悬空，零守卫 |
| **D2** | B6-R-004 | MEDIUM / P0 | D1 | 3 承重 reference 薄占位（仅 Python/JS），叠加 D1 使非 Python/JS 下游双重失效 |
| **A1** | B2-R-001 | MEDIUM / P1 | — | reflector 偏差类型枚举 `{preference\|constraint\|domain-knowledge}` 虚构，与 `corrections.DeviationType`(5 值) 及自身 `self-caused` 过滤键三方矛盾 |
| **A2** | B1-R-003 | MEDIUM / P1 | — | needs_revision 人工介入阈值通用 ≥2 vs cascade ≥3（Q2→统一 ≥2）|
| **A3** | B1-R-004+B6-R-003 | MEDIUM / P1 | — | `MANUAL_REVIEW_CHECKPOINTS` 默认：Bootstrap+configuration.md 漏 post_sprint，SSOT 为 3 项；且硬编码裸值 |
| **A4** | B3-R-002 | MEDIUM / P1 | — | task-decomp(250)/tdd-engine(200)/`TDD_LIGHT`(150) 三裸值散落，"250 因触发 200"因果自相矛盾（Q1→保留分层改因果+注册常量）|
| **A5** | B4-R-001+B5-R-002 | MEDIUM / P1 | — | `PLATFORM_FEATURES`(17) 缺 `subagent_interactive`，profile/schema 均 18；capability-matrix 权限模式名 snake vs camel；feature 计数三方打架 |
| **A6** | B4-R-002 | MEDIUM / P1 | — | framework-review 自身 SKILL severity 表 B7-β 标 WARN(实 FAIL)、B5-γ 漏 FAIL，与 manifest 矛盾 |
| **A7** | B5-R-003 | MEDIUM / P1 | — | `check_meta` 强制 `consumers`，与 COMMON-RULES 最小字段集(4 项)漂移（Q7→补规则）|
| **A8** | B5-R-005 | MEDIUM / P1 | — | `check_orphaned_components` 抽 `C-` 前缀，ui-spec SSOT 为 `UC-` → 孤儿检测从不触发 |
| **A9** | B6-R-003 | MEDIUM / P1 | — | docs/reference SSOT 漂移簇：版本横幅、cli 缺 5 命令、skill 计数 28/26、category 9/14、event 5/9、exit 缺 3、常量缺 7-8 |
| **A10** | B3-R-007 | LOW / P2 | — | 散落 SSOT/残留：finalize 复述、S/M/L vs XL、task-dep §2 表述、sprint-review 版本里程碑入正文 |
| **A11** | B4-R-003+B4-R-007 | MEDIUM / P1 | — | platform-audit 模板强制"工作量估算"（违 §禁止估算）；framework-feedback `--threshold 3`/workflow-gen "30%" 硬编码；framework-review `--focus` 漏 B8/B9 |
| **B1** | B3-R-003 | MEDIUM / P1 | A2.3 | agent-dispatch 7 task_type 中 3 个无恢复流程、不经 dispatch（Q3→删 3 项）|
| **B2** | B3-R-004 | MEDIUM / P1 | — | sprint-review lite 档与微型 Sprint 短路共用常量，orchestrator 无 lite 入口（Q4→删 lite）|
| **B3** | B4-R-004 | MEDIUM / P1 | A2.3 | framework-issue-resolve 非法 `status: triage-draft` + 未注册 `docs/reviews/triage/`（Q5→注册+draft）|
| **B4** | B5-R-007 | MEDIUM / P2 | — | `check_no_raw_subprocess` `ADVISORY_MODE=False` 使 advisory 分支死代码 |
| **B5** | B5-R-012(1,2,10) | LOW / P2 | — | 死代码群：`layer_dependencies` 空集分支、`doc_consistency/_parse` 9 零引用正则、`task_dep` 递归无深度保护 |
| **E1** | B2-R-004 | MEDIUM / P1 | D1 | test-writer 正文内嵌 JS/TS lint/matcher 反例表 |
| **E2** | B3-R-001 | MEDIUM / P1 | D1 | testing/deploy-config 等多 skill 正文内嵌语言标识符 |
| **F1** | B1-R-005 | LOW / P2 | — | Phase Routing 在 framework.json + AGENT 表 + Mode Routing Protocol 三处复述 |
| **F2** | B2-R-002 | MEDIUM / P2 | — | Mid-Progress 落盘契约在 reviewer/debugger/test-writer 三 AGENT.md 逐字复制 |
| **F3** | B4-R-006 | LOW / P2 | — | reference/跨资产复制：platform-audit SKILL↔checklist、capability-matrix↔docs、maxTurns 档位 |
| **G1** | B2-R-003 | MEDIUM / P2 | — | devops 缺具名默认倾向护栏，弱于同批其它角色 |
| **G2** | B3-R-009 | LOW / P2 | — | 子代理逃生口缺失：user-interview inline vs dispatch、arc-design 空 languages、task-decomp 收 blocked |
| **G3** | B3-R-005 | MEDIUM / P2 | — | change-guard `clarification` 未定义 `drift_level` 合法值，XML schema 无 n/a |
| **H1** | B2-R-005 | MEDIUM / P1 | — | reflector `model_tier: light`(→haiku) 与综合职责失配（Q6→standard）|
| **H2** | B2-R-006 | LOW / P2 | — | product-manager 持不受限 `shell_exec`，同类文档创作角色均收紧 |
| **I1** | B5-R-004 | MEDIUM / P2 | — | `check_no_todo` `todo - assumption` 净计数，未配对 `[ASSUMPTION]` 掩盖真实 TODO |
| **I2** | B5-R-008 | MEDIUM / P2 | — | 守卫导入失败处理不一致（顶层 import 致 FAIL 而非 skip）；`check_hooks_yaml_schema` 无 try/except |
| **I3** | B5-R-009 | MEDIUM / P2 | — | `collect_files`/`_collect` `rglob("*")` 后逐 part 过滤，无法剪枝排除子树 |
| **I4** | B5-R-011 | MEDIUM / P2 | — | `sprint_review/_extract.py:209` `open()` 无 `encoding=`/`errors=`，BOM 崩溃 |
| **J1** | B1-R-001 | MEDIUM / P1 | 全 canonical 编辑 | `.claude/rules/` 镜像漂移（缺整段）+ 同一权威文件双份注入（~25KB/会话冗余）|
| **K1** | B1-R-002 守卫缺口 | MEDIUM / P2 | — | residue 守卫未覆盖中文对比叙事（"收紧自/改为/原方案"）；正文残留需删 |
| **K2** | B1-R-006/007+B3-R-006+B4-R-005+B5-R-010+B6-R-002 | MEDIUM / P1 | 内容线全部 | SCAN_GLOBS 漏 templates/references/rules/docs-reference、heading/表格编号失明、`_common.py` 未抽取 |
| **K3** | B5-R-006 | MEDIUM / P2 | — | `run_local.py` 漏挂 `check_no_dev_branch_refs`（全量扫描非 BASE_REF），注释归因错误 |
| **K4** | B6-R-001 守卫缺口 | MEDIUM / P1 | D1 | 无守卫校验"分发资产内 markdown 链接在部署布局下可解析" |
| **K5** | B2-R-001/B4-R-001/002/004/B5-R-001/002/003/005/B6-R-003 守卫缺口 | MEDIUM / P1 | 内容线全部 | 缺对账探针：PLATFORM_FEATURES↔schema、退出码契约、AGENT 枚举↔Literal、severity↔manifest、status∈合法、path∈注册表、CLI/常量/枚举/计数 SSOT |
| **K6** | B5-R-012(3,4,5,11) | LOW / P2 | — | 守卫质量：`ALLOW_MARKER` 无 IGNORECASE、`check_schema_python_parity` 硬编码文案、`b6.py` 错 id、`check_skill_count` 不滤 SKILL.md |

**归并-LOW 余项落点**：`B5-R-012.6`(iter_files 重复)→K2；`B5-R-012.7/8`(ui_fidelity 静态分析局限)→I3；`B5-R-012.9`(framework_feedback docstring 设计动机)→S5.4；`B5-R-012.12`(`_render` warnings_only 文案)→S5.4；`B6-R-005`(front matter 缺失/debug-patterns 内部编号/builtin-skill-layout 迁移叙事/wiring-checks §3.2 覆盖)→S1.1+S2.8；`B3-R-008`(ui-design P-{NNN}/Step9/MVP 裸词/debug 单句节)→S5.3。

---

## 3. 修复计划（阶段 → 步骤）

**阶段 = 依赖层**。拓扑序：`P1-引用架构 → P2/P3/P4(largely 并行) → P5 → P6 → P7-启用`。守卫**编写**可与 P1–P6 重叠，守卫**启用**（接入 run_local/CI）是终端门，必须在内容线全部落地后 —— 这是六批报告共同硬约束（守卫变严即刻对存量报红）。

```
P1 ──┬─→ P2 ──┐
     │   P3 ──┼─→ P5 ──→ P6 ──→ P7(启用)
     └─→ P4 ──┘                  ↑
         (P7 编写可与 P1-P6 并行)──┘
```

### 阶段 P1 — 引用架构 / 部署边界（含 HIGH D1）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S1.1** 迁移承重 reference + 补全 | D1, D2 | 卸载目标放在不可部署的 repo 级 `docs/reference/` | `wiring-checks`/`debug-patterns`/`test-and-e2e-apis` 迁入消费方 `.cataforge/skills/<skill>/references/`（多消费方共享者放可部署共享位）；补齐 `languages.md` 已注册语言(csharp/go/rust/java)最小条目，或在引用方明示"仅 Python/JS 有细则，余走通用准则"；顺带修 `debug-patterns.md:17` 内部编号、`wiring-checks.md §3.2` 覆盖与标题对齐 | AD-1 | 下游 deploy 布局变化：reference 改随 per-skill scaffold 部署 | 文件在 `.cataforge/` 树；非 Python/JS 下游有内容或明确边界声明 |
| **S1.2** 改链接 + 语言卸载入新家 | D1(链接), E1, E2 | 链接指向不可部署路径；语言标识符内嵌正文 | `code-review/SKILL:63`、`tech-lead/AGENT:50`、`test-writer/AGENT:123`、`debug/SKILL:78,85`、`testing/SKILL:90`、`sprint-review/SKILL:65`、`qa-engineer/AGENT:43,54` 的 ≈9 处链接改写为 skill-local 相对路径；同遍把 test-writer JS/TS 反例表、testing/deploy-config 语言标识符卸载进新 references，正文仅留语言无关纪律 + 链接 | S1.1 | 无（内部重排） | 部署态链接解析到 `.cataforge/` 内存在文件；正文无语言/DSL 字面 |

### 阶段 P2 — 单一事实来源（内容收敛到终值；多步文件不相交可并行）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S2.1** orchestrator 收口 | A2, A3(bootstrap), F1, B1-R-006, K1(正文), B1-R-002 | 同一事实多处裸值复述 + 变更叙事残留 + 编号跳序 | 删 `:135` "收紧自 N≥3" 叙事；cascade `:406` 阈值改 ≥2 并引用 §needs_revision 计数规范单一定义（Q2）；Bootstrap `:11` 默认改引用 `MANUAL_REVIEW_CHECKPOINTS`（删裸列表）；Phase Routing 细节唯一落 Mode Routing Protocol，`AGENT.md:37-55` 表降为骨架+指针；Phase Transition `:161-211` 步骤重排连续整数，去 `allow-doc-structure` | — | 无 | doc-structure+residue 守卫绿；三处阈值/默认/路由各仅一处权威 |
| **S2.2** reflector 收口 | A1, H1, B3(input) | 手写虚构枚举 + tier 失配 | `:31` 改引用 `corrections.DeviationType`(5 值)，显式区分 deviation vs root_cause 两套枚举；`:11` tier→standard（Q6）；triage 入 Input Contract（Q5）| — | tier 变更影响 fallback subagent 模型 | 枚举值集==`VALID_DEVIATIONS`；过滤键在集合内 |
| **S2.3** 常量/阈值/路径注册表 | A4, A7(规则侧), B3(注册) | 裸阈值散落 + 注册表缺项 | COMMON-RULES 常量表 + `framework.json` 常量块（双向 SSOT + migration_check）注册 `TASK_SPLIT_LOC=250`、`MID_PROGRESS_LOC=200`（Q1，保留分层值）；`task-decomp:51`/`tdd-engine:41` 引用并删错误因果；最小字段集补 `consumers`+例外（Q7）；§报告 Front Matter 约定表注册 triage 行（Q5）| — | 无（增量） | LOC 阈值同源；`framework.json`↔COMMON-RULES 常量一致；triage 路径已注册 |
| **S2.4** PLATFORM_FEATURES 对齐 | A5 | 常量陈旧 + reference 字面不符 profile | `types.py:117-135` 补 `subagent_interactive`(→18)；`capability-matrix.md` 权限模式名改 camelCase 全称、feature 计数改引用 | — | 无 | `set(PLATFORM_FEATURES)==_schema features keys`；逐字对照 profile |
| **S2.5** framework-review 自洽 | A6, A11(focus) | doc↔manifest 漂移 | `SKILL.md:69` B7-β→FAIL、`:59` B5-γ→FAIL/WARN/INFO 与 manifest 单点对齐；`:45` `--focus` 补 B8/B9、Step1 补 B3-β 行 | — | 无 | 表 severity==manifest；自审绿 |
| **S2.6** doc_consistency 前缀 | A8 | 前缀错位致检查空转 | `_checks.py:297` `_extract_all_ids(content,"C")`→`"UC"` | — | 无 | 合规 ui-spec 上孤儿检测真正触发 |
| **S2.7** 维护者文档 SSOT 订正 | A9 | 手维护镜像滞后 SSOT | 版本横幅→指向 `__version__`；`cli.md` 补 5 命令(bootstrap/issue/penpot/phase/claude-md)；`configuration.md` 修 checkpoints/常量/kg 块归位；`status-codes.md` category 14/event 9/exit 补 3；`agents-and-skills.md` 计数(26)+矩阵(补 project-visualization/design 路径)；`platform-capability-matrix.md` 补 deploy_drift | — | 无 | 各值==当前 SSOT |
| **S2.8** 散落残留/裸值 | A10, A11(rest), B4-R-003, B3-R-008(部分), B6-R-002(存量清理) | 局部复述/残留 | 删 `evaluate-new-platform.md:75` "工作量估算"→成本/复杂度维度；`framework-feedback:60` `--threshold` 引用常量；workflow-gen 30% 注册或去魔法数；finalize 复述删、S/M/L↔XL 对齐、sprint-review 版本里程碑入 frontmatter、`task-decomp:43` "MVP 切分"→"Sprint 切分"、`builtin-skill-layout.md:73` 迁移叙事删；清 `kg-verified-behaviors.md`/`cli.md` 残留（Q8 扫描前置） | — | 无 | grep"工作量估算/小时/MVP"零命中；裸值均引用常量 |

### 阶段 P3 — 退出码契约（HIGH C1，可与 P2 并行）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S3.1** 退出码单一权威 | C1, I4, doc_review 编码 | 退出码 `2` 三方互斥语义 | 以 COMMON-RULES §Layer 1 为唯一源：`_shared.py:99-105` advisory-only→`0`、`2` 仅 bad-args/不可执行；`runner.py:198` needs_revision 升级与三态对齐；`doc_consistency`/`doc_review`(`:62` 编码)/`e2e_scan`/`sprint_review`(`_extract.py:209` `errors="replace"`) 退出与编码统一 | — | **破坏**：`2=advisory` 语义改变（无正确消费者依赖）；退出码消费方需回归 | 新单测断言取值域==Layer 1 四态；doc-consistency 仅 MEDIUM 时不再误升阻塞 |

### 阶段 P4 — 死路径消除（AD-7，依赖 P2 注册表）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S4.1** agent-dispatch 枚举 | B1 | 死枚举无恢复协议 | `SKILL.md:21` 删 retrospective/skill-improvement/apply-learnings，触发方式就近写明（inline/CLI）；`dispatch-prompt.md` 条件块同步；SUB-AGENT-PROTOCOLS 已仅覆盖 continuation/revision/amendment，枚举对齐其覆盖集（Q3）| — | **破坏**：移除 dispatch task_type 值（CLI `--task-type` 面保留）| 枚举⊆SUB-AGENT-PROTOCOLS 覆盖集∪inline/CLI 白名单 |
| **S4.2** sprint-review lite | B2 | 不可达死档 | `sprint-review/SKILL.md:21` 删 lite 行（保留 standard/merged-review）（Q4）| — | **破坏**：移除文档化档位 | 走查无死路径 |
| **S4.3** framework-issue-resolve 合规 | B3(内容) | 自造 status/路径 | `:58` `status: triage-draft`→`draft`；路径已由 S2.3 注册 | S2.3 | frontmatter 值变更 | status∈合法枚举；路径∈注册表 |
| **S4.4** 代码死块清理 | B4, B5 | 死代码 | 删 `check_no_raw_subprocess.py:51` `ADVISORY_MODE`+`:79-94` 块；删 `layer_dependencies.py:182,206` 空集分支；删 `doc_consistency/_parse.py:12-20` 9 零引用正则；`task_dep_analysis.py` `detect_cycles` 加深度保护 | — | 无 | vulture/人工确认无不可达 |

### 阶段 P5 — 方法论去重 & 指导/健壮性补齐（依赖 P1）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S5.1** Mid-Progress 契约单点化 | F2 | 三处逐字复制 | 抽到 SUB-AGENT-PROTOCOLS（紧邻 §并行写盘纪律）单点定义；`reviewer:41-47`/`debugger:39-45`/`test-writer:34-40` 仅留引用+角色落盘单元一句特化 | P1（test-writer 已改）| 无 | 三 AGENT 仅引用；doc-structure 绿 |
| **S5.2** reference 矩阵去重 | F3 | 副本漂移 | platform-audit SKILL 删与 checklist 重复段留指针；`capability-matrix.md` 以 profile/docs 单源；workflow-gen maxTurns 档位统一（三档 30/80/150）| — | 无 | 重复段仅留指针 |
| **S5.3** 指导/边界补齐 | G1, G2, G3, H2, B3-R-008(余) | 离群护栏/逃生口缺失 | devops 补具名默认倾向 Anti-Pattern + 决策视角；change-guard `:84` `drift_level` 加 `n/a`、Step 4 显式 clarification→n/a；research/tech-eval/arc-design/task-decomp 补 inline-vs-dispatch/空 languages/收 blocked 降级分支；pm Anti-Patterns 补 Bash 收紧；ui-design `P-{NNN}` 统一、Step9 移入"不做"、debug 单句节删 | — | pm 工具边界收窄 | Anti-Patterns≥`ANTI_PATTERN_MIN_COUNT_AGENT`；每分支有定义值/降级路径 |
| **S5.4** 代码健壮性 | I1, I2, I3, B5-R-012(convention 余) | 边界/一致性 | `check_no_todo` `:159-164` 改逐匹配判定；导入失败统一延迟导入+skip、`check_hooks_yaml_schema:56` try/except→clean FAIL；`collect_files`/`_collect` 改 `os.walk` 剪枝；删 `framework_feedback.py:7-14` 设计动机 docstring；`_render.py:30` warnings_only 文案修正 | — | 无 | 各加最小单测；`run_local` 绿 |

### 阶段 P6 — 镜像重生（依赖 P1–P5 全部 canonical 编辑）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S6.1** 镜像由 deploy 生成 + 单份加载 | J1 | 手维护漂移 + 双份注入 | 重跑 `cataforge deploy` 由 canonical 生成 `.claude/**`；消除双份注入（CLAUDE.md 不再 `@import` rules 与 `.claude/` 镜像二选一，保证单份加载）| P1–P5 | **破坏**：CLAUDE.md 加载链路调整 | `diff .cataforge/rules ↔ .claude/rules` 仅余占位符替换；上下文不再现两版 COMMON-RULES |

### 阶段 P7 — 守卫补强（编写可重叠 P1–P6，启用为终端门）

| 步骤 | 解决 | 根因 | 目标设计（终态） | 前置 | 破坏性 | 验收 |
|------|------|------|----------------|------|--------|------|
| **S7.1** 抽 `_common.py` | K2(基建), K6 | 三处 SCAN/iter_files/escape-hatch 漂移 | `scripts/checks/_common.py` 共享 `iter_files()`/frontmatter/code-fence toggle/escape-hatch/`re.IGNORECASE` | — | 无 | 三守卫复用同一实现 |
| **S7.2** 统一扫描覆盖 | K1, K2 | 覆盖盲区 | 三守卫扫 `.cataforge/**` 全可部署 prompt 资产（含 references/+templates/+rules/）+ `docs/reference/`（Q8，rationale 扩写为"含长期 repo 文档"）；doc-structure 补 heading(`^#{1,6}\s+\d+[a-z]`)+表格编号；residue 补中文对比叙事锚点（排除 anti-pattern 示例避免误报）| 内容线全部 | **启用即对未修存量报红 → 必须在 P1-P6 后** | 各守卫单测；存量零命中 |
| **S7.3** run_local 补全 | K3 | 漏挂 + 注释错误 | `check_no_dev_branch_refs` 入 `CHECKS`；修 `:170-172` 注释（仅留真 BASE_REF 依赖项）；加元守卫"确定性全量 check 都在 run_local" | — | 无 | 本地==CI |
| **S7.4** markdown 链接守卫 | K4 | 零链接解析守卫 | 新 doctor/check：部署态 SKILL/AGENT 每条 markdown 链接解析到 `.cataforge/` 树内存在文件 | P1 | 无 | 悬空链接 FAIL |
| **S7.5** 对账探针族 | K5 | 静默漂移无拦截 | 新增/扩展：`PLATFORM_FEATURES↔_schema`、退出码契约取值域、AGENT/SKILL 枚举↔core `Literal`、severity 表↔manifest、报告 status∈合法、skill 产出路径∈注册表、CLI 命令/常量/category/event/exit/计数/版本横幅 SSOT 对账（扩展 `check_skill_count` 思路）| 内容线全部 | 无 | 各探针单测；对当前态绿 |
| **S7.6** 守卫质量 | K6 | 局部缺陷 | `check_schema_python_parity:123` 动态消息；`b6.py:54` 修 id；`check_skill_count:38` 滤 SKILL.md+查头部计数；`check_orphan_cli` 扫 hooks.yaml | — | 无 | 单测 |

**启用门**：S7.2/S7.5 接入 `run_local.py`/CI 只能在 P1–P6 落地后，否则守卫变严即刻红。S7.1/S7.3/S7.4/S7.6 编写无此约束。

**建议 PR 切分**：P1=1 PR（部署边界，含 HIGH D1+K4 守卫）；P3=1 PR（退出码 HIGH C1）；P2 按文件簇 2-3 PR；P4/P5 各 1-2 PR；P6=1 PR；P7=1 个"anti-rot 守卫补强"PR（编写期并行，末位启用）。

---

## 4. 终态一致性说明（为何不留补丁痕迹）

1. **没有"兼容旧值"的脚手架**。A2/A3/A4 不保留旧阈值并陈，B1-B5 死代码直接删除（不留 deprecated 标记），C1 不保留 `2=advisory` 兼容分支 —— 让 commit diff 自身承载证据，符合 COMMON-RULES §禁止变更说明残留。读者看到的都是"当前唯一态"。
2. **没有重复定义可再漂移**。AD-2 执行后每个枚举/阈值/常量/路由只有一个权威源，其余按名引用；F1/F2/F3 把复制的方法论/路由收敛到单一定义。这从拓扑上消除了六批反复出现的"复述后失同步"根因 —— 不是修了 N 处漂移，而是消除了"能漂移"的结构。
3. **守卫与规则同构，且最后启用**。AD-4 让三硬约束在全资产上均匀可执行，K5 探针把此前靠人工 review 兜底的 SSOT 关系变成机检。守卫在内容线落地后启用，启用瞬间全绿 —— 无"修了内容守卫还红"或"守卫先行逼出临时豁免"的过渡态。escape hatch 被结构整改消除而非堆叠。
4. **部署边界一次划清**。AD-1 后"可部署资产→可部署引用"成为不变量，K4 守卫钉死它。承重 reference 迁到唯一正确归属层，`docs/reference/` 角色明确为维护者文档。边界画对一次，E1/E2 语言卸载与未来新增 reference 都自然落在正确侧。
5. **镜像是纯函数输出**。AD-5 后 `.claude/**` 是 `deploy(canonical)` 的确定性产物 + freshness 守卫，J1 的双份注入与漂移在生成模型下不可复现。
6. **死路径清零，声明=可达**。AD-7 后 task_type 枚举、sprint-review 档位、退出码取值、代码分支都与实际可达路径一一对应，无"声明了但永不触发"的幽灵能力误导 LLM。
