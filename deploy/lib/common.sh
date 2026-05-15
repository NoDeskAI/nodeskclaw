#!/usr/bin/env bash

DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$DEPLOY_LIB_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
PUBLIC_REGISTRY=""
KUBE_CONTEXT=""
STAGING_NS="nodeskclaw-staging"
PROD_NS="nodeskclaw-system"

[[ -f "$DEPLOY_DIR/.env.local" ]] && source "$DEPLOY_DIR/.env.local"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
AMBER='\033[0;33m'
NC='\033[0m'

log()  { echo -e "${CYAN}[NoDeskClaw]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

confirm() {
  echo ""
  echo -e "${YELLOW}$1${NC}"
  read -r -p "继续? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { log "已取消"; exit 0; }
}

require_option_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    err "$option 需要参数"
    exit 1
  fi
}

ctag() {
  case "$1" in
    backend) echo -e "${BLUE}backend${NC}" ;;
    admin)   echo -e "${RED}admin${NC}" ;;
    portal)  echo -e "${GREEN}portal${NC}" ;;
    proxy)   echo -e "${AMBER}proxy${NC}" ;;
    genehub) echo -e "${CYAN}genehub${NC}" ;;
    *)       echo "$1" ;;
  esac
}

get_image_name() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    proxy)   echo "nodeskclaw-llm-proxy" ;;
    genehub) echo "genehub-registry" ;;
    *)       return 1 ;;
  esac
}

get_build_context() {
  case "$1" in
    backend) echo "$PROJECT_ROOT" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal" ;;
    proxy)   echo "$PROJECT_ROOT/nodeskclaw-llm-proxy" ;;
    genehub) echo "$PROJECT_ROOT/genehub" ;;
    *)       return 1 ;;
  esac
}

get_dockerfile() {
  case "$1" in
    backend) echo "$PROJECT_ROOT/nodeskclaw-backend/Dockerfile" ;;
    admin)   echo "$PROJECT_ROOT/ee/nodeskclaw-frontend/Dockerfile" ;;
    portal)  echo "$PROJECT_ROOT/nodeskclaw-portal/Dockerfile" ;;
    proxy)   echo "$PROJECT_ROOT/nodeskclaw-llm-proxy/Dockerfile" ;;
    genehub) echo "$PROJECT_ROOT/genehub/Dockerfile" ;;
    *)       return 1 ;;
  esac
}

get_k8s_deployment() {
  case "$1" in
    backend) echo "nodeskclaw-backend" ;;
    admin)   echo "nodeskclaw-admin" ;;
    portal)  echo "nodeskclaw-portal" ;;
    proxy)   echo "nodeskclaw-llm-proxy" ;;
    genehub) echo "genehub" ;;
    *)       return 1 ;;
  esac
}

get_k8s_container() {
  case "$1" in
    proxy)   echo "llm-proxy" ;;
    genehub) echo "genehub" ;;
    *)       get_image_name "$1" ;;
  esac
}

get_component_registry() {
  case "$1" in
    admin) echo "$REGISTRY" ;;
    *)     echo "${PUBLIC_REGISTRY:-$REGISTRY}" ;;
  esac
}

require_context() {
  if [[ -z "$KUBE_CONTEXT" ]]; then
    err "需要 K8s 操作但未配置上下文"
    echo ""
    echo "请在 deploy/.env.local 中设置 KUBE_CONTEXT，或使用 --context 参数"
    echo ""
    echo "可用上下文:"
    kubectl config get-contexts -o name 2>/dev/null | while read -r ctx; do echo "  $ctx"; done
    exit 1
  fi
}

require_gh() {
  if ! command -v gh &>/dev/null; then
    err "gh CLI 未安装。请运行: brew install gh"
    exit 1
  fi
  if ! gh auth status &>/dev/null; then
    err "gh CLI 未认证。请运行: gh auth login"
    exit 1
  fi
}

load_mirrors() {
  local mirrors="$1"
  [[ -z "$mirrors" ]] && return 0

  local mirrors_file="$DEPLOY_DIR/mirrors/${mirrors}.env"
  if [[ ! -f "$mirrors_file" ]]; then
    err "镜像预设不存在: $mirrors_file"
    echo "可用预设:"
    for f in "$DEPLOY_DIR/mirrors/"*.env; do
      [[ -f "$f" ]] && echo "  $(basename "$f" .env)"
    done
    exit 1
  fi
  source "$mirrors_file"
  log "使用镜像预设: $mirrors"
}

configure_kubectl() {
  KUBECTL="kubectl"
  [[ -n "$KUBE_CONTEXT" ]] && KUBECTL="kubectl --context $KUBE_CONTEXT"
}

set_namespace() {
  if [[ "${IS_PROD:-false}" == true ]]; then
    NAMESPACE="$PROD_NS"
  else
    NAMESPACE="$STAGING_NS"
  fi
}

ensure_edition() {
  if [[ "${EE_MODE:-false}" == true ]]; then
    if [[ ! -d "$PROJECT_ROOT/ee" ]]; then
      err "--ee 模式需要 ee/ 目录（仅 EE 开发环境可用）"
      exit 1
    fi
    CE_ONLY=false
  else
    CE_ONLY=true
  fi
}

validate_target() {
  local target="$1"
  if [[ "$target" != "all" ]] && ! get_image_name "$target" >/dev/null 2>&1; then
    err "未知目标: $target"
    return 1
  fi
  if [[ "$target" == "admin" && "${EE_MODE:-false}" != true ]]; then
    err "admin 组件需要 --ee 参数"
    return 1
  fi
}

get_all_targets() {
  local targets=(backend portal)
  [[ "${EE_MODE:-false}" == true ]] && targets=(backend admin portal)
  [[ "${SKIP_PROXY:-false}" != true ]] && targets+=(proxy)
  [[ "${SKIP_GENEHUB:-false}" != true ]] && targets+=(genehub)
  echo "${targets[@]}"
}

format_targets() {
  local colored_targets=""
  for target in "$@"; do
    [[ -n "$colored_targets" ]] && colored_targets+=" "
    colored_targets+="$(ctag "$target")"
  done
  echo "$colored_targets"
}
