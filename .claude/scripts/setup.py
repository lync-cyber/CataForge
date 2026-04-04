#!/usr/bin/env python3
"""setup.py — CataForge 初始化安装脚本

从零开始检测运行环境、安装依赖、配置项目。

用法:
  python .claude/scripts/setup.py               # 完整安装检测
  python .claude/scripts/setup.py --with-penpot  # 含 Penpot MCP 安装
  python .claude/scripts/setup.py --check-only   # 仅检测，不做任何修改

返回: exit 0=成功, exit 1=发现问题
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================================
# 输出工具
# ============================================================================

# 检测终端是否支持 ANSI (Windows Terminal / Git Bash / Unix)
_SUPPORTS_COLOR = (
    (hasattr(sys.stdout, "isatty") and sys.stdout.isatty())
    or os.environ.get("TERM")
    or os.environ.get("WT_SESSION")
)

if _SUPPORTS_COLOR:
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    NC = "\033[0m"
else:
    GREEN = RED = YELLOW = BLUE = CYAN = BOLD = DIM = NC = ""

TICK = f"{GREEN}OK{NC}"
CROSS = f"{RED}FAIL{NC}"
WARN = f"{YELLOW}WARN{NC}"
INFO = f"{BLUE}INFO{NC}"
SKIP = f"{DIM}SKIP{NC}"


def ok(msg: str):
    print(f"  [{TICK}] {msg}")


def fail(msg: str):
    print(f"  [{CROSS}] {msg}")


def warn(msg: str):
    print(f"  [{WARN}] {msg}")


def info(msg: str):
    print(f"  [{INFO}] {msg}")


def skip(msg: str):
    print(f"  [{SKIP}] {msg}")


def section(title: str):
    print(f"\n{BOLD}--- {title} ---{NC}")


def has_command(name: str) -> bool:
    """检查命令是否在 PATH 中可用"""
    return shutil.which(name) is not None


def get_command_version(cmd: list) -> str:
    """获取命令版本输出"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


# ============================================================================
# 检测模块
# ============================================================================


def check_python() -> bool:
    """检测 Python 版本 >= 3.8"""
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 8):
        ok(f"Python {ver_str}")
        return True
    else:
        fail(f"Python {ver_str} — 需要 >= 3.8")
        return False


def check_git() -> bool:
    """检测 Git"""
    if has_command("git"):
        ver = get_command_version(["git", "--version"])
        ok(f"Git {DIM}({ver}){NC}")
        return True
    else:
        fail("Git 未安装 — 请安装: https://git-scm.com")
        return False


def check_optional_linters() -> dict:
    """检测可选的 linter/formatter 工具（hooks 使用）"""
    tools = {}

    # Python: ruff
    if has_command("ruff"):
        ver = get_command_version(["ruff", "--version"])
        ok(f"ruff {DIM}({ver}){NC}")
        tools["ruff"] = True
    else:
        warn(f"ruff 未安装 — Python 代码格式化/检查将跳过 {DIM}(pip install ruff){NC}")
        tools["ruff"] = False

    # JS/TS: npx (prettier + eslint)
    if has_command("npx"):
        ok(f"npx 可用 {DIM}(prettier/eslint 将通过 npx 调用){NC}")
        tools["npx"] = True
    else:
        warn(
            f"npx 未安装 — JS/TS 格式化将跳过 {DIM}(安装 Node.js: https://nodejs.org){NC}"
        )
        tools["npx"] = False

    # C#: dotnet
    if has_command("dotnet"):
        ok(f"dotnet 可用 {DIM}(C# 格式化){NC}")
        tools["dotnet"] = True
    else:
        skip(f"dotnet 未安装 — C# 格式化将跳过 {DIM}(非 C# 项目可忽略){NC}")
        tools["dotnet"] = False

    # Go: golangci-lint (code-review skill)
    if has_command("golangci-lint"):
        ok(f"golangci-lint 可用 {DIM}(Go 代码检查){NC}")
        tools["golangci-lint"] = True
    else:
        skip(f"golangci-lint 未安装 {DIM}(非 Go 项目可忽略){NC}")
        tools["golangci-lint"] = False

    return tools


def check_env_file(check_only: bool = False) -> bool:
    """检测 .env 文件，不存在时从 .env.example 复制"""
    if os.path.exists(".env"):
        ok(".env 文件已存在")
        return True

    example_file = ".env.example"
    if not os.path.exists(example_file):
        warn(".env 和 .env.example 均不存在")
        return False

    if check_only:
        warn(f".env 不存在 — 运行 setup 时将从 {example_file} 复制")
        return False

    shutil.copy2(example_file, ".env")
    ok(f".env 已从 {example_file} 复制 — 请编辑填入实际值")
    return True


