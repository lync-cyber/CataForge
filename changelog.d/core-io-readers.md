### Added

- **`cataforge.core.io.read_json` / `read_yaml`** —— 集中"读 UTF-8 文本 → 解析 → 失败时带路径抛 `ConfigError`"模式（此前在约 30 处手写）。空 YAML 文档归一为 `{}`。供"配置文件缺失/损坏应清晰报错"的读取点复用；刻意容忍缺失的尽力读取点保留各自的 try/except 默认值语义。

### Changed

- **`ConfigManager.load` / `load_raw` 经 `read_json` 读取 framework.json** —— framework.json 损坏时抛出统一的 `ConfigError`（在 CLI 边界渲染为 `Error: Malformed JSON in ...`）而非裸 `json.JSONDecodeError`。`collect_environment` 相应改为捕获 `ConfigError` 以维持对损坏配置的诊断容忍。
