# Python · 调试诊断细则

## 调试器使用

- **pdb**：标准库内置，无需安装；在关键行插入 `breakpoint()`（Python 3.7+，等价于 `import pdb; pdb.set_trace()`）
- **ipdb**：pdb 的 IPython 增强版，支持语法高亮和 Tab 补全；`pip install ipdb` 后设置 `PYTHONBREAKPOINT=ipdb.set_trace`
- **IDE debugger**（VS Code / PyCharm）：配合 launch.json / pytest 插件，支持条件断点、变量监视；推荐用于复杂场景
- 关键 pdb 命令：`n`（next）、`s`（step into）、`c`（continue）、`p expr`（打印）、`pp obj`（pprint）、`l`（列出上下文代码）、`bt`（调用栈）

## Traceback 解读

1. 从**最底部一行**读起——这是触发异常的直接位置
2. 向上追溯调用链，定位真正的逻辑错误点（常在栈中段）
3. 注意 `During handling of the above exception, another exception occurred`——链式异常，两个 traceback 均须检查
4. `RecursionError: maximum recursion depth exceeded` → 先检查递归终止条件，再检查循环依赖导致的无限递归

常见异常速查：

| 异常 | 常见原因 |
|------|---------|
| `AttributeError: 'NoneType' object has no attribute` | 未检查 None 返回值即解引用 |
| `KeyError` | dict 访问不存在的键；用 `.get(key)` 或先 `in` 判断 |
| `ImportError / ModuleNotFoundError` | 包未安装或 PYTHONPATH 不含 src/ |
| `RuntimeError: no running event loop` | 在同步上下文调用了 asyncio 协程 |
| `TypeError: object is not subscriptable` | 对非序列/映射类型使用 `[]`，常因返回 None |

## 日志实践

```python
import logging

logger = logging.getLogger(__name__)  # 按模块命名，层级可控

# 基础配置（入口点）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# 结构化日志（生产推荐 structlog 或 python-json-logger）
logger.info("user created", extra={"user_id": uid, "email": email})
```

- 禁止在热路径用 `f"..."` 构造日志消息再传给 logger；改用惰性格式 `logger.debug("val=%s", val)`
- 敏感字段（密码、token）在记录前必须屏蔽

## Profiling 工具

| 工具 | 用途 | 命令 |
|------|------|------|
| `cProfile` | 函数级 CPU 耗时，内置 | `python -m cProfile -s cumtime script.py` |
| `pstats` | cProfile 结果分析 | `python -m pstats profile.out` |
| `py-spy` | 生产环境采样，无需重启进程 | `py-spy top --pid <PID>` |
| `memory_profiler` | 逐行内存用量 | `@profile` 装饰器 + `mprof run` |
| `tracemalloc` | 标准库内存快照对比 | `tracemalloc.start(); ... snapshot = tracemalloc.take_snapshot()` |

## 常见运行时问题定位

- **循环导入**：`ImportError: cannot import name X from partially initialized module` → 检查 `__init__.py` 中的交叉导入，改为延迟导入或提取公共模块
- **asyncio 死锁**：任务互相 `await` 对方且无超时 → 用 `asyncio.wait_for(..., timeout=N)` + `asyncio.Task.cancel()`
- **进程内存持续增长**：先用 `tracemalloc` 定位对象类型，再检查是否有全局缓存无限追加或回调持有对象引用
- 先稳定复现再动手：读完整链式 traceback 定位根因，不要凭栈信息臆测就改码
- 不要用 `except: pass` 或过宽 catch 压掉异常掩盖症状；每个修复配一个能复现原 bug 的回归测试，确认改前失败、改后通过
