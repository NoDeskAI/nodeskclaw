#!/usr/bin/env bash
# NoDeskClaw init CLI: initialize K8s namespace, Secret, and base manifests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/k8s.sh"

usage() {
  local exit_code="${1:-1}"
  cat <<EOF
用法: $0 [options]

初始化目标 Namespace、后端 Secret 和基础 Deployment/Service。

选项:
  --ee             EE 模式（包含 admin，写入 NODESKCLAW_EDITION=ee）
  --staging        staging 环境（默认，可省略）
  --prod           生产环境
  --context CTX    覆盖默认 K8s 上下文
  --env-file FILE  指定 .env 文件（默认 nodeskclaw-backend/.env）
  --force          跳过 Secret 差异确认
EOF
  exit "$exit_code"
}

cmd_init() {
  ensure_edition
  set_namespace
  configure_kubectl
  require_context

  local env_file="${ENV_FILE:-$PROJECT_ROOT/nodeskclaw-backend/.env}"

  if [[ ! -f "$env_file" ]]; then
    err "环境变量文件不存在: $env_file"
    echo "请复制 .env.example 并填写实际值:"
    echo "  cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env"
    exit 1
  fi

  log "集群: $KUBE_CONTEXT"
  log "Namespace: $NAMESPACE"

  log "检查 Namespace: $NAMESPACE"
  if ! $KUBECTL get namespace "$NAMESPACE" &>/dev/null; then
    log "创建 Namespace..."
    $KUBECTL create namespace "$NAMESPACE"
  fi
  ok "Namespace $NAMESPACE 就绪"

  local clean_env; clean_env=$(mktemp)
  trap 'rm -f "$clean_env" "${clean_env}.tmp"' EXIT

  while IFS= read -r line; do
    stripped="${line%%#*}"
    stripped="$(printf '%s' "$stripped" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$stripped" || "$stripped" != *"="* ]] && continue
    echo "$stripped"
  done < "$env_file" > "$clean_env"

  if [[ ! -s "$clean_env" ]]; then
    err ".env 文件中没有有效的键值对"
    exit 1
  fi

  local edition_val="ce"
  [[ "$EE_MODE" == true ]] && edition_val="ee"
  grep -v '^NODESKCLAW_EDITION=' "$clean_env" > "${clean_env}.tmp" || true
  mv "${clean_env}.tmp" "$clean_env"
  echo "NODESKCLAW_EDITION=${edition_val}" >> "$clean_env"
  log "NODESKCLAW_EDITION=${edition_val}（由 --ee 标志决定）"

  local env_count; env_count=$(wc -l < "$clean_env" | xargs)
  local secret_name="nodeskclaw-backend-env"

  if diff_output=$(diff_secret "$secret_name" "$clean_env" 2>&1); then
    warn "Secret $secret_name 已存在，检测到以下差异:"
    echo "$diff_output"
    if [[ "$FORCE" == true ]]; then
      log "--force 模式，跳过确认"
    else
      confirm "是否覆盖 Secret $secret_name？"
    fi
    log "更新 Secret: $secret_name"
    $KUBECTL -n "$NAMESPACE" create secret generic "$secret_name" \
      --from-env-file="$clean_env" \
      --dry-run=client -o yaml | $KUBECTL apply -f -
    ok "Secret $secret_name 已更新 ($env_count 个变量)"
  elif [[ $? -eq 10 ]]; then
    ok "Secret $secret_name 无变更，跳过"
  else
    log "创建 Secret: $secret_name"
    $KUBECTL -n "$NAMESPACE" create secret generic "$secret_name" \
      --from-env-file="$clean_env" \
      --dry-run=client -o yaml | $KUBECTL apply -f -
    ok "Secret $secret_name 已创建 ($env_count 个变量)"
  fi

  log "应用 K8s 部署清单（Deployment + Service）..."
  for f in backend.yaml admin.yaml portal.yaml genehub.yaml; do
    [[ "$f" == "admin.yaml" && "$EE_MODE" != true ]] && continue
    if [[ -f "$DEPLOY_DIR/k8s/$f" ]]; then
      local comp_name="${f%.yaml}"
      local comp_reg; comp_reg="$(get_component_registry "$comp_name" 2>/dev/null || echo "${PUBLIC_REGISTRY:-$REGISTRY}")"
      sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${comp_reg}|g" "$DEPLOY_DIR/k8s/$f" \
        | $KUBECTL -n "$NAMESPACE" apply -f -
      ok "$f"
    fi
  done
  log "Ingress 需要单独配置域名后手动 apply:"
  log "  kubectl --context $KUBE_CONTEXT -n $NAMESPACE apply -f $DEPLOY_DIR/k8s/ingress.yaml"

  echo ""
  log "初始化完成。接下来运行部署:"
  echo ""
  echo "  ./deploy/deploy.sh deploy --tag <TAG> --context $KUBE_CONTEXT"
  echo ""
  log "当前 Deployment 状态:"
  $KUBECTL -n "$NAMESPACE" get deployments \
    -l 'app in (nodeskclaw-backend, nodeskclaw-admin, nodeskclaw-portal)' 2>/dev/null || true
}

ENV_FILE=""
FORCE=false
IS_PROD=false
EE_MODE=false
CE_ONLY=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ee)          EE_MODE=true ;;
    --staging)     IS_PROD=false ;;
    --prod)        IS_PROD=true ;;
    --context)     require_option_value "$1" "${2:-}"; KUBE_CONTEXT="$2"; shift ;;
    --env-file)    require_option_value "$1" "${2:-}"; ENV_FILE="$2"; shift ;;
    --force)       FORCE=true ;;
    --help|-h)     usage 0 ;;
    *)             err "未知参数: $1"; usage 1 ;;
  esac
  shift
done

cmd_init
