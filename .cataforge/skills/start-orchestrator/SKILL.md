---
name: start-orchestrator
description: "启动CataForge编排流程 — 从需求到交付的全流程入口。当用户说'开始新项目''继续上次''continue'或描述一个待开发项目、需要初始化或恢复推进编排流程时使用。"
argument-hint: "<项目描述 或 'continue' 继续上次>"
suggested-tools: file_read, file_glob
depends: []
disable-model-invocation: false
user-invocable: true
---

# 启动编排流程 (start-orchestrator)

## 能力边界
- 能做: 判断启动模式（新项目初始化 A / 已有项目恢复 B）、加载 orchestrator 角色定义、框架版本与 framework.json 检查、定位恢复阶段
- 不做: 通过 agent-dispatch 启动 orchestrator 子代理（见 §角色假设）；不替代 orchestrator 各 phase 的编排判定逻辑；不直接写 docs/ 子目录产物

## 角色假设（关键）
**你（当前主线程会话）即是 orchestrator。** 读取 AGENT.md 是为了加载角色定义，**不要通过 agent-dispatch 启动 orchestrator 子代理**。orchestrator 在主线程运行、跨会话持续感知状态，由主线程直接扮演该角色是框架设计的核心约束。

## 输入规范
- 必填: 项目描述自然语言字符串，或 `continue` 关键字（触发分支 B 恢复模式）
- 可选: {INSTRUCTION_FILE}（存在即触发分支 B）+ `.cataforge/framework.json`（版本检查依据）

## 输出规范
- 新项目: 触发 ORCHESTRATOR-PROTOCOLS §Project Bootstrap，产出 {INSTRUCTION_FILE} 初版并进入初始阶段
- 恢复推进: 不产出新文档，仅更新 {INSTRUCTION_FILE} §项目状态 块并继续推进当前阶段
- 本 skill 自身不写入 docs/ 任何子目录（实际文档产出由后续阶段 agent 完成）

## Anti-Patterns
- 不通过 agent-dispatch 调度 orchestrator — 主线程直接扮演 orchestrator 角色；若误派为子代理，orchestrator 失去跨会话主线程状态感知，§项目状态 写权限链路断裂，恢复会话时无法定位进度
- 不跳过 §角色假设 直接进入步骤 — 角色声明是防止误用 agent-dispatch 的唯一显式约束
- 不在分支 B 跳过框架版本检查 — 版本占位符 `0.0.0-template` 表示 scaffold 未初始化，直接恢复会让后续 agent 读到不一致状态
- 不在 `.cataforge/framework.json` 缺失（框架尚未部署）时启动本 skill — 应先用 framework-update 同步包/scaffold 层再交接 start-orchestrator，否则跳过 scaffold 层同步

## 执行步骤

### Step 1: 判断启动模式
- {INSTRUCTION_FILE} 不存在 → 分支 A（新项目）
- {INSTRUCTION_FILE} 存在 → 分支 B（已有项目）

### 分支 A: 新项目启动
1. 读取 {AGENTS_SRC_DIR}/orchestrator/AGENT.md 的角色定义
2. 执行 `{AGENTS_SRC_DIR}/orchestrator/ORCHESTRATOR-PROTOCOLS.md` §Project Bootstrap
   - 其中 Step 2 会通过 AskUserQuestion 询问执行模式（standard / agile-lite / agile-prototype），选项语义见 COMMON-RULES §执行模式矩阵
3. 进入初始阶段（由执行模式决定，见 Bootstrap Step 8）

### 分支 B: 继续已有项目

#### B.1: 框架版本检查
1. 读取 `.cataforge/framework.json` 的 `version` 字段获取当前框架版本
2. 如果 `.cataforge/framework.json` 不存在或 `version` 为占位符（`0.0.0-template`）→ 提示用户: "未检测到框架版本信息，当前框架可能需要重新初始化。可运行 `cataforge setup` 或 `pip install --upgrade cataforge && cataforge upgrade apply` 修复。"
3. 版本检查仅提示，不阻断流程，继续 B.2

#### B.2: 恢复推进
1. 读取 {INSTRUCTION_FILE} 获取当前阶段和项目状态
2. 分支处理:
   - 当前阶段=completed → 提示项目已完成，询问用户意图(新版本/新需求/重新审查)
   - 当前阶段=development 且存在未完成任务 → 定位到当前Sprint和具体任务，恢复TDD流程
   - 用户指定目标阶段（如"从架构设计开始"）→ 验证前置条件后跳转（前置条件校验规则见 ORCHESTRATOR-PROTOCOLS §Phase Transition Protocol，如上游文档须已 approved）
   - 其他 → 正常恢复
3. 读取 {AGENTS_SRC_DIR}/orchestrator/AGENT.md 的角色定义
4. 执行 Startup Protocol 恢复推进
