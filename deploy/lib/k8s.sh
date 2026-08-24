#!/usr/bin/env bash

diff_secret() {
  local secret_name="$1" clean_env="$2"
  if ! $KUBECTL -n "$NAMESPACE" get secret "$secret_name" &>/dev/null; then
    return 1
  fi
  local current_json
  current_json=$($KUBECTL -n "$NAMESPACE" get secret "$secret_name" -o jsonpath='{.data}')
  python3 -c "
import sys, json, base64
cur_b64 = json.loads(sys.argv[1]) if sys.argv[1] else {}
cur = {k: base64.b64decode(v).decode() for k, v in cur_b64.items()}
new = {}
with open(sys.argv[2]) as f:
    for line in f:
        line = line.strip()
        if not line or '=' not in line:
            continue
        k, v = line.split('=', 1)
        new[k] = v
added = sorted(set(new) - set(cur))
removed = sorted(set(cur) - set(new))
changed = sorted(k for k in set(new) & set(cur) if new[k] != cur[k])
if not added and not removed and not changed:
    sys.exit(10)
for k in changed:  print(f'  [变更] {k}')
for k in added:    print(f'  [新增] {k}')
for k in removed:  print(f'  [移除] {k} (将从 Secret 中删除)')
sys.exit(0)
" "$current_json" "$clean_env"
}

read_env_value() {
  local key="$1" env_file="$2"
  awk -v key="$key" 'index($0, key "=") == 1 {print substr($0, length(key) + 2)}' "$env_file" | tail -n 1
}

generate_hosted_registry_htpasswd() {
  local username="$1" password="$2"
  if command -v htpasswd >/dev/null 2>&1; then
    printf '%s\n%s\n' "$password" "$password" | htpasswd -Bni "$username"
    return
  fi
  if ! command -v docker >/dev/null 2>&1; then
    err "Hosted Registry 需要 htpasswd，或可运行 Docker 的环境"
    exit 1
  fi
  printf '%s\n%s\n' "$password" "$password" \
    | docker run --rm -i --platform linux/amd64 --entrypoint htpasswd \
        httpd:2.4-alpine -Bni "$username"
}

