#!/usr/bin/env bash
# ============================================================
# ClawBuddy 首次部署初始化脚本
#
# 功能:
#   1. 从 .env 文件创建后端 K8s Secret
#   2. 应用全部 K8s 部署清单
#
# 用法:
#   ./deploy/init-secrets.sh [--env-file path/to/.env]
#
# 前置条件:
#   - kubectl 已配置正确的集群上下文
#   - cr-pull-secret 已在 clawbuddy-system 中创建
# ============================================================
set -euo pipefail

NAMESPACE="clawbuddy-system"
SECRET_NAME="clawbuddy-backend-env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/claw-buddy-backend/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[Init]${NC} $*"; }
ok()  { echo -e "${GREEN}[ OK ]${NC} $*"; }
err() { echo -e "${RED}[ERR ]${NC} $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
    *) err "未知参数: $1"; exit 1 ;;
  esac
  shift
done

if [[ ! -f "$ENV_FILE" ]]; then
  err "环境变量文件不存在: $ENV_FILE"
  echo "请复制 .env.example 并填写实际值:"
  echo "  cp claw-buddy-backend/.env.example claw-buddy-backend/.env"
  exit 1
fi

# ── 确保 Namespace 存在 ──────────────────────────────────
log "检查 Namespace: $NAMESPACE"
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
  log "创建 Namespace..."
  kubectl create namespace "$NAMESPACE"
fi
ok "Namespace $NAMESPACE 就绪"

# ── 创建/更新后端 Secret ─────────────────────────────────
log "从 $ENV_FILE 创建 Secret: $SECRET_NAME"

LITERAL_ARGS=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(echo "$line" | xargs)"
  [[ -z "$line" ]] && continue
  [[ "$line" != *"="* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  LITERAL_ARGS+=("--from-literal=$key=$value")
done < "$ENV_FILE"

if [[ ${#LITERAL_ARGS[@]} -eq 0 ]]; then
  err ".env 文件中没有有效的键值对"
  exit 1
fi

kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  "${LITERAL_ARGS[@]}" \
  --dry-run=client -o yaml | kubectl apply -f -

ok "Secret $SECRET_NAME 已创建/更新 (${#LITERAL_ARGS[@]} 个变量)"

# ── 应用 K8s 部署清单 ───────────────────────────────────
log "应用 K8s 部署清单..."
kubectl apply -f "$SCRIPT_DIR/k8s/"
ok "部署清单已应用"

# ── 结果 ─────────────────────────────────────────────────
echo ""
log "初始化完成。接下来请运行部署脚本构建并推送镜像:"
echo ""
echo "  ./deploy/deploy.sh all"
echo ""
log "当前 Deployment 状态:"
kubectl -n "$NAMESPACE" get deployments -l 'app in (clawbuddy-backend, clawbuddy-admin, clawbuddy-portal)' 2>/dev/null || true
