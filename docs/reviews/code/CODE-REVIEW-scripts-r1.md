# CODE-REVIEW-scripts-r1

- **审查范围**: `.claude/scripts/` 目录下全部 Python 脚本（7 个）+ 1 个 Shell 脚本
- **审查类型**: 代码审查（功能正确性 + 代码气味 + 重复冗余 + 过度包装）
- **Layer 1**: Lint hook 未配置，ruff 未安装，Python lint 跳过 — Layer 1 delegated (tool unavailable)
- **审查日期**: 2026-04-12

---

## 问题列表

### [R-001] HIGH: `upgrade.py` 的 `_load_dotenv()` 未实际加载环境变量

- **category**: error-handling
- **root_cause**: self-caused
- **文件**: `.claude/scripts/upgrade.py:452-454`
- **描述**: `_load_dotenv()` 的 docstring 声称"从 .env 文件加载配置到 os.environ"，但实际调用 `load_dotenv()` 时未传 `set_env=True`，因此 `.env` 中的变量（如 `GITHUB_TOKEN`、代理配置）**不会**写入 `os.environ`。下游 `get_github_token()` (line 467) 通过 `os.environ.get()` 读取 token，在用户仅在 `.env` 中配置 token 的场景下将静默获取空值，导致 GitHub API 认证失败。
- **建议**: 修改为 `load_dotenv(set_env=True)`，或删除 `_load_dotenv()` 包装函数直接调用 `load_dotenv(set_env=True)`。

### [R-002] MEDIUM: `setup_penpot.py` 使用已废弃参数名 `override=True`

- **category**: convention
- **root_cause**: self-caused
- **文件**: `.claude/scripts/setup_penpot.py:1084`
- **描述**: `load_dotenv(override=True)` 使用了向后兼容的旧参数名。`_common.py` 中 `load_dotenv` 的当前签名是 `set_env`，`override` 通过 `**kwargs` 兼容处理。功能上不影响运行，但：1) 依赖兼容层增加认知负担；2) 如果未来移除兼容层会静默失败。
- **建议**: 改为 `load_dotenv(set_env=True)`。

### [R-003] MEDIUM: `upgrade.py` 中 `read_project_phase()` 与 `phase_reader.py` 功能重复

- **category**: structure
- **root_cause**: self-caused
- **文件**: `.claude/scripts/upgrade.py:851-859` vs `.claude/scripts/phase_reader.py:16-44`
- **描述**: 两处实现功能相同（从 CLAUDE.md 读取当前阶段），但实现细节不同：`phase_reader.py` 逐行读取并处理模板占位符，`upgrade.py` 使用 `f.read()` + 正则。`upgrade.py` 已 import `_common` 但未复用 `phase_reader`。
- **建议**: `upgrade.py` 改为 `from phase_reader import read_current_phase`，删除自有的 `read_project_phase()`。

### [R-004] MEDIUM: `setup.py` 的 `load_env_proxy()` 手动实现了 `load_dotenv(set_env=True)` 的子集

- **category**: structure
- **root_cause**: self-caused
- **文件**: `.claude/scripts/setup.py:134-141`
- **描述**: `load_env_proxy()` 调用 `load_dotenv()` 获取字典，再手动逐一写入 `os.environ`（仅代理相关 key）。这个"仅加载代理变量"的需求本身合理，但实现中 `load_dotenv()` 不传 `set_env=True` 后又手动写入的模式，与 `_common.load_dotenv(set_env=True)` 的"仅写入尚未设置的变量"语义完全重合。如果意图是只加载代理变量而非全部变量，当前实现正确但应加注释说明意图。
- **建议**: 添加注释说明"此处有意仅加载代理变量而非全部 .env 变量"，或改用 `load_dotenv(set_env=True)` 后删除手动写入逻辑。

### [R-005] LOW: 遗留 Shell 脚本 `setup-penpot-mcp.sh` 可能为死代码

- **category**: completeness
- **root_cause**: self-caused
- **文件**: `.claude/scripts/setup-penpot-mcp.sh`
- **描述**: `setup_penpot.py` 已完整实现了 Penpot 部署 + MCP 注册功能（含 `mcp-only` 子命令）。Shell 脚本似乎是 Python 改写前的遗留版本。如果仍有外部引用则需保留，否则属于死代码。
- **建议**: 确认无外部引用后删除，或在文件头添加 deprecation 注释指向 `setup_penpot.py`。

### [R-006] LOW: `_common.py` 的 `load_dotenv` 向后兼容 `override` 参数增加维护负担

- **category**: structure
- **root_cause**: self-caused
- **文件**: `.claude/scripts/_common.py:87-109`
- **描述**: `load_dotenv` 函数通过 `**kwargs` 接受旧参数名 `override` 并映射到 `set_env`。目前仅 `setup_penpot.py` 一处使用旧名。兼容层使函数签名不直观，且 `**kwargs` 吞掉了拼写错误的参数名（虽然有显式检查）。
- **建议**: 修复 R-002 后，移除 `**kwargs` 兼容层，函数签名回归简洁。

### [R-007] LOW: `event_logger.py` 验证枚举集合与 schema 文件可能不同步

- **category**: consistency
- **root_cause**: self-caused
- **文件**: `.claude/scripts/event_logger.py:36-70`
- **描述**: `VALID_EVENTS`、`VALID_STATUSES`、`VALID_TASK_TYPES` 三个集合硬编码在 Python 中，而权威定义在 `.claude/schemas/event-log.schema.json`。如果 schema 更新但脚本未同步，会导致新增的合法事件类型被拒绝。
- **建议**: 考虑在脚本启动时从 schema JSON 动态加载枚举值，或在代码注释中标注"需与 event-log.schema.json 保持同步"。

### [R-008] LOW: `_common.py` 的 `_load_dotenv` wrapper（`upgrade.py` 中）为不必要的间接层

- **category**: structure
- **root_cause**: self-caused
- **文件**: `.claude/scripts/upgrade.py:452-454`
- **描述**: `_load_dotenv()` 仅是对 `load_dotenv()` 的一行包装，没有添加任何逻辑（连 `set_env=True` 都未传）。这属于过度包装，增加了一层不必要的间接调用。
- **建议**: 删除 `_load_dotenv()`，调用处直接使用 `load_dotenv(set_env=True)`。

---

## 审查总结

| 严重等级 | 数量 |
|----------|------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 4 |

**高优先级问题**: R-001 是实际 bug — `upgrade.py` 的远程升级功能在用户仅通过 `.env` 配置 GitHub token 时无法正常认证，属于功能正确性问题。

**主题归纳**:
1. **`.env` 加载语义不统一** (R-001, R-002, R-004, R-006, R-008): 多个脚本对 `load_dotenv` 的使用方式不一致，部分未传 `set_env=True` 导致环境变量未注入，部分使用废弃参数名，部分手动重复注入逻辑。建议统一为：需要环境变量注入时显式传 `set_env=True`。
2. **功能重复** (R-003, R-005): `phase_reader` 功能在 `upgrade.py` 中重复实现；Shell 脚本被 Python 版本替代后未清理。

---

## 判定

**needs_revision** — 存在 1 个 HIGH 问题 (R-001: `_load_dotenv()` 未实际加载环境变量，影响 upgrade 远程功能)。
