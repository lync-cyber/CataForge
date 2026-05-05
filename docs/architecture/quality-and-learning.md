# 质量闸与学习系统

> CataForge 通过多层质量闸保证产出质量，并通过学习系统自动提取跨项目经验。

## 1. 文档审查（doc-review）

```text
Layer 1 — 脚本检查：
  ├── 结构完整性（必要章节是否齐全）
  ├── 格式合规性（标题层级、编号格式）
  ├── 交叉引用有效性（doc_id#§section 引用是否可解析）
  └── 常量引用正确性

Layer 2 — AI 审查（可按文档类型跳过）：
  ├── 语义一致性（与上游文档是否矛盾）
  ├── 业务逻辑正确性
  ├── 完整性（需求是否遗漏）
  └── 可行性评估

跳过条件（阈值位于 `.cataforge/framework.json → constants`）：
  - 文档行数 < DOC_REVIEW_L2_SKIP_THRESHOLD_LINES（默认 200）
  - 文档类型 ∈ DOC_REVIEW_L2_SKIP_DOC_TYPES
```

## 2. 代码审查（code-review）

```text
Layer 1 — Lint 检查：
  ├── ruff / eslint 等工具自动检查
  └── 格式化验证

Layer 2 — AI 审查：
  ├── 架构合规性（是否符合 arch 设计）
  ├── 安全性（OWASP Top 10 等）
  ├── 业务逻辑正确性
  └── 测试覆盖充分性
```

## 2.1 Layer 1 调用协议（single entry）

> **本节为接口契约（Reference 性质），混在 Architecture 文档中是出于 Layer 1 与 Layer 2 衔接说明的需要。** 完整 CLI 参数定义见 [`../reference/cli.md`](../reference/cli.md) §skill；状态码定义见 [`../reference/status-codes.md`](../reference/status-codes.md) §1。

三个审查 Skill（`doc-review` / `code-review` / `sprint-review`）的 Layer 1 脚本**唯一合法入口**为：

```
cataforge skill run <skill-id> -- <args...>
```

由 `SkillRunner` 解析 SKILL.md 元数据后派发——对内置脚本走 `python -m cataforge.skill.builtins.<pkg>.<script>`，对项目覆写脚本走 `python <project-script-path>`。**不得**直接 `python .cataforge/skills/<id>/scripts/*.py`：该路径为框架内部实现细节，在仅发放 SKILL.md（无 `scripts/` 目录）的默认 scaffold 中不存在。

当项目仅覆写了 SKILL.md 文本（`scripts=[]`）而未提供自己的脚本时，`SkillLoader` 自动回落到内置脚本（参见 `SkillLoader._merge_builtin_fallback`），无需手动桥接。

失败分类（SKILL.md 必须按以下四态处理 Layer 1 返回）：

| 退出码 / 异常 | 语义 | 动作 |
|---|---|---|
| `0` | 通过 | 进入 Layer 2 |
| `1` | 发现问题 | 报告问题，不进 Layer 2 |
| `2` / `127` / `CataforgeError("no executable scripts")` | 脚本不可达 | **FAIL**（先 `cataforge doctor`） |
| Python 运行异常 / 超时 | 降级 | 标注"Layer 1 降级"并进入 Layer 2 |

`cataforge doctor` 在 `Review skill Layer 1 reachability` 段对三个 Skill 做一次性可达性检查，防止脚本路径错配再次潜伏。

## 3. 问题分类体系

审查发现的问题按 9 类（`completeness` / `consistency` / `convention` / `security` / `feasibility` / `ambiguity` / `structure` / `error-handling` / `performance`）× 4 严重等级（`CRITICAL` > `HIGH` > `MEDIUM` > `LOW`）组织。修订流程仅处理 `CRITICAL` 与 `HIGH`。

完整表格与每类举例见 [`../reference/status-codes.md`](../reference/status-codes.md) §2、§3；修订协议见 [`runtime-workflow.md`](./runtime-workflow.md) §4。

---

## 4. Sprint Review

每完成 `SPRINT_REVIEW_MICRO_TASK_COUNT` 个微任务（默认 3），由 `reviewer` Agent 调用 `sprint-review` skill 审查：

- AC（acceptance criteria，验收标准）覆盖率
- 范围偏移检测（是否引入了超出计划的改动）
- 完成度一致性
- 输出 `docs/reviews/sprint/SPRINT-<n>.md`

---

## 5. On-Correction Learning

通过 `detect_correction` hook 自动捕获用户对 Agent 决策的覆盖：

```text
1. Agent 通过 AskUserQuestion 提供选项
2. 用户选择了 Agent 未推荐的选项（option-override 信号）
3. Hook 捕获此信号并记录到 CORRECTIONS-LOG.md
4. 当 self-caused 问题（指 Agent 输出本身造成的错误，区别于用户输入引起的错误）累计达到 RETRO_TRIGGER_SELF_CAUSED（默认 5）次时
5. 触发 reflector Agent 进行回顾分析
```

