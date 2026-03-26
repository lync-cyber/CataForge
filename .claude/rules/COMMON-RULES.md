# 通用行为规则 (COMMON-RULES)

## 全局约定
- 遵循 CLAUDE.md 效率原则中的全局约定
- Agent间传递 doc_id#section 引用，非全文复制
- 单一事实来源: 每条规则只在一个文件中定义完整内容，其他文件通过"见 {文件}#{章节}"引用，不重述
- 不确定时通过 research skill 调研，不猜测 (详见 .claude/skills/research/SKILL.md)
- 选择题优先：需要用户输入时优先提供选项

## 输出语言
- 所有Agent产出的文档、审查报告、RETRO报告、用户交互均使用**中文**
- 例外: 代码、变量命名、CLI参数、框架参数（doc_type/template_id等）使用英文
- 枚举值（status codes、category、root_cause、severity 等）始终使用英文，即使在中文文本中也不翻译。示例: "问题严重等级为 CRITICAL" 而非 "问题严重等级为严重"

## 统一状态码（共7个）
所有Agent和子代理返回的状态码使用以下枚举:

| 状态码 | 含义 | 使用场景 | orchestrator处理 |
|--------|------|---------|-----------------|
| completed | 任务正常完成 | 所有Agent、TDD子代理 | 提取outputs，进入下一步 |
| needs_input | 需要用户输入才能继续 | 所有Agent | 进入Interrupt-Resume Protocol |
| blocked | 无法继续，需外部干预 | TDD子代理、任何Agent遇到不可恢复错误 | 记录阻塞原因，请求人工介入，不自动重试 |
| rolled-back | 重构失败已回滚 | REFACTOR子代理 | 使用GREEN阶段产出，标记MEDIUM |
| approved | 审查通过，无问题 | reviewer | 更新文档状态，进入下一Phase |
| approved_with_notes | 审查通过但有MEDIUM/LOW建议（无CRITICAL/HIGH时触发） | reviewer | 向用户展示问题列表，用户选择"接受并继续"或"要求修复" |
| needs_revision | 审查不通过(有CRITICAL/HIGH) | reviewer | 进入Revision Protocol |

## Revision Protocol（子代理侧）
> orchestrator 侧的调度逻辑见 ORCHESTRATOR-PROTOCOLS.md §Revision Protocol。本节定义子代理收到 revision 任务后的执行步骤。

当 task_type = revision 时，执行以下修订流程:

1. **加载REVIEW报告** — 从 `docs/reviews/` 下找到编号最大的 `REVIEW-{doc_id}-r{N}.md` 或 `CODE-REVIEW-{task_id}-r{N}.md` 加载审查报告
2. **分析问题列表** — 按严重等级排序 (CRITICAL > HIGH > MEDIUM > LOW)
3. **增量修复** — 仅修复 CRITICAL 和 HIGH 级别问题:
   - 使用 doc-gen write-section 修改相关章节
   - 不重新执行完整 Skill Toolkit 流程，除非 REVIEW 明确要求整章重写
4. **重新finalize** — 修复完成后调用 doc-gen finalize 更新文档
5. **返回产出路径** — 与新建任务相同的返回格式

注意: Revision 是在已有文档基础上的增量修订，不是从零开始。

## Continuation Protocol
> 本协议定义**子代理侧**的恢复执行步骤。orchestrator 侧的调度逻辑见 ORCHESTRATOR-PROTOCOLS.md §Interrupt-Resume Protocol。agent-dispatch 负责将两者衔接。

当 task_type = continuation 时，执行以下恢复流程:

1. **加载中间产出** — 从 continuation 参数的 `上次中间产出` 文件路径列表中读取已完成的工作
2. **应用用户回答** — 将 `用户回答` 中的决策作为后续内容的依据，不再对已回答的问题重复提问
3. **定位恢复点** — 根据 `恢复指引` 确定应从 Skill Toolkit 的哪个步骤继续执行
4. **从恢复点继续** — 在已有中间产出基础上继续执行剩余步骤，使用 doc-gen write-section 就地编辑已有文档
5. **正常返回** — 完成后返回与 new_creation 相同格式的产出路径列表 + 执行摘要

注意: Continuation 是在中间产出基础上的恢复执行，文档已存在(status=draft)，直接编辑即可。

## Amendment Protocol（子代理侧）
> orchestrator 侧的调度逻辑见 ORCHESTRATOR-PROTOCOLS.md §Change Request Protocol。本节定义子代理收到 amendment 任务后的执行步骤。

当 task_type = amendment 时，执行以下变更修订流程:

1. **加载变更分析** — 从 amendment 参数中读取 `<change-analysis>` XML 和用户变更描述
2. **定位影响章节** — 根据 affected_docs 中的 doc_id#section 引用定位需修订的章节
3. **增量修订** — 根据变更描述和 change_type 修订受影响的章节:
   - clarification: 仅澄清措辞，不改变语义
   - enhancement: 扩展已有定义，新增条目或修改约束
   - new_requirement: 新增章节或重大改写
4. **保持一致性** — 修订后检查内部交叉引用仍然有效
5. **重新finalize** — 修订完成后调用 doc-gen finalize 更新文档
6. **返回产出路径** — 与 new_creation 相同的返回格式

注意: Amendment 与 Revision 的区别 — Revision 以 REVIEW 报告为输入修复审查问题，Amendment 以变更分析为输入适应用户变更。

## 通用 Error Handling
所有Agent遇到以下场景时按统一策略处理:

