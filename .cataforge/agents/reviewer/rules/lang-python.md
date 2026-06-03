# Python · 代码评审细则

## 典型坏味道

- **可变默认参数**：`def fn(items=[])` 在所有调用间共享同一列表；应改为 `items=None` 并在函数体内初始化
- **过宽异常捕获**：`except Exception: pass` 吞掉所有错误，掩盖真实问题；应捕获具体类型并至少记录日志
- **字符串格式化拼接**：用 `+` 拼接路径或 SQL 片段而非 `pathlib.Path` / ORM 参数绑定，埋下注入风险
- **全局可变状态**：模块级可变 `dict`/`list` 在并发或测试中引发隐性耦合；改用依赖注入或局部变量
- **过深嵌套**：超过 3 层 `if/for` 嵌套；提取子函数或用 early return 打平

## 安全陷阱

| 陷阱 | 后果 | 替代 |
|------|------|------|
| `eval()` / `exec()` 执行外部输入 | 任意代码执行 | `ast.literal_eval` 或白名单解析 |
| `pickle.loads(untrusted)` | 反序列化 RCE | 改用 `json` / `msgpack` |
| SQL 字符串拼接 | SQL 注入 | ORM 绑定参数或 `?` 占位符 |
| `subprocess` 未用列表形式 + `shell=True` | shell 注入 | `subprocess.run(["cmd", arg], shell=False)` |
| 明文存储密钥（源码 / 日志） | 凭证泄露 | 环境变量 + `python-dotenv`；日志屏蔽敏感字段 |
| `tempfile.mktemp()`（非原子） | TOCTOU 竞争 | `tempfile.mkstemp()` 或 `NamedTemporaryFile` |

## 常见缺陷模式

- **N+1 查询**：循环内执行数据库查询而不是批量加载；使用 ORM 的 `joinedload` / `selectinload`
- **资源泄露**：文件/连接未用 `with` 包裹，异常路径不关闭；强制要求上下文管理器
- **线程不安全的单例初始化**：`if not instance: instance = ...` 在多线程下存在竞态；用 `threading.Lock` 或模块级单例
- **未处理 `None` 返回值**：调用可能返回 `None` 的函数后直接解引用属性；须先做非空检查

## 性能反模式

- 在循环中做 `list.insert(0, x)`（O(n)）→ 改用 `collections.deque`
- 大列表用 `+` 拼接字符串 → 改用 `"".join(parts)`
- 重复编译正则 `re.match(r"...", s)` 在热路径 → 提取到模块级 `re.compile`
- 同步 I/O 阻塞在 asyncio 事件循环线程 → 用 `asyncio.to_thread` / `run_in_executor`

## 评审 Checklist

1. 所有公共接口有类型注解；返回 `None` 的路径明确
2. 无裸 `except:` / `except Exception: pass`；异常须记录或重新抛出
3. 外部输入未直接传入 `eval` / `subprocess(shell=True)` / SQL 拼接
4. 资源（文件、连接、锁）在 `with` 或 `finally` 中释放
5. 测试覆盖主路径、边界值、异常路径
6. 无可变默认参数；无模块级可变全局状态（除配置单例外）
7. 热路径无不必要的对象创建或重复计算
8. 依赖第三方库的版本有上界约束（`pyproject.toml`）
9. 第三方 API 调用真实存在，无虚构的方法或参数
10. 依赖版本与调用未使用已弃用的写法
