#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EE_DIR="$SCRIPT_DIR/ee"
BACKEND_DIR="$SCRIPT_DIR/nodeskclaw-backend"
LLM_PROXY_DIR="$SCRIPT_DIR/nodeskclaw-llm-proxy"
PORTAL_DIR="$SCRIPT_DIR/nodeskclaw-portal"
ADMIN_DIR="$EE_DIR/nodeskclaw-frontend"

BLUE=$'\033[0;34m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RED=$'\033[0;31m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

PIDS=()
FRESH=false
DOCKER_PG=false
DOCKER_PG_CONTAINER="nodeskclaw-pg"
DOCKER_PG_VOLUME="nodeskclaw_pg_dev"
IS_MSYS=false
if [ -n "${MSYSTEM:-}" ] || [ -n "${MINGW_PREFIX:-}" ]; then
  IS_MSYS=true
fi

usage() {
  cat <<EOF
用法: ./dev.sh [ce|ee] [--fresh] [--docker-pg] [--help]

模式:
  (无参数)   自动检测：ee/ 存在 → EE，否则 → CE
  ce         强制 CE 模式（backend + portal）
  ee         强制 EE 模式（backend + portal + admin）

选项:
  --fresh      强制重新安装依赖（删除 .venv / node_modules 后重装）
  --docker-pg  使用 Docker 启动本地 PostgreSQL（无需自行安装 PG）
  --help       显示本帮助

服务端口:
  backend    http://localhost:4510
  llm-proxy  http://localhost:4511
  portal     http://localhost:4517
  admin(EE)  http://localhost:4518
EOF
  exit 0
}

log() { echo "${CYAN}[dev]${RESET} $*"; }
err() { echo "${RED}[dev] ERROR:${RESET} $*" >&2; }

_find_pids_on_port() {
  local port="$1"
  if command -v lsof &>/dev/null; then
    lsof -ti :"$port" 2>/dev/null || true
  elif command -v ss &>/dev/null; then
    ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' || true
  fi
}

_show_port_usage() {
  local port="$1"
  if command -v lsof &>/dev/null; then
    lsof -i :"$port" -P -n 2>/dev/null | head -5 >&2
  elif command -v ss &>/dev/null; then
    ss -tlnp 2>/dev/null | grep ":${port} " >&2
  else
    echo "  (lsof/ss 均不可用，无法显示占用详情)" >&2
  fi
}

cleanup() {
  echo ""
  log "正在停止所有服务..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  for port in 4510 4511; do
    local remaining
    remaining=$(_find_pids_on_port "$port")
    if [ -n "$remaining" ]; then
      log "清理端口 $port 上的残留进程..."
      echo "$remaining" | xargs kill -9 2>/dev/null || true
    fi
  done
  if [ "$DOCKER_PG" = true ]; then
    log "停止 Docker PostgreSQL ($DOCKER_PG_CONTAINER)..."
    docker stop "$DOCKER_PG_CONTAINER" 2>/dev/null || true
  fi
  log "已停止。"
}

trap cleanup SIGINT SIGTERM

# ── 解析参数 ──────────────────────────────────────────────
MODE=""
for arg in "$@"; do
  case "$arg" in
    ce)      MODE="ce" ;;
    ee)      MODE="ee" ;;
    --fresh) FRESH=true ;;
    --docker-pg) DOCKER_PG=true ;;
    --help|-h) usage ;;
    *) err "未知参数: $arg"; usage ;;
  esac
done

if [ -z "$MODE" ]; then
  if [ -d "$EE_DIR" ]; then
    MODE="ee"
    log "检测到 ee/ 目录，自动进入 ${BOLD}EE${RESET} 模式"
  else
    MODE="ce"
    log "未检测到 ee/ 目录，自动进入 ${BOLD}CE${RESET} 模式"
  fi
fi

if [ "$MODE" = "ee" ] && [ ! -d "$EE_DIR" ]; then
  err "EE 模式需要 ee/ 目录，请将 EE 私有仓库 clone 到项目根目录的 ee/ 下"
  exit 1