| 场景 | 处理策略 |
|------|---------|
| 输入信息模糊/不完整 | 通过research skill的user-interview指令向用户确认(选择题优先，每批≤3题) |
| 上游文档间存在矛盾 | 以上游权威文档为准(PRD→ARCH→DEV-PLAN)，标注差异并在当前文档备注 |
| 所需信息缺失且无法从用户获取 | 标注[ASSUMPTION]给出合理默认值，确保可追溯 |
| 技术方案存在多个合理选项 | 通过tech-eval或research记录对比，标注推荐项和理由 |

## 框架配置常量
以下常量为框架级参数，各文件引用时以本节为准:

| 常量名 | 值 | 说明 |
|--------|-----|------|
| MAX_QUESTIONS_PER_BATCH | 3 | 每批向用户提问的最大问题数 |
| MIN_REVIEW_SOURCES | 3 | reflector 执行 retrospective 的最小信号源文件数（REVIEW + CODE-REVIEW + CORRECTIONS-LOG + MICRO-RETRO 合计） |

## 文档引用格式
Agent 间传递文档引用时使用以下统一格式:

```
{doc_id}#§{section_number}[.{item_id}]
```

| 示例 | 含义 |
|------|------|
| `prd#§2` | PRD 文档第 2 章（功能需求） |
| `prd#§2.F-003` | PRD 文档第 2 章中的 F-003 条目 |
| `arch#§3.API-001` | 架构文档第 3 章中的 API-001 接口 |
| `dev-plan#§1` | 开发计划第 1 章（Sprint 规划表） |

规则:
- `doc_id` = template_id（见 doc-gen 映射表），如 prd、arch、dev-plan
- `section_number` 为纯数字（1, 2, 3...）
- `item_id` 为条目编号（F-xxx, M-xxx, API-xxx, E-xxx, T-xxx, C-xxx, P-xxx）
- 分卷文件的引用格式不变，doc-nav 负责定位到正确的分卷文件

## maxTurns 指南
Agent 的 maxTurns 基准值:

| Agent 类型 | 基准 maxTurns | 说明 |
|-----------|-------------|------|
| 文档类 Agent（product-manager, architect, ui-designer, tech-lead） | 30 | 文档生成含多轮 doc-gen 操作 |
| 代码执行类（test-writer, implementer, refactorer） | 20 | 单任务聚焦，工具调用密集 |
| 质量检查类（reviewer, qa-engineer） | 20-30 | 取决于审查范围 |
| 部署/回顾类（devops, reflector） | 15-30 | 流程较短 |
| orchestrator | 200 | 主编排线程，覆盖全生命周期 |

原则: 每个 turn 约对应 1 次工具调用，maxTurns ≈ 预期工具调用数 × 1.5。
超限应对: 子代理应在剩余 turns 不足时主动 finalize 已完成内容并返回 needs_input，由 orchestrator 以 continuation 模式恢复。

## 通用 Anti-Patterns
- 禁止: 猜测项目状态，以 CLAUDE.md 和 docs/ 目录为唯一事实来源
- 禁止: 遗留未标注的 TODO/TBD/FIXME (必须标注 [ASSUMPTION])
- 禁止: 写入 CLAUDE.md 项目状态区 (orchestrator 专属)

## 统一问题分类体系
所有审查报告（文档审查和代码审查）使用以下统一分类:

| category | 适用范围 | 说明 |
|----------|---------|------|
| completeness | 文档+代码 | 逻辑缺失、定义不全 |
| consistency | 文档+代码 | 与上游/内部矛盾 |
| convention | 文档+代码 | 命名/格式/风格规范 |
| security | 文档+代码 | 安全漏洞、合规风险 |
| feasibility | 文档 | 技术可行性、实现性 |
| ambiguity | 文档 | 模糊不清、多义 |
| structure | 代码 | 架构/组织/耦合 |
| error-handling | 代码 | 异常处理、边界条件 |
| performance | 代码 | 性能/效率 |

## 审查报告规范
所有审查报告（doc-review 和 code-review）共享以下规范。各 Skill 的 Layer 1 检查项和 Layer 2 审查维度分别定义在各自 SKILL.md 中。

### 报告编号规则
- 首次审查: `REVIEW-{doc_id}-r1.md` 或 `CODE-REVIEW-{task_id}-r1.md`
- 第 N 次审查: `-r{N}`（N = docs/reviews/ 下同前缀 `-r*` 文件数 + 1）
- 最新版本 = 编号最大的文件，无需归档重命名

### 问题格式
```
### [R-{NNN}] {SEVERITY}: {标题}
- **category**: {问题分类，见 §统一问题分类体系}
- **root_cause**: {归因分类}
- **描述**: {问题描述}
- **建议**: {改进建议}
```

### 归因分类 (root_cause) 枚举
| root_cause | 含义 |
|------------|------|
| self-caused | 当前 Agent/开发者自身的遗漏或错误 |
| upstream-caused | 上游文档质量问题传导或定义不清导致的偏差 |
| input-caused | 用户输入不足或模糊 |
| reviewer-calibration | 审查标准争议 |

### 三态判定逻辑
| 条件 | 结论 |
|------|------|
| 存在 CRITICAL 或 HIGH 问题 | **needs_revision** |
| 无 CRITICAL/HIGH，但有 MEDIUM/LOW 问题 | **approved_with_notes** |
| 无问题 | **approved** |

## Skill depends 字段语义
SKILL.md frontmatter 中的 `depends` 字段含义:
- 列出本 Skill 执行过程中**会调用**的其他 Skill（调用链依赖）
- 也包含前置条件型依赖（需先完成的 Skill，如 penpot-implement depends penpot-sync）
- 不包含运行环境依赖（如 Python、Node.js）
- 不用于运行时自动校验，仅供开发者参考和 Agent-Skill 匹配审查
- `suggested-tools` 必须包含本 Skill 所有执行路径中**直接使用**的工具（通过 depends 间接使用的工具不重复列出）
