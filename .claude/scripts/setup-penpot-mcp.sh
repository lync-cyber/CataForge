#!/usr/bin/env bash
# ============================================================================
#  Penpot MCP 一键部署脚本 (for Claude Code / CataForge)
#  从零开始：检查环境 → 克隆仓库 → 安装依赖 → 构建启动 → 注册到 Claude Code
#
#  用法:
#    bash .claude/scripts/setup-penpot-mcp.sh
#
#  环境变量 (可选覆盖):
#    PENPOT_MCP_DIR               安装目录 (默认: $HOME/penpot-mcp)
#    PENPOT_MCP_SERVER_PORT       MCP Server 端口 (默认: 4401)
#    PENPOT_MCP_PLUGIN_PORT       Plugin Server 端口 (默认: 4400)
#    PENPOT_MCP_WEBSOCKET_PORT    WebSocket 端口 (默认: 4402)
# ============================================================================
set -euo pipefail

# ── 加载 .env 配置（优先于系统环境变量） ────────────────────────────────────
ENV_FILE="${CLAUDE_PROJECT_DIR:-.}/.env"
if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"          # 去除注释
        # 仅去除行首尾空白，保留值中的空格
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" ]] && continue
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            val="${val%\"}" ; val="${val#\"}"   # 去除引号
            val="${val%\'}" ; val="${val#\'}"
            export "$key=$val"
        fi
    done < "$ENV_FILE"
fi

# ── 颜色与符号 ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

TICK="${GREEN}✔${NC}"
CROSS="${RED}✘${NC}"
ARROW="${CYAN}➜${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${BLUE}ℹ${NC}"

# ── 配置 ────────────────────────────────────────────────────────────────────
INSTALL_DIR="${PENPOT_MCP_DIR:-$HOME/penpot-mcp}"
REPO_URL="https://github.com/penpot/penpot.git"
BRANCH="develop"
MCP_SUBDIR="mcp"
MCP_PORT="${PENPOT_MCP_SERVER_PORT:-4401}"
PLUGIN_PORT="${PENPOT_MCP_PLUGIN_PORT:-4400}"
WS_PORT="${PENPOT_MCP_WEBSOCKET_PORT:-4402}"
NODE_MIN_VERSION=18
NODE_REC_VERSION=22
HEALTH_TIMEOUT=30

# ── 平台检测 ────────────────────────────────────────────────────────────────
detect_platform() {
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        Darwin*)              PLATFORM="macos" ;;
        Linux*)               PLATFORM="linux" ;;
        *)                    PLATFORM="unknown" ;;
    esac
}
detect_platform

# ── 计时 ──────────────────────────────────────────────────────────────────
SCRIPT_START=$SECONDS
STEP_START=$SECONDS
STEP_LOG="/tmp/penpot-mcp-step.log"

elapsed_since() { echo "$(( SECONDS - $1 ))s"; }

# ── 工具函数 ────────────────────────────────────────────────────────────────
print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║          Penpot MCP 一键部署脚本                    ║"
    echo "  ║          for Claude Code / CataForge                ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "  ${DIM}仓库: penpot/penpot (develop branch, mcp/ 目录)${NC}"
    echo -e "  ${DIM}安装目录: ${INSTALL_DIR}${NC}"
    echo -e "  ${DIM}平台: ${PLATFORM}${NC}"
    echo ""
}

step() {
    local step_num=$1
    local total=$2
    local msg=$3
    # 打印上一步耗时（跳过第一步）
    if [[ "$step_num" -gt 1 ]]; then
        echo -e "  ${DIM}  ── 步骤耗时: $(elapsed_since $STEP_START) ──${NC}"
    fi
    STEP_START=$SECONDS
    echo ""
    echo -e "  ${BOLD}[${step_num}/${total}]${NC} ${ARROW} ${msg}"
    echo -e "  ${DIM}$(printf '%.0s─' {1..52})${NC}"
}

ok()   { echo -e "       ${TICK} $1"; }
fail() { echo -e "       ${CROSS} $1"; }
info() { echo -e "       ${INFO} $1"; }
warn() { echo -e "       ${WARN} $1"; }

