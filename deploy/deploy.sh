#!/usr/bin/env bash
# ============================================================
# NoDeskClaw CI/CD 统一构建 & 部署脚本
#
# 用法:
#   ./deploy/deploy.sh <target> [options]
#
# 目标:
#   backend   后端 (FastAPI)
#   admin     Admin 前端 (Nginx)
#   portal    Portal 前端 (Nginx)
#   all       以上全部
#
# 选项:
#   --context CTX   指定 kubectl 上下文（必填，防止误操作到错误集群）
#   --build-only    仅构建+推送镜像，不更新 K8s
#   --deploy-only   仅更新 K8s (需要 --tag 指定镜像标签)
#   --tag TAG       指定镜像标签 (默认自动生成)
#   --namespace NS  指定目标 Namespace（默认 nodeskclaw-system）
#   --no-cache      docker build 不使用缓存
# ============================================================
set -euo pipefail

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
NAMESPACE="nodeskclaw-system"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
[[ -f "$SCRIPT_DIR/.env.local" ]] && source "$SCRIPT_DIR/.env.local"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[NoDeskClaw]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

# ── 组件配置查表（兼容 bash 3.x / macOS）─────────────────
ALL_COMPONENTS="backend admin portal"

get_image_name() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    *)       return 1 ;;
  esac
}

get_build_context() {
  case "$1" in
    backend) echo "$PROJECT_ROOT" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal" ;;
    *)       return 1 ;;
  esac
}

get_dockerfile() {
  case "$1" in
    backend) echo "$PROJECT_ROOT/nodeskclaw-backend/Dockerfile" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend/Dockerfile" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal/Dockerfile" ;;
    *)       return 1 ;;
  esac
}

get_k8s_deployment() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    *)       return 1 ;;
  esac
}

# ── 参数解析 ──────────────────────────────────────────────
TARGET=""
BUILD_ONLY=false
DEPLOY_ONLY=false
CUSTOM_TAG=""
CUSTOM_NS=""
NO_CACHE=""
KUBE_CONTEXT=""

usage() {
  echo "用法: $0 <backend|admin|portal|all> --context <kubectl-context> [--namespace NS] [--build-only] [--deploy-only] [--tag TAG] [--no-cache]"
  exit 1
}

[[ $# -lt 1 ]] && usage

TARGET="$1"; shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)     KUBE_CONTEXT="$2"; shift ;;
    --namespace)   CUSTOM_NS="$2"; shift ;;
    --build-only)  BUILD_ONLY=true ;;
    --deploy-only) DEPLOY_ONLY=true ;;
    --tag)         CUSTOM_TAG="$2"; shift ;;
    --no-cache)    NO_CACHE="--no-cache" ;;
    *)             err "未知参数: $1"; usage ;;
  esac
  shift
done

if [[ "$BUILD_ONLY" == true && "$DEPLOY_ONLY" == true ]]; then
  err "--build-only 和 --deploy-only 不能同时使用"
  exit 1
fi

if [[ "$BUILD_ONLY" != true && -z "$KUBE_CONTEXT" ]]; then
  err "需要 K8s 操作但未指定 --context，请显式指定目标集群上下文"
  echo ""
  echo "可用上下文:"
  kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do echo "  $ctx"; done
  echo ""
  usage
fi

[[ -n "$CUSTOM_NS" ]] && NAMESPACE="$CUSTOM_NS"

KUBECTL="kubectl"
if [[ -n "$KUBE_CONTEXT" ]]; then
  KUBECTL="kubectl --context $KUBE_CONTEXT"
fi

# ── 确定构建目标列表 ─────────────────────────────────────
TARGETS=()
if [[ "$TARGET" == "all" ]]; then
  TARGETS=(backend admin portal)
elif get_image_name "$TARGET" >/dev/null 2>&1; then
  TARGETS=("$TARGET")
else
  err "未知目标: $TARGET"
  usage
fi

# ── 生成标签 ─────────────────────────────────────────────
if [[ -n "$CUSTOM_TAG" ]]; then
  TAG="$CUSTOM_TAG"
else
  TAG="$(date +%Y%m%d)-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'manual')"
fi

log "镜像标签: $TAG"
log "目标组件: ${TARGETS[*]}"
log "Namespace: $NAMESPACE"
[[ -n "$KUBE_CONTEXT" ]] && log "K8s 上下文: $KUBE_CONTEXT"
echo ""

