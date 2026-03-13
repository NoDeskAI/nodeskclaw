#!/usr/bin/env bash
# ============================================================
# NoDeskClaw 首次部署初始化脚本
#
# 功能:
#   1. 从 .env 文件创建后端 K8s Secret
#   2. 应用全部 K8s 部署清单
#
# 用法:
#   ./deploy/init-secrets.sh --context <k8s-context> [--env-file path/to/.env]
#
# 前置条件:
#   - cr-pull-secret 已在 nodeskclaw-system 中创建
# ============================================================
set -euo pipefail

NAMESPACE="nodeskclaw-system"
SECRET_NAME="nodeskclaw-backend-env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/nodeskclaw-backend/.env"
KUBE_CONTEXT=""

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[Init]${NC} $*"; }
ok()  { echo -e "${GREEN}[ OK ]${NC} $*"; }
err() { echo -e "${RED}[ERR ]${NC} $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context) KUBE_CONTEXT="$2"; shift ;;
    --env-file) ENV_FILE="$2"; shift ;;
    *) err "未知参数: $1"; exit 1 ;;
  esac
  shift
done

if [[ -z "$KUBE_CONTEXT" ]]; then
  err "必须通过 --context 指定 K8s 集群上下文"
  echo "可用上下文:"
  kubectl config get-contexts -o name 2>/dev/null | sed 's/^/  /'
  exit 1
fi

KUBECTL="kubectl --context $KUBE_CONTEXT"

if [[ ! -f "$ENV_FILE" ]]; then
  err "环境变量文件不存在: $ENV_FILE"
  echo "请复制 .env.example 并填写实际值:"
  echo "  cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env"
  exit 1
fi

# ── 确保 Namespace 存在 ──────────────────────────────────
log "检查 Namespace: $NAMESPACE"
if ! $KUBECTL get namespace "$NAMESPACE" &>/dev/null; then
  log "创建 Namespace..."
  $KUBECTL create namespace "$NAMESPACE"
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

$KUBECTL -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  "${LITERAL_ARGS[@]}" \
  --dry-run=client -o yaml | $KUBECTL apply -f -

ok "Secret $SECRET_NAME 已创建/更新 (${#LITERAL_ARGS[@]} 个变量)"

# ── 应用 K8s 部署清单 ───────────────────────────────────
log "应用 K8s 部署清单..."
$KUBECTL apply -f "$SCRIPT_DIR/k8s/"
ok "部署清单已应用"

# ── 结果 ─────────────────────────────────────────────────
echo ""
log "初始化完成。接下来请运行部署脚本构建并推送镜像:"
echo ""
echo "  ./deploy/deploy.sh all"
echo ""
log "当前 Deployment 状态:"
$KUBECTL -n "$NAMESPACE" get deployments -l 'app in (nodeskclaw-backend, nodeskclaw-admin, nodeskclaw-portal)' 2>/dev/null || true
