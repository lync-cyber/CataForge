# 领域工作流模式库

本文档收录常见领域的工作流模式，供 workflow-framework-generator 在架构规划阶段参考。
每个模式包含：推荐的 Agent 角色、核心 Skill、工作流编排模式和关键产出物。

---

## 1. 软件开发 (Software Development)

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 阶段路由、状态管理、质量门禁 |
| product-manager | 产品经理 | 需求分析、PRD 撰写 |
| architect | 架构师 | 技术选型、架构设计 |
| tech-lead | 技术主管 | 任务分解、开发计划 |
| implementer | 实现者 | TDD 开发、代码实现 |
| reviewer | 审查者 | 代码/文档审查、质量门禁 |
| tester | 测试者 | 测试策略、QA 验证 |
| devops | 运维 | 部署配置、CI/CD |

### 核心 Skill
- tdd-engine: TDD三阶段开发 (RED→GREEN→REFACTOR)
- code-review: 代码审查 (lint + AI 双层)
- doc-gen: 文档生成与模板填充
- task-decomp: 任务分解为可执行开发任务

### 工作流模式
```
requirements → architecture → dev-planning → development → testing → deployment
     ↑              ↑              ↑              ↑            ↑
     └── review ────┴── review ────┴── review ────┴── review ──┘
```
- 模式: 线性 + 门禁
- 每个阶段产出经过 reviewer 审查后才进入下一阶段
- 支持修订循环 (needs_revision → 同阶段重新执行)

### 关键产出物
- docs/requirements/PRD.md
- docs/architecture/ARCH.md
- docs/dev-plan/DEV-PLAN.md
- src/ (代码) + tests/ (测试)
- docs/deployment/DEPLOY.md

---

## 2. 内容创作 (Content Creation)

### 子领域变体
- **公众号写作**: 选题→大纲→正文→排版→发布
- **博客写作**: 主题研究→结构→草稿→编辑→SEO优化→发布
- **书籍写作**: 提纲→章节规划→初稿→修订→校对→排版
- **视频脚本**: 选题→脚本→分镜→旁白→审核

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 流程管理、进度跟踪 |
| planner | 策划者 | 选题分析、内容规划、受众定位 |
| researcher | 调研员 | 素材收集、竞品分析、数据调研 |
| writer | 撰稿人 | 内容创作、初稿撰写 |
| editor | 编辑 | 内容修改、风格统一、质量把控 |
| seo-optimizer | SEO优化师 | 关键词优化、标题优化、元数据 |
| publisher | 发布者 | 格式转换、平台适配、发布操作 |

### 核心 Skill
- content-plan: 选题分析与内容规划
- content-gen: 按模板和风格指南生成内容
- content-edit: 内容编辑与润色
- seo-optimize: SEO 关键词和结构优化
- format-convert: Markdown→HTML/微信排版/PDF转换

### 工作流模式
```
planning → research → writing → editing → [seo] → publishing
    ↑                    ↑         ↑
    └── revision ────────┴─────────┘
```
- 模式: 线性 + 修订循环
- writing→editing 可能多次循环
- SEO 阶段可选（取决于发布渠道）

### 关键产出物
- docs/plan/content-plan.md (选题+大纲)
- docs/research/research-notes.md (调研素材)
- docs/draft/draft-v{N}.md (草稿迭代)
- docs/final/article.md (定稿)
- docs/publish/publish-config.yaml (发布配置)

---

## 3. 电商运营 (E-commerce Operations)

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 流程协调、任务分发 |
| market-analyst | 市场分析师 | 市场调研、竞品分析、趋势洞察 |
| product-selector | 选品专员 | 选品策略、供应链评估 |
| copywriter | 文案策划 | 商品描述、营销文案、广告创意 |
| campaign-manager | 投放经理 | 广告策略、预算分配、投放优化 |
| data-analyst | 数据分析师 | 数据采集、指标分析、报告生成 |
| customer-ops | 客户运营 | 用户分层、复购策略、客服话术 |

### 核心 Skill
- market-research: 市场数据采集与分析
- product-analysis: 商品数据评估与选品推荐
- copy-gen: 营销文案批量生成
- campaign-plan: 投放计划与预算规划
- data-report: 数据可视化与报告生成

### 工作流模式
```
market-research ──→ product-selection ──→ copy-creation
        │                                      │
        ↓                                      ↓
  data-analysis ←── campaign-execution ←── campaign-planning
        │
        ↓
  optimization-report
```
- 模式: 并行 + 汇总
- 市场调研和选品可并行
- 文案和投放计划可并行
- 最终汇总为优化报告

