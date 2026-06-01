### Added

- **`cataforge phase status`** —— 只读校验当前 SDLC 阶段应有产物（阶段非占位符、期望文档存在且已 index、有 phase_start、文档状态非未开始），缺失即非零退出。
- **platform-audit 离线子集** —— `cataforge skill run platform-audit -- --offline` 静态跑 conformance + 一致性 + profile schema，FAIL 级阻断 PR、已接入 CI guards。
- **`cataforge setup --context-strategy`** —— 显式选 `kg-first` / `doc-only` 上下文后端，scaffold 缺失时交互提示。
- **profile 时效守卫** —— `check_profile_version_tested` 进 anti-rot 周扫，平台 profile 超 180 天未更新即告警。

### Changed

- **conformance 一致性检查升 WARN** —— web_fetch→shell 工具替换、computer_use×browser_preview 路由不可见、worktree_isolation 缺 isolation 字段、native 离群 hook、deploy_rules 路径偏离。
- **opencode 插件携带 matcher_agent_id 前置过滤** —— 非匹配 agent 不再 spawn Python 进程。
- **framework-review B9** —— migration_checks 三维结构审查（path 真实性 / allow_missing 类型 / deprecate_after 时序）。
- **doctor 反向孤儿检出** —— 部署 manifest 中 source 已删的 skill 发 WARN。

### Fixed

- **claude-code `reads_claude_md`** —— 订正为 `true`（原 `false` 与原生加载 CLAUDE.md 语义相反）。
- **section-merge 保留下游手写指令文件** —— 与模板零 schema/runtime 重叠时整体保留 + 仅追加框架导航，不再注入模板章节。
- **translator skills 字段降级提示** —— codex/opencode 不部署 skills 时丢弃 `skills:` 发 WARN，不再静默。