def load_env_proxy():
    """从 .env 文件加载代理配置到环境变量（如未设置）"""
    env_file = ".env"
    if not os.path.exists(env_file):
        return

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Z_]+)\s*=\s*(.+)$", line)
            if match:
                key, value = (
                    match.group(1),
                    match.group(2).strip().strip('"').strip("'"),
                )
                # 仅设置代理相关的环境变量
                if key in (
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "NO_PROXY",
                    "http_proxy",
                    "https_proxy",
                    "no_proxy",
                ):
                    if key not in os.environ:
                        os.environ[key] = value
                        info(f"从 .env 加载代理: {key}={value}")


def check_proxy_status():
    """报告当前代理配置状态"""
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
    found = False
    for var in proxy_vars:
        val = os.environ.get(var)
        if val:
            ok(f"代理已配置: {var}={val}")
            found = True
    if not found:
        info("未配置网络代理 (受限网络环境可在 .env 中配置)")


def detect_python_pkg_manager() -> str:
    """检测 Python 项目的包管理器，返回 'uv' | 'pip'

    优先级: uv.lock 存在 → uv; 否则检测 uv 命令可用性 + pyproject.toml 中
    [tool.uv] 配置; 最后 fallback 到 pip。
    """
    # uv.lock 文件是 uv 项目的明确标志
    if os.path.exists("uv.lock"):
        return "uv"
    # pyproject.toml 中含 [tool.uv] 配置
    if os.path.exists("pyproject.toml"):
        try:
            with open("pyproject.toml", "r", encoding="utf-8") as f:
                if "[tool.uv]" in f.read():
                    return "uv"
        except OSError:
            pass
    # uv 命令可用且有 pyproject.toml (现代 Python 项目)
    if has_command("uv") and os.path.exists("pyproject.toml"):
        return "uv"
    return "pip"


def detect_node_pkg_manager() -> str:
    """检测 Node.js 项目的包管理器，返回 'npm' | 'yarn' | 'pnpm' | 'bun'

    优先级: lock 文件 → fallback npm。
    """
    if os.path.exists("pnpm-lock.yaml"):
        return "pnpm"
    if os.path.exists("yarn.lock"):
        return "yarn"
    if os.path.exists("bun.lockb") or os.path.exists("bun.lock"):
        return "bun"
    return "npm"


def check_project_dependencies() -> list:
    """检测用户项目的依赖是否已安装"""
    suggestions = []

    # Node.js 项目
    if os.path.exists("package.json"):
        node_mgr = detect_node_pkg_manager()
        ok(f"检测到 Node 包管理器: {node_mgr}")
        if os.path.exists("node_modules"):
            ok("package.json 存在，node_modules/ 已安装")
        else:
            warn("package.json 存在，但 node_modules/ 缺失")
            suggestions.append(f"{node_mgr} install")

    # Python 项目: 检测包管理器
    is_python = os.path.exists("requirements.txt") or os.path.exists("pyproject.toml")
    if is_python:
        pkg_mgr = detect_python_pkg_manager()
        if pkg_mgr == "uv":
            ok("检测到 Python 包管理器: uv")
        else:
            ok("检测到 Python 包管理器: pip")

    # Python 项目 (requirements.txt)
    if os.path.exists("requirements.txt"):
        if is_python and detect_python_pkg_manager() == "uv":
            info("requirements.txt 存在 — 建议运行: uv pip install -r requirements.txt")
            suggestions.append("uv pip install -r requirements.txt")
        else:
            info("requirements.txt 存在 — 建议运行: pip install -r requirements.txt")
            suggestions.append("pip install -r requirements.txt")

    # Python 项目 (pyproject.toml with dependencies)
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            content = f.read()
        # 检查是否有非空 dependencies
        dep_match = re.search(
            r"^\s*dependencies\s*=\s*\[([^\]]*)\]", content, re.MULTILINE | re.DOTALL
        )
        if dep_match and dep_match.group(1).strip():
            if detect_python_pkg_manager() == "uv":
                info("pyproject.toml 声明了依赖 — 建议运行: uv sync")
                suggestions.append("uv sync")
            else:
                info("pyproject.toml 声明了依赖 — 建议运行: pip install -e .")
                suggestions.append("pip install -e .")

    if not suggestions and not os.path.exists("package.json"):
        info("未检测到项目依赖文件 (package.json / requirements.txt)")

    return suggestions


