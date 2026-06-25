# 安装

> 目标：在本机装上 `cataforge` CLI 并通过 `cataforge --version` 验证。

## 环境要求

| 条件 | 版本 / 说明 |
|------|-------------|
| 操作系统 | Windows 10+ / macOS 12+ / Linux（主流发行版） |
| Python | `>=3.10`（已验证 3.10 / 3.11 / 3.12 / 3.13 / 3.14） |
| 包管理器 | `uv>=0.4`（**推荐**）；纯 `pip` 见下方告警 |
| Git | 近期版本（CataForge 依赖 git 元信息） |
| 可选工具 | `ruff`、`docker`、`npx`（`doctor` 会检测但不强制） |

---

## 安装方式

### A. uv tool（全局 CLI · 推荐终端用户）

```bash
uv tool install cataforge
cataforge --version
```

> 仅安装运行时依赖。若需运行 `pytest`，请另建项目 venv（见 B/C）或追加 `uv pip install pytest pydantic pyyaml click` 到同一环境。

### B. 项目本地开发（推荐贡献者）

```bash
uv venv
uv pip install -e ".[dev]"
# Windows PowerShell / cmd:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
# Windows Git Bash:
# source .venv/Scripts/activate
```

### C. 纯 pip（无 uv）

> ⚠️ **推荐用 uv（方式 A/B）安装。** 传递依赖链 `linkml-runtime → prefixcommons 0.1.12` 把测试期工具 `pytest-logging`（运行时从不导入）误声明为运行时依赖，新版 setuptools 下其 wheel 构建会报 `install_layout AttributeError` 而失败。CataForge 用 `pyproject.toml` 的 `[tool.uv] override-dependencies` 中和了它——但该 override **仅对 uv 生效**，pip 没有等价的传递依赖覆盖机制，故纯 pip 安装可能在此处构建失败。upstream `prefixcommons` 0.1.12 已是最新、无更高版本可绕，因此这是 pip 的结构性限制；遇到该报错请改用 uv。

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
python -m pip install -U pip
pip install -e ".[dev]"
```

---

## 升级

先确认当前版本，再按安装方式选对应命令：

```bash
cataforge --version
```

| 安装方式 | 升级命令 |
|---------|---------|
| `uv tool install`（方式 A） | `uv tool upgrade cataforge` |
| `uv pip install`（方式 B） | `uv pip install --upgrade cataforge` |
| `pip install`（方式 C） | `pip install --upgrade cataforge` |

升级后运行 `cataforge doctor` 验证新版本环境正常。版本变更详见 [CHANGELOG](https://github.com/lync-cyber/CataForge/blob/main/CHANGELOG.md)。

---

## 可选依赖组

`pyproject.toml` 声明了多个可选依赖组，按需安装：

| extra | 包含 | 典型场景 |
|-------|------|---------|
| `dev` | `pytest` / `ruff` / `mypy` / `build` / `twine` 等 | 开发与测试 |
| `mcp` | `mcp>=1.0` | 需要直接与 MCP 协议交互 |
| `docker` | `docker>=7.0` | 容器化相关 skill |
| `penpot` | `docker>=7.0` | Penpot 设计工具集成 |
| `all` | `docker` + `mcp` | 一次装齐可选能力 |

```bash
pip install -e ".[dev,mcp]"
```

---

## Windows 最小可跑清单

| 步骤 | PowerShell | cmd.exe | Git Bash |
|------|-----------|---------|----------|
| 1. 选 Python | `py -3.12 --version` | `py -3.12 --version` | `python --version` |
| 2. 建 venv | `py -3.12 -m venv .venv` | `py -3.12 -m venv .venv` | `python -m venv .venv` |
| 3. 激活 venv | `.\.venv\Scripts\Activate.ps1` | `.venv\Scripts\activate.bat` | `source .venv/Scripts/activate` |
| 4. 装依赖 | `pip install -e ".[dev]"` | 同左 | 同左 |
| 5. 健康检查 | `cataforge doctor` | 同左 | 同左 |
| 6. 乱码兜底 | `$env:PYTHONUTF8 = "1"` | `set PYTHONUTF8=1` | `export PYTHONUTF8=1` |
| 7. PATH 检查 | `Get-Command cataforge` | `where cataforge` | `which cataforge` |

**常见坑位**：

- `py -3.12 -m venv` 优于 `python -m venv`：绕过 Windows Store 的 `python.exe` 别名。
- PowerShell 激活被策略拦：`Set-ExecutionPolicy -Scope Process RemoteSigned` 一次性放行当前 shell。
- `mklink /J` 需要管理员或 "开发者模式"：Windows 部署优先使用 junction，失败自动回退为目录拷贝。
- **Git Bash 是 Windows 前置条件**：`cataforge deploy` 会把 `CLAUDE_CODE_USE_POWERSHELL_TOOL=0` 写进 `.claude/settings.json`，让 Claude Code 的 Bash 工具走 Git Bash 而非原生 PowerShell 工具（CataForge 的 SKILL / AGENT 命令均为 POSIX 写法）。未装 Git for Windows 时 `cataforge doctor` 的「Shell preference」段会 WARN；装 Git for Windows，或设 `CLAUDE_CODE_GIT_BASH_PATH` 指向 `bash.exe`，或删掉该 env 键回退到 PowerShell 工具。
- **uv tool 安装后提示 PATH 警告**：`uv tool install / upgrade` 完成后出现 `` warning: `C:\Users\<you>\.local\bin` is not on your PATH ``，执行一次 `uv tool update-shell` 并重启终端即可永久消除，无需手动编辑环境变量。

---

## 下一步

- 跑通最短示例：[`quick-start.md`](./quick-start.md)
- 四平台端到端验证：[`../guide/manual-verification.md`](../guide/manual-verification.md)
- 故障排查：[`./troubleshooting.md`](./troubleshooting.md)（按症状索引）· [`../faq.md`](../faq.md)（按主题索引）