# spinner 动画：在后台命令运行期间显示旋转动画 + 已用时间
# 用法: some_command > "$STEP_LOG" 2>&1 & spin_while $! "提示文字" "完成文字"
# 失败时自动打印日志尾部帮助排查
spin_while() {
    local pid=$1
    local msg=$2
    local done_msg="${3:-$msg}"
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local frame_count=${#frames[@]}
    local i=0
    local start=$SECONDS

    # 隐藏光标
    tput civis 2>/dev/null || true

    while kill -0 "$pid" 2>/dev/null; do
        local elapsed=$(( SECONDS - start ))
        printf "\r       ${CYAN}%s${NC} %s ${DIM}(%ds)${NC}   " "${frames[$((i % frame_count))]}" "$msg" "$elapsed"
        i=$((i + 1))
        sleep 0.1 2>/dev/null || sleep 1
    done

    # 恢复光标
    tput cnorm 2>/dev/null || true

    # 获取退出码
    wait "$pid"
    local exit_code=$?
    local elapsed=$(( SECONDS - start ))

    # 清除 spinner 行
    printf "\r%-70s\r" " "

    if [[ $exit_code -eq 0 ]]; then
        ok "${done_msg} ${DIM}(${elapsed}s)${NC}"
    else
        fail "${msg} — 失败 ${DIM}(${elapsed}s)${NC}"
        # 打印日志尾部帮助排查
        if [[ -f "$STEP_LOG" ]] && [[ -s "$STEP_LOG" ]]; then
            echo -e "       ${DIM}── 最后 10 行日志 ──${NC}"
            tail -10 "$STEP_LOG" | sed 's/^/         /'
            echo -e "       ${DIM}── 完整日志: ${STEP_LOG} ──${NC}"
        fi
    fi
    return $exit_code
}

die() {
    echo ""
    fail "$1"
    # 打印日志上下文（如有）
    if [[ -f "$STEP_LOG" ]] && [[ -s "$STEP_LOG" ]]; then
        echo -e "       ${DIM}── 最后 10 行日志 ──${NC}"
        tail -10 "$STEP_LOG" | sed 's/^/         /'
        echo -e "       ${DIM}── 完整日志: ${STEP_LOG} ──${NC}"
    fi
    echo ""
    echo -e "  ${RED}部署中止。请修复上述问题后重新运行脚本。${NC}"
    echo ""
    exit 1
}

# ── 跨平台端口检查 ──────────────────────────────────────────────────────────
check_port() {
    local port=$1
    local name=$2
    local occupied=false

    case "$PLATFORM" in
        windows)
            # Windows (Git Bash / MSYS2): 使用 netstat
            if netstat -ano 2>/dev/null | grep -qE "[:.]${port}\s.*LISTENING"; then
                occupied=true
            fi
            ;;
        macos)
            if lsof -i ":$port" -sTCP:LISTEN &>/dev/null 2>&1; then
                occupied=true
            fi
            ;;
        linux)
            if ss -tlnp 2>/dev/null | grep -q ":$port "; then
                occupied=true
            elif netstat -tlnp 2>/dev/null | grep -q ":$port "; then
                occupied=true
            fi
            ;;
    esac

    if [[ "$occupied" == "true" ]]; then
        warn "端口 ${port} (${name}) 已被占用，可能会冲突"
        return 1
    fi
    return 0
}

# 跨平台端口监听检测 (用于健康检查)
is_port_listening() {
    local port=$1
    case "$PLATFORM" in
        windows)
            netstat -ano 2>/dev/null | grep -qE "[:.]${port}\s.*LISTENING"
            ;;
        macos)
            lsof -i ":$port" -sTCP:LISTEN &>/dev/null 2>&1
            ;;
        linux)
            ss -tlnp 2>/dev/null | grep -q ":$port " \
                || netstat -tlnp 2>/dev/null | grep -q ":$port "
            ;;
        *)
            return 1
            ;;
    esac
}

