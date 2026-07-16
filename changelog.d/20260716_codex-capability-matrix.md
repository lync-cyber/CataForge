### Fixed

- codex 能力矩阵对齐实测现状（profile `version_tested: 2026.07`）：skills 面启用原生部署到
  `.agents/skills`（open agent skills 标准，read-first 降级随之退役）；六个 hook 从 degraded
  转 native（guard_frozen_docs / lint_format / log_agent_dispatch / validate_agent_result /
  detect_review_flag / notify_permission，Notification 事件映射到 PermissionRequest）；
  per-agent model 启用（tier_map 更新至 gpt-5.6 / gpt-5.6-terra）；dispatch 契约修正为
  spawn_agent v2（agent_type / message / task_name）。
- hook 运行时消费 `hooks.tool_overrides`（与部署侧 matcher 同一优先级），修复 codex 上
  guard_dangerous 因 payload `tool_name: Bash` 与 tool_map `shell` 失配而静默放行的缺陷；
  新增 `extract_edited_paths` 从 apply_patch 补丁文本解析被改文件路径，guard_frozen_docs /
  lint_format / matcher_file_pattern 过滤在 codex payload 下可用。
- 清理死配置面：`hooks.matcher_map`（schema + 四平台 profile，零消费方）、
  `get_project_root_env_var()`（零调用方）、CODEX_HOME 平台探测（Codex 不注入该变量，
  且会误判其他平台会话）。
