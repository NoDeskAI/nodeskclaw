#!/usr/bin/env bash
# ============================================================
# NoDeskClaw LLM Proxy 构建 & 部署脚本
#
# 用法:
#   ./nodeskclaw-llm-proxy/deploy.sh --context <ctx> [options]
#
# 选项:
#   --context CTX     指定 kubectl 上下文（必填，防止误操作）
#   --namespace NS    目标 Namespace（默认 nodeskclaw-system）
#   --tag TAG         指定镜像标签（默认 YYYYMMDD-<git-hash>）
#   --build-only      仅构建+推送镜像，不更新 K8s
#   --deploy-only     仅更新 K8s（需要 --tag）
#   --no-cache        docker build 不使用缓存
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
IMAGE_NAME="nodeskclaw-llm-proxy"
NAMESPACE="nodeskclaw-system"
DEPLOYMENT="nodeskclaw-llm-proxy"
CONTAINER="llm-proxy"

[[ -f "$PROJECT_ROOT/deploy/.env.local" ]] && source "$PROJECT_ROOT/deploy/.env.local"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[LLM-Proxy]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

KUBE_CONTEXT=""
CUSTOM_TAG=""
CUSTOM_NS=""
BUILD_ONLY=false
DEPLOY_ONLY=false
NO_CACHE=""

usage() {
  echo "用法: $0 --context <ctx> [--namespace NS] [--tag TAG] [--build-only] [--deploy-only] [--no-cache]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)     KUBE_CONTEXT="$2"; shift ;;
    --namespace)   CUSTOM_NS="$2"; shift ;;
    --tag)         CUSTOM_TAG="$2"; shift ;;
    --build-only)  BUILD_ONLY=true ;;
    --deploy-only) DEPLOY_ONLY=true ;;
    --no-cache)    NO_CACHE="--no-cache" ;;
    *)             err "未知参数: $1"; usage ;;
  esac
  shift
done

[[ -n "$CUSTOM_NS" ]] && NAMESPACE="$CUSTOM_NS"

if [[ "$BUILD_ONLY" == true && "$DEPLOY_ONLY" == true ]]; then
  err "--build-only 和 --deploy-only 不能同时使用"
  exit 1
fi

if [[ "$BUILD_ONLY" != true && -z "$KUBE_CONTEXT" ]]; then
  err "需要 K8s 操作但未指定 --context"
  echo ""
  echo "可用上下文:"
  kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do echo "  $ctx"; done
  echo ""
  usage
fi

KUBECTL="kubectl"
[[ -n "$KUBE_CONTEXT" ]] && KUBECTL="kubectl --context $KUBE_CONTEXT"

if [[ -n "$CUSTOM_TAG" ]]; then
  TAG="$CUSTOM_TAG"
else
  TAG="$(date +%Y%m%d)-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'manual')"
fi

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

log "镜像: ${FULL_IMAGE}"
log "Namespace: ${NAMESPACE}"
[[ -n "$KUBE_CONTEXT" ]] && log "K8s 上下文: ${KUBE_CONTEXT}"
echo ""

# ── 构建 & 推送 ──────────────────────────────────────────
if [[ "$DEPLOY_ONLY" != true ]]; then
  log "构建镜像..."
  docker build --platform linux/amd64 \
    $NO_CACHE \
    --build-arg http_proxy= \
    --build-arg https_proxy= \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    -t "${FULL_IMAGE}" \
    "$SCRIPT_DIR"

  log "推送镜像..."
  docker push "${FULL_IMAGE}"
  ok "镜像推送完成: ${FULL_IMAGE}"
fi

# ── K8s 滚动更新 ─────────────────────────────────────────
if [[ "$BUILD_ONLY" != true ]]; then
  if ! $KUBECTL -n "$NAMESPACE" get deployment "$DEPLOYMENT" &>/dev/null; then
    warn "Deployment 不存在，执行首次部署..."
    $KUBECTL -n "$NAMESPACE" apply -f "$SCRIPT_DIR/deploy/deployment.yaml"
    $KUBECTL -n "$NAMESPACE" apply -f "$SCRIPT_DIR/deploy/service.yaml"
  fi

  log "更新 Deployment: ${DEPLOYMENT} -> ${FULL_IMAGE}"
  $KUBECTL -n "$NAMESPACE" set image "deployment/${DEPLOYMENT}" "${CONTAINER}=${FULL_IMAGE}"

  log "等待滚动更新完成..."
  if $KUBECTL -n "$NAMESPACE" rollout status "deployment/${DEPLOYMENT}" --timeout=120s; then
    ok "部署完成"
  else
    err "部署超时，请检查 Pod 状态"
    $KUBECTL -n "$NAMESPACE" get pods -l "app=${DEPLOYMENT}" -o wide
    exit 1
  fi

  $KUBECTL -n "$NAMESPACE" get pods -l "app=${DEPLOYMENT}" -o wide
fi

echo ""
ok "全部完成: ${FULL_IMAGE}"
