#!/bin/bash
# 构建 amd64 架构的 Nanobot 镜像并推送到容器镜像仓库
#
# 用法:
#   ./build-and-push.sh --version 0.1.0
#   ./build-and-push.sh --version 0.1.0 --build-only
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>/nodeskclaw-nanobot-base"

check_docker
parse_common_args "$@"

if [ -z "${VERSION}" ]; then
  log_error "必须通过 --version 指定 Nanobot 版本（如 0.1.0）"
  exit 1
fi

IMAGE_TAG="v${VERSION}"

print_build_summary "Nanobot" "${VERSION}" "${REGISTRY}"

docker_build "${SCRIPT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
  --build-arg NANOBOT_VERSION="${VERSION}" \
  --build-arg IMAGE_VERSION="${IMAGE_TAG}"

log_success "构建完成"

if [ "${SKIP_VERIFY}" = false ]; then
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
