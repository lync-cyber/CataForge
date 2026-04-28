---
name: framework-review
description: "框架元资产审查 — 对 .cataforge/ 下的 agents/skills/hooks/rules + workflow 拓扑做内容质量与一致性审查。与 platform-audit 形成内审/外审对偶；与 code-review/doc-review 服务于业务产物不同，本 skill 专审框架自身配置。当用户提到框架腐化、SKILL.md/AGENT.md 质量、agent 引用孤立、SKILL/MANIFEST 漂移、Workflow 完整性、model_tier 合规时使用。"
argument-hint: "<scope: agents|skills|hooks|rules|workflow|all> [--focus <category[,...]>] [--target <asset_id>]"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 框架元资产审查 (framework-review)

## 能力边界
- 能做: 审查 `.cataforge/` 下的 agents / skills / hooks / rules 元资产；对账 SKILL.md ↔ CHECKS_MANIFEST；交叉引用图完整性；裸常量数值检测；workflow phase × agent × skill 覆盖矩阵；agent model_tier 合规
- 不做: 修改被审元资产（仅产报告）；审查 src/ 下的业务代码（由 code-review scan 负责）；审查 IDE 厂商 profile 漂移（由 platform-audit 负责）

## 输入规范
- scope: agents | skills | hooks | rules | workflow | all
- 可选 `--focus`: 限定子检查（B1-α/β、B2-α、B3-α、B4-α、B5-α/β/γ/δ、B6-α/β/γ/δ/ε、B7-α/β/γ）
- 可选 `--target <asset_id>`: 仅审单个 agent / skill 名（Layer 2 节省 token；Layer 1 仍按 scope 全跑）
- 项目根下的 `.cataforge/` 目录（必读）
- `cataforge.skill.builtins.*.CHECKS_MANIFEST`（B3 对账数据源，从已安装的 cataforge 包导入）
- `cataforge.hook.scripts.*` (B6-α/β script 可达性 + ast.parse 数据源)
- `cataforge.core.types.CAPABILITY_IDS` / `EXTENDED_CAPABILITY_IDS` (B6-γ matcher 校验集)
- `framework.json#/constants/AGENT_MODEL_DEFAULTS` + `AGENT_MODEL_TIER_HEAVY_WHITELIST` (B7 数据源)
- `framework.json#/dispatcher_skills` (B5-α 区分 skill-as-router vs 未定义 agent)

## 输出规范
- 框架审查报告: `docs/reviews/framework/FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}-r{N}.md`
- 审查结论: approved / approved_with_notes / needs_revision

## 推荐触发路径

framework-review 是按需触发的元资产审查，**不进入业务流程主循环**。推荐的合规触发面：

- **用户手动**: `cataforge skill run framework-review -- all`（或具体 scope）
- **CI 守卫**: 在 PR pipeline 增加一步 `cataforge skill run framework-review -- all --focus B1,B2,B3,B7`，仅 FAIL 时阻塞合并
- **doctor 深扫**: `cataforge doctor --deep` 可选附带 framework-review 全量
- **不要**: 让 reviewer agent 在业务流程内自动调起（reviewer.allowed_paths 不覆盖此报告路径，会污染审查独立性）

## 操作指令: 框架审查 (review)

### Step 1: Layer 1 — 静态结构检查
执行: `cataforge skill run framework-review -- {scope} [--focus B1,B2,B3,B4,B5,B6,B7]`

返回码语义按 §Layer 1 调用协议。Layer 1 的子检查映射:

