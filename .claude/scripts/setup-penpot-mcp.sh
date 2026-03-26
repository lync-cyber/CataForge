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
#    PENPOT_MCP_WEBSOCKET_PORT    WebSocket 端口 (默认: 4402)
# ============================================================================
set -euo pipefail

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
SPARSE_PATH="mcp"
MCP_PORT="${PENPOT_MCP_SERVER_PORT:-4401}"
PLUGIN_PORT=4400
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
    echo ""
    echo -e "  ${BOLD}[${step_num}/${total}]${NC} ${ARROW} ${msg}"
    echo -e "  ${DIM}$(printf '%.0s─' {1..52})${NC}"
}

ok()   { echo -e "       ${TICK} $1"; }
fail() { echo -e "       ${CROSS} $1"; }
info() { echo -e "       ${INFO} $1"; }
warn() { echo -e "       ${WARN} $1"; }

die() {
    echo ""
    fail "$1"
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

# ── 清理函数 (Ctrl+C 或异常退出时杀掉后台进程) ─────────────────────────────
BG_PID=""
cleanup() {
    if [[ -n "$BG_PID" ]] && kill -0 "$BG_PID" 2>/dev/null; then
        kill "$BG_PID" 2>/dev/null || true
        wait "$BG_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

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

# npm
if command -v npm &>/dev/null; then
    NPM_VER=$(npm -v)
    ok "npm ${DIM}(v${NPM_VER})${NC}"
else
    die "未找到 npm。请随 Node.js 一起安装。"
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
        git fetch origin "$BRANCH" --quiet 2>/dev/null || true
        git pull --ff-only origin "$BRANCH" 2>/dev/null \
            || warn "快进合并失败 (可能有本地修改)，继续使用现有代码"
        ok "代码已更新到最新"
    else
        info "目录已存在但非 Git 仓库，使用现有文件"
    fi
else
    info "使用 sparse checkout 只克隆 mcp/ 目录 (节省时间和空间)..."
    git clone --filter=blob:none --no-checkout --branch "$BRANCH" \
        "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -1 || die "Git clone 失败"
    cd "$INSTALL_DIR"
    git sparse-checkout init --cone 2>/dev/null
    git sparse-checkout set "$SPARSE_PATH" 2>/dev/null
    git checkout "$BRANCH" 2>/dev/null
    ok "源代码已克隆到 ${DIM}${INSTALL_DIR}${NC}"
fi

# 定位 mcp 工作目录
MCP_WORK_DIR="$INSTALL_DIR/$SPARSE_PATH"
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

# ── Step 3: 安装依赖 ─────────────────────────────────────────────────────
step 3 $TOTAL_STEPS "安装依赖"

# 检测并配置 npm 代理（从环境变量读取）
if [[ -n "${HTTP_PROXY:-}" ]]; then
    info "检测到 HTTP_PROXY，配置 npm 代理: ${HTTP_PROXY}"
    npm config set proxy "$HTTP_PROXY" 2>/dev/null || true
fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then
    info "检测到 HTTPS_PROXY，配置 npm 代理: ${HTTPS_PROXY}"
    npm config set https-proxy "$HTTPS_PROXY" 2>/dev/null || true
fi
if [[ -n "${NO_PROXY:-}" ]]; then
    npm config set noproxy "$NO_PROXY" 2>/dev/null || true
fi

info "正在运行 npm install (可能需要 1-2 分钟)..."
if npm install --loglevel=error --verbose 2>&1 | tail -3; then
    ok "依赖安装完成"
else
    die "npm install 失败。请检查网络连接和 Node.js 版本。"
fi

# ── Step 4: 构建项目 ─────────────────────────────────────────────────────
step 4 $TOTAL_STEPS "构建项目"

info "正在构建所有组件 (common / mcp-server / penpot-plugin)..."

SERVER_STARTED_BY_BOOTSTRAP=false

# 检查可用的构建命令
if npm run 2>/dev/null | grep -q "bootstrap"; then
    npm run bootstrap 2>&1 | tail -5
    ok "构建完成 (bootstrap)"
    # bootstrap 可能包含 start，服务已启动
    SERVER_STARTED_BY_BOOTSTRAP=true
elif npm run 2>/dev/null | grep -q "build:all"; then
    npm run build:all 2>&1 | tail -5 || die "构建失败"
    ok "构建完成 (build:all)"
elif npm run 2>/dev/null | grep -q "build"; then
    npm run build 2>&1 | tail -5 || die "构建失败"
    ok "构建完成"
else
    warn "未找到标准构建命令，跳过构建步骤"
fi

# ── Step 5: 启动服务 ─────────────────────────────────────────────────────
step 5 $TOTAL_STEPS "启动 MCP Server & Plugin Server"

LOG_FILE="/tmp/penpot-mcp-server.log"

if [[ "$SERVER_STARTED_BY_BOOTSTRAP" == "true" ]]; then
    info "服务已由 bootstrap 命令启动"
else
    # 启动服务到后台
    if npm run 2>/dev/null | grep -q "start:all"; then
        info "正在后台启动服务..."
        npm run start:all > "$LOG_FILE" 2>&1 &
        BG_PID=$!
    elif npm run 2>/dev/null | grep -q "start"; then
        info "正在后台启动服务..."
        npm run start > "$LOG_FILE" 2>&1 &
        BG_PID=$!
    else
        die "未找到启动命令 (start:all / start)"
    fi
fi

# 等待服务就绪
info "等待服务就绪 (最多 ${HEALTH_TIMEOUT}s)..."
MCP_READY=false
PLUGIN_READY=false

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

    printf "\r       ⏳ 等待中... (%ds/${HEALTH_TIMEOUT}s)" "$i"
    sleep 1
done
echo "" # 换行

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
    # 检查是否已在 settings.json 中配置
    SETTINGS_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/settings.json"
    if [[ -f "$SETTINGS_FILE" ]] && grep -q '"penpot"' "$SETTINGS_FILE" 2>/dev/null; then
        ok "settings.json 中已配置 penpot MCP，跳过重复注册"
    else
        info "正在注册 Penpot MCP Server..."
        if claude mcp add penpot -t http "$MCP_URL" 2>/dev/null; then
            ok "已注册到 Claude Code"
        else
            warn "自动注册失败，请手动执行:"
            info "  claude mcp add penpot -t http ${MCP_URL}"
        fi
    fi
else
    info "请手动注册 (安装 Claude Code 后运行):"
    echo ""
    echo -e "       ${BOLD}claude mcp add penpot -t http ${MCP_URL}${NC}"
    echo ""
fi

# ── 完成 ────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}${BOLD}══════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}  ✅ 部署完成！${NC}"
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
echo -e "    重启服务:  ${DIM}cd ${MCP_WORK_DIR} && npm run start:all${NC}"
echo -e "    查看日志:  ${DIM}cat ${LOG_FILE}${NC}"
echo -e "    停止服务:  ${DIM}kill \$(lsof -ti :${MCP_PORT}) 2>/dev/null${NC}"
echo ""
echo -e "  ${WARN} ${DIM}注意: 使用过程中请勿关闭 Penpot 中的插件 UI 窗口${NC}"
echo ""