# ── --ensure 快速模式：仅检测/启动，不安装 ────────────────────────────────────
if [[ "${1:-}" == "--ensure" ]]; then
    # 已在运行 → 秒级退出
    if is_port_listening "$MCP_PORT"; then
        echo "Penpot MCP already running on port $MCP_PORT"
        exit 0
    fi
    # 已安装但未运行 → 启动服务
    MCP_WORK_DIR="$INSTALL_DIR/$MCP_SUBDIR"
    [[ ! -d "$MCP_WORK_DIR" ]] && [[ -f "$INSTALL_DIR/package.json" ]] && MCP_WORK_DIR="$INSTALL_DIR"
    if [[ -d "$MCP_WORK_DIR" ]] && [[ -f "$MCP_WORK_DIR/package.json" ]]; then
        cd "$MCP_WORK_DIR"
        # 使用用户目录的 pnpm shim（由主流程安装）
        export PATH="$HOME/.local/bin:$PATH"
        if ! command -v pnpm >/dev/null 2>&1; then
            corepack enable --install-directory "$HOME/.local/bin" pnpm >/dev/null 2>&1 || true
        fi
        pnpm run start > /tmp/penpot-mcp-server.log 2>&1 &
        for i in $(seq 1 "$HEALTH_TIMEOUT"); do
            is_port_listening "$MCP_PORT" && { echo "Penpot MCP started on port $MCP_PORT"; exit 0; }
            sleep 1
        done
        echo "Penpot MCP failed to start within ${HEALTH_TIMEOUT}s" >&2; exit 1
    fi
    echo "Penpot MCP not installed. Run: bash .claude/scripts/setup-penpot-mcp.sh" >&2; exit 1
fi

# ── 清理函数 (仅在 Ctrl+C / TERM / 异常失败时触发) ─────────────────────────
# 注意：成功结束时脚本会 exit 0，但 cleanup_on_signal 只挂在 INT/TERM 上，
# 因此不会杀掉后台服务。EXIT 只负责恢复光标。
BG_PID=""
restore_cursor() { tput cnorm 2>/dev/null || true; }
cleanup_on_signal() {
    restore_cursor
    if [[ -n "$BG_PID" ]] && kill -0 "$BG_PID" 2>/dev/null; then
        kill "$BG_PID" 2>/dev/null || true
    fi
    exit 130
}
trap restore_cursor EXIT
trap cleanup_on_signal INT TERM

# ============================================================================
#  主流程
# ============================================================================
TOTAL_STEPS=6

print_banner

# ── Step 1: 检查系统依赖 ───────────────────────────────────────────────────
step 1 $TOTAL_STEPS "检查系统依赖"

# Git
if command -v git &>/dev/null; then
    GIT_VER=$(git --version | awk '{print $3}')
    ok "Git ${DIM}(${GIT_VER})${NC}"
else
    die "未找到 Git。请先安装: https://git-scm.com"
fi

# Node.js
if command -v node &>/dev/null; then
    NODE_VER_FULL=$(node -v | sed 's/^v//')
    NODE_MAJOR=$(echo "$NODE_VER_FULL" | cut -d. -f1)

    if [[ "$NODE_MAJOR" -lt "$NODE_MIN_VERSION" ]]; then
        die "Node.js 版本过低 (v${NODE_VER_FULL})。需要 v${NODE_MIN_VERSION}+，推荐 v${NODE_REC_VERSION}。"
    elif [[ "$NODE_MAJOR" -lt "$NODE_REC_VERSION" ]]; then
        warn "Node.js v${NODE_VER_FULL} 可用，但推荐 v${NODE_REC_VERSION}+"
    else
        ok "Node.js ${DIM}(v${NODE_VER_FULL})${NC}"
    fi
else
    die "未找到 Node.js。请安装 v${NODE_REC_VERSION}: https://nodejs.org"
fi

# Corepack (pnpm 版本由 package.json 的 packageManager 字段固定，由 corepack 拉取)
if command -v corepack &>/dev/null; then
    COREPACK_VER=$(corepack --version 2>/dev/null || echo "?")
    ok "Corepack ${DIM}(v${COREPACK_VER})${NC}"
else
    die "未找到 corepack。请升级 Node.js 至 v${NODE_REC_VERSION} (corepack 随 Node 自带)。"
fi

# curl (健康检查需要)
if command -v curl &>/dev/null; then
    ok "curl ${DIM}(已安装)${NC}"
else
    warn "未找到 curl — 健康检查将仅使用端口探测"
fi

