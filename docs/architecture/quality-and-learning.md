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

跳过条件：
  - 文档行数 < DOC_REVIEW_L2_SKIP_THRESHOLD_LINES（200）
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

## 3. 问题分类体系

审查发现的问题按 9 类分类：

| 类别 | 说明 |
|------|------|
| `completeness` | 内容完整性 |
| `consistency` | 与上下游文档 / 代码的一致性 |
| `convention` | 命名 / 格式 / 编码规范 |
| `security` | 安全性问题 |
| `feasibility` | 技术可行性 |
| `ambiguity` | 表述模糊 |
| `structure` | 文档 / 代码结构 |
| `error-handling` | 错误处理 |
| `performance` | 性能相关 |

严重等级：**CRITICAL > HIGH > MEDIUM > LOW**

审查结果状态：

- `approved`：审查通过
- `approved_with_notes`：通过但有 MEDIUM/LOW 建议
- `needs_revision`：存在 CRITICAL/HIGH 问题，需要修订（见 [`runtime-workflow.md`](./runtime-workflow.md) §4）

---

## 4. Sprint Review

每完成 `SPRINT_REVIEW_MICRO_TASK_COUNT` 个微任务（默认 3），由 `reviewer` Agent 调用 `sprint-review` skill 审查：

- AC（验收标准）覆盖率
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
4. 当 self-caused 问题累计达到 RETRO_TRIGGER_SELF_CAUSED（5）次时
5. 触发 reflector Agent 进行回顾分析
```

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

## 参考

- 运行时流程与修订协议：[`runtime-workflow.md`](./runtime-workflow.md)
- 审查相关 Skill 详细定义：[`../reference/agents-and-skills.md`](../reference/agents-and-skills.md)
- 状态码全集：[`../reference/status-codes.md`](../reference/status-codes.md)
