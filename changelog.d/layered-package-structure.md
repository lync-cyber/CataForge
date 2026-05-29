### Changed

- **分层包结构迁移** —— `src/cataforge/` 顶层包重组为分层结构：`cataforge.cli` → `cataforge.interface.cli`、`services` → `application.services`、`deploy`/`agent`/`skill`/`hook`/`mcp`/`plugin` → `runtime.*`、`platform`/`integrations` → `adapter.*`、`kg`/`docs` → `domain.*`、`schema` → `core.schema`（`core`/`utils` 保持顶层）。行为等价。直接 import 这些子模块、或通过 `python -m cataforge.skill.builtins.*` 与 hook 脚本模块路径调用的下游需同步路径；`cataforge` 控制台脚本与 entry-point 组名（`cataforge.plugins` / `cataforge.platforms`）不变。

### Added

- **圈复杂度门禁** —— ruff 启用 `C901`（`max-complexity = 20`），最高复杂度的函数已拆分到阈值以下。
- **分层依赖方向守卫** —— `scripts/checks/check_layer_dependencies.py` 强制 `interface → application → {runtime, domain} → adapter → core → utils` 的模块级 import 方向（lazy / `TYPE_CHECKING` import 豁免，可用 `# allow-layer-dep:` 行内例外），纳入 pre-commit 与 `run_local.py`。
