### Changed

- **framework-review 检查的 profile.yaml / hooks.yaml 读取改用 `core.io.read_yaml`** —— `b5` / `b6` / `b7` 的 `yaml.safe_load(path.read_text(...))` + `except (OSError, yaml.YAMLError)` 收敛为 `read_yaml(path)` + `except ConfigError`，移除各文件对 `yaml` 的直接依赖。行为等价（缺失文件由既有 `is_file()` 前置判断处理）。