# Claude Code (可选)
HAS_CLAUDE=false
if command -v claude &>/dev/null; then
    ok "Claude Code CLI ${DIM}(已安装)${NC}"
    HAS_CLAUDE=true
else
    warn "未检测到 Claude Code CLI — 稍后需手动注册 MCP"
fi

# 端口检查
PORTS_OK=true
check_port $MCP_PORT "MCP Server"       || PORTS_OK=false
check_port $PLUGIN_PORT "Plugin Server"  || PORTS_OK=false
check_port $WS_PORT "WebSocket"          || PORTS_OK=false

if [[ "$PORTS_OK" == "true" ]]; then
    ok "端口 ${MCP_PORT}/${PLUGIN_PORT}/${WS_PORT} 均可用"
fi

# ── Step 2: 获取源代码 ────────────────────────────────────────────────────
step 2 $TOTAL_STEPS "获取源代码"

if [[ -d "$INSTALL_DIR" ]]; then
    # 目录已存在，尝试更新
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        info "目录已存在，拉取最新代码..."
        cd "$INSTALL_DIR"
        git fetch origin "$BRANCH" --quiet > "$STEP_LOG" 2>&1 &
        spin_while $! "拉取最新代码" "代码已更新到最新" || true
        git pull --ff-only origin "$BRANCH" > "$STEP_LOG" 2>&1 \
            || warn "快进合并失败 (可能有本地修改)，继续使用现有代码"
    else
        info "目录已存在但非 Git 仓库，使用现有文件"
    fi
else
    git clone --depth 1 --branch "$BRANCH" \
        "$REPO_URL" "$INSTALL_DIR" > "$STEP_LOG" 2>&1 &
    spin_while $! "浅克隆 penpot 仓库 (--depth 1)" "源代码已克隆到 ${DIM}${INSTALL_DIR}${NC}" \
        || die "Git clone 失败"
    cd "$INSTALL_DIR"
fi

# 定位 mcp 工作目录
MCP_WORK_DIR="$INSTALL_DIR/$MCP_SUBDIR"
if [[ ! -d "$MCP_WORK_DIR" ]]; then
    # 可能仓库结构就是 mcp 本身
    if [[ -f "$INSTALL_DIR/package.json" ]]; then
        MCP_WORK_DIR="$INSTALL_DIR"
    else
        die "未找到 mcp/ 目录。请确认仓库结构正确。"
    fi
fi

cd "$MCP_WORK_DIR"
ok "工作目录: ${DIM}${MCP_WORK_DIR}${NC}"

# ── Step 3: 安装依赖 (Corepack + pnpm) ───────────────────────────────────
step 3 $TOTAL_STEPS "安装依赖 (Corepack + pnpm)"

# 检测并配置代理（供 corepack / pnpm 使用）
if [[ -n "${HTTP_PROXY:-}" ]]; then
    info "检测到 HTTP_PROXY: ${HTTP_PROXY}"
fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then
    info "检测到 HTTPS_PROXY: ${HTTPS_PROXY}"
fi

# Windows 下 Node 常装在 C:\Program Files\nodejs（非用户可写），
# 直接 `corepack enable` 会因 EPERM 失败。改用用户目录放置 pnpm shim。
COREPACK_SHIM_DIR="$HOME/.local/bin"
mkdir -p "$COREPACK_SHIM_DIR"
export PATH="$COREPACK_SHIM_DIR:$PATH"
info "Corepack shim 目录: ${COREPACK_SHIM_DIR}"

# 手动执行 corepack（绕开 scripts/setup 中无参数的 corepack enable）
{
    set -e
    corepack enable --install-directory "$COREPACK_SHIM_DIR" pnpm
    corepack install
    pnpm -r install
} > "$STEP_LOG" 2>&1 &
spin_while $! "corepack enable + pnpm -r install" "依赖安装完成" \
    || die "corepack/pnpm 安装失败。请检查网络/代理与 Node.js 版本。"

# 确保 pnpm 已激活
if ! command -v pnpm &>/dev/null; then
    die "pnpm 未能激活。请检查 ${COREPACK_SHIM_DIR} 是否在 PATH 中。"
fi
PNPM_VER=$(pnpm -v 2>/dev/null || echo "?")
ok "pnpm ${DIM}(v${PNPM_VER})${NC}"

