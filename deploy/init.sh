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
  --staging        staging 环境（需显式指定）
  --prod           生产环境
  --context CTX    覆盖默认 K8s 上下文
  --env-file FILE  指定 .env 文件（默认 nodeskclaw-backend/.env）
  --with-hosted-registry  部署 Hosted Registry（配置从 env 文件读取）
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

  local backend_preexisting=false
  if $KUBECTL -n "$NAMESPACE" get deployment nodeskclaw-backend &>/dev/null; then
    backend_preexisting=true
  fi

  local clean_env; clean_env=$(mktemp)
  trap 'rm -f "$clean_env" "${clean_env}.tmp" "${HOSTED_REGISTRY_HTPASSWD_FILE:-}" "${HOSTED_REGISTRY_MANIFEST_FILE:-}"' EXIT

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

  if [[ "$WITH_HOSTED_REGISTRY" == true ]]; then
    grep -v '^REGISTRY_MODE=' "$clean_env" > "${clean_env}.tmp" || true
    mv "${clean_env}.tmp" "$clean_env"
    echo "REGISTRY_MODE=hosted" >> "$clean_env"
    log "REGISTRY_MODE=hosted（由 --with-hosted-registry 标志决定）"
  fi

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

  if [[ "$WITH_HOSTED_REGISTRY" == true ]]; then
    init_hosted_registry "$clean_env"
  fi

  log "应用 K8s 部署清单（Deployment + Service）..."
  for f in backend.yaml admin.yaml portal.yaml; do
    [[ "$f" == "admin.yaml" && "$EE_MODE" != true ]] && continue
    if [[ -f "$DEPLOY_DIR/k8s/$f" ]]; then
      local comp_name="${f%.yaml}"
      local comp_reg; comp_reg="$(get_component_registry "$comp_name")"
      sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${comp_reg}|g" "$DEPLOY_DIR/k8s/$f" \
        | $KUBECTL -n "$NAMESPACE" apply -f -
      ok "$f"
    fi
  done
  if [[ "$WITH_HOSTED_REGISTRY" == true && "$backend_preexisting" == true ]]; then
    log "重启后端以加载 Hosted Registry 环境配置..."
    $KUBECTL -n "$NAMESPACE" rollout restart deployment/nodeskclaw-backend
    $KUBECTL -n "$NAMESPACE" rollout status deployment/nodeskclaw-backend --timeout=180s
    ok "后端已加载 Hosted Registry 环境配置"
    log "如系统当前仍使用 Custom Registry，请在 Admin 或 Portal 的镜像仓库设置中切换为团队托管仓库。"
  fi
  log "Ingress 需要单独配置域名后手动 apply:"
  log "  kubectl --context $KUBE_CONTEXT -n $NAMESPACE apply -f $DEPLOY_DIR/k8s/ingress.yaml"

  local env_flag="--staging"
  [[ "$IS_PROD" == true ]] && env_flag="--prod"

  echo ""
  log "初始化完成。接下来运行部署:"
  echo ""
  echo "  ./deploy/deploy.sh deploy --tag <TAG> $env_flag --context $KUBE_CONTEXT"
  echo ""
  log "当前 Deployment 状态:"
  $KUBECTL -n "$NAMESPACE" get deployments \
    -l 'app in (nodeskclaw-backend, nodeskclaw-admin, nodeskclaw-portal)' 2>/dev/null || true
}

ENV_FILE=""
FORCE=false
IS_PROD=false
IS_STAGING=false
EE_MODE=false
CE_ONLY=true
WITH_HOSTED_REGISTRY=false
HOSTED_REGISTRY_HTPASSWD_FILE=""
HOSTED_REGISTRY_MANIFEST_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ee)          EE_MODE=true ;;
    --staging)     IS_STAGING=true; IS_PROD=false ;;
    --prod)        IS_PROD=true; IS_STAGING=false ;;
    --context)     require_option_value "$1" "${2:-}"; KUBE_CONTEXT="$2"; shift ;;
    --env-file)    require_option_value "$1" "${2:-}"; ENV_FILE="$2"; shift ;;
    --with-hosted-registry) WITH_HOSTED_REGISTRY=true ;;
    --force)       FORCE=true ;;
    --help|-h)     usage 0 ;;
    *)             err "未知参数: $1"; usage 1 ;;
  esac
  shift
done

cmd_init
