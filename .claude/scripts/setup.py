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
import json
import os
import re
import shutil
import subprocess
import sys

# 共享工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    NC,
    RED,
    YELLOW,
    ensure_utf8_stdio,
    fail,
    get_command_version,
    has_command,
    info,
    load_dotenv,
    ok,
    section,
    skip,
    warn,
)


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
    """从 .env 文件加载代理配置到环境变量（如未设置）。

    有意仅加载代理相关变量，而非全部 .env 变量，
    避免 setup 阶段意外覆盖用户环境。
    """
    env_vars = load_dotenv()
    proxy_keys = {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}
    for key, value in env_vars.items():
        if key in proxy_keys and key not in os.environ:
            os.environ[key] = value
            # 掩码凭据: http://user:pass@host -> http://***@host
            masked = re.sub(r"://[^@]+@", "://***@", value) if "@" in value else value
            info(f"从 .env 加载代理: {key}={masked}")


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


def _safe_read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _is_uv_project(project_dir: str = ".") -> bool:
    """判断项目是否使用 uv 作为 Python 包管理器。

    统一判定逻辑，供 detect_python_pkg_manager / build_env_block / detect_active_stacks 复用。
    优先级: uv.lock → pyproject.toml 中 [tool.uv]。
    仅凭 uv 命令在 PATH 中不足以判定为 uv 项目（pip 项目也可能装有 uv）。
    """
    join = os.path.join
    if os.path.isfile(join(project_dir, "uv.lock")):
        return True
    pyproject = join(project_dir, "pyproject.toml")
    if os.path.isfile(pyproject):
        if "[tool.uv]" in _safe_read(pyproject):
            return True
    return False


def detect_python_pkg_manager(project_dir: str = ".") -> str:
    """检测 Python 项目的包管理器，返回 'uv' | 'pip'"""
    return "uv" if _is_uv_project(project_dir) else "pip"


def detect_node_pkg_manager(project_dir: str = ".") -> str:
    """检测 Node.js 项目的包管理器，返回 'npm' | 'yarn' | 'pnpm' | 'bun'

    优先级: lock 文件 → fallback npm。
    """
    join = os.path.join
    if os.path.exists(join(project_dir, "pnpm-lock.yaml")):
        return "pnpm"
    if os.path.exists(join(project_dir, "yarn.lock")):
        return "yarn"
    if os.path.exists(join(project_dir, "bun.lockb")) or os.path.exists(
        join(project_dir, "bun.lock")
    ):
        return "bun"
    return "npm"


def build_env_block(project_dir: str = ".") -> str:
    """根据项目实际技术栈构建 CLAUDE.md §执行环境 节。

    返回 Markdown 片段（不含标题），Bootstrap 阶段由 orchestrator 注入 CLAUDE.md。
    返回空字符串表示未检测到任何已知技术栈。

    支持: Python (uv/pip), Node.js (npm/yarn/pnpm/bun), Go, .NET.
    """
    join = os.path.join
    exists = os.path.isfile
    lines: list[str] = []

    # --- Python ---
    has_pyproject = exists(join(project_dir, "pyproject.toml"))
    has_requirements = exists(join(project_dir, "requirements.txt"))
    if has_pyproject or has_requirements:
        pkg = detect_python_pkg_manager(project_dir)
        install = "uv sync" if pkg == "uv" else "pip install -e ."
        test = "uv run python -m pytest" if pkg == "uv" else "python -m pytest"
        lines.append(f"- Python: 包管理器={pkg} | install=`{install}` | test=`{test}`")

    # --- Node.js ---
    if exists(join(project_dir, "package.json")):
        pkg = detect_node_pkg_manager(project_dir)
        run_prefix = {"npm": "npx", "yarn": "yarn", "pnpm": "pnpm exec", "bun": "bunx"}[pkg]
        lines.append(
            f"- Node: 包管理器={pkg} | install=`{pkg} install` | run=`{run_prefix}`"
        )

    # --- Go ---
    if exists(join(project_dir, "go.mod")):
        lines.append("- Go: install=`go mod download` | test=`go test ./...`")

    # --- .NET ---
    try:
        has_dotnet = any(
            f.endswith((".csproj", ".sln")) for f in os.listdir(project_dir)
        )
    except OSError:
        has_dotnet = False
    if has_dotnet:
        lines.append("- .NET: install=`dotnet restore` | test=`dotnet test`")

    if not lines:
        return ""

    return (
        "\n".join(lines)
        + "\n- 约束: 整个项目生命周期内不混用同语言的其他包管理器（如 uv/pip、npm/yarn/pnpm）"
    )