# ── Step 4: 构建项目 ─────────────────────────────────────────────────────
step 4 $TOTAL_STEPS "构建项目 (pnpm run build)"

pnpm run build > "$STEP_LOG" 2>&1 &
spin_while $! "构建所有 workspace 包" "构建完成" \
    || die "构建失败 (pnpm run build)"

# ── Step 5: 启动服务 ─────────────────────────────────────────────────────
step 5 $TOTAL_STEPS "启动 MCP Server & Plugin Server"

LOG_FILE="/tmp/penpot-mcp-server.log"

# pnpm run start 由 package.json 定义为 `pnpm -r --parallel run start`，
# 同时启动 HTTP/SSE(4401) + WebSocket(4402) + Plugin Web(4400)
info "正在后台启动服务 (pnpm run start)..."
# setsid (若可用) 启动新 session，确保父 bash 退出时子进程不会收到 SIGHUP
if command -v setsid &>/dev/null; then
    setsid pnpm run start > "$LOG_FILE" 2>&1 < /dev/null &
else
    pnpm run start > "$LOG_FILE" 2>&1 < /dev/null &
fi
BG_PID=$!
disown "$BG_PID" 2>/dev/null || true

# 等待服务就绪 — 带进度条和逐服务状态
MCP_READY=false
PLUGIN_READY=false
SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
BAR_WIDTH=20

tput civis 2>/dev/null || true  # 隐藏光标

for i in $(seq 1 $HEALTH_TIMEOUT); do
    # 检查 MCP endpoint
    if [[ "$MCP_READY" == "false" ]]; then
        if curl -sf "http://localhost:${MCP_PORT}/mcp" -o /dev/null 2>/dev/null \
           || curl -sf "http://localhost:${MCP_PORT}/sse" -o /dev/null -m 2 2>/dev/null \
           || is_port_listening "$MCP_PORT"; then
            MCP_READY=true
        fi
    fi

    # 检查 Plugin Server
    if [[ "$PLUGIN_READY" == "false" ]]; then
        if curl -sf "http://localhost:${PLUGIN_PORT}/manifest.json" -o /dev/null 2>/dev/null \
           || is_port_listening "$PLUGIN_PORT"; then
            PLUGIN_READY=true
        fi
    fi

    if [[ "$MCP_READY" == "true" && "$PLUGIN_READY" == "true" ]]; then
        break
    fi

    # 绘制进度条
    filled=$(( i * BAR_WIDTH / HEALTH_TIMEOUT ))
    empty=$(( BAR_WIDTH - filled ))
    bar=""
    for (( b=0; b<filled; b++ )); do bar+="━"; done
    for (( b=0; b<empty;  b++ )); do bar+="░"; done

    # 逐服务状态
    spin_char="${SPIN_FRAMES[$((i % ${#SPIN_FRAMES[@]}))]}"
    if [[ "$MCP_READY" == "true" ]]; then
        mcp_status="${GREEN}✔${NC}"
    else
        mcp_status="${CYAN}${spin_char}${NC}"
    fi
    if [[ "$PLUGIN_READY" == "true" ]]; then
        plugin_status="${GREEN}✔${NC}"
    else
        plugin_status="${CYAN}${spin_char}${NC}"
    fi

    # 双行显示: 进度条 + 服务状态
    printf "\r\033[K       ⏳ 等待服务就绪 ${CYAN}%s${NC} %ds/%ds" "$bar" "$i" "$HEALTH_TIMEOUT"
    printf "\n\033[K          MCP: %b   Plugin: %b" "$mcp_status" "$plugin_status"
    printf "\033[1A"  # 光标回到上一行

    sleep 1
done

# 清除双行进度显示
printf "\r\033[K\n\033[K\033[1A\r"
tput cnorm 2>/dev/null || true  # 恢复光标

if [[ "$MCP_READY" == "true" ]]; then
    ok "MCP Server 就绪 ${DIM}→ http://localhost:${MCP_PORT}/mcp${NC}"
else
    warn "MCP Server 可能尚未就绪 (端口 ${MCP_PORT})，请手动确认"
fi

if [[ "$PLUGIN_READY" == "true" ]]; then
    ok "Plugin Server 就绪 ${DIM}→ http://localhost:${PLUGIN_PORT}${NC}"
