# Python · 构建部署细则

## 构建与打包工具

- **构建后端**：`hatchling`（hatch 生态）或 `setuptools`；两者均支持 PEP 517/518
- **构建前端**：`python -m build` 生成 wheel + sdist；不直接调用 `setup.py`
- 发布命令：`twine upload dist/*`（需预先 `twine check dist/*` 验证元数据）
- 单文件可执行产物：`PyInstaller --onefile` 或 `Nuitka`（性能敏感时）

## 依赖锁定与可复现构建

- 使用 **uv**：`uv lock` 生成 `uv.lock`（跨平台哈希锁定）；CI 用 `uv sync --frozen` 安装，不更新 lock
- 使用 **Poetry**：`poetry.lock` 提交到版本控制；CI 用 `poetry install --no-root`
- 使用 **pip-tools**：`pip-compile requirements.in -o requirements.txt --generate-hashes`；`pip install -r requirements.txt --require-hashes`
- 原则：lockfile 必须提交；CI 严禁在构建阶段执行依赖解析（`--frozen` / `--no-update`）
- 依赖与基镜像 tag 须确认真实存在的版本，不写 `latest` 或臆造版本；改动依赖范围后重新 `uv lock` 并核对锁文件

## CI 缓存策略

```yaml
# GitHub Actions 示例（uv）
- uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
    restore-keys: uv-${{ runner.os }}-
```

- 缓存键包含 lockfile 哈希，lock 变更时自动失效
- 将 `.venv` 与 uv 缓存分开：`.venv` 不缓存（路径含 runner 临时目录）；uv 全局缓存缓存

## 容器基镜像选择

| 基镜像 | 适用场景 | 权衡 |
|--------|---------|------|
| `python:3.12-slim` | 通用服务，需要 pip/sh | 含 apt，镜像 ~50 MB |
| `python:3.12-alpine` | 极小体积 | musl libc，部分 C 扩展需重编译 |
| `gcr.io/distroless/python3` | 生产最小攻击面，无 shell | 调试不便，须多阶段构建 |

多阶段构建模板：

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "my_pkg"]
```

## 产物发布与版本管理

- 版本号单一事实来源：`pyproject.toml [project].version`；禁止在代码中硬编码
- 发版流程：打 git tag → CI 检测 tag 触发发布 job → `python -m build` → `twine upload`
- PyPI token 通过 CI secret 注入（`TWINE_PASSWORD`），不写入代码或配置文件
- 开发依赖（lint/test/build 工具）归入 `[project.optional-dependencies] dev`，不污染生产依赖
