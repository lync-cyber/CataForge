---
name: start-orchestrator
description: "启动CataForge编排流程 — 从需求到交付的全流程入口。新项目初始化或已有项目恢复推进。"
argument-hint: "<项目描述 或 'continue' 继续上次>"
suggested-tools: Read, Glob
depends: []
disable-model-invocation: false
user-invocable: true
---

# 启动编排流程 (start-orchestrator)

## 能力边界
- 能做: orchestrator 编排流程的用户入口
- 不做: 替代 orchestrator 的编排逻辑

## 执行步骤

### Step 1: 判断启动模式
- CLAUDE.md 不存在 → 分支 A（新项目）
- CLAUDE.md 存在 → 分支 B（已有项目）

### 分支 A: 新项目启动
1. 读取 .claude/agents/orchestrator/AGENT.md 的角色定义
2. 执行 `.claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` §Project Bootstrap
3. 进入 Phase 1

### 分支 B: 继续已有项目

#### B.1: 框架版本检查
1. 读取 pyproject.toml 的 `[project].version` 获取当前框架版本
2. 如果 pyproject.toml 不存在 → 提示用户: "未检测到版本元数据文件(pyproject.toml)，当前框架可能需要升级。可运行 `python .claude/scripts/upgrade.py <新版路径>` 升级。"
3. 版本检查仅提示，不阻断流程，继续 B.2

#### B.2: 恢复推进
1. 读取 CLAUDE.md 获取当前阶段和项目状态
2. 分支处理:
   - 当前阶段=completed → 提示项目已完成，询问用户意图(新版本/新需求/重新审查)
   - 当前阶段=development 且存在未完成任务 → 定位到当前Sprint和具体任务，恢复TDD流程
   - 用户指定目标阶段（如"从架构设计开始"）→ 验证前置条件后跳转
   - 其他 → 正常恢复
3. 读取 .claude/agents/orchestrator/AGENT.md 的角色定义
4. 执行 Startup Protocol 恢复推进