else
    warn "Plugin Server 可能尚未就绪 (端口 ${PLUGIN_PORT})，请手动确认"
fi

# ── Step 6: 注册到 Claude Code ───────────────────────────────────────────
step 6 $TOTAL_STEPS "注册 MCP 到 Claude Code"

MCP_URL="http://localhost:${MCP_PORT}/mcp"

if [[ "$HAS_CLAUDE" == "true" ]]; then
    # claude mcp add 写入的是 ~/.claude.json（项目级 local scope），
    # 不是项目下的 .claude/settings.json。先用 `claude mcp list` 检测是否已注册。
    if claude mcp list 2>/dev/null | grep -qE '^penpot[: ]'; then
        ok "Claude Code 已注册 penpot MCP，跳过"
    else
        info "正在注册 Penpot MCP Server..."
        # 合并 stderr 以便在失败时看到真实错误
        ADD_OUTPUT=$(claude mcp add penpot -t http "$MCP_URL" 2>&1)
        ADD_EXIT=$?
        if [[ $ADD_EXIT -eq 0 ]] \
           || echo "$ADD_OUTPUT" | grep -qiE "Added|already exists"; then
            ok "已注册到 Claude Code"
        else
            warn "自动注册失败 (exit=$ADD_EXIT)，请手动执行:"
            info "  claude mcp add penpot -t http ${MCP_URL}"
            [[ -n "$ADD_OUTPUT" ]] && echo "$ADD_OUTPUT" | sed 's/^/         /'
        fi
    fi
else
    info "请手动注册 (安装 Claude Code 后运行):"
    echo ""
    echo -e "       ${BOLD}claude mcp add penpot -t http ${MCP_URL}${NC}"
    echo ""
fi

# ── 完成 ────────────────────────────────────────────────────────────────────
echo -e "  ${DIM}  ── 步骤耗时: $(elapsed_since $STEP_START) ──${NC}"
TOTAL_ELAPSED=$(( SECONDS - SCRIPT_START ))
echo ""
echo -e "  ${GREEN}${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}  ✅ 部署完成！${NC} ${DIM}(总耗时: ${TOTAL_ELAPSED}s)${NC}"
echo -e "  ${GREEN}${BOLD}══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}服务端点:${NC}"
echo -e "    MCP Server (HTTP):  ${CYAN}http://localhost:${MCP_PORT}/mcp${NC}"
echo -e "    MCP Server (SSE):   ${CYAN}http://localhost:${MCP_PORT}/sse${NC}"
echo -e "    Plugin Manifest:    ${CYAN}http://localhost:${PLUGIN_PORT}/manifest.json${NC}"
echo -e "    WebSocket:          ${CYAN}ws://localhost:${WS_PORT}${NC}"
echo ""
echo -e "  ${BOLD}CataForge 集成:${NC}"
echo -e "    ${WARN} 请将 CLAUDE.md 中 ${BOLD}设计工具${NC} 改为 ${BOLD}penpot${NC} 以启用集成"
echo -e "    相关 Skills: penpot-sync / penpot-implement / penpot-review"
echo ""
echo -e "  ${BOLD}下一步操作:${NC}"
echo -e "    1. 在浏览器中打开 Penpot 设计文件"
echo -e "    2. 打开 Plugins 菜单"
echo -e "    3. 加载插件: ${CYAN}http://localhost:${PLUGIN_PORT}/manifest.json${NC}"
echo -e "    4. 在插件 UI 中点击 ${BOLD}\"Connect to MCP server\"${NC}"
echo -e "    5. 在 Claude Code 中开始使用！"
echo ""
echo -e "  ${BOLD}常用命令:${NC}"
echo -e "    重启服务:  ${DIM}cd ${MCP_WORK_DIR} && pnpm run start${NC}"
echo -e "    查看日志:  ${DIM}cat ${LOG_FILE}${NC}"
echo -e "    停止服务:  ${DIM}kill \$(lsof -ti :${MCP_PORT}) 2>/dev/null${NC}"
echo ""
echo -e "  ${WARN} ${DIM}注意: 使用过程中请勿关闭 Penpot 中的插件 UI 窗口${NC}"
echo ""
