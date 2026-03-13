#!/bin/bash
# 构建 amd64 架构的 Nanobot 镜像并推送到容器镜像仓库
#
# 用法:
#   ./build-and-push.sh --version 0.1.0                            # base 镜像
#   ./build-and-push.sh --with-security --base-tag v0.1.0          # 安全层镜像
#   ./build-and-push.sh --version 0.1.0 --build-only               # 仅构建
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>/nodeskclaw-nanobot-base"

check_docker
parse_common_args "$@"

if [ "${WITH_SECURITY}" = true ]; then
  # ── 安全层模式 ──────────────────────────────────
  DOCKERFILE="${SCRIPT_DIR}/Dockerfile.security"
  CONTEXT_DIR="${SCRIPT_DIR}/../../"
  IMAGE_TAG="${BASE_TAG}-sec"

  print_build_summary "Nanobot (security)" "${BASE_TAG}" "${REGISTRY}" "linux/amd64" "security"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    -f "${DOCKERFILE}" \
    --build-arg BASE_TAG="${BASE_TAG}" \
    --build-arg BASE_REGISTRY="${REGISTRY}"
else
  # ── Base 模式（现有逻辑不变）─────────────────────
  if [ -z "${VERSION}" ]; then
    log_error "必须通过 --version 指定 Nanobot 版本（如 0.1.0）"
    exit 1
  fi

  IMAGE_TAG="v${VERSION}"
  CONTEXT_DIR="${SCRIPT_DIR}"

  print_build_summary "Nanobot" "${VERSION}" "${REGISTRY}" "linux/amd64" "base"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    --build-arg NANOBOT_VERSION="${VERSION}" \
    --build-arg IMAGE_VERSION="${IMAGE_TAG}"
fi

log_success "构建完成"

if [ "${SKIP_VERIFY}" = false ] && [ "${WITH_SECURITY}" = false ]; then
  log_info "验证镜像..."
  echo "  Python: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" python --version)"
  echo "  Nanobot: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" pip show nanobot-ai 2>/dev/null | grep Version || echo '(需启动后验证)')"
fi

if [ "${BUILD_ONLY}" = true ]; then
  log_info "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG}"
  exit 0
fi

docker_push "${REGISTRY}:${IMAGE_TAG}"
print_done "${REGISTRY}:${IMAGE_TAG}"
