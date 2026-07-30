### Added

- 新增类型化 `CapabilityBinding`、条件能力解析、hook policy/fallback、问题交互归一化、
  agent 权限编译与每平台 `capability-report.json`。

### Changed

- Codex `user_question` 映射为条件原生 `request_user_input`；`detect_correction` 使用
  `PostToolUse(request_user_input)` 原生 hook 加 partial 人工记录 fallback。
- Codex agent 权限改为 `inherit_only`，不再输出无效的 allow/deny 字段；可证明全写能力
  被禁止时才编译为 `sandbox_mode = "read-only"`，其余限制显式标为 `unenforced`。

### Removed

- 0.19.0 直接移除 scalar/null capability、`hooks.tool_overrides`、
  `hooks.degradation` 与 `degradation_templates` 兼容解析。
