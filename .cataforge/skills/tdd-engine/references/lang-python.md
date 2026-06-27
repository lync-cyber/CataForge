# Python · 实现编码细则

## 格式化与 Lint

- 格式化工具：**ruff format**（black 兼容，速度更快）；不单独引入 black
- Lint 工具：**ruff check**（涵盖 pyflakes / pycodestyle / isort / flake8-bugbear 等规则集）
- 最小配置（写入 `pyproject.toml`）：

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "SIM"]
ignore = ["E501"]   # 由 formatter 管理行长
```

- CI 中跑 `ruff check . && ruff format --check .`；本地提交前通过 pre-commit 自动触发

## 类型注解惯例

- 所有公共函数、方法签名须完整注解；私有函数按需注解
- Python 3.10+：使用 `X | None` 代替 `Optional[X]`；使用内置 `list[str]`、`dict[str, int]` 代替 `List` / `Dict`
- 推迟求值（`from __future__ import annotations`）在需要前向引用时添加
- `TypeVar` / `Generic` 用于容器型工具函数；避免过度泛化导致可读性下降
- 不要用 `# type: ignore` / `# noqa` 掩盖类型错误，应消除根因；确需豁免时同行附理由说明

## 错误处理惯用法

- 优先抛出具体异常（继承自标准库或自定义基类），而非返回 `None` / 错误码
- 自定义异常继承链示例：`AppError → DomainError → SpecificError`
- 资源管理一律用 `with` 语句（上下文管理器）；临时资源可用 `contextlib.contextmanager`
- 捕获异常须具名：`except ValueError as e`；禁止裸 `except:` 或 `except Exception: pass`
- 跨层传播时用 `raise NewError(...) from original_err` 保留原始上下文
- 对可能为 `None`、空集合或抛异常的路径写显式处理，不要只覆盖正常输入
- 调用标准库 / 第三方 API 前确认函数与签名真实存在，不要凭记忆拼方法名

## 项目/模块结构

推荐 **src 布局**（避免导入时误引用未安装包）：

```
project-root/
├── src/
│   └── my_pkg/
│       ├── __init__.py
│       ├── core/
│       └── utils/
├── tests/
├── pyproject.toml
└── README.md
```

- 每个模块职责单一；公共 API 在 `__init__.py` 显式 `__all__` 导出
- 循环导入是设计坏味道，应通过拆分接口层或延迟导入解决

## 常用标准库与惯用工具

| 需求 | 推荐 |
|------|------|
| 路径操作 | `pathlib.Path`（禁止 `os.path` 字符串拼接） |
| 配置/环境变量 | `os.environ` + pydantic `BaseSettings` |
| 日期时间 | `datetime`（UTC 存储，带时区）；序列化用 `isoformat()` |
| 不可变数据 | `dataclasses(frozen=True)` 或 `pydantic` |
| 枚举 | `enum.Enum` / `enum.StrEnum`（Python 3.11+）|
| 延迟计算 | `functools.cached_property`；集合操作用生成器表达式 |