fi

if [ "$IS_MSYS" = true ]; then
  log "${YELLOW}检测到 MSYS/Git Bash 环境（Windows）${RESET}"
  log "${YELLOW}  - 如遇端口检测跳过，属正常行为（lsof 不可用）${RESET}"
  log "${YELLOW}  - 如遇 \\r 报错，请执行: git config core.autocrlf false && git checkout -- dev.sh${RESET}"
fi

# ── Docker PostgreSQL（可选）──────────────────────────────
if [ "$DOCKER_PG" = true ]; then
  if ! command -v docker &>/dev/null; then
    err "未找到 docker，--docker-pg 需要 Docker"
    exit 1
  fi

  if docker ps --format '{{.Names}}' | grep -q "^${DOCKER_PG_CONTAINER}$"; then
    log "Docker PostgreSQL ($DOCKER_PG_CONTAINER) 已在运行"
  else
    if docker ps -a --format '{{.Names}}' | grep -q "^${DOCKER_PG_CONTAINER}$"; then
      log "启动已存在的 Docker PostgreSQL..."
      docker start "$DOCKER_PG_CONTAINER"
    else
      log "创建并启动 Docker PostgreSQL..."
      docker run -d --name "$DOCKER_PG_CONTAINER" \
        -p 5432:5432 \
        -e POSTGRES_USER=nodeskclaw \
        -e POSTGRES_PASSWORD=nodeskclaw \
        -e POSTGRES_DB=nodeskclaw \
        -v "$DOCKER_PG_VOLUME":/var/lib/postgresql/data \
        postgres:16-alpine
    fi

    log "等待 PostgreSQL 就绪..."
    for i in $(seq 1 30); do
      if docker exec "$DOCKER_PG_CONTAINER" pg_isready -U nodeskclaw &>/dev/null; then
        break
      fi
      if [ "$i" -eq 30 ]; then
        err "PostgreSQL 启动超时"
        exit 1
      fi
      sleep 1
    done
    log "PostgreSQL 就绪"
  fi

  export DATABASE_URL="postgresql+asyncpg://nodeskclaw:nodeskclaw@localhost:5432/nodeskclaw"
  export DATABASE_NAME_SUFFIX=""
  log "DATABASE_URL 已设置为 Docker PostgreSQL (localhost:5432)"
fi

# ── 前置检查 ──────────────────────────────────────────────
log "前置检查..."

if ! command -v uv &>/dev/null; then
  err "未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
  err "未找到 node/npm，请先安装 Node.js >= 18"
  exit 1
fi

if [ ! -f "$BACKEND_DIR/.env" ]; then
  err "未找到 $BACKEND_DIR/.env"
  echo "  请先复制并配置: cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env"
  exit 1
fi

log "前置检查通过 (uv=$(uv --version 2>/dev/null || echo '?'), node=$(node --version))"

# ── 依赖安装 ──────────────────────────────────────────────
if [ "$FRESH" = true ]; then
  log "--fresh: 清理并重新安装依赖..."
  rm -rf "$BACKEND_DIR/.venv"
  rm -rf "$LLM_PROXY_DIR/.venv"
  rm -rf "$PORTAL_DIR/node_modules"
  [ "$MODE" = "ee" ] && rm -rf "$ADMIN_DIR/node_modules"
fi

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  log "安装后端依赖 (uv sync)..."
  (cd "$BACKEND_DIR" && uv sync)
else
  log "后端依赖已就绪，跳过安装"
fi

if [ ! -d "$LLM_PROXY_DIR/.venv" ]; then
  log "安装 LLM Proxy 依赖 (uv sync)..."
  (cd "$LLM_PROXY_DIR" && uv sync)
else
  log "LLM Proxy 依赖已就绪，跳过安装"
fi

if [ ! -d "$PORTAL_DIR/node_modules" ]; then
  log "安装 Portal 前端依赖 (npm install)..."
  (cd "$PORTAL_DIR" && npm install)
