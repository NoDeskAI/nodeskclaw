#!/bin/bash
# 构建 amd64 架构的 OpenClaw 镜像并推送到火山云 CR
#
# 用法:
#   ./build-and-push.sh                      # 使用 Dockerfile 中的默认版本
#   ./build-and-push.sh --version 2026.2.26  # 指定 OpenClaw 版本
#   ./build-and-push.sh --build-only         # 仅构建，不推送
#   ./build-and-push.sh --version 2026.2.26 --build-only
set -e

REGISTRY="nodesk-center-cn-beijing.cr.volces.com/base-image/nodeskclaw-openclaw-base"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"

VERSION=""
BUILD_ONLY=false
SKIP_VERIFY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --build-only)
      BUILD_ONLY=true
      shift
      ;;
    --skip-verify)
      SKIP_VERIFY=true
      shift
      ;;
    *)
      echo "未知参数: $1"
      echo "用法: $0 [--version <openclaw_version>] [--build-only] [--skip-verify]"
      exit 1
      ;;
  esac
done

if [ -z "${VERSION}" ]; then
  VERSION=$(sed -n 's/^ARG OPENCLAW_VERSION=//p' "${DOCKERFILE}")
  if [ -z "${VERSION}" ]; then
    echo "错误: 无法从 Dockerfile 读取 OPENCLAW_VERSION"
    exit 1
  fi
  echo "使用 Dockerfile 中的版本: ${VERSION}"
fi

echo "验证 openclaw@${VERSION} 在 npm 上是否存在..."
NPM_INFO=$(npm view "openclaw@${VERSION}" version 2>/dev/null || true)
if [ -z "${NPM_INFO}" ]; then
  echo "错误: openclaw@${VERSION} 在 npm 上不存在"
  echo "可用的最新版本:"
  npm view openclaw versions --json 2>/dev/null | tail -10
  exit 1
fi
echo "已确认: openclaw@${VERSION} 存在"

IMAGE_TAG="v${VERSION}"

echo ""
echo "=========================================="
echo "  OpenClaw 镜像构建"
echo "=========================================="
echo "  OpenClaw 版本: ${VERSION}"
echo "  镜像 Tag:      ${IMAGE_TAG}"
echo "  仓库:          ${REGISTRY}"
echo "  平台:          linux/amd64"
echo "=========================================="
echo ""

docker build --platform linux/amd64 \
  --build-arg OPENCLAW_VERSION="${VERSION}" \
  --build-arg IMAGE_VERSION="${IMAGE_TAG}" \
  --build-arg http_proxy= \
  --build-arg https_proxy= \
  --build-arg HTTP_PROXY= \
  --build-arg HTTPS_PROXY= \
  -t "${REGISTRY}:${IMAGE_TAG}" \
  -t "${REGISTRY}:latest" \
  "${SCRIPT_DIR}"

echo ""
echo "构建完成"
if [ "${SKIP_VERIFY}" = false ]; then
  echo "验证镜像（Apple Silicon 上较慢，可用 --skip-verify 跳过）..."
  echo "  Node.js: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" node --version)"
  echo "  OpenClaw: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" openclaw --version 2>/dev/null || echo '(需启动后验证)')"
  echo "  版本标记: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" cat /root/.openclaw-version)"
fi

if [ "${BUILD_ONLY}" = true ]; then
  echo ""
  echo "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG} && docker push ${REGISTRY}:latest"
  exit 0
fi

echo ""
echo "推送镜像..."
docker push "${REGISTRY}:${IMAGE_TAG}"
docker push "${REGISTRY}:latest"

echo ""
echo "=========================================="
echo "  完成"
echo "=========================================="
echo "  ${REGISTRY}:${IMAGE_TAG}"
echo "  ${REGISTRY}:latest"
echo "=========================================="
