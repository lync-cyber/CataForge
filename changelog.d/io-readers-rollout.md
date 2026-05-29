### Changed

- **全仓 JSON / YAML 文件读取收敛到 `core.io.read_json` / `read_yaml`** —— 把散落在 deploy / hook / adapter / doctor / mcp / docs / kg / scaffold 等约 30 处的 `json.loads(path.read_text(...))`、`json.load(open(...))` 手写读取统一为 `read_json(path)`，容忍点改捕 `ConfigError`（已同时覆盖 `OSError` + `JSONDecodeError`），抛错点获得带路径的统一报错。行为等价。
