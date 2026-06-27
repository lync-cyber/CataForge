# Python · 架构师技术选型细则

## 包与依赖管理

| 工具 | 适用场景 | 权衡 |
|------|---------|------|
| uv | 新项目首选；速度极快，兼容 pip/PEP 517 | 生态较新，团队需统一升级 |
| Poetry | 需要完整发布流程（PyPI）+ lockfile | 解析速度慢于 uv |
| pip-tools | 已有 requirements.txt 体系，求最小侵入 | 功能单一，无虚拟环境管理 |

推荐：新项目用 uv；需发布 PyPI 包且团队熟悉 Poetry 时保留 Poetry。选型前核实每个库的当前最新稳定版与维护状态，不沿用记忆中的旧默认；引用的库与扩展须确认真实存在且仍维护，不写入"看起来合理"的虚构依赖。

## 主流框架与库选项

**Web API**
- FastAPI：异步优先，自动 OpenAPI，适合新建 REST/GraphQL 服务
- Flask：轻量，生态成熟，适合简单 API 或已有 Flask 基础的团队

**CLI**
- Click：声明式、可嵌套命令，主流选择
- Typer：基于 Click + 类型注解，适合 FastAPI 技术栈统一

**数据层**
- SQLAlchemy 2.x（async 支持）：关系型 DB，ORM + Core 双模式
- SQLModel：SQLAlchemy + Pydantic 融合，适合已用 FastAPI 的项目
- psycopg3 / aiosqlite：需细粒度控制时直接用驱动

## 并发与运行模型

- **asyncio**：I/O 密集型服务首选；注意 GIL 对 asyncio 无影响，但 CPU 密集段须用 `run_in_executor` 或 `multiprocessing`
- **线程（threading）**：I/O 密集 + 第三方阻塞库（无 async 版）时的折中；GIL 限制 CPU 并行
- **多进程（multiprocessing / concurrent.futures.ProcessPoolExecutor）**：CPU 密集任务绕开 GIL 的唯一原生方案
- **选型准则**：服务网络调用 → asyncio；封装旧阻塞库 → 线程；图像/数值处理 → 多进程或 Cython/Rust 扩展

## 类型系统与边界

- 所有公共接口须有完整类型注解（Python 3.10+ 推荐 `X | Y` 代替 `Optional[X]`）
- 数据校验层用 **Pydantic v2**；内部工具函数可用 `dataclasses` 省去序列化开销
- 静态检查：**mypy**（`--strict` 作为基线）或 **pyright**（VS Code 原生集成好）；两者选其一，统一进 CI
- 协议/结构子类型用 `typing.Protocol` 代替抽象基类以降低耦合

## 构建产物形态

- **库/框架**：打 wheel（`python -m build`），发布 PyPI；sdist 作为补充
- **服务**：容器镜像（Dockerfile），基于 `python:3.12-slim` 或 `gcr.io/distroless/python3`
- **CLI 工具**：wheel 发布 PyPI，或用 **PyInstaller / Nuitka** 打包为单文件可执行文件（分发给非 Python 环境）
- **版本号**：严格遵循 SemVer；单一事实来源写在 `pyproject.toml [project].version` 或 `src/<pkg>/__init__.py`
