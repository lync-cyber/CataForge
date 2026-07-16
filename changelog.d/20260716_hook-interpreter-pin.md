### Fixed

- **hook 命令解释器钉死为 deploy 进程自身 `sys.executable`** —— 此前生成的 hook 命令用裸 `python`，cataforge 经 `uv tool install` / pipx 装在隔离 venv 时（尤其 Windows 上裸 `python` 解析到 Microsoft Store shim），每次 hook 触发都 `ModuleNotFoundError`。现在 deploy 生成的所有 hook 命令（内置 `-m` 模块、`custom:` 脚本、OpenCode TS 插件的 `spawn`、`cataforge hook test`）统一写入 deploy 进程自身解释器的带引号正斜杠路径——能跑 deploy 的解释器必然能 import cataforge，对 uv tool / pipx / venv pip 任何安装方式自动正确。settings 合并的框架自有条目识别从「前缀匹配」改为「标记子串匹配」（`-m cataforge.runtime.hook.scripts.` / `.cataforge/hooks/custom/`），存量裸 `python`、任意绝对路径解释器的旧条目重新 deploy 时都会被替换而非留下新旧重复 hook。