init_hosted_registry() {
  local env_file="$1"
  local registry_url username password tls_secret storage_class storage_size ingress_class
  registry_url="$(read_env_value HOSTED_REGISTRY_URL "$env_file")"
  username="$(read_env_value HOSTED_REGISTRY_USERNAME "$env_file")"
  password="$(read_env_value HOSTED_REGISTRY_PASSWORD "$env_file")"
  tls_secret="$(read_env_value HOSTED_REGISTRY_TLS_SECRET "$env_file")"
  storage_class="$(read_env_value HOSTED_REGISTRY_STORAGE_CLASS "$env_file")"
  storage_size="$(read_env_value HOSTED_REGISTRY_STORAGE_SIZE "$env_file")"
  ingress_class="$(read_env_value HOSTED_REGISTRY_INGRESS_CLASS "$env_file")"

  registry_url="${registry_url#http://}"
  registry_url="${registry_url#https://}"
  registry_url="${registry_url%/}"
  local registry_host="${registry_url%%/*}"

  [[ -n "$registry_url" ]] || { err "HOSTED_REGISTRY_URL 未配置"; exit 1; }
  [[ -n "$username" ]] || { err "HOSTED_REGISTRY_USERNAME 未配置"; exit 1; }
  [[ -n "$password" ]] || { err "HOSTED_REGISTRY_PASSWORD 未配置"; exit 1; }
  [[ -n "$tls_secret" ]] || { err "HOSTED_REGISTRY_TLS_SECRET 未配置"; exit 1; }
  [[ "$registry_host" =~ ^[a-zA-Z0-9.-]+$ ]] || { err "Hosted Registry 域名格式无效"; exit 1; }
  [[ "$username" =~ ^[a-zA-Z0-9._-]+$ ]] || { err "Hosted Registry 用户名格式无效"; exit 1; }
  [[ "$tls_secret" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] || { err "Hosted Registry TLS Secret 名称格式无效"; exit 1; }

  storage_size="${storage_size:-100Gi}"
  ingress_class="${ingress_class:-nginx}"
  [[ "$storage_size" =~ ^[1-9][0-9]*(Mi|Gi|Ti)$ ]] || { err "HOSTED_REGISTRY_STORAGE_SIZE 格式无效"; exit 1; }
  [[ "$ingress_class" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] || { err "Hosted Registry Ingress Class 格式无效"; exit 1; }
  if [[ -n "$storage_class" && ! "$storage_class" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]]; then
    err "Hosted Registry StorageClass 名称格式无效"
    exit 1
  fi

  if ! $KUBECTL -n "$NAMESPACE" get secret "$tls_secret" >/dev/null 2>&1; then
    err "Hosted Registry TLS Secret 不存在: $NAMESPACE/$tls_secret"
    exit 1
  fi

  HOSTED_REGISTRY_HTPASSWD_FILE="$(mktemp)"
  HOSTED_REGISTRY_MANIFEST_FILE="$(mktemp)"
  generate_hosted_registry_htpasswd "$username" "$password" > "$HOSTED_REGISTRY_HTPASSWD_FILE"

  $KUBECTL -n "$NAMESPACE" create secret generic nodeskclaw-hosted-registry-auth \
    --from-file=htpasswd="$HOSTED_REGISTRY_HTPASSWD_FILE" \
    --dry-run=client -o yaml | $KUBECTL apply -f -

  sed \
    -e "s|<HOSTED_REGISTRY_STORAGE_CLASS>|${storage_class}|g" \
    -e "s|<HOSTED_REGISTRY_STORAGE_SIZE>|${storage_size}|g" \
    -e "s|<HOSTED_REGISTRY_INGRESS_CLASS>|${ingress_class}|g" \
    -e "s|<HOSTED_REGISTRY_HOST>|${registry_host}|g" \
    -e "s|<HOSTED_REGISTRY_TLS_SECRET>|${tls_secret}|g" \
    "$DEPLOY_DIR/k8s/hosted-registry.yaml" > "$HOSTED_REGISTRY_MANIFEST_FILE"
  if [[ -z "$storage_class" ]]; then
    sed -i.bak '/^[[:space:]]*storageClassName:[[:space:]]*$/d' "$HOSTED_REGISTRY_MANIFEST_FILE"
    rm -f "${HOSTED_REGISTRY_MANIFEST_FILE}.bak"
  fi

  $KUBECTL -n "$NAMESPACE" apply -f "$HOSTED_REGISTRY_MANIFEST_FILE"
  $KUBECTL -n "$NAMESPACE" rollout status deployment/nodeskclaw-hosted-registry --timeout=180s
  rm -f "$HOSTED_REGISTRY_HTPASSWD_FILE" "$HOSTED_REGISTRY_MANIFEST_FILE"
  HOSTED_REGISTRY_HTPASSWD_FILE=""
  HOSTED_REGISTRY_MANIFEST_FILE=""
  ok "Hosted Registry 已初始化: https://${registry_host}"
}

deploy_to_k8s() {
  local component="$1"
  local image_name; image_name="$(get_image_name "$component")"
  local comp_registry; comp_registry="$(get_component_registry "$component")"
  local image="${comp_registry}/${image_name}:${TAG}"
  local deployment; deployment="$(get_k8s_deployment "$component")"
  local container; container="$(get_k8s_container "$component")"

  log "[$(ctag "$component")] 更新 Deployment: $deployment -> $image (context: $KUBE_CONTEXT)"

  if ! $KUBECTL -n "$NAMESPACE" get deployment "$deployment" &>/dev/null; then
    warn "[$(ctag "$component")] Deployment 不存在，执行首次部署..."
    if [[ "$component" == "proxy" ]]; then
      local proxy_dir="$PROJECT_ROOT/nodeskclaw-llm-proxy/deploy"
      [[ -f "$proxy_dir/deployment.yaml" ]] && \
        sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${comp_registry}|g" "$proxy_dir/deployment.yaml" \
          | $KUBECTL -n "$NAMESPACE" apply -f -
      [[ -f "$proxy_dir/service.yaml" ]] && \
        $KUBECTL -n "$NAMESPACE" apply -f "$proxy_dir/service.yaml"
    else
      local manifest="$DEPLOY_DIR/k8s/${component}.yaml"
      [[ -f "$manifest" ]] && \
        sed "s|<YOUR_REGISTRY>/<YOUR_NAMESPACE>|${comp_registry}|g" "$manifest" \
          | $KUBECTL -n "$NAMESPACE" apply -f -
    fi
  fi

  $KUBECTL -n "$NAMESPACE" set image "deployment/$deployment" "$container=$image"

  log "[$(ctag "$component")] 等待滚动更新完成..."
  local timeout=180
  [[ "$component" == "proxy" ]] && timeout=120
  if $KUBECTL -n "$NAMESPACE" rollout status "deployment/$deployment" --timeout="${timeout}s"; then
    ok "[$(ctag "$component")] 部署完成"
  else
    err "[$(ctag "$component")] 部署超时，请检查 Pod 状态"
    $KUBECTL -n "$NAMESPACE" get pods -l "app=$deployment"
    return 1
  fi
}
