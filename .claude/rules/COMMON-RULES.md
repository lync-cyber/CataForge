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
| approved | 审查通过，无问题 | reviewer | 执行Phase Transition Protocol |
| approved_with_notes | 审查通过但有MEDIUM/LOW建议（无CRITICAL/HIGH时触发） | reviewer | 向用户展示问题列表，用户选择"接受并继续"或"要求修复" |
| needs_revision | 审查不通过(有CRITICAL/HIGH) | reviewer | 进入Revision Protocol |

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
| MIN_REVIEW_SOURCES | 3 | reflector 执行 retrospective 的最小信号源文件数（REVIEW + CODE-REVIEW + CORRECTIONS-LOG 合计） |

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
- 第 N 次审查: `-r{N}`（N = 对应子目录下同前缀 `-r*` 文件数 + 1）
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
