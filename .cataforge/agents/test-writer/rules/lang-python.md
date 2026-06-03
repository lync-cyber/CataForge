# Python · 测试编写细则

## 框架与工具栈

- 测试框架：**pytest**（行业主流，插件生态最丰富）
- 覆盖率：**pytest-cov**（`--cov=src --cov-report=term-missing`）；目标行覆盖率由项目配置，典型基线 80%
- 异步测试：**pytest-asyncio**（`asyncio_mode = "auto"` 写入 `pyproject.toml`）
- HTTP 桩：**respx**（httpx）/ **responses**（requests）

最小配置（`pyproject.toml`）：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src --cov-report=term-missing -q"
```

## 断言风格

- 使用原生 `assert`，依靠 pytest rewrite 获得详细失败输出；不用 `assertEqual` 等 unittest 方法
- 浮点比较用 `pytest.approx`：`assert result == pytest.approx(0.1 + 0.2)`
- 断言须能真正失败，不写 `assert x is not None` 这类恒真断言充数；每个被测函数覆盖边界值与异常路径，不要只测正常输入
- 异常断言：

```python
import pytest

def test_raises_value_error():
    with pytest.raises(ValueError, match="invalid input"):
        parse("")
```

## Fixture 与 Setup/Teardown

```python
import pytest

@pytest.fixture
def db_session(tmp_path):
    """提供一个隔离的临时数据库会话。"""
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture(scope="module")
def api_client():
    """模块级客户端，避免重复初始化。"""
    from httpx import Client
    with Client(base_url="http://testserver") as client:
        yield client
```

- `scope` 优先用 `function`（隔离最好）；确认无副作用后才升 `module` / `session`

## 参数化测试

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("",      ""),
    ("  ",    "  "),
])
def test_upper(input, expected):
    assert upper(input) == expected
```

## Mock / Stub

- 优先使用 **pytest monkeypatch**（简单属性替换、环境变量）
- 复杂行为用 `unittest.mock.MagicMock` / `AsyncMock`：

```python
from unittest.mock import AsyncMock, patch

async def test_fetch_user(monkeypatch):
    mock_get = AsyncMock(return_value={"id": 1})
    monkeypatch.setattr("myapp.client.get_user", mock_get)
    result = await fetch_user(1)
    mock_get.assert_awaited_once_with(1)
    assert result["id"] == 1
```

- 禁止 mock 被测单元本身的内部实现；mock 边界处的外部依赖

## 测试文件命名与分层

- 单元测试：`tests/unit/test_<module>.py`
- 集成测试：`tests/integration/test_<feature>.py`
- 测试函数命名：`test_<被测函数>_<场景>_<预期>`（如 `test_parse_empty_string_raises`）