# ── 构建 & 推送 ──────────────────────────────────────────
build_and_push() {
  local component="$1"
  local image_name; image_name="$(get_image_name "$component")"
  local image="${REGISTRY}/${image_name}:${TAG}"
  local context; context="$(get_build_context "$component")"
  local dockerfile; dockerfile="$(get_dockerfile "$component")"
  local extra_args=""

  if [[ -d "$PROJECT_ROOT/ee" ]]; then
    local ee_df
    ee_df="$(mktemp)"
    case "$component" in
      backend)
        cat "$dockerfile" > "$ee_df"
        echo 'COPY ee/ ./ee/' >> "$ee_df"
        dockerfile="$ee_df"
        ;;
      admin)
        if [[ ! -d "$PROJECT_ROOT/ee/nodeskclaw-frontend" ]]; then
          warn "[$component] ee/nodeskclaw-frontend 不存在，跳过 admin 构建"
          return 0
        fi
        ;;
      portal)
        cat > "$ee_df" <<EODF
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
COPY --from=ee frontend/portal/ /ee/frontend/portal/
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EODF
        dockerfile="$ee_df"
        extra_args="--build-context ee=$PROJECT_ROOT/ee"
        ;;
    esac
    log "[$component] 检测到 ee/ 目录，构建 EE 版镜像"
  elif [[ "$component" == "admin" ]]; then
    warn "[$component] ee/ 目录不存在（CE 版本），跳过 admin 构建"
    return 0
  fi

  log "[$component] 构建镜像: $image"
  if ! docker build --platform linux/amd64 \
    $NO_CACHE \
    $extra_args \
    -f "$dockerfile" \
    --build-arg http_proxy= \
    --build-arg https_proxy= \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    -t "$image" \
    "$context"; then
    err "[$component] 镜像构建失败"
    return 1
  fi

  log "[$component] 推送镜像..."
  if ! docker push "$image"; then
    err "[$component] 镜像推送失败"
    return 1
  fi

  ok "[$component] $image"
}

# ── K8s 滚动更新 ─────────────────────────────────────────
deploy_to_k8s() {
  local component="$1"
  local image_name; image_name="$(get_image_name "$component")"
  local image="${REGISTRY}/${image_name}:${TAG}"
  local deployment; deployment="$(get_k8s_deployment "$component")"
  local container="$image_name"

  log "[$component] 更新 Deployment: $deployment -> $image (context: $KUBE_CONTEXT)"

  if ! $KUBECTL -n "$NAMESPACE" get deployment "$deployment" &>/dev/null; then
    warn "[$component] Deployment 不存在，执行首次部署..."
    $KUBECTL -n "$NAMESPACE" apply -f "$SCRIPT_DIR/k8s/${component}.yaml"
  fi

  $KUBECTL -n "$NAMESPACE" set image "deployment/$deployment" "$container=$image"

  log "[$component] 等待滚动更新完成..."
  if $KUBECTL -n "$NAMESPACE" rollout status "deployment/$deployment" --timeout=180s; then
    ok "[$component] 部署完成"
  else
    err "[$component] 部署超时，请检查 Pod 状态"
    $KUBECTL -n "$NAMESPACE" get pods -l "app=$deployment"
    return 1
  fi
}

# ── 执行 ─────────────────────────────────────────────────
FAILED=()

for t in "${TARGETS[@]}"; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ "$DEPLOY_ONLY" != true ]]; then
    if ! build_and_push "$t"; then
      FAILED+=("$t:build")
      continue
    fi
  fi

  if [[ "$BUILD_ONLY" != true ]]; then
    if ! deploy_to_k8s "$t"; then
      FAILED+=("$t:deploy")
    fi
  fi
done

# ── 结果汇总 ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "部署摘要"
echo "  标签: $TAG"
echo "  仓库: $REGISTRY"
echo "  Namespace: $NAMESPACE"
[[ -n "$KUBE_CONTEXT" ]] && echo "  集群: $KUBE_CONTEXT"
for t in "${TARGETS[@]}"; do
  local_failed=false
  for f in "${FAILED[@]+"${FAILED[@]}"}"; do
    [[ "$f" == "$t:"* ]] && local_failed=true
  done
  if $local_failed; then
    echo -e "  ${RED}✗${NC} $t"
  else
    echo -e "  ${GREEN}✓${NC} $t"
  fi
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
  err "部分组件失败: ${FAILED[*]}"
  exit 1
fi

ok "全部完成"
