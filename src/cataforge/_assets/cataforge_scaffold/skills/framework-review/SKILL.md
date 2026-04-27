---
name: framework-review
description: "框架元资产审查 — 对 .cataforge/ 下的 agents/skills/hooks/rules + workflow 拓扑做内容质量与一致性审查。与 platform-audit 形成内审/外审对偶；与 code-review/doc-review 服务于业务产物不同，本 skill 专审框架自身配置。当用户提到框架腐化、SKILL.md/AGENT.md 质量、agent 引用孤立、SKILL/MANIFEST 漂移、Workflow 完整性时使用。"
argument-hint: "<scope: agents|skills|hooks|rules|workflow|all> [--focus <category[,...]>]"
suggested-tools: Read, Glob, Grep, Bash
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 框架元资产审查 (framework-review)

## 能力边界
- 能做: 审查 `.cataforge/` 下的 agents / skills / hooks / rules 元资产；对账 SKILL.md ↔ CHECKS_MANIFEST；交叉引用图完整性；裸常量数值检测；workflow phase × agent × skill 覆盖矩阵
- 不做: 修改被审元资产（仅产报告）；审查 src/ 下的业务代码（由 code-review scan 负责）；审查 IDE 厂商 profile 漂移（由 platform-audit 负责）

## 输入规范
- scope: agents | skills | hooks | rules | workflow | all
- 可选 --focus: 限定子检查（B1-α/β、B2-α、B3-α、B4-α、B5-α、B6-α/β/γ/δ）
- 项目根下的 `.cataforge/` 目录（必读）
- `cataforge.skill.builtins.*.CHECKS_MANIFEST`（B3 对账数据源，从已安装的 cataforge 包导入）
- `cataforge.hook.scripts.*` (B6-α/β script 可达性 + ast.parse 数据源)
- `cataforge.core.types.CAPABILITY_IDS` / `EXTENDED_CAPABILITY_IDS` (B6-γ matcher 校验集)

## 输出规范
- 框架审查报告: `docs/reviews/framework/FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}-r{N}.md`
- 审查结论: approved / approved_with_notes / needs_revision

## 操作指令: 框架审查 (review)

### Step 1: Layer 1 — 静态结构检查
执行: `cataforge skill run framework-review -- {scope} [--focus B1,B2,B3,B4,B5,B6]`

返回码语义按 §Layer 1 调用协议。Layer 1 的子检查映射:

| 子检查 ID | 对应能力 | scope | 失败级别 |
|----------|---------|-------|---------|
| B1-α | 必填段存在 (能力边界 / 输入规范 / 输出规范 / Anti-Patterns / 操作指令) | agents, skills | FAIL |
| B1-β | 元资产行数 ≤ META_DOC_SPLIT_THRESHOLD_LINES | agents, skills, rules | WARN |
| B2-α | 交叉引用图完整 (AGENT.md.skills + SKILL.md.depends + framework.json.features) | agents, skills, all | FAIL (引用不存在) / WARN (孤立) |
| B3-α | SKILL.md "## Layer 1 检查项" 段与 builtin CHECKS_MANIFEST 对账 | skills | FAIL |
| B4-α | SKILL.md / AGENT.md / 协议文档不得出现常量名对应的裸数值 | agents, skills, rules | WARN |
| B5-α | Workflow 覆盖矩阵 (phase × agent × skill, dispatch 表 vs framework.json) | workflow, all | WARN (空位) / WARN (孤立 agent) |
| B6-α | hooks.yaml 引用的 script 必须解析到真实 .py 文件 (builtin / custom) | hooks, all | FAIL |
| B6-β | 每个 hook script .py 必须 ast.parse 成功 | hooks, all | FAIL |
| B6-γ | matcher_capability 必须是 CAPABILITY_IDS / EXTENDED_CAPABILITY_IDS 成员 | hooks, all | FAIL |
| B6-δ | 每 platform profile.yaml 的 hooks.degradation 与 hooks.yaml 脚本集对账 | hooks, all | WARN (缺) / WARN (孤儿) |

`--focus` 缺省时执行 scope 对应的全部子检查。

### Step 2: Layer 2 — AI 内容质量审查
通过 doc-nav 加载被审 SKILL.md / AGENT.md，按以下维度审查（括号内为对应 category 枚举值）:
- 描述触发性(ambiguity): description 是否包含触发关键词，足以让 LLM 在正确场景自动调用
- 能力边界对称(completeness): "能做" / "不做" 是否成对、互不重叠
- Anti-Patterns 具体性(convention): 是否使用"做 A 而非 B"格式并附具例（呼应 COMMON-RULES §对比式约束）
- 与同类 skill 的能力重叠(structure): 是否与已有 skill 职责模糊重叠
- 输入/输出契约完整(completeness): 是否明确输入数据形式与产出路径

