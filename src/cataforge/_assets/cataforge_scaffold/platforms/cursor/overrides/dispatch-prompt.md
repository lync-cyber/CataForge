<!-- OVERRIDE:dispatch_syntax -->
Task:
  subagent_type: "{agent_id}"
  description: "Phase {N}: {简短描述}"
  prompt: |
<!-- /OVERRIDE:dispatch_syntax -->

<!-- OVERRIDE:startup_notes -->
    === 启动须知 ===
    - COMMON-RULES.md 已通过 .cursor/rules/（兼容路径: .claude/rules/）自动注入上下文
    - 你的 AGENT.md 已通过 subagent_type 自动加载
<!-- /OVERRIDE:startup_notes -->

<!-- OVERRIDE:tool_usage -->
    === 平台工具说明 ===
    - 文件编辑使用 edit_file（非 Edit）
    - 命令执行使用 run_terminal_cmd（非 Bash）
    - 子代理调度使用 Task（非 Agent）
    - 无原生 WebFetch 工具
<!-- /OVERRIDE:tool_usage -->
