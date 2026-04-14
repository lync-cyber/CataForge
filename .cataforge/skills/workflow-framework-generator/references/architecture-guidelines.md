# 框架架构设计指南

本文档定义 workflow-framework-generator 在生成框架时必须遵循的架构原则和设计约束。

---

## 核心架构原则

### 1. 单一事实来源 (Single Source of Truth)

- `.cataforge/framework.json` 是框架级配置的唯一来源
- 每个 Agent 的 `AGENT.md` 是其角色定义的唯一来源
- 每个 Skill 的 `SKILL.md` 是其能力定义的唯一来源
- 平台差异由 `profile.yaml` 集中管理，不散落在各文件中

### 2. 能力标识符抽象

**规则**: 所有 Agent 和 Skill 定义中的工具引用必须使用 CataForge 能力标识符，不使用平台原生名称。

```yaml
# 正确
tools: file_read, file_write, shell_exec

# 错误
tools: Read, Write, Bash
```

平台原生名称仅出现在 `profile.yaml` 的 `tool_map` 中，由 deployer 在部署时翻译。

### 3. 文件系统即消息总线

Agent 间不共享内存、不直接通信。所有状态传递通过文件系统:

```
Agent A 写入 → docs/phase-a/output.md → Agent B 读取
```

好处:
- 上下文隔离，每个 Agent 只加载必要信息
- 状态可审计（文件即记录）
- 断点续传（从文件恢复状态）

### 4. 渐进式复杂度

生成的框架应匹配工作流的实际复杂度:

| 工作流复杂度 | Agent 数量 | Skill 数量 | 工作流模式 |
|------------|-----------|-----------|-----------|
| 简单 (2-3步) | 1-2 | 1-3 | 线性 |
| 中等 (4-6步) | 3-5 | 3-6 | 线性+门禁 |
| 复杂 (7+步) | 5-10 | 5-10 | 线性+分支+并行 |

**过度设计信号**:
- Agent 数量超过工作流步骤数
- Skill 仅被一个 Agent 使用且逻辑不足10行
- 工作流有超过3层嵌套

### 5. 开闭原则

生成的框架支持扩展而无需修改已有文件:

- 新增 Agent: 创建新目录 + AGENT.md → 工作流引用
- 新增 Skill: 创建新目录 + SKILL.md → Agent 引用
- 新增平台: 创建新 profile.yaml → framework.json 切换

---

## Agent 设计指南

### 角色定义

每个 Agent 必须满足:

1. **单一职责**: 一个 Agent 负责一个明确的职能领域
2. **自包含**: Agent 的指令包含完成任务所需的全部信息
3. **可替换**: 替换一个 Agent 不影响其他 Agent 的功能
4. **无副作用**: Agent 只写入 `allowed_paths` 声明的路径

### maxTurns 设置

根据任务复杂度设置:

| 任务类型 | maxTurns | 示例 |
|---------|----------|------|
| 简单产出 | 20-30 | 单一文档生成、格式转换 |
| 中等产出 | 50-80 | 分析报告、代码模块 |
| 复杂产出 | 100-150 | 架构设计、完整功能开发 |
| 编排控制 | 150-200 | orchestrator |

### Orchestrator 必备能力

当 multi_agent=true 时，orchestrator 必须具备:

1. **阶段路由**: 根据当前状态决定下一个激活的 Agent
2. **状态感知**: 读取 PROJECT-STATE.md 了解当前进度
3. **质量门禁**: 检查每个阶段的产出是否满足质量标准
4. **错误恢复**: 处理子代理的非正常状态 (needs_revision, blocked)
5. **用户交互**: 在关键决策点征询用户意见

---

## Skill 设计指南

### 类型选择

| 类型 | 特征 | 适用场景 |
|------|------|---------|
| instructional | 纯指令，无可执行脚本 | 流程指导、协议定义 |
| executable | 有 scripts/ 目录，可直接运行 | 数据处理、格式转换、校验 |
| hybrid | 指令 + 脚本结合 | 需要LLM判断+自动化处理 |

