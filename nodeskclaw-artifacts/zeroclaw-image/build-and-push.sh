#!/bin/bash
# 构建 amd64 架构的 ZeroClaw 镜像并推送到容器镜像仓库
#
# 用法:
#   ./build-and-push.sh --version v0.1.0                            # base 镜像（预编译二进制）
#   ./build-and-push.sh --with-security --base-tag v0.1.0           # 安全层镜像（Rust 源码构建）
#   ./build-and-push.sh --version v0.1.0 --build-only               # 仅构建
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>/nodeskclaw-zeroclaw-base"

check_docker
parse_common_args "$@"

if [ "${WITH_SECURITY}" = true ]; then
  # ── 安全层模式（多阶段 Rust 源码构建）──────────
  DOCKERFILE="${SCRIPT_DIR}/Dockerfile.security"
  CONTEXT_DIR="${SCRIPT_DIR}/../../"
  IMAGE_TAG="${BASE_TAG}-sec"

  ZEROCLAW_REPO="${ZEROCLAW_REPO:-https://github.com/nicholasgasior/zeroclaw.git}"
  ZEROCLAW_REF="${ZEROCLAW_REF:-main}"

  print_build_summary "ZeroClaw (security)" "${BASE_TAG}" "${REGISTRY}" "linux/amd64" "security"
  log_info "ZeroClaw 源码: ${ZEROCLAW_REPO} @ ${ZEROCLAW_REF}"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    -f "${DOCKERFILE}" \
    --build-arg ZEROCLAW_REPO="${ZEROCLAW_REPO}" \
    --build-arg ZEROCLAW_REF="${ZEROCLAW_REF}" \
    --build-arg IMAGE_VERSION="${IMAGE_TAG}"
else
  # ── Base 模式（现有逻辑不变）─────────────────────
  if [ -z "${VERSION}" ]; then
    log_error "必须通过 --version 指定 ZeroClaw 版本（如 v0.1.0）"
    exit 1
  fi

  IMAGE_TAG="${VERSION}"
  CONTEXT_DIR="${SCRIPT_DIR}"

  print_build_summary "ZeroClaw" "${VERSION}" "${REGISTRY}" "linux/amd64" "base"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    --build-arg ZEROCLAW_VERSION="${VERSION}" \
    --build-arg IMAGE_VERSION="${IMAGE_TAG}"
fi

log_success "构建完成"

if [ "${SKIP_VERIFY}" = false ] && [ "${WITH_SECURITY}" = false ]; then
  log_info "验证镜像..."
  echo "  版本: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" zeroclaw --version 2>/dev/null || echo '(需启动后验证)')"
fi

if [ "${BUILD_ONLY}" = true ]; then
  log_info "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG}"
  exit 0
fi

docker_push "${REGISTRY}:${IMAGE_TAG}"
print_done "${REGISTRY}:${IMAGE_TAG}"