### 5.1 Deviation 类型

`cataforge correction record --deviation <type>` 把每一条偏离归入五个互斥类别，决定后续路径：

| 值 | 含义 | 触发后续 |
|----|------|----------|
| `preference` | 纯偏好，不算缺陷 | 仅留存档 |
| `self-caused` | 下游自身造成的偏离 | 累计 ≥ `RETRO_TRIGGER_SELF_CAUSED`（默认 5）→ §6 Reflector 回顾 |
| `external` | 外部约束（依赖、政策） | 仅留存档 |
| `framework-bug` | CataForge 框架本体缺陷（崩溃、行为错误） | 由 `cataforge feedback bug` 上报 |
| `upstream-gap` | 上游 baseline 本身对此项目场景不准/不全（行为没崩，但建议不到位） | 累计 ≥ `RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT`（默认 3）→ §8 上游反馈通道 |

`framework-bug` 与 `upstream-gap` 正交：前者是"框架坏了，需要修"，后者是"框架建议在此场景下不合适，需要更新指引或补充选项"。两者都不会通过 reflector 回顾积累内部经验，而是通过 §8 直接回流到 CataForge 上游仓库。

---

## 6. Reflector 回顾

`reflector` Agent 按以下流程提取经验：

```text
1. 聚合 CORRECTIONS-LOG.md 中的问题记录
2. 按 (agent, category) 维度分组统计
3. 对每组问题至少需要 2 条证据才生成 EXP 条目
4. 生成经验条目（EXP entries）→ .cataforge/learnings/
5. 提出 SKILL-IMPROVE 建议（改进 Skill 定义）
6. 校准评审标准（Adaptive Review）
```

---

## 7. 经验积累路径

```text
Agent 决策
    ↓
Reviewer 发现问题（按 9 类 + 4 等级）
    ↓
CORRECTIONS-LOG.md
    ↓
Reflector 聚合（阈值触发）
    ↓
.cataforge/learnings/EXP-*.md
    ↓
下次 Agent 通过 doc-nav 加载相关经验，避免重蹈覆辙
```

---

## 8. 上游反馈通道（Downstream → CataForge upstream）

§5–§7 关注的是"项目内"的学习闭环。CataForge 框架本体的演进还需要另一条独立通道：把下游使用中发现的框架问题 / 改进建议 / 累积的 `upstream-gap` 纠偏回流到上游仓库。

### 8.1 触发面

| 来源 | 类型 | 推荐入口 |
|------|------|----------|
| 用户人工发现框架 bug | `bug` | `cataforge feedback bug --gh` |
| 用户人工提建议 | `suggest` | `cataforge feedback suggest --clip` |
| 累计 `upstream-gap` 纠偏 ≥ 阈值 | `correction-export` | orchestrator 自动调起 `framework-feedback` skill 落盘到 `docs/feedback/` 后由用户决定是否上报 |

### 8.2 数据流

```text
本地诊断信号                     → cataforge.core.feedback assembler
  ├── cataforge --version              ─┐
  ├── cataforge doctor (FAIL/WARN 抽取) │
  ├── 最近 N 条 EVENT-LOG.jsonl        │  → 单个 markdown body
  ├── CORRECTIONS-LOG (deviation=       │     (默认脱敏 ~ / <project>)
  │     upstream-gap 过滤)              │
  └── framework-review Layer 1 FAIL    ─┘
                                         ↓
四选一互斥 sink (--print / --out / --clip / --gh)
                                         ↓
                  上游 .github/ISSUE_TEMPLATE/feedback-from-cli.yml
                  (字段与 body 1:1 对齐)
```

### 8.3 等价入口

* **CLI**：`cataforge feedback <bug|suggest|correction-export>`，给人 / pipeline 用
* **Skill**：`cataforge skill run framework-feedback -- <kind>`，给 orchestrator / agent 用；`record-to-event-log: true`，每次运行写一条 `state_change` 到 `EVENT-LOG`，便于跟踪下游反馈频次

两者共用 `cataforge.core.feedback` 同一份 assembler，差别仅在 skill 路径会触发 EVENT-LOG instrumentation。

### 8.4 命名边界

* `framework-feedback` 与 `framework-review` 平行：都针对 `.cataforge/` 框架本体，与下游产品自身的用户反馈渠道无关
* `framework-bug` deviation 表"框架坏了"；`upstream-gap` deviation 表"框架建议不到位"。前者通常一次就上报，后者按阈值聚合上报

详细参数见 [`../reference/cli.md` §feedback](../reference/cli.md#feedback) 与 [`../reference/agents-and-skills.md`](../reference/agents-and-skills.md) §管理 Skill。

---

## 参考

- 运行时流程与修订协议：[`runtime-workflow.md`](./runtime-workflow.md)
- 审查相关 Skill 详细定义：[`../reference/agents-and-skills.md`](../reference/agents-and-skills.md)
- 状态码全集：[`../reference/status-codes.md`](../reference/status-codes.md)