else
  log "Portal 依赖已就绪，跳过安装"
fi

if [ "$MODE" = "ee" ]; then
  if [ ! -d "$ADMIN_DIR/node_modules" ]; then
    log "安装 Admin 前端依赖 (npm install)..."
    (cd "$ADMIN_DIR" && npm install)
  else
    log "Admin 依赖已就绪，跳过安装"
  fi
fi

# ── 带颜色前缀的输出函数 ──────────────────────────────────
prefix_output() {
  local color="$1"
  local label="$2"
  sed -u "s/^/${color}[${label}]${RESET} /"
}

# ── 数据库迁移 ────────────────────────────────────────────
log "执行数据库迁移 (alembic upgrade head)..."
(cd "$BACKEND_DIR" && uv run alembic upgrade head)

# ── 端口检查 ──────────────────────────────────────────────
require_port_free() {
  local port="$1" label="$2"
  local pids
  pids=$(_find_pids_on_port "$port")
  if [ -n "$pids" ]; then
    err "端口 $port ($label) 已被占用:"
    _show_port_usage "$port"
    exit 1
  fi
}

require_port_free 4510 "backend"
require_port_free 4511 "llm-proxy"

# ── 启动服务 ──────────────────────────────────────────────
log "启动服务..."

export NODESKCLAW_EDITION="$MODE"
export LLM_PROXY_URL="http://localhost:4511"
export LLM_PROXY_INTERNAL_URL="http://localhost:4511"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

if [ -z "${DATABASE_URL:-}" ]; then
  DATABASE_URL=$(grep '^DATABASE_URL=' "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
  export DATABASE_URL
fi

_LLM_PROXY_DB_URL=$(cd "$BACKEND_DIR" && uv run python3 -c "from app.core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)

(cd "$LLM_PROXY_DIR" && DATABASE_URL="${_LLM_PROXY_DB_URL:-$DATABASE_URL}" uv run uvicorn app.main:app --host 0.0.0.0 --port 4511 --timeout-graceful-shutdown 3) \
  2>&1 | prefix_output "$CYAN" "llm-prx" &
PIDS+=($!)

(cd "$BACKEND_DIR" && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 4510 --timeout-graceful-shutdown 3) \
  2>&1 | prefix_output "$BLUE" "backend" &
PIDS+=($!)

sleep 1

(cd "$PORTAL_DIR" && npm run dev) \
  2>&1 | prefix_output "$GREEN" "portal " &
PIDS+=($!)

if [ "$MODE" = "ee" ]; then
  (cd "$ADMIN_DIR" && npm run dev) \
    2>&1 | prefix_output "$YELLOW" "admin  " &
  PIDS+=($!)
fi

sleep 2

# ── 打印摘要 ──────────────────────────────────────────────
echo ""
MODE_UPPER=$(echo "$MODE" | tr '[:lower:]' '[:upper:]')
echo "${BOLD}========================================${RESET}"
echo "${BOLD} NoDeskClaw 本地开发环境 (${MODE_UPPER})${RESET}"
echo "${BOLD}========================================${RESET}"
echo "  ${BLUE}Backend${RESET}  http://localhost:4510"
echo "  ${CYAN}LLM Prx${RESET}  http://localhost:4511"
echo "  ${GREEN}Portal${RESET}   http://localhost:4517"
if [ "$MODE" = "ee" ]; then
  echo "  ${YELLOW}Admin${RESET}    http://localhost:4518"
fi
echo "${BOLD}========================================${RESET}"
echo "  Ctrl+C 停止所有服务"
echo ""

# ── 等待子进程 ────────────────────────────────────────────
wait_for_children() {
  while true; do
    local all_dead=true
    for pid in "${PIDS[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        all_dead=false
        break
      fi
    done
    if [ "$all_dead" = true ]; then
      log "所有服务已退出。"
      break
    fi
    sleep 1
  done
}

wait_for_children
