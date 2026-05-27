#!/usr/bin/env bash
# NoDeskClaw deploy CLI: update K8s deployments to an existing image tag.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/k8s.sh"

usage() {
  local exit_code="${1:-1}"
  cat <<EOF
用法: $0 deploy [target] --tag TAG [options]

命令:
  deploy [target]   将指定组件更新到已存在镜像标签

目标:
  all       backend + portal + proxy + genehub（默认；--ee 时加 admin）
  backend   后端
  admin     Admin 前端（需 --ee）
  portal    Portal 前端
  proxy     LLM Proxy
  genehub   GeneHub 基因库

选项:
  --tag TAG         必填，目标镜像标签
  --ee              EE 模式（包含 admin）
  --staging         staging 环境（默认，可省略）
  --prod            生产环境（需交互确认）
  --context CTX     覆盖默认 K8s 上下文
  --skip-proxy      all 时跳过 proxy
  --skip-genehub    all 时跳过 genehub
  --mirrors NAME    加载镜像源预设中的仓库相关配置
EOF
  exit "$exit_code"
}

cmd_deploy() {
  if [[ -z "$TAG" ]]; then
    err "deploy 命令必须通过 --tag 指定已存在的镜像标签"
    exit 1
  fi

  ensure_edition
  load_mirrors "$MIRRORS"
  set_namespace
  configure_kubectl
  require_context

  validate_target "$TARGET" || usage 1

  local targets=()
  if [[ "$TARGET" == "all" ]]; then
    read -ra targets <<< "$(get_all_targets)"
  else
    targets=("$TARGET")
  fi

  log "镜像标签: ${TAG}"
  log "目标组件: $(format_targets "${targets[@]}")"
  log "Namespace: $NAMESPACE"
  log "K8s 上下文: $KUBE_CONTEXT"
  echo ""

  if [[ "$IS_PROD" == true ]]; then
    log "部署计划（${#targets[@]} 个组件）:"
    echo ""
    for target in "${targets[@]}"; do
      local image_name; image_name="$(get_image_name "$target")"
      local comp_registry; comp_registry="$(get_component_registry "$target")"
      local new_image="${comp_registry}/${image_name}:${TAG}"
      local deployment; deployment="$(get_k8s_deployment "$target")"
      local container; container="$(get_k8s_container "$target")"
      local current_image=""
      local jsonpath="{.spec.template.spec.containers[?(@.name==\"${container}\")].image}"
      current_image=$($KUBECTL -n "$NAMESPACE" get deployment "$deployment" \
        -o jsonpath="$jsonpath" 2>/dev/null) || true

      echo -e "  $(ctag "$target")"
      if [[ -z "$current_image" ]]; then
        echo -e "    当前: ${YELLOW}(未部署)${NC}"
      elif [[ "$current_image" == "$new_image" ]]; then
        echo -e "    当前: $current_image ${YELLOW}(已是目标版本)${NC}"
      else
        echo -e "    当前: $current_image"
      fi
      echo -e "    目标: ${GREEN}${new_image}${NC}"
      echo ""
    done
    confirm "确认将以上 ${#targets[@]} 个组件部署到生产环境？"
  fi

  for target in "${targets[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ! deploy_to_k8s "$target"; then
      err "[$(ctag "$target")] 部署失败，中止后续组件"
      exit 1
    fi
  done

  echo ""
  ok "部署完成（标签: ${TAG}, Namespace: ${NAMESPACE}）"
}

[[ $# -lt 1 ]] && usage 1

COMMAND="$1"; shift
TARGET="all"
TAG=""
SKIP_PROXY=false
SKIP_GENEHUB=false
IS_PROD=false
EE_MODE=false
CE_ONLY=true
MIRRORS="${MIRRORS:-}"

case "$COMMAND" in
  deploy)
    if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
      TARGET="$1"
      shift
    fi
    ;;
  --help|-h)
    usage 0
    ;;
  *)
    err "未知命令: $COMMAND"
    usage 1
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)         require_option_value "$1" "${2:-}"; TAG="$2"; shift ;;
    --ee)          EE_MODE=true ;;
    --staging)     IS_PROD=false ;;
    --prod)        IS_PROD=true ;;
    --context)     require_option_value "$1" "${2:-}"; KUBE_CONTEXT="$2"; shift ;;
    --skip-proxy)    SKIP_PROXY=true ;;
    --skip-genehub)  SKIP_GENEHUB=true ;;
    --mirrors)       require_option_value "$1" "${2:-}"; MIRRORS="$2"; shift ;;
    --help|-h)       usage 0 ;;
    *)               err "未知参数: $1"; usage 1 ;;
  esac
  shift
done

cmd_deploy
