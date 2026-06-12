### Changed

- **Windows shell 统一走 Git Bash** —— `.claude/settings.json` 以 `env.CLAUDE_CODE_USE_POWERSHELL_TOOL=0` + `defaultShell: bash` 关闭 Claude Code 的 PowerShell 工具；`setup.py --apply-permissions` 在 Windows 上为下游项目写入同样配置（Bootstrap 与 framework-update 自动调用）。Shell 约束从 CLAUDE.md / PROJECT-STATE 模板文字下沉到配置层，模型不再看到 PowerShell 工具。

### Fixed

- **Windows 会话误用 PowerShell** —— harness 在 Git Bash 已安装时仍渐进暴露 PowerShell 工具并设为默认 shell，与项目 Git Bash 约定冲突；现由配置层物理消除该工具，而非依赖 prompt 文字约束。