| 子检查 ID | 对应能力 | scope | 失败级别 |
|----------|---------|-------|---------|
| B1-α | 必填段存在 (能力边界 / 输入规范 / 输出规范 / Anti-Patterns / 操作指令) | agents, skills | FAIL |
| B1-β | 元资产行数 ≤ META_DOC_SPLIT_THRESHOLD_LINES | agents, skills, rules | WARN |
| B2-α | 交叉引用图完整 (AGENT.md.skills + SKILL.md.depends + framework.json.features) | agents, skills, all | FAIL (引用不存在) / WARN (孤立) |
| B3-α | SKILL.md "## Layer 1 检查项" 段与 builtin CHECKS_MANIFEST 对账 | skills | FAIL |
| B4-α | SKILL.md / AGENT.md / 协议文档不得出现常量名对应的裸数值 | agents, skills, rules | WARN |
| B5-α | Workflow 覆盖矩阵 phase→agent 单跳 (dispatch 表 vs agents/, dispatcher_skills 豁免) | workflow, all | WARN |
| B5-β | phase→agent→skill 三跳 (每个 phase-routed agent ≥1 skill 且 skill 必须存在) | workflow, all | WARN |
| B5-γ | EVENT-LOG.jsonl agent_return 事件 ↔ phase routing 对账 (≥`EVENT_LOG_DRIFT_MIN_EVENTS` 启用，否则 INFO) | workflow, all | WARN / INFO |
| B5-δ | framework.json features[*].phase_guard ↔ Phase Routing 已知 phase 对账 | workflow, all | WARN |
| B6-α | hooks.yaml 引用的 script 必须解析到真实 .py 文件 (builtin / custom) | hooks, all | FAIL |
| B6-β | 每个 hook script .py 必须 ast.parse 成功 | hooks, all | FAIL |
| B6-γ | matcher_capability 必须是 CAPABILITY_IDS / EXTENDED_CAPABILITY_IDS 成员 | hooks, all | FAIL |
| B6-δ | 每 platform profile.yaml 的 hooks.degradation 与 hooks.yaml 脚本集对账 | hooks, all | WARN (缺) / WARN (孤儿) |
| B6-ε | hooks.yaml 非 custom: 脚本 ∈ cataforge.hook.manifest.HOOKS_MANIFEST | hooks, all | FAIL (孤儿引用) / WARN (未挂的 manifest 条目) |
| B7-α | AGENT.md `model_tier` 合规 + 与 AGENT_MODEL_DEFAULTS 一致；heavy 需进白名单 | agents, all | FAIL / WARN |
| B7-β | AGENT.md 仍含 legacy `model:` 字段（deprecated） | agents, all | WARN |
| B7-γ | platform profile.yaml `model_routing.tier_map` 覆盖 light/standard/heavy | agents, all | WARN |

`--focus` 缺省时执行 scope 对应的全部子检查。

### Step 2: Layer 2 — AI 内容质量审查（按资产类型分层）

通过 doc-nav 加载被审资产，按资产类型应用对应维度矩阵。**scope=all 时按类型分批送 LLM**（先 SKILL 一批、再 AGENT 一批、再 hooks 一批），避免一次性塞入稀释关注度。`--target <asset_id>` 时仅审单个资产，跳过分批。

#### SKILL 维度矩阵（scope=skills）

| 维度 | category | 检查内容 |
|------|----------|---------|
| 描述触发性 | ambiguity | description 是否包含触发关键词，足以让 LLM 在正确场景自动调用 |
| 能力边界对称 | completeness | "能做" / "不做" 是否成对、互不重叠 |
| Anti-Patterns 具体性 | convention | 是否使用"做 A 而非 B"格式并附具例（呼应 COMMON-RULES §对比式约束） |
| 同类 skill 重叠 | structure | 是否与已有 skill 职责模糊重叠 |
| 输入/输出契约完整 | completeness | 是否明确输入数据形式与产出路径 |

#### AGENT 维度矩阵（scope=agents）

| 维度 | category | 检查内容 |
|------|----------|---------|
| Identity ↔ Phase 一致 | structure | Identity 段声明的角色与 orchestrator Phase Routing 中分配给该 agent 的阶段一致 |
| tools / disallowedTools 自洽 | consistency | 不重叠；tools 不含 agent 不该用的能力（如 phase-bound 子代理含 agent_dispatch） |
| allowed_paths 边界合理 | structure | 写入路径限定 agent 职责域（如 reviewer 只允许 docs/reviews/）；无空数组例外不应在非 orchestrator 出现 |
| model_tier 选择合理 | convention | 与任务复杂度匹配；heavy 需在白名单；light 适合机械任务、不适合需要权衡的决策 |
| Anti-Patterns 具体性 | convention | 同 SKILL 维度，但聚焦 agent 行为反模式（不越权、不绕审等） |

#### Hooks 维度矩阵（scope=hooks）

| 维度 | category | 检查内容 |
|------|----------|---------|
| matcher_capability 必要性 | completeness | 每条 hook 都声明 matcher_capability；无 matcher 的全局 hook 仅在 SessionStart/Stop 等无匹配事件下合理 |
| degradation 合理性 | consistency | 每平台 native vs degraded 的判定与该平台的 capability 限制一致（如 codex 无 user_question → detect_correction degraded） |
| script 命名与位置一致 | structure | builtin 在 cataforge.hook.scripts；custom 在 .cataforge/hooks/custom；命名 snake_case |

