### Changed

- **路径解析统一收敛到 `ProjectPaths`（SSOT）** —— 将散落在 hook runtime、deploy manifest、docs index、framework-review 检查中的 `.cataforge/...` 字面量路径改为经 `cataforge.core.paths.ProjectPaths` 派生。新增 `HOOK_ERROR_LOG_REL` / `DEPLOY_MANIFEST_REL` 常量与 `hook_error_log` / `deploy_manifest` / `docs_dir` 属性，并新增 `find_project_root_or_none()`（无 cwd 回退、无告警）供"非项目内不得动作"的尽力日志/平台探测路径分支使用。删除 `runtime/hook/base.py` 中与 `find_project_root` 重复的 `_find_framework_json` 上行游走逻辑。对外行为等价。