**维度收敛**: `--focus <category[,...]>` 同上。

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

front matter 之后按 COMMON-RULES §问题格式 列出问题，可用 category: structure / consistency / convention / completeness / ambiguity / duplication（B3 漂移按 consistency；裸数值按 convention；孤立 skill 按 dead-code）。

### Step 5: 判定结论
三态判定按 COMMON-RULES §三态判定逻辑。framework-review 默认不阻塞业务流程（不进 needs_revision 自动重试），仅产出报告供后续元资产维护决策。

## Layer 1 检查项 (framework_check.py)

> 权威清单见 `cataforge.skill.builtins.framework_review.CHECKS_MANIFEST`。

- B1-α: AGENT.md / SKILL.md 必填段（能力边界 / 输入规范 / 输出规范 / Anti-Patterns / 操作指令 任选其一作为入口段）
- B1-β: 单文件行数 ≤ META_DOC_SPLIT_THRESHOLD_LINES (WARN 提示拆分)
- B2-α: 解析所有 AGENT.md `skills:` + SKILL.md `depends:` + framework.json `features` → 引用不存在的 skill/agent FAIL；无任何 AGENT.md 引用的 skill WARN（白名单豁免：基础设施类 skill 如 agent-dispatch / tdd-engine / change-guard / start-orchestrator / doc-nav / doc-gen / research / debug / self-update / workflow-framework-generator / platform-audit / framework-review）
- B3-α: skill SKILL.md 的 "## Layer 1 检查项" 段与对应 builtin 的 `CHECKS_MANIFEST` 对账（条目数 + 关键词重叠度）；缺该段且对应 builtin 存在 manifest → FAIL
- B4-α: 在 .cataforge/{agents,skills,rules}/**/*.md 中 grep 框架常量对应的裸数值（如 `≤3 问` / `300 行` / `>200 行`），未引用常量名 → WARN（豁免：代码块、版本号、ID 编号）
- B5-α: 解析 ORCHESTRATOR-PROTOCOLS.md 的 dispatch 表 + framework.json features → 输出 phase × agent × skill 覆盖矩阵；空位标 WARN（某 phase 无 agent 覆盖，或某 agent 定义但未被任何 phase 引用）
- B6-α: 解析 .cataforge/hooks/hooks.yaml，每个 `script` 字段须解析到真实 .py（builtin: `cataforge.hook.scripts.<name>` 通过 `importlib.resources` 定位；custom: `.cataforge/hooks/custom/<name>.py`）→ FAIL on missing
- B6-β: 每个解析到的 hook script .py 必须 `ast.parse` 通过（不依赖 import 副作用）→ FAIL on SyntaxError
- B6-γ: 每个 `matcher_capability` 值必须是 `CAPABILITY_IDS` ∪ `EXTENDED_CAPABILITY_IDS` 成员（typo 会让 hook 静默永不触发）→ FAIL on unknown capability
- B6-δ: 遍历 `.cataforge/platforms/<id>/profile.yaml`，`hooks.degradation` 的 keys 必须严格等于 hooks.yaml 引用的 script name 集合（`custom:` 前缀脱皮后比较）→ 缺失 WARN（deploy 默认 native 可能掩盖真实降级需求）/ 孤儿 WARN（dead config）

## Anti-Patterns
- 禁止: framework-review 报告写入 `docs/reviews/doc/` 或 `docs/reviews/code/` — 必须写 `docs/reviews/framework/`，否则会与业务审查报告混淆并污染 reflector 聚合
- 禁止: 在 TDD / Bootstrap 主循环内自动触发 framework-review — 该 skill 按需触发（用户手动 / `cataforge doctor --deep` 可选附带）
- 禁止: 让 reviewer agent 直接执行 framework-review — reviewer.allowed_paths 限定 docs/reviews/{doc,code,sprint}/，framework-review 应由独立调用方触发，避免审查独立性受污染
- 避免: 把通用规则塞进本 SKILL.md — COMMON-RULES 已自动加载到 Agent 上下文，本 SKILL.md 只描述 framework-review 自身的差异化语义

## 效率策略
- scope 切片: 默认按 scope 过滤检查项，避免一次性扫全部资产产生过长报告
- --focus 进一步收敛: 同 doc-review / code-review 的 Layer 2 收敛策略
- 与 platform-audit 互补: 后者审 IDE 厂商对账，本 skill 审框架内部资产；两者通过统一报告契约协同
