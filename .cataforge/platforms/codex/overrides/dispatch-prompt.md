<!-- OVERRIDE:dispatch_syntax -->
调度（两步式）:
  Step 1: spawn_agent(agent_type="{agent_id}", task_name="<小写下划线任务名>", message=下方prompt内容)
  Step 2: wait_agent(<Step 1 返回的 agent id>)
  message: |
<!-- /OVERRIDE:dispatch_syntax -->

<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - 请首先读取 {RULES_DIR}/COMMON-RULES.md（Codex 不自动注入规则文件）
    - 你的角色定义见 {AGENTS_SRC_DIR}/{agent_id}/AGENT.md
<!-- /OVERRIDE:startup_notes -->

<!-- OVERRIDE:tool_usage -->
    === 平台工具说明 ===
    - 文件编辑使用 apply_patch
    - 命令执行使用 shell
    - 不可使用 AskUserQuestion（异步模式，如需输入返回 blocked）
    - 使用 send_input 向运行中的子代理发送后续指令
<!-- /OVERRIDE:tool_usage -->

<!-- OVERRIDE:context_limits -->
    === 上下文限制 ===
    - 子代理不继承主线程对话上下文，所需输入一律传路径引用、由子代理自行 Read
    - 优先分拆为多个子任务而非一次性完成
    - 产出中避免复制输入内容
    - 模型支持自动 compaction，超长会话会自动压缩早期上下文
<!-- /OVERRIDE:context_limits -->
