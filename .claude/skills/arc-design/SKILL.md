---
name: arc-design
description: "架构设计 — 模块划分、接口定义、数据模型、系统架构建模。"
argument-hint: "<PRD文档路径或功能需求描述>"
suggested-tools: Read, Write, Edit, Glob, Grep
depends: [doc-gen, doc-nav, tech-eval, research]
disable-model-invocation: false
user-invocable: true
---

# 架构设计 (arc-design)
## 能力边界
- 能做: 架构风格选型、模块划分、接口契约定义、数据模型设计、系统上下文建模
- 不做: 需求分析、UI设计、代码实现

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
- 通过doc-nav加载PRD全文(首次需全量理解)
- §1.1 确定项目类型: fullstack | backend-only | CLI | API-only
  (此决定影响orchestrator是否跳过Phase 3 UI设计)
- §1.2 架构风格选型: 结合tech-eval调研结果
  决策标准: 团队规模 / 性能要求 / 部署环境 / 可维护性
  不确定时**必须**通过research skill的user-interview指令向用户确认，不得直接标注[ASSUMPTION]跳过
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
- 接口数 > 10时，通过doc-gen拆分为arch-api分卷

### Step 4: 数据模型 (对应ARCH §4)
- 描述实体关系(1:N / M:N / 继承等，Mermaid erDiagram 格式)
- 定义实体E-{NNN}，字段表格(字段 | 类型 | 约束 | 说明)
- 实体数 > 8时，通过doc-gen拆分为arch-data分卷

### Step 5: 非功能架构 (对应ARCH §5)
- §5.1 性能方案: 缓存策略 / 异步处理 / 分页方案
- §5.2 安全方案: 认证机制 / 授权模型 / 数据加密
- §5.3 错误处理: 错误码体系 / 重试策略 / 降级方案
- 对应PRD§3非功能需求逐项给出架构级方案

### Step 6: 目录结构与开发约定 (对应ARCH §6-§7)
- §6 目录结构: 按模块划分目录树(text格式)
- §7.1 命名规范: 文件/变量/接口命名规则
- §7.2 代码风格: Lint/格式化工具配置
- §7.3 Git约定: 分支策略/Commit格式
- 通过doc-gen finalize交付ARCH

## 效率策略
- 功能→模块映射确保无遗漏
- 接口先于实现，契约驱动
- 执行流程各Step与ARCH模板§1-§7一一对应，减少模板填充时的二次整理
