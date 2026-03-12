#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EE_DIR="$SCRIPT_DIR/ee"
BACKEND_DIR="$SCRIPT_DIR/nodeskclaw-backend"
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

usage() {
  cat <<EOF
用法: ./dev.sh [ce|ee] [--fresh] [--help]

模式:
  (无参数)   自动检测：ee/ 存在 → EE，否则 → CE
  ce         强制 CE 模式（backend + portal）
  ee         强制 EE 模式（backend + portal + admin）

选项:
  --fresh    强制重新安装依赖（删除 .venv / node_modules 后重装）
  --help     显示本帮助

服务端口:
  backend    http://localhost:8000
  portal     http://localhost:4517
  admin(EE)  http://localhost:4518
EOF
  exit 0
}

log() { echo "${CYAN}[dev]${RESET} $*"; }
err() { echo "${RED}[dev] ERROR:${RESET} $*" >&2; }

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
  err "EE 模式需要 ee/ 目录，请先运行 scripts/setup-ee.sh"
  exit 1
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
  rm -rf "$PORTAL_DIR/node_modules"
  [ "$MODE" = "ee" ] && rm -rf "$ADMIN_DIR/node_modules"
fi

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  log "安装后端依赖 (uv sync)..."
  (cd "$BACKEND_DIR" && uv sync)
else
  log "后端依赖已就绪，跳过安装"
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

# ── 启动服务 ──────────────────────────────────────────────
log "启动服务..."

(cd "$BACKEND_DIR" && uv run uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3) \
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
echo "  ${BLUE}Backend${RESET}  http://localhost:8000"
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
