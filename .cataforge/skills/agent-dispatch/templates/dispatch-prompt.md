# Agent Dispatch Prompt Template
> 本文件为 agent-dispatch 的核心 prompt 模板。
> 含 OVERRIDE 标记点，由 template_renderer 根据当前平台合并 override 后使用。

<!-- OVERRIDE:dispatch_syntax -->
Agent tool:
  subagent_type: "{agent_id}"
  description: "Phase {N}: {简短描述}"
  prompt: |
<!-- /OVERRIDE:dispatch_syntax -->

    当前项目: {项目名}。

    <!-- BEGIN COMMON-SECTIONS -->
<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - COMMON-RULES.md 已通过 .claude/rules/ 自动注入上下文，无需手动读取
    - 你的 AGENT.md 已通过 subagent_type 自动加载
<!-- /OVERRIDE:startup_notes -->
    - 开始工作前，阅读你的核心 Skill 的 SKILL.md（见 AGENT.md skills 列表）
    - 通用 Skill（doc-gen/doc-nav）仅在需要操作时查阅
    - 所有文档和报告输出使用中文（代码、变量命名、框架参数除外）
    - 信息不足时标注[ASSUMPTION]并给出合理默认值

    === 任务信息 ===
    任务: {task}
    任务类型: {task_type}
    输入文档: {input_docs}
    输出要求: {expected_output}
    {仅revision: REVIEW报告: {review_path}}
    {仅continuation: 用户回答: {answers}}
    {仅continuation: 上次中间产出: {intermediate_outputs}}
    {仅continuation: 恢复指引: {resume_guidance}}
    {仅amendment: 变更分析: {change_analysis}}
    {仅amendment: 变更描述: {change_description}}
    {仅当Adaptive Review触发时由orchestrator注入:
    === 本项目已识别的反复问题 ===
    - {category}: {问题描述}，已出现{N}次
    }

<!-- OVERRIDE:tool_usage -->
<!-- /OVERRIDE:tool_usage -->

    === 执行约束 ===
    - 新建文档(task_type=new_creation)至少执行一轮用户确认

<!-- OVERRIDE:return_format -->
    === 返回格式(必须严格遵循) ===
    完成后，你的最终回复中**必须**包含以下XML块:

    <agent-result>
    <status>completed|needs_input|blocked|approved|approved_with_notes|needs_revision|rolled-back</status>
    <outputs>产出物文件路径，逗号+空格分隔</outputs>
    <summary>执行摘要(≤3句)</summary>
    </agent-result>

    status 值含义见 COMMON-RULES §统一状态码。

    needs_input 时**必须**追加:
    <questions>[{"id":"Q1","text":"问题","options":["A: 说明","B: 说明"]}]</questions>
    <completed-steps>已完成的Skill步骤编号</completed-steps>
    <resume-guidance>从第N步恢复，具体上下文</resume-guidance>

    blocked 时**可选**追加 <questions> 字段描述需要澄清的问题。
<!-- /OVERRIDE:return_format -->

<!-- OVERRIDE:context_limits -->
<!-- /OVERRIDE:context_limits -->

    <!-- END COMMON-SECTIONS -->

    === 返回示例 ===
    <!-- completed: 仅含 status+outputs+summary -->

    needs_input:
    <agent-result>
    <status>needs_input</status>
    <outputs>docs/arch/arch-myapp-v1.md</outputs>
    <summary>已完成模块划分，数据库选型需用户确认。</summary>
    </agent-result>
    <questions>[{"id":"Q1","text":"数据库选型","options":["A: PostgreSQL — 关系型","B: MongoDB — 文档型"]}]</questions>
    <completed-steps>Step 1, Step 2, Step 3</completed-steps>
    <resume-guidance>从Step 4数据模型设计恢复，§1-§3已完成</resume-guidance>
