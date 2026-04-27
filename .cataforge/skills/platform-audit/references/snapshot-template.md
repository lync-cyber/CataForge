# 平台能力快照模板

`Phase 1 / Step 3` 用，整理时**不写文件、保持在上下文中**，作为 Phase 2 差异对比的输入。每个目标平台填一份。

```
Platform: <id>
Version: <latest version>

=== Core Tool Names (10) ===
file_read:       <native name or null>
file_write:      <native name>
file_edit:       <native name>
file_glob:       <native name or null>
file_grep:       <native name or null>
shell_exec:      <native name>
web_search:      <native name or null>
web_fetch:       <native name or null>
user_question:   <native name or null>
agent_dispatch:  <native name>

=== Extended Capabilities (4) ===
notebook_edit:   <native name or null>
browser_preview: <native name or null>
image_input:     <native name or null>
code_review:     <native name or null>

=== Hook Events ===
PreToolUse:      <platform event name or null>
PostToolUse:     <platform event name>
Stop:            <platform event name or null>
SessionStart:    <platform event name or null>
Notification:    <platform event name or null>

=== Hook Matcher Overrides ===
<capability>: <override name if different from tool_map>

=== Agent Config ===
Format: yaml-frontmatter | toml | json
Scan dirs: <paths>
Supported fields: <list>
Memory scopes: <list or none>
Isolation modes: <list or none>

=== Features (17) ===
cloud_agents: true/false
agent_teams: true/false
parallel_agents: true/false
scheduled_tasks: true/false
background_agents: true/false
plan_mode: true/false
computer_use: true/false
realtime_voice: true/false
multi_model: true/false
session_resume: true/false
worktree_isolation: true/false
autonomy_slider: true/false
ci_cd_integration: true/false
multi_root: true/false
agent_memory: true/false
plugin_marketplace: true/false
context_management: true/false

=== Permissions ===
Modes: <list>

=== Model Routing ===
Available models: <list>
Per-agent model: true/false

=== Other ===
Context window: <size>
Default model: <model>
Sandbox: <mode>
MCP: <support level>
```

> 17 个 features 的语义见 `src/cataforge/core/types.py::PLATFORM_FEATURES`；17 个 agent frontmatter 字段见同文件 `AGENT_FRONTMATTER_FIELDS`。