**维度收敛**: `--focus <category[,...]>` 同上；可与 `--target <asset_id>` 组合。

### Step 3: 审查报告编号
报告编号按 COMMON-RULES §报告编号规则，前缀 `FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}`，目录 `docs/reviews/framework/`。

### Step 4: 产出审查报告
产出 `FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}-r{N}.md`，**首行必须为 YAML front matter**：

```yaml
---
id: "framework-review-{scope}-{YYYYMMDD}-r{N}"
doc_type: framework-review
author: reviewer
status: draft
deps: []
---
```

front matter 之后按 COMMON-RULES §问题格式 列出问题，可用 category: structure / consistency / convention / completeness / ambiguity / duplication（B3 漂移按 consistency；裸数值按 convention；孤立 skill 按 dead-code；model_tier 不当按 convention）。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。framework-review 默认不阻塞业务流程（不进 needs_revision 自动重试），仅产出报告供后续元资产维护决策。

## Layer 1 检查项 (framework_check.py)

> 权威清单见 `cataforge.skill.builtins.framework_review.CHECKS_MANIFEST`。

- B1-α: AGENT.md / SKILL.md 必填段（能力边界 / 输入规范 / 输出规范 / Anti-Patterns / 操作指令 任选其一作为入口段）<!-- check_id: B1_required_sections -->
- B1-β: 单文件行数 ≤ META_DOC_SPLIT_THRESHOLD_LINES (WARN 提示拆分)<!-- check_id: B1_size_threshold -->
- B2-α: 解析所有 AGENT.md `skills:` + SKILL.md `depends:` + framework.json `features` → 引用不存在的 skill/agent FAIL；无任何 AGENT.md 引用的 skill WARN（白名单豁免：基础设施类 skill 如 agent-dispatch / tdd-engine / change-guard / start-orchestrator / doc-nav / doc-gen / research / debug / self-update / workflow-framework-generator / platform-audit / framework-review）<!-- check_id: B2_cross_reference_graph -->
- B3-α: skill SKILL.md 的 "## Layer 1 检查项" 段与对应 builtin 的 `CHECKS_MANIFEST` 对账。两种识别策略二者必居其一：(1) **anchor 模式** — 段内若出现 `<!-- check_id: <id> -->` HTML 注释锚点，按 ID 双向校验（孤儿锚点 / 缺失锚点 → FAIL）；(2) **delegation 模式** — 段内出现 `权威清单见 ...CHECKS_MANIFEST` 短语，跳过逐条对照（manifest 存在性即契约）。缺该段、或既无锚点又无 delegation 句 → FAIL<!-- check_id: B3_manifest_drift -->
- B4-α: 在 .cataforge/{agents,skills,rules}/**/*.md 中 grep 框架常量对应的裸数值（如 `≤3 问` / `300 行` / `>200 行`），未引用常量名 → WARN（豁免：代码块、版本号、ID 编号）<!-- check_id: B4_hardcoded_constants -->
- B5-α: 解析 orchestrator AGENT.md Phase Routing → 输出 phase × agent 覆盖矩阵；空位标 WARN（phase 路由到既不在 .cataforge/agents/ 又不在 framework.json#/dispatcher_skills 的目标 / agent 定义但未被任何 phase 引用）<!-- check_id: B5_workflow_coverage_matrix -->
- B5-β: 对每个 phase-routed agent 解析 AGENT.md `skills:` 字段 → 三跳验证（agent 必须 ≥1 skill；引用的 skill 必须存在于 `.cataforge/skills/` 或 builtin）<!-- check_id: B5_phase_skill_coverage -->
- B5-γ: 读 `docs/EVENT-LOG.jsonl`，按 `event=agent_return` 聚合 → phase-routed agent 0 returns + 总 returns ≥ `EVENT_LOG_DRIFT_MIN_EVENTS` 时 WARN（潜在 dead routing）；未达阈值时输出一条 INFO（"drift check skipped"）；agent 有 returns 但全部缺 `ref` 字段 → WARN（output_path 追溯断链）<!-- check_id: B5_eventlog_agent_return_drift -->
- B5-δ: 解析 framework.json `features` → 每个非 null `phase_guard` 必须命中 Phase Routing 已知 phase<!-- check_id: B5_feature_phase_alignment -->
- B6-α: 解析 .cataforge/hooks/hooks.yaml，每个 `script` 字段须解析到真实 .py（builtin: `cataforge.hook.scripts.<name>` 通过 `importlib.resources` 定位；custom: `.cataforge/hooks/custom/<name>.py`）→ FAIL on missing<!-- check_id: B6_hook_script_reachability -->
- B6-β: 每个解析到的 hook script .py 必须 `ast.parse` 通过（不依赖 import 副作用）→ FAIL on SyntaxError<!-- check_id: B6_hook_script_syntax -->
- B6-γ: 每个 `matcher_capability` 值必须是 `CAPABILITY_IDS` ∪ `EXTENDED_CAPABILITY_IDS` 成员（typo 会让 hook 静默永不触发）→ FAIL on unknown capability<!-- check_id: B6_hook_matcher_capability -->
- B6-δ: 遍历 `.cataforge/platforms/<id>/profile.yaml`，`hooks.degradation` 的 keys 必须严格等于 hooks.yaml 引用的 script name 集合（`custom:` 前缀脱皮后比较）→ 缺失 WARN（deploy 默认 native 可能掩盖真实降级需求）/ 孤儿 WARN（dead config）<!-- check_id: B6_hook_degradation_coverage -->
- B6-ε: hooks.yaml 中所有非 `custom:` 前缀的 `script` 必须在 `cataforge.hook.manifest.HOOKS_MANIFEST` 中注册 → FAIL（manifest 缺失则脚本是 helper 而非 hook target，B6-α 单纯文件存在性查不出来）；HOOKS_MANIFEST 条目未被 hooks.yaml 引用 → WARN（dead inventory）<!-- check_id: B6_hook_manifest_drift -->
- B7-α: AGENT.md `model_tier ∈ {light, standard, heavy, inherit, none}`；与 `constants.AGENT_MODEL_DEFAULTS` 一致（不一致 → WARN）；`heavy` 需进 `constants.AGENT_MODEL_TIER_HEAVY_WHITELIST`（不在白名单 → FAIL，控制成本面）<!-- check_id: B7_model_tier_value -->
- B7-β: AGENT.md 仍含 legacy `model: <id>` 字段（无 `model_tier:`）→ FAIL，必须迁移；deploy 直接丢弃 legacy `model:` 行（无过渡期）<!-- check_id: B7_legacy_model_field -->
- B7-γ: platform `profile.yaml#/model_routing` 在 `per_agent_model: true` 且 `user_resolved: false` 时，`tier_map` 必须同时声明 `light` / `standard` / `heavy` 三档；缺哪档则该档 deploy 时静默不写 `model:` → WARN<!-- check_id: B7_platform_tier_map -->

