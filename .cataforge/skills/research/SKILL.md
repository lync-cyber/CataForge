---
name: research
description: "调查研究 — 网络检索、用户访谈、资料查阅，解决不确定性。"
argument-hint: "<调研模式: web-search|user-interview|doc-lookup> <问题描述>"
suggested-tools: Read, Glob, Grep, WebSearch, WebFetch, AskUserQuestion
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 调查研究 (research)
## 能力边界
- 能做: 网络检索(web-search)、用户访谈(user-interview)、资料查阅(doc-lookup)
- 不做: 替Agent做决策、生成文档内容

## 调研决策树
Agent遇到不确定性时:
- 信息可从网络获取? → web-search
- 信息取决于用户偏好/业务决策? → user-interview (选择题优先)
- 信息在已有文档中? → doc-lookup (通过doc-nav加载)
- 以上均不适用? → 标注为[ASSUMPTION]并在文档中声明

## 操作指令

### 指令1: 网络检索 (web-search)
触发场景: 技术选型/最佳实践/竞品分析/API文档查阅
执行步骤:
1. 使用 WebSearch 工具搜索相关信息
2. 使用 WebFetch 获取具体页面内容
3. 整理为结构化调研摘要(来源 + 结论 + 可信度)
4. 通过doc-gen创建research-note文档记录调研结果
5. 标注来源URL和可信度评级

### 指令2: 用户访谈 (user-interview)
触发场景: 需求模糊/缺失/存在多个合理选项
工具: AskUserQuestion (前台子代理和主线程Agent均可直接使用；仅后台子代理需使用指令2b)
执行步骤:
1. 组织问题: 一次最多3个问题，每问题最多4个选项
2. 每个选项包含简短说明帮助决策
3. 通过AskUserQuestion向用户展示并等待回答
4. 收集完信息后写入当前文档相关章节
5. 不猜测，收集完再继续

降级触发条件: AskUserQuestion 工具调用返回错误（工具不可用、权限被拒等运行时错误）时触发降级，切换到指令2b。用户回答"其他"或回答不完整**不触发降级**，应追问澄清。

### 指令2b: 用户访谈 — 降级 (user-interview-deferred)
触发条件: AskUserQuestion 调用失败或工具不可用
步骤:
1. 保存已完成工作到正式文档路径（status=draft）
2. 以 `<agent-result>` 格式返回 needs_input 状态 + 问题列表 + 中间产出路径
3. orchestrator 通过 Interrupt-Resume Protocol 代为提问后以 continuation 模式恢复

### 指令3: 资料查阅 (doc-lookup)
触发场景: 需要参考已有项目文档/技术规范
执行步骤:
1. 通过doc-nav的load-section指令加载相关章节
2. 提取并汇总相关信息
3. 将摘要返回给调用Agent

## 效率策略
- 选择题优先，降低用户回答成本
- 调研结果直接写入文档，避免二次整理
- 所有假设标注[ASSUMPTION]，可追溯