# ============================================================================
# Permissions 生成器 (P2-1)
# ============================================================================

# 框架级最小 permissions — 任何 CataForge 项目都需要
FRAMEWORK_CORE_PERMISSIONS = [
    "WebSearch",
    "Bash(git status*)",
    "Bash(git log*)",
    "Bash(git diff*)",
    "Bash(git add*)",
    "Bash(git commit*)",
    "Bash(git checkout -- docs/*)",
    "Bash(ls *)",
    "Bash(mkdir *)",
    "Bash(python .claude/skills/*/scripts/*.py*)",
    "Bash(python .claude/scripts/*.py*)",
    "Bash(python .claude/scripts/setup_penpot.py --ensure)",
]

# 按技术栈 → 允许的 Bash 模式列表
STACK_PERMISSIONS = {
    "python-uv": [
        "Bash(uv sync*)",
        "Bash(uv run *)",
        "Bash(uv pip install*)",
        "Bash(python -m pytest*)",
        "Bash(ruff *)",
    ],
    "python-pip": [
        "Bash(python -m pytest*)",
        "Bash(python -m pip install*)",
        "Bash(ruff *)",
    ],
    "node-npm": [
        "Bash(npm install*)",
        "Bash(npm run *)",
        "Bash(npm test*)",
        "Bash(npx prettier*)",
        "Bash(npx eslint*)",
    ],
    "node-yarn": [
        "Bash(yarn install*)",
        "Bash(yarn run *)",
        "Bash(yarn test*)",
    ],
    "node-pnpm": [
        "Bash(pnpm install*)",
        "Bash(pnpm run *)",
        "Bash(pnpm test*)",
        "Bash(pnpm exec *)",
    ],
    "node-bun": [
        "Bash(bun install*)",
        "Bash(bun run *)",
        "Bash(bun test*)",
        "Bash(bunx *)",
    ],
    "go": [
        "Bash(go mod *)",
        "Bash(go test *)",
        "Bash(go build *)",
    ],
    "dotnet": [
        "Bash(dotnet restore*)",
        "Bash(dotnet build*)",
        "Bash(dotnet test*)",
        "Bash(dotnet format*)",
    ],
}


def detect_active_stacks(project_dir: str = ".") -> list[str]:
    """检测当前项目实际使用的技术栈 key 列表（用于生成 permissions）。"""
    join = os.path.join
    exists = os.path.isfile
    stacks: list[str] = []

    has_pyproject = exists(join(project_dir, "pyproject.toml"))
    has_requirements = exists(join(project_dir, "requirements.txt"))
    if has_pyproject or has_requirements:
        stacks.append("python-uv" if _is_uv_project(project_dir) else "python-pip")

    if exists(join(project_dir, "package.json")):
        node_mgr = detect_node_pkg_manager(project_dir)
        stacks.append(f"node-{node_mgr}")

    if exists(join(project_dir, "go.mod")):
        stacks.append("go")

    try:
        if any(f.endswith((".csproj", ".sln")) for f in os.listdir(project_dir)):
            stacks.append("dotnet")
    except OSError:
        pass

    return stacks