## Anti-Patterns
- 禁止: framework-review 报告写入 `docs/reviews/doc/` 或 `docs/reviews/code/` — 必须写 `docs/reviews/framework/`，否则会与业务审查报告混淆并污染 reflector 聚合
- 禁止: 在 TDD / Bootstrap 主循环内自动触发 framework-review — 该 skill 按需触发（用户手动 / `cataforge doctor --deep` 可选附带 / CI 守卫显式调用，见 §推荐触发路径）
- 禁止: 让 reviewer agent 直接执行 framework-review — reviewer.allowed_paths 限定 docs/reviews/{doc,code,sprint}/，framework-review 应由独立调用方触发，避免审查独立性受污染
- 避免: 把通用规则塞进本 SKILL.md — COMMON-RULES 已自动加载到 Agent 上下文，本 SKILL.md 只描述 framework-review 自身的差异化语义
- 禁止: 新 SKILL 的"## Layer 1 检查项"段使用纯 prose — 必须用 `<!-- check_id: ... -->` 锚点或 `权威清单见 ...CHECKS_MANIFEST` delegation 句（B3-α 二者必居其一，否则 FAIL）

## 效率策略
- scope 切片: 默认按 scope 过滤检查项，避免一次性扫全部资产产生过长报告
- `--target <asset_id>` 单文件 Layer 2: 仅审单个 agent / skill 名，节省 token；适合 PR 中只改一个资产时的针对性审查
- `--focus <category[,...]>` 进一步收敛: 同 doc-review / code-review 的 Layer 2 收敛策略
- scope=all 自动分批 Layer 2: 按 SKILL → AGENT → hooks 顺序分别送 LLM，三个独立批次而非一次性塞入
- 与 platform-audit 互补: 后者审 IDE 厂商对账，本 skill 审框架内部资产；两者通过统一报告契约协同