def check_hooks_executable() -> bool:
    """验证 hooks 脚本可执行"""
    hooks_dir = os.path.join(".claude", "hooks")
    if not os.path.exists(hooks_dir):
        warn(".claude/hooks/ 目录不存在")
        return False

    all_ok = True
    hook_files = [f for f in os.listdir(hooks_dir) if f.endswith(".py")]

    for hook_file in hook_files:
        hook_path = os.path.join(hooks_dir, hook_file)
        # 将路径中的反斜杠转义，避免 Windows 路径破坏 Python 字符串
        safe_path = hook_path.replace("\\", "/")
        try:
            # 验证 Python 语法
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import py_compile; py_compile.compile(r'{safe_path}', doraise=True)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                ok(f"hook: {hook_file}")
            else:
                fail(f"hook: {hook_file} — 语法错误")
                all_ok = False
        except Exception as e:
            fail(f"hook: {hook_file} — 检测失败: {e}")
            all_ok = False

    return all_ok


def check_framework_integrity() -> bool:
    """检查框架目录结构完整性"""
    required_dirs = [
        ".claude/agents",
        ".claude/skills",
        ".claude/rules",
        ".claude/hooks",
        ".claude/scripts",
    ]
    all_ok = True
    for d in required_dirs:
        if os.path.exists(d):
            ok(f"目录: {d}/")
        else:
            fail(f"目录缺失: {d}/")
            all_ok = False

    # 检查关键文件
    required_files = [
        ".claude/rules/COMMON-RULES.md",
        ".claude/rules/SUB-AGENT-PROTOCOLS.md",
        ".claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md",
    ]
    for f in required_files:
        if os.path.exists(f):
            ok(f"文件: {f}")
        else:
            fail(f"文件缺失: {f}")
            all_ok = False

    return all_ok


def run_penpot_setup():
    """调用 Penpot MCP 安装脚本"""
    script = os.path.join(".claude", "scripts", "setup-penpot-mcp.sh")
    if not os.path.exists(script):
        fail(f"Penpot 安装脚本不存在: {script}")
        return False

    print(f"\n{BOLD}正在启动 Penpot MCP 安装...{NC}\n")
    try:
        result = subprocess.run(["bash", script], timeout=600)
        return result.returncode == 0
    except FileNotFoundError:
        fail("bash 不可用 — Penpot MCP 安装需要 bash 环境 (Git Bash / WSL / Unix)")
        return False
    except subprocess.TimeoutExpired:
        fail("Penpot MCP 安装超时 (10 分钟)")
        return False


# ============================================================================
# 主流程
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="CataForge 初始化安装脚本",
        epilog=(
            "示例:\n"
            "  python .claude/scripts/setup.py               # 完整安装检测\n"
            "  python .claude/scripts/setup.py --with-penpot  # 含 Penpot MCP\n"
            "  python .claude/scripts/setup.py --check-only   # 仅检测\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--with-penpot", action="store_true", help="同时安装 Penpot MCP 设计工具集成"
    )
    parser.add_argument(
        "--check-only", action="store_true", help="仅检测环境，不做任何修改"
    )
    args = parser.parse_args()

    print("")
    print(f"{CYAN}{BOLD}  CataForge 环境初始化{NC}")
    print(f"  {'=' * 40}")
    print("")

    has_issues = False
    dep_suggestions = []

    # 1. 必要依赖
    section("必要依赖")
    if not check_python():
        has_issues = True
    if not check_git():
        has_issues = True

    # 2. 框架完整性
    section("框架完整性")
    if not check_framework_integrity():
        has_issues = True

    # 3. Hooks 可执行性
    section("Hooks 脚本验证")
    if not check_hooks_executable():
        has_issues = True

    # 4. 可选 linter/formatter
    section("可选工具 (hooks 使用)")
    check_optional_linters()

    # 5. 环境配置文件
    section("环境配置")
    check_env_file(args.check_only)
    load_env_proxy()
    check_proxy_status()

    # 6. 项目依赖
    section("项目依赖")
    dep_suggestions = check_project_dependencies()

    # 7. Penpot MCP (可选)
    if args.with_penpot:
        section("Penpot MCP 安装")
        if args.check_only:
            info("--check-only 模式，跳过 Penpot 安装")
        else:
            if not run_penpot_setup():
                has_issues = True

    # 总结
    print(f"\n{BOLD}{'=' * 44}{NC}")
    if has_issues:
        print(f"  {RED}{BOLD}发现问题，请检查上方输出并修复{NC}")
    else:
        print(f"  {GREEN}{BOLD}环境检测通过{NC}")

    if dep_suggestions:
        print(f"\n  {BOLD}建议执行:{NC}")
        for cmd in dep_suggestions:
            print(f"    {CYAN}{cmd}{NC}")

    if not args.with_penpot:
        print(f"\n  {DIM}提示: 如需 Penpot 设计集成，运行:{NC}")
        print(f"    {DIM}python .claude/scripts/setup.py --with-penpot{NC}")

    print("")
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