def build_minimal_allow_list(project_dir: str = ".") -> list[str]:
    """根据实际技术栈生成最小 permissions.allow 列表。"""
    allow = list(FRAMEWORK_CORE_PERMISSIONS)
    for stack in detect_active_stacks(project_dir):
        allow.extend(STACK_PERMISSIONS.get(stack, []))
    # 去重且保持插入顺序
    seen = set()
    deduped = []
    for item in allow:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def check_project_dependencies() -> list:
    """检测用户项目的依赖是否已安装"""
    suggestions = []

    # Node.js 项目
    if os.path.exists("package.json"):
        node_mgr = detect_node_pkg_manager(".")
        ok(f"检测到 Node 包管理器: {node_mgr}")
        if os.path.exists("node_modules"):
            ok("package.json 存在，node_modules/ 已安装")
        else:
            warn("package.json 存在，但 node_modules/ 缺失")
            suggestions.append(f"{node_mgr} install")

    # Python 项目: 检测包管理器
    is_python = os.path.exists("requirements.txt") or os.path.exists("pyproject.toml")
    pkg_mgr = detect_python_pkg_manager() if is_python else "pip"
    if is_python:
        if pkg_mgr == "uv":
            ok("检测到 Python 包管理器: uv")
        else:
            ok("检测到 Python 包管理器: pip")

    # Python 项目 (requirements.txt)
    if os.path.exists("requirements.txt"):
        if pkg_mgr == "uv":
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
            if pkg_mgr == "uv":
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
        try:
            # 验证 Python 语法 — 通过 -m py_compile 避免路径注入
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", hook_path],
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
    """调用 Penpot 完整部署脚本 (setup_penpot.py)"""
    script = os.path.join(".claude", "scripts", "setup_penpot.py")
    if not os.path.exists(script):
        fail(f"Penpot 部署脚本不存在: {script}")
        return False

    print(f"\n{BOLD}正在启动 Penpot 完整部署...{NC}\n")
    try:
        result = subprocess.run([sys.executable, script, "deploy"], timeout=900)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        fail("Penpot 部署超时 (15 分钟)")
        return False


# ============================================================================
# 主流程
# ============================================================================


def main():
    ensure_utf8_stdio()
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
    parser.add_argument(
        "--emit-env-block",
        action="store_true",
        help="仅检测当前目录的技术栈并向 stdout 输出 CLAUDE.md §执行环境 节的 Markdown 片段",
    )
    parser.add_argument(
        "--emit-permissions",
        action="store_true",
        help="向 stdout 输出当前项目技术栈对应的最小 permissions.allow JSON 数组",
    )
    parser.add_argument(
        "--apply-permissions",
        action="store_true",
        help="根据技术栈重写 .claude/settings.json 的 permissions.allow 为最小集合",
    )
    args = parser.parse_args()

    # --emit-env-block: 轻量模式，供 orchestrator Bootstrap 调用以获取环境信息
    if args.emit_env_block:
        block = build_env_block(".")
        if block:
            print(block)
            sys.exit(0)
        else:
            sys.exit(2)  # 2 = 未检测到任何已知技术栈

    # --emit-permissions: 输出最小 allow 列表（供 orchestrator 或用户审查）
    if args.emit_permissions:
        print(json.dumps(build_minimal_allow_list("."), ensure_ascii=False, indent=2))
        sys.exit(0)

    # --apply-permissions: 实际写入 settings.json
    if args.apply_permissions:
        settings_path = os.path.join(".claude", "settings.json")
        if not os.path.exists(settings_path):
            fail(f"{settings_path} 不存在")
            sys.exit(1)
        with open(settings_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 容忍尾随逗号: 先尝试原样解析，失败后再清理
        try:
            settings = json.loads(content)
        except json.JSONDecodeError:
            content = re.sub(r",\s*([}\]])", r"\1", content)
            settings = json.loads(content)
        settings.setdefault("permissions", {})
        old_count = len(settings["permissions"].get("allow", []))
        new_allow = build_minimal_allow_list(".")
        settings["permissions"]["allow"] = new_allow
        # 保留原有 deny
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.write("\n")
        ok(
            f"已写入最小 permissions.allow: {old_count} -> {len(new_allow)} 条 "
            f"(检测到栈: {', '.join(detect_active_stacks('.')) or '(无)'})"
        )
        sys.exit(0)

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
