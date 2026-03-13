#!/bin/bash
# 构建 amd64 架构的 OpenClaw 镜像并推送到容器镜像仓库
#
# 用法:
#   ./build-and-push.sh                                           # base 镜像（默认版本）
#   ./build-and-push.sh --version 2026.2.26                       # base 镜像（指定版本）
#   ./build-and-push.sh --with-security --base-tag v2026.2.26     # 安全层镜像
#   ./build-and-push.sh --build-only                              # 仅构建，不推送
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>/nodeskclaw-openclaw-base"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"

check_docker
parse_common_args "$@"

if [ "${WITH_SECURITY}" = true ]; then
  # ── 安全层模式 ──────────────────────────────────
  DOCKERFILE="${SCRIPT_DIR}/Dockerfile.security"
  CONTEXT_DIR="${SCRIPT_DIR}/../../"
  IMAGE_TAG="${BASE_TAG}-sec"

  print_build_summary "OpenClaw (security)" "${BASE_TAG}" "${REGISTRY}" "linux/amd64" "security"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    -f "${DOCKERFILE}" \
    --build-arg BASE_TAG="${BASE_TAG}" \
    --build-arg BASE_REGISTRY="${REGISTRY}"
else
  # ── Base 模式（现有逻辑不变）─────────────────────
  if [ -z "${VERSION}" ]; then
    VERSION=$(sed -n 's/^ARG OPENCLAW_VERSION=//p' "${DOCKERFILE}")
    if [ -z "${VERSION}" ]; then
      log_error "无法从 Dockerfile 读取 OPENCLAW_VERSION"
      exit 1
    fi
    log_info "使用 Dockerfile 中的版本: ${VERSION}"
  fi

  log_info "验证 openclaw@${VERSION} 在 npm 上是否存在..."
  NPM_INFO=$(npm view "openclaw@${VERSION}" version 2>/dev/null || true)
  if [ -z "${NPM_INFO}" ]; then
    log_error "openclaw@${VERSION} 在 npm 上不存在"
    echo "可用的最新版本:"
    npm view openclaw versions --json 2>/dev/null | tail -10
    exit 1
  fi
  log_success "openclaw@${VERSION} 存在"

  IMAGE_TAG="v${VERSION}"
  CONTEXT_DIR="${SCRIPT_DIR}"

  print_build_summary "OpenClaw" "${VERSION}" "${REGISTRY}" "linux/amd64" "base"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    --build-arg OPENCLAW_VERSION="${VERSION}" \
    --build-arg IMAGE_VERSION="${IMAGE_TAG}"
fi

log_success "构建完成"

if [ "${SKIP_VERIFY}" = false ] && [ "${WITH_SECURITY}" = false ]; then
  log_info "验证镜像（Apple Silicon 上较慢，可用 --skip-verify 跳过）..."
  echo "  Node.js: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" node --version)"
  echo "  OpenClaw: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" openclaw --version 2>/dev/null || echo '(需启动后验证)')"
  echo "  版本标记: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" cat /root/.openclaw-version)"
fi

if [ "${BUILD_ONLY}" = true ]; then
  log_info "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG}"
  exit 0
fi

docker_push "${REGISTRY}:${IMAGE_TAG}"
print_done "${REGISTRY}:${IMAGE_TAG}"