### 关键产出物
- docs/research/market-report.md
- docs/products/selection-report.md
- docs/content/product-copies/ (批量文案)
- docs/campaigns/campaign-plan.md
- docs/analytics/performance-report.md

---

## 4. 研究分析 (Research & Analysis)

### 子领域变体
- **技术调研**: 技术选型评估、可行性分析
- **行业分析**: 市场规模、竞争格局、趋势预测
- **学术研究**: 文献综述、方法论、实验设计
- **数据分析**: 数据清洗、统计分析、可视化

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 研究计划管理、进度协调 |
| researcher | 研究员 | 信息检索、文献收集、一手资料获取 |
| analyst | 分析师 | 数据分析、模式识别、洞察提取 |
| synthesizer | 综合者 | 跨源信息整合、主题提炼 |
| critic | 评审者 | 论证审查、偏差检测、方法论评估 |
| reporter | 报告撰写 | 研究报告撰写、可视化呈现 |

### 核心 Skill
- literature-search: 文献/资料检索与筛选
- data-analysis: 数据处理与统计分析
- synthesis: 多源信息综合与主题提炼
- argument-review: 论证逻辑审查
- report-gen: 研究报告生成

### 工作流模式
```
scope-definition → information-gathering → analysis → synthesis → reporting
       ↑                    ↑                 ↑           ↑
       └──── deep-dive ─────┴── iteration ────┴── review ─┘
```
- 模式: 迭代深化
- 每轮迭代可能引发新的调研方向
- 分析→综合→审查→再分析的循环
- 深度优先探索特定主题

### 关键产出物
- docs/scope/research-plan.md
- docs/sources/literature-notes/ (文献笔记)
- docs/analysis/analysis-report.md
- docs/synthesis/synthesis-report.md
- docs/final/research-report.md

---

## 5. 教育培训 (Education & Training)

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 课程管理、学习路径编排 |
| curriculum-designer | 课程设计师 | 学习目标、课程大纲、知识图谱 |
| content-creator | 内容创作者 | 教材编写、案例设计、习题设计 |
| assessor | 评估设计师 | 评估标准、考核设计、反馈机制 |
| reviewer | 审查者 | 内容准确性、教学法审查 |

### 核心 Skill
- curriculum-plan: 课程规划与学习路径设计
- lesson-gen: 课时内容生成
- quiz-gen: 习题与评估生成
- knowledge-map: 知识图谱构建

### 工作流模式
```
needs-analysis → curriculum-design → content-creation → assessment-design → review
       ↑                                    ↑                    ↑
       └──────────── iteration ─────────────┴────────────────────┘
```
- 模式: 线性 + 迭代
- 内容创作和评估设计可并行

---

## 6. 项目管理 (Project Management)

### Agent 角色
| Agent ID | 角色 | 核心职责 |
|----------|------|---------|
| orchestrator | 编排者 | 项目协调、状态追踪 |
| planner | 计划者 | 范围定义、WBS分解、排期 |
| risk-analyst | 风险分析师 | 风险识别、评估、应对策略 |
| tracker | 跟踪者 | 进度监控、偏差分析 |
| reporter | 报告者 | 状态报告、汇报材料生成 |

### 核心 Skill
- wbs-decompose: WBS 工作分解
- schedule-plan: 排期与资源规划
- risk-assess: 风险评估矩阵
- status-report: 项目状态报告生成

### 工作流模式
```
initiation → planning → execution-monitoring → reporting → closure
                 ↑              ↑                  │
                 └── replanning ┴── status-update ──┘
```
- 模式: 周期循环
- 执行监控和报告持续循环

---

## 通用模式提取规则

当遇到未收录的领域时，按以下规则提取模式：

1. **识别核心流程**: 该领域从输入到产出的主要步骤是什么？
2. **识别角色**: 每个步骤需要什么专业角色？合并相似角色
3. **识别复用逻辑**: 哪些操作跨步骤重复？提取为 Skill
4. **确定编排模式**:
   - 步骤间有严格前后依赖 → 线性
   - 步骤间可独立执行 → 并行
   - 产出需要反复打磨 → 修订循环
   - 问题域需要逐步深入 → 迭代深化
   - 活动周期性重复 → 周期循环
5. **确定质量门禁**: 哪些步骤的产出质量影响最终结果？设置审查关卡
6. **Agent 数量控制**: 初始不超过 5 个，随复杂度增长不超过 10 个