### 提取标准

将逻辑提取为独立 Skill 的条件（满足任一即可）:

1. **跨 Agent 复用**: 两个以上 Agent 需要相同能力
2. **独立可测试**: 该逻辑有明确的输入输出，可独立验证
3. **领域完整**: 该逻辑构成一个完整的领域操作（如"代码审查"）
4. **频繁变更**: 该逻辑可能随业务需求频繁调整

不应提取为 Skill 的逻辑:
- 仅在一个 Agent 内使用的简单逻辑
- 与 Agent 角色紧密耦合的决策逻辑
- 不足 10 行指令的简单操作

---

## Workflow 设计指南

### 编排模式

#### 线性模式
```yaml
phases: [A → B → C → D]
```
适用: 步骤间有严格先后依赖

#### 线性 + 门禁模式
```yaml
phases: [A → gate → B → gate → C]
```
适用: 每个阶段产出需要质量审查

#### 并行模式
```yaml
phases: [A, B] → merge → C
```
适用: 独立步骤可同时执行
注意: 需要目标平台支持 parallel_agents

#### 修订循环模式
```yaml
phases: [A → B → review → {pass: C, fail: B}]
```
适用: 产出需要反复打磨

#### 迭代深化模式
```yaml
phases: [explore → analyze → synthesize → {complete: report, incomplete: explore}]
```
适用: 问题域需要逐步深入理解

### 状态流转

```
                    ┌── needs_revision ──┐
                    │                    ↓
 initial → active → completed → next_phase
                ↓                    ↑
         needs_input → [user input] ─┘
                ↓
            blocked → [manual intervention]
```

### 质量门禁设置

在以下位置设置门禁:

1. **高影响决策点**: 架构决策、技术选型等不可轻易回退的决策
2. **下游依赖密集**: 多个后续步骤依赖该产出
3. **外部交付物**: 最终交付给用户/客户的产出

门禁类型:
- **automated**: 脚本检查（格式、完整性）
- **review**: Agent 审查（内容质量、逻辑一致性）
- **manual**: 用户人工确认（业务决策、最终审批）

---

## 跨平台适配指南

### 适配优先级

1. **优先使用原生能力**: 平台原生支持的功能优先使用
2. **组合替代**: 用多个可用工具组合实现等效功能
3. **指令降级**: 将自动化逻辑降级为 Agent 指令中的手动步骤
4. **标记不可用**: 明确标注不可用能力及其影响

### 平台特定注意事项

#### CodeX 异步调度
CodeX 的 `spawn_agent` 是异步的，orchestrator 需要:
- 使用轮询或回调机制等待结果
- 处理可能的并发文件冲突
- 设置合理的超时时间

#### OpenCode 无并行
OpenCode 不支持并行代理，需要:
- 将并行步骤转为串行
- 调整 workflow 预期执行时间
- 避免设计需要并行才能工作的逻辑

#### Cursor 无 user_question
Cursor 没有稳定的 user_question 工具，需要:
- 在 Agent 指令中预设"信息不足时的行为"
- 使用输出文件中的 `[CONFIRM]` 标记需要用户确认的项
- orchestrator 定期检查 `[CONFIRM]` 标记并汇总提问

---

## 反模式清单

| 反模式 | 说明 | 正确做法 |
|--------|------|---------|
| 平台泄漏 | Agent 指令中出现平台原生工具名 | 使用能力标识符 |
| 上帝 Agent | 一个 Agent 承担所有职责 | 按职责拆分 |
| 过度拆分 | 每个小操作都独立 Agent | 合并相关职责 |
| 循环依赖 | Agent A 依赖 B，B 依赖 A | 重构为单向依赖或合并 |
| 隐式通信 | Agent 间通过约定俗成的文件名通信 | 在 Input/Output Contract 中显式声明 |
| 空壳 Skill | Skill 仅转发请求无附加逻辑 | 删除或合并到 Agent |
| 硬编码路径 | Agent 中写死文件路径 | 使用配置或参数传入 |
