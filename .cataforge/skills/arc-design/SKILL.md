---
name: arc-design
description: "架构设计 — 模块划分、接口定义、数据模型、系统架构建模。当 PRD 完成、需要做架构风格选型、模块划分、接口契约或数据模型设计时使用此 skill。本 skill 不做需求分析（req-analysis）与 UI 设计（ui-design）。"
argument-hint: "<PRD文档路径或功能需求描述>"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep
depends: [context, tech-eval, research]
disable-model-invocation: false
user-invocable: true
---

# 架构设计 (arc-design)
## 能力边界
- 能做: 架构风格选型、模块划分、接口契约定义、数据模型设计、系统上下文建模
- 不做: 需求分析（req-analysis）、UI 设计（ui-design）、代码实现（implementer/TDD）

## 输入规范
- PRD功能需求(F-{NNN}列表)
- PRD非功能需求
- 技术选型结果(来自tech-eval)

## 输出规范
- 架构概览(风格 + 系统上下文图)
- 模块划分(M-{NNN})，每个模块映射PRD功能点
- 接口契约(API-{NNN})，完整request/response定义
- 数据模型(E-{NNN})，字段含类型和约束
- 目录结构 + 开发约定

## 执行流程

### Step 1: 需求分析与架构决策 (对应ARCH §1)
- 通过 `cataforge context read prd#§2`（功能需求）/ `prd#§3`（非功能需求）按需分章节加载，不一次性读取 PRD 整篇（见 COMMON-RULES §文档加载纪律）
- §1.1 确定项目类型: fullstack | backend-only | CLI | API-only
  (此决定影响orchestrator是否跳过Phase 3 UI设计)
- §1.2 架构风格选型: 结合tech-eval调研结果
  决策标准: 团队规模 / 性能要求 / 部署环境 / 可维护性
  不确定时**必须**通过research skill的user-interview指令向用户确认，不得直接标注[ASSUMPTION]跳过
  决策记录: 选型结果须包含"考虑了X和Y，选择X因为{理由}，当{条件}时应重新评估"
- §1.3 系统上下文图: Mermaid C4Context 格式(系统边界、外部依赖、用户交互)
- §1.4 技术栈: 每项技术填写(层次 | 技术 | 版本 | 选型理由 | 调研来源)表

### Step 2: 模块划分 (对应ARCH §2)
- 从PRD功能点(F-{NNN})推导模块(M-{NNN})
- 每个模块包含:
  - **职责**: 单一职责描述
  - **映射功能**: F-{NNN}列表(引用PRD)
  - **对外接口**: API-{NNN}列表(引用接口分卷)
  - **依赖模块**: M-{NNN}列表
  - **内部关键组件**: 类/组件列表
- 验证: 所有F-{NNN}至少被一个M-{NNN}覆盖(无遗漏)
- 模块间依赖应为有向无环

### Step 3: 接口契约 (对应ARCH §3)
- 为每个对外接口定义API-{NNN}
- 格式使用YAML:
  ```yaml
  path: /api/v1/{resource}
  method: POST
  module: M-{NNN}
  request:
    headers: { Authorization: "Bearer {token}" }
    body:
      field1: { type: string, required: true, desc: "{说明}" }
  response:
    200: { schema: "{ResponseType}" }
    400: { schema: "ErrorResponse" }
  ```
- 必填: request headers + body字段(type + required + desc)
- 必填: response成功码 + 错误码schema
- 接口数 > 10时，通过context拆分为arch-api分卷

### Step 4: 数据模型 (对应ARCH §4)
- 描述实体关系(1:N / M:N / 继承等，Mermaid erDiagram 格式)
- 定义实体E-{NNN}，字段表格(字段 | 类型 | 约束 | 说明)
- 实体数 > 8时，通过context拆分为arch-data分卷

### Step 5: 非功能架构 (对应ARCH §5)
- §5.1 性能方案: 缓存策略 / 异步处理 / 分页方案
- §5.2 安全方案: 认证机制 / 授权模型 / 数据加密
- §5.3 错误处理: 错误码体系 / 重试策略 / 降级方案
- §5.4 配置管理: 环境变量清单 / 配置文件格式与加载策略 / 敏感信息(secrets)处理方式。所有可变参数须外部化，禁止硬编码在文档或代码中。本节定义配置形态决策；实际 CI/CD 配置文件生成由 deploy-config 负责
- 对应PRD§3非功能需求逐项给出架构级方案

### Step 6: 目录结构与开发约定 (对应ARCH §6-§7)
- §6 目录结构: 按模块划分目录树(text格式)
- §7.1 命名规范: 文件/变量/接口命名规则
- §7.2 代码风格: Lint/格式化工具配置
- §7.3 Git约定: 分支策略/Commit格式
- 通过context finalize交付ARCH

## Anti-Patterns
- 禁止: 在 ARCH 主卷塞入实现细节代码 —— ARCH 写接口契约 / 数据流 / 模块边界；实现归 implementer 的 src/，越界让两层职责粘连
- 禁止: 跳过 §5.4 配置管理章节 —— 没有配置形态决策（环境变量清单 / 加载策略 / secrets 处理）的 ARCH 让 deploy-config 与 devops 无据可依，下游断链
- 禁止: 模块划分循环依赖 —— ARCH 阶段的依赖图必须是 DAG；循环会让 tech-lead 任务拆解无起点
- 避免: 把多个候选方案并列写在 ARCH 正文 —— 终态决策入 ARCH，候选讨论进 research-note 或 decision-log
- 避免: 不假思索套用"微服务 + PostgreSQL + Redis + Docker + Nginx"全家桶 —— 小型项目单体架构通常更易维护，架构复杂度须匹配 PRD§3 非功能需求的实际约束

## 效率策略
- 功能→模块映射确保无遗漏
- 接口先于实现，契约驱动
- 执行流程各Step与ARCH模板§1-§7一一对应，减少模板填充时的二次整理
